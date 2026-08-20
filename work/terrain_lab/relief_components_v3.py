"""Component-wide, cell-authoritative relief grammar for Project1991.

The current sprite pass is intentionally one-cell oriented.  That is safe, but
large hill and mountain components consequently look like repeated stickers.
This module is a renderer-neutral replacement *planner*: it turns the complete
authoritative Civ world into topology-aware micro footprints (one to four
cells) or a deterministic ridge spine with branches (five or more cells).

Two contracts are deliberately explicit:

* The complete world is planned once.  Render chunks only select immutable
  metadata from that world plan, so crop boundaries cannot change a ridge.
* Every drawable primitive has ``clip_cells``.  A compositor must clip the
  primitive to the union of those exact same-terrain Civ cells.  Neither a
  green apron nor a mountain base is ever licensed over a different cell.

Horizontal world wrap is part of the component graph.  Vertical wrap is not.
The module does not load artwork and does not modify the existing renderer.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

import numpy as np

from .world import HILLS, MOUNTAINS


WorldCell = tuple[int, int]
ComponentKey = tuple[int, int, int]
Direction = Literal["N", "E", "S", "W"]
MicroTopology = Literal["single", "pair", "line", "L", "T", "block", "path"]
PlanMode = Literal["micro", "ridge"]
CellRole = Literal[
    "single",
    "pair_end",
    "line_end",
    "line_mid",
    "corner",
    "tee_hub",
    "block_corner",
    "path_end",
    "path_mid",
    "spine_end",
    "spine_mid",
    "spine_corner",
    "spine_hub",
    "branch_end",
    "branch_mid",
    "branch_hub",
]
SegmentKind = Literal["spine", "branch"]

N, E, S, W = 1, 2, 4, 8
RELIEF_TERRAINS = frozenset((HILLS, MOUNTAINS))

_DIRECTION_BITS: tuple[tuple[Direction, int], ...] = (
    ("N", N),
    ("E", E),
    ("S", S),
    ("W", W),
)
_OPPOSITE = {"N": "S", "E": "W", "S": "N", "W": "E"}


@dataclass(frozen=True, slots=True)
class ReliefCellPlacement:
    """One exact Civ cell's relief role and safe local art anchor.

    ``anchor_uv`` is normalized within the cell and never leaves ``[0, 1]``.
    It is suitable as an authored sprite foot or a ridge control point.
    ``clip_cells`` intentionally contains only this logical owner.
    """

    placement_id: tuple[ComponentKey, int, int]
    cell: WorldCell
    terrain: int
    role: CellRole
    neighbour_mask: int
    anchor_uv: tuple[float, float]
    rotation_quarters: int
    mirror: bool
    variant: int
    scale: float
    clip_cells: tuple[WorldCell, ...]


@dataclass(frozen=True, slots=True)
class RidgeSegment:
    """A cardinal connection between two adjacent exact feature cells.

    The renderer resolves the two normalized endpoint anchors in its own
    wrapped chunk coordinate system and clips the stroke/mesh to ``clip_cells``.
    This avoids a numerically long segment between x=79 and x=0.
    """

    segment_id: tuple[ComponentKey, SegmentKind, WorldCell, WorldCell]
    kind: SegmentKind
    start: WorldCell
    end: WorldCell
    direction: Direction
    start_uv: tuple[float, float]
    end_uv: tuple[float, float]
    width_scale: float
    variant: int
    clip_cells: tuple[WorldCell, ...]


@dataclass(frozen=True, slots=True)
class ReliefComponentPlan:
    """Complete immutable visual grammar for one exact-terrain component."""

    key: ComponentKey
    terrain: int
    mode: PlanMode
    topology: str
    topology_variant: str
    cells: tuple[WorldCell, ...]
    placements: tuple[ReliefCellPlacement, ...]
    spine: tuple[WorldCell, ...]
    segments: tuple[RidgeSegment, ...]
    clip_cells: tuple[WorldCell, ...]

    @property
    def size(self) -> int:
        return len(self.cells)


@dataclass(frozen=True, slots=True)
class ReliefSelection:
    """Metadata intersecting a render chunk (normally its core plus halo)."""

    component_keys: tuple[ComponentKey, ...]
    placements: tuple[ReliefCellPlacement, ...]
    segments: tuple[RidgeSegment, ...]


def _hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    """Stable 32-bit mix; independent of Python's randomized hash seed."""

    value = (int(seed) ^ (x * 0x9E3779B1) ^ (y * 0x85EBCA77) ^ (salt * 0xC2B2AE3D)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _cell_key(cell: WorldCell) -> tuple[int, int]:
    return (cell[1], cell[0])


def _neighbour(cell: WorldCell, direction: Direction, world_width: int) -> WorldCell:
    x, y = cell
    if direction == "N":
        return (x, y - 1)
    if direction == "E":
        return ((x + 1) % world_width, y)
    if direction == "S":
        return (x, y + 1)
    return ((x - 1) % world_width, y)


def _direction(start: WorldCell, end: WorldCell, world_width: int) -> Direction:
    for direction, _ in _DIRECTION_BITS:
        if _neighbour(start, direction, world_width) == end:
            return direction
    raise ValueError(f"cells are not cardinal neighbours: {start!r} -> {end!r}")


def _graph(cells: Iterable[WorldCell], world_width: int) -> dict[WorldCell, tuple[WorldCell, ...]]:
    cell_set = set(cells)
    result: dict[WorldCell, tuple[WorldCell, ...]] = {}
    for cell in sorted(cell_set, key=_cell_key):
        neighbours = {
            candidate
            for direction, _ in _DIRECTION_BITS
            if (candidate := _neighbour(cell, direction, world_width)) in cell_set
            and candidate != cell
        }
        result[cell] = tuple(sorted(neighbours, key=_cell_key))
    return result


def _mask(cell: WorldCell, graph: dict[WorldCell, tuple[WorldCell, ...]], world_width: int) -> int:
    neighbours = set(graph[cell])
    return sum(
        bit
        for direction, bit in _DIRECTION_BITS
        if _neighbour(cell, direction, world_width) in neighbours
    )


def _mask_directions(mask: int) -> tuple[Direction, ...]:
    return tuple(direction for direction, bit in _DIRECTION_BITS if mask & bit)


def _is_straight(mask: int) -> bool:
    directions = _mask_directions(mask)
    return len(directions) == 2 and _OPPOSITE[directions[0]] == directions[1]


def _rotation(mask: int) -> int:
    """Quarter-turn hint for canonical artwork whose primary axis is north."""

    directions = _mask_directions(mask)
    if not directions:
        return 0
    primary = directions[0]
    return {"N": 0, "E": 1, "S": 2, "W": 3}[primary]


def _ordered_path(graph: dict[WorldCell, tuple[WorldCell, ...]]) -> tuple[WorldCell, ...]:
    """Return a stable order for a non-branching open component."""

    endpoints = sorted((cell for cell, neighbours in graph.items() if len(neighbours) == 1), key=_cell_key)
    if not endpoints:
        return tuple(sorted(graph, key=_cell_key))
    path = [endpoints[0]]
    previous: WorldCell | None = None
    while len(path) < len(graph):
        candidates = [cell for cell in graph[path[-1]] if cell != previous]
        if not candidates:
            break
        following = min(candidates, key=_cell_key)
        previous = path[-1]
        path.append(following)
    return tuple(path)


def _path_directions(path: Sequence[WorldCell], world_width: int) -> tuple[Direction, ...]:
    return tuple(_direction(a, b, world_width) for a, b in zip(path, path[1:]))


def _micro_topology(
    graph: dict[WorldCell, tuple[WorldCell, ...]],
    world_width: int,
) -> tuple[MicroTopology, str, tuple[WorldCell, ...]]:
    size = len(graph)
    if size == 1:
        only = next(iter(graph))
        return "single", "isolated", (only,)
    if size == 2:
        ordered = tuple(sorted(graph, key=_cell_key))
        axis = "EW" if _direction(ordered[0], ordered[1], world_width) in {"E", "W"} else "NS"
        return "pair", axis, ordered

    degrees = Counter(len(neighbours) for neighbours in graph.values())
    if size == 4 and degrees == Counter({2: 4}) and all(not _is_straight(_mask(cell, graph, world_width)) for cell in graph):
        return "block", "2x2", tuple(sorted(graph, key=_cell_key))
    if size == 4 and degrees == Counter({1: 3, 3: 1}):
        hub = next(cell for cell, neighbours in graph.items() if len(neighbours) == 3)
        missing = next(direction for direction, bit in _DIRECTION_BITS if not (_mask(hub, graph, world_width) & bit))
        ordered = (hub,) + tuple(sorted((cell for cell in graph if cell != hub), key=_cell_key))
        return "T", f"missing_{missing}", ordered

    ordered = _ordered_path(graph)
    directions = _path_directions(ordered, world_width)
    turns = sum(a != b for a, b in zip(directions, directions[1:]))
    axes = {"EW" if direction in {"E", "W"} else "NS" for direction in directions}
    if turns == 0:
        return "line", next(iter(axes)), ordered
    if turns == 1:
        corner_index = next(index + 1 for index, (a, b) in enumerate(zip(directions, directions[1:])) if a != b)
        corner_mask = _mask(ordered[corner_index], graph, world_width)
        corner = "".join(_mask_directions(corner_mask))
        return "L", corner, ordered
    # The four-cell S/Z tetromino is a real topology.  It cannot truthfully be
    # labelled a straight or one-corner L, so it receives an authored path slot.
    encoded = "-".join(directions)
    return "path", encoded, ordered


def _bfs(
    graph: dict[WorldCell, tuple[WorldCell, ...]],
    start: WorldCell,
    *,
    seed: int,
    salt: int,
) -> tuple[dict[WorldCell, int], dict[WorldCell, WorldCell | None]]:
    distance = {start: 0}
    parent: dict[WorldCell, WorldCell | None] = {start: None}
    queue: deque[WorldCell] = deque((start,))
    while queue:
        cell = queue.popleft()
        neighbours = sorted(
            graph[cell],
            key=lambda item: (_hash(seed, item[0], item[1], salt), item[1], item[0]),
        )
        for neighbour in neighbours:
            if neighbour in distance:
                continue
            distance[neighbour] = distance[cell] + 1
            parent[neighbour] = cell
            queue.append(neighbour)
    return distance, parent


def _farthest(distance: dict[WorldCell, int], *, seed: int, salt: int) -> WorldCell:
    return min(
        distance,
        key=lambda cell: (-distance[cell], _hash(seed, cell[0], cell[1], salt), cell[1], cell[0]),
    )


def _ridge_tree(
    graph: dict[WorldCell, tuple[WorldCell, ...]],
    *,
    seed: int,
) -> tuple[tuple[WorldCell, ...], tuple[tuple[WorldCell, WorldCell], ...]]:
    """Build a deterministic long spine plus a complete branch forest."""

    canonical = min(graph, key=_cell_key)
    first_distance, _ = _bfs(graph, canonical, seed=seed, salt=3101)
    endpoint_a = _farthest(first_distance, seed=seed, salt=3103)
    second_distance, second_parent = _bfs(graph, endpoint_a, seed=seed, salt=3119)
    endpoint_b = _farthest(second_distance, seed=seed, salt=3121)

    reverse_path = [endpoint_b]
    while reverse_path[-1] != endpoint_a:
        parent = second_parent[reverse_path[-1]]
        if parent is None:  # pragma: no cover - connected graph invariant
            raise AssertionError("ridge path unexpectedly lost its parent")
        reverse_path.append(parent)
    spine = tuple(reversed(reverse_path))

    claimed = set(spine)
    queue: deque[WorldCell] = deque(spine)
    branches: list[tuple[WorldCell, WorldCell]] = []
    while queue:
        parent = queue.popleft()
        candidates = sorted(
            graph[parent],
            key=lambda cell: (_hash(seed, cell[0], cell[1], 3203), cell[1], cell[0]),
        )
        for child in candidates:
            if child in claimed:
                continue
            claimed.add(child)
            branches.append((parent, child))
            queue.append(child)
    if claimed != set(graph):  # pragma: no cover - connected graph invariant
        raise AssertionError("ridge branch tree did not claim every feature cell")
    return spine, tuple(branches)


def _anchor(seed: int, cell: WorldCell, terrain: int) -> tuple[float, float]:
    value = _hash(seed, cell[0], cell[1], 4101 + terrain)
    jitter_x = (((value >> 8) & 0xFF) / 255.0 - 0.5) * 0.12
    jitter_y = (((value >> 16) & 0xFF) / 255.0 - 0.5) * 0.08
    return (round(0.5 + jitter_x, 4), round(0.67 + jitter_y, 4))


def _small_role(topology: MicroTopology, cell: WorldCell, graph: dict[WorldCell, tuple[WorldCell, ...]], world_width: int) -> CellRole:
    degree = len(graph[cell])
    mask = _mask(cell, graph, world_width)
    if topology == "single":
        return "single"
    if topology == "pair":
        return "pair_end"
    if topology == "block":
        return "block_corner"
    if topology == "T":
        return "tee_hub" if degree == 3 else "line_end"
    if topology == "L":
        if degree == 2 and not _is_straight(mask):
            return "corner"
        return "line_end" if degree == 1 else "line_mid"
    if topology == "line":
        return "line_end" if degree == 1 else "line_mid"
    return "path_end" if degree == 1 else "path_mid"


def _large_roles(
    graph: dict[WorldCell, tuple[WorldCell, ...]],
    spine: tuple[WorldCell, ...],
    branches: tuple[tuple[WorldCell, WorldCell], ...],
    world_width: int,
) -> dict[WorldCell, CellRole]:
    spine_set = set(spine)
    branch_degree: Counter[WorldCell] = Counter()
    for start, end in branches:
        branch_degree[start] += 1
        branch_degree[end] += 1
    roles: dict[WorldCell, CellRole] = {}
    for index, cell in enumerate(spine):
        mask = _mask(cell, graph, world_width)
        if branch_degree[cell] > 0 or len(graph[cell]) >= 3:
            roles[cell] = "spine_hub"
        elif index in {0, len(spine) - 1}:
            roles[cell] = "spine_end"
        elif _is_straight(mask):
            roles[cell] = "spine_mid"
        else:
            roles[cell] = "spine_corner"
    for cell in graph:
        if cell in spine_set:
            continue
        degree = branch_degree[cell]
        if degree <= 1:
            roles[cell] = "branch_end"
        elif degree == 2:
            roles[cell] = "branch_mid"
        else:
            roles[cell] = "branch_hub"
    return roles


def _placement(
    key: ComponentKey,
    terrain: int,
    cell: WorldCell,
    role: CellRole,
    graph: dict[WorldCell, tuple[WorldCell, ...]],
    *,
    seed: int,
    world_width: int,
) -> ReliefCellPlacement:
    value = _hash(seed, cell[0], cell[1], 4201 + terrain)
    mask = _mask(cell, graph, world_width)
    base_scale = 0.91 if terrain == MOUNTAINS else 0.84
    role_scale = {
        "single": -0.04,
        "pair_end": -0.01,
        "line_end": 0.00,
        "line_mid": 0.03,
        "corner": 0.03,
        "tee_hub": 0.06,
        "block_corner": 0.04,
        "path_end": 0.00,
        "path_mid": 0.03,
        "spine_end": 0.01,
        "spine_mid": 0.06,
        "spine_corner": 0.07,
        "spine_hub": 0.10,
        "branch_end": -0.01,
        "branch_mid": 0.02,
        "branch_hub": 0.05,
    }[role]
    return ReliefCellPlacement(
        placement_id=(key, cell[0], cell[1]),
        cell=cell,
        terrain=terrain,
        role=role,
        neighbour_mask=mask,
        anchor_uv=_anchor(seed, cell, terrain),
        rotation_quarters=_rotation(mask),
        mirror=bool(value & 1),
        variant=(value >> 1) & 3,
        scale=round(base_scale + role_scale, 3),
        clip_cells=(cell,),
    )


def _segment(
    key: ComponentKey,
    terrain: int,
    start: WorldCell,
    end: WorldCell,
    kind: SegmentKind,
    *,
    seed: int,
    world_width: int,
) -> RidgeSegment:
    direction = _direction(start, end, world_width)
    value = _hash(seed, start[0] ^ end[0], start[1] ^ end[1], 5101 if kind == "spine" else 5201)
    return RidgeSegment(
        segment_id=(key, kind, start, end),
        kind=kind,
        start=start,
        end=end,
        direction=direction,
        start_uv=_anchor(seed, start, terrain),
        end_uv=_anchor(seed, end, terrain),
        width_scale=round((0.37 if terrain == MOUNTAINS else 0.27) * (1.0 if kind == "spine" else 0.78), 3),
        variant=value & 3,
        clip_cells=(start, end),
    )


def _component_plan(
    terrain: int,
    cells: tuple[WorldCell, ...],
    *,
    seed: int,
    world_width: int,
) -> ReliefComponentPlan:
    graph = _graph(cells, world_width)
    canonical = min(cells, key=_cell_key)
    key: ComponentKey = (terrain, canonical[0], canonical[1])
    if len(cells) <= 4:
        topology, variant, order = _micro_topology(graph, world_width)
        roles = {cell: _small_role(topology, cell, graph, world_width) for cell in cells}
        placements = tuple(
            _placement(key, terrain, cell, roles[cell], graph, seed=seed, world_width=world_width)
            for cell in sorted(cells, key=_cell_key)
        )
        return ReliefComponentPlan(
            key=key,
            terrain=terrain,
            mode="micro",
            topology=topology,
            topology_variant=variant,
            cells=tuple(sorted(cells, key=_cell_key)),
            placements=placements,
            spine=order if topology in {"line", "L", "path"} else (),
            segments=(),
            clip_cells=tuple(sorted(cells, key=_cell_key)),
        )

    spine, branches = _ridge_tree(graph, seed=seed)
    roles = _large_roles(graph, spine, branches, world_width)
    placements = tuple(
        _placement(key, terrain, cell, roles[cell], graph, seed=seed, world_width=world_width)
        for cell in sorted(cells, key=_cell_key)
    )
    segments: list[RidgeSegment] = []
    for start, end in zip(spine, spine[1:]):
        segments.append(_segment(key, terrain, start, end, "spine", seed=seed, world_width=world_width))
    for start, end in branches:
        segments.append(_segment(key, terrain, start, end, "branch", seed=seed, world_width=world_width))
    return ReliefComponentPlan(
        key=key,
        terrain=terrain,
        mode="ridge",
        topology="ridge",
        topology_variant=f"spine_{len(spine)}_branches_{len(branches)}",
        cells=tuple(sorted(cells, key=_cell_key)),
        placements=placements,
        spine=spine,
        segments=tuple(segments),
        clip_cells=tuple(sorted(cells, key=_cell_key)),
    )


def plan_relief_components_v3(
    raw_grid: np.ndarray,
    *,
    seed: int,
    world_width: int | None = None,
    world_x0: int = 0,
    world_y0: int = 0,
) -> tuple[ReliefComponentPlan, ...]:
    """Plan exact HILLS/MOUNTAINS components from a complete world grid.

    ``raw_grid`` must contain every horizontal world column exactly once.
    It may be cyclically rolled when ``world_x0`` identifies the absolute world
    x coordinate of local column zero.  Calling this on arbitrary render chunks
    is rejected because a truncated component cannot have a stable global
    spine; plan once and use :func:`select_relief_metadata_v3` per chunk.
    """

    grid = np.asarray(raw_grid)
    if grid.ndim != 2:
        raise ValueError(f"raw_grid must be 2-D, got {grid.shape}")
    if grid.shape[0] <= 0 or grid.shape[1] <= 0:
        raise ValueError("raw_grid must not be empty")
    width = grid.shape[1] if world_width is None else int(world_width)
    if width <= 0:
        raise ValueError("world_width must be positive")
    if grid.shape[1] != width:
        raise ValueError(
            "component-wide relief requires the complete horizontal world: "
            f"grid width {grid.shape[1]} != world_width {width}"
        )

    terrain_by_world: dict[WorldCell, int] = {}
    for local_y in range(grid.shape[0]):
        for local_x in range(grid.shape[1]):
            terrain = int(grid[local_y, local_x])
            if terrain not in RELIEF_TERRAINS:
                continue
            world = ((int(world_x0) + local_x) % width, int(world_y0) + local_y)
            if world in terrain_by_world:  # pragma: no cover - guarded by width equality
                raise ValueError(f"duplicate world coordinate {world}")
            terrain_by_world[world] = terrain

    unseen = set(terrain_by_world)
    components: list[tuple[int, tuple[WorldCell, ...]]] = []
    while unseen:
        start = min(unseen, key=_cell_key)
        terrain = terrain_by_world[start]
        queue: deque[WorldCell] = deque((start,))
        unseen.remove(start)
        cells: list[WorldCell] = []
        while queue:
            cell = queue.popleft()
            cells.append(cell)
            for direction, _ in _DIRECTION_BITS:
                neighbour = _neighbour(cell, direction, width)
                if neighbour in unseen and terrain_by_world.get(neighbour) == terrain:
                    unseen.remove(neighbour)
                    queue.append(neighbour)
        components.append((terrain, tuple(sorted(cells, key=_cell_key))))

    plans = (
        _component_plan(terrain, cells, seed=int(seed), world_width=width)
        for terrain, cells in components
    )
    return tuple(sorted(plans, key=lambda plan: (plan.key[2], plan.key[1], plan.terrain)))


def select_relief_metadata_v3(
    plans: Iterable[ReliefComponentPlan],
    render_cells: Iterable[WorldCell],
) -> ReliefSelection:
    """Select immutable metadata whose exact clip intersects a render chunk.

    Pass core-plus-halo cells.  A wrapped segment is selected from either side,
    yet retains the same world-coordinate ID and endpoints as the full plan.
    """

    requested = set(render_cells)
    component_keys: list[ComponentKey] = []
    placements: list[ReliefCellPlacement] = []
    segments: list[RidgeSegment] = []
    for plan in plans:
        if not requested.intersection(plan.clip_cells):
            continue
        component_keys.append(plan.key)
        placements.extend(placement for placement in plan.placements if placement.cell in requested)
        segments.extend(segment for segment in plan.segments if requested.intersection(segment.clip_cells))
    return ReliefSelection(
        component_keys=tuple(sorted(component_keys, key=lambda key: (key[2], key[1], key[0]))),
        placements=tuple(sorted(placements, key=lambda placement: _cell_key(placement.cell))),
        segments=tuple(sorted(segments, key=lambda segment: (segment.start[1], segment.start[0], segment.end[1], segment.end[0], segment.kind))),
    )


def relief_statistics_v3(plans: Iterable[ReliefComponentPlan], *, world_width: int) -> dict[str, object]:
    """Return JSON-friendly coverage and topology statistics for QA reports."""

    plan_tuple = tuple(plans)
    topology = Counter(plan.topology for plan in plan_tuple)
    terrain = Counter("mountains" if plan.terrain == MOUNTAINS else "hills" for plan in plan_tuple)
    sizes = Counter(
        "1" if plan.size == 1 else "2" if plan.size == 2 else "3" if plan.size == 3 else "4" if plan.size == 4 else "5+"
        for plan in plan_tuple
    )
    cells = [cell for plan in plan_tuple for cell in plan.cells]
    wrap_components = 0
    for plan in plan_tuple:
        plan_cells = set(plan.cells)
        if any((world_width - 1, y) in plan_cells and (0, y) in plan_cells for _, y in plan.cells):
            wrap_components += 1
    return {
        "components": len(plan_tuple),
        "cells": len(cells),
        "unique_cells": len(set(cells)),
        "max_component_size": max((plan.size for plan in plan_tuple), default=0),
        "terrain_components": dict(sorted(terrain.items())),
        "size_classes": dict(sorted(sizes.items())),
        "topologies": dict(sorted(topology.items())),
        "ridge_components": sum(plan.mode == "ridge" for plan in plan_tuple),
        "spine_segments": sum(segment.kind == "spine" for plan in plan_tuple for segment in plan.segments),
        "branch_segments": sum(segment.kind == "branch" for plan in plan_tuple for segment in plan.segments),
        "wrap_components": wrap_components,
    }


__all__ = (
    "ComponentKey",
    "ReliefCellPlacement",
    "ReliefComponentPlan",
    "ReliefSelection",
    "RidgeSegment",
    "WorldCell",
    "plan_relief_components_v3",
    "relief_statistics_v3",
    "select_relief_metadata_v3",
)
