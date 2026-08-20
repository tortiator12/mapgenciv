"""World-stable forest and jungle region grammar for Project1991.

The legacy object pass places one opaque cluster in every woodland tile.  That
is cell-authoritative, but produces a very obvious 96 px wallpaper.  This
module is a renderer-neutral alternative: it plans several individual tree
feet per exact Civ cell, joins neighbouring cells with paired ``seam_grove``
clusters and varies species, crown size and depth in absolute world space.

The important contracts are intentionally data-level and testable:

* FOREST and JUNGLE are separate four-connected component families.
* Every woodland cell owns exactly one centre signature, so its gameplay
  terrain remains readable even in a sparse or isolated cell.
* Every tree foot belongs to one exact same-terrain Civ cell.  At the 96 px
  reference scale exposed feet retreat 14--18 px from Grass/Plains and
  19--23 px from Water/Desert/relief or any other hard material boundary.
* Isolated cells carry 6--7 feet, exposed/corner/corridor cells 6--8, and
  junction/interior cells 8--10.  Jungle adds one foot.  Shared woodland
  seams own two or three explicit crowns before the remaining budget is
  filled with real, deterministic interior feet.
* Full-world planning is immutable.  Chunks merely select metadata, therefore
  a full render and any chunk decomposition receive byte-for-byte equal point
  records.  Horizontal world wrap belongs to the component graph.

Only asset keys already used by :mod:`terrain_lab.decor` are emitted.  This
module loads and draws no artwork.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from html import escape
from typing import Iterable, Literal

import numpy as np

from .world import FOREST, GRASSLAND, JUNGLE, PLAINS


WorldCell = tuple[int, int]
ComponentKey = tuple[int, int, int]
PlacementId = tuple[ComponentKey, int, int, int]
ClusterKey = tuple[ComponentKey, str, int, int]
Direction = Literal["N", "E", "S", "W"]
ComponentMode = Literal["copse", "grove", "forest_mass"]
CellRole = Literal["isolated", "edge", "corridor", "corner", "junction", "interior"]
PointRole = Literal["cell_signature", "shared_edge", "edge_fill", "interior_fill"]
ClusterKind = Literal["mass", "seam_grove"]

N, E, S, W = 1, 2, 4, 8
WOODLAND_TERRAINS = frozenset((FOREST, JUNGLE))
ASSET_KEYS = frozenset(("broadleaf", "conifer"))

_DIRECTIONS: tuple[tuple[Direction, int], ...] = (
    ("N", N),
    ("E", E),
    ("S", S),
    ("W", W),
)
_OPPOSITE = {"N": "S", "E": "W", "S": "N", "W": "E"}


@dataclass(frozen=True, slots=True)
class TreePlacement:
    """One tree foot licensed by exactly one woodland Civ cell.

    ``anchor_px`` is local to ``owner_cell`` and uses integer pixels in
    ``[0, tile_px - 1]``.  ``world_anchor_px`` is the corresponding absolute
    horizontal-wrapped world position.  Artwork may let a crown overlap a
    neighbouring *same-terrain* cell, but the foot and contact shadow must be
    clipped/owned according to ``clip_cells``.
    """

    placement_id: PlacementId
    component_key: ComponentKey
    cluster_id: ClusterKey
    owner_cell: WorldCell
    terrain: int
    cell_role: CellRole
    role: PointRole
    asset_key: str
    variant: int
    anchor_px: tuple[int, int]
    anchor_uv: tuple[float, float]
    world_anchor_px: tuple[int, int]
    crown_diameter_px: int
    height_scale: float
    mirror: bool
    tint: float
    depth_layer: int
    neighbour_mask: int
    exposed_mask: int
    edge_retreat_px: tuple[int, int, int, int]
    is_cell_signature: bool
    clip_cells: tuple[WorldCell, ...]


@dataclass(frozen=True, slots=True)
class WoodlandCluster:
    """A component-level mass band or a grove spanning one shared edge."""

    cluster_id: ClusterKey
    component_key: ComponentKey
    kind: ClusterKind
    cells: tuple[WorldCell, ...]
    placement_ids: tuple[PlacementId, ...]
    clip_cells: tuple[WorldCell, ...]


@dataclass(frozen=True, slots=True)
class WoodlandComponentPlan:
    """Complete immutable scatter grammar for one exact terrain component."""

    key: ComponentKey
    terrain: int
    mode: ComponentMode
    cells: tuple[WorldCell, ...]
    placements: tuple[TreePlacement, ...]
    clusters: tuple[WoodlandCluster, ...]
    shared_edges: tuple[tuple[WorldCell, WorldCell], ...]
    clip_cells: tuple[WorldCell, ...]

    @property
    def size(self) -> int:
        return len(self.cells)


@dataclass(frozen=True, slots=True)
class WoodlandSelection:
    """Immutable full-plan metadata intersecting a render core plus halo."""

    component_keys: tuple[ComponentKey, ...]
    placements: tuple[TreePlacement, ...]
    clusters: tuple[WoodlandCluster, ...]


def _hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    """Stable 32-bit mix, independent of Python's randomized hash seed."""

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
    for direction, _ in _DIRECTIONS:
        if _neighbour(start, direction, world_width) == end:
            return direction
    raise ValueError(f"cells are not cardinal neighbours: {start!r} -> {end!r}")


def _graph(cells: Iterable[WorldCell], world_width: int) -> dict[WorldCell, tuple[WorldCell, ...]]:
    cell_set = set(cells)
    graph: dict[WorldCell, tuple[WorldCell, ...]] = {}
    for cell in sorted(cell_set, key=_cell_key):
        neighbours = {
            candidate
            for direction, _ in _DIRECTIONS
            if (candidate := _neighbour(cell, direction, world_width)) in cell_set
            and candidate != cell
        }
        graph[cell] = tuple(sorted(neighbours, key=_cell_key))
    return graph


def _mask(cell: WorldCell, graph: dict[WorldCell, tuple[WorldCell, ...]], world_width: int) -> int:
    neighbours = set(graph[cell])
    return sum(
        bit
        for direction, bit in _DIRECTIONS
        if _neighbour(cell, direction, world_width) in neighbours
    )


def _is_straight(mask: int) -> bool:
    directions = [direction for direction, bit in _DIRECTIONS if mask & bit]
    return len(directions) == 2 and _OPPOSITE[directions[0]] == directions[1]


def _cell_role(mask: int) -> CellRole:
    degree = int(mask).bit_count()
    if degree == 0:
        return "isolated"
    if degree == 1:
        return "edge"
    if degree == 2:
        return "corridor" if _is_straight(mask) else "corner"
    if degree == 3:
        return "junction"
    return "interior"


def _bfs_distances(
    graph: dict[WorldCell, tuple[WorldCell, ...]],
    root: WorldCell,
) -> dict[WorldCell, int]:
    distance = {root: 0}
    queue: deque[WorldCell] = deque((root,))
    while queue:
        cell = queue.popleft()
        for neighbour in graph[cell]:
            if neighbour in distance:
                continue
            distance[neighbour] = distance[cell] + 1
            queue.append(neighbour)
    return distance


def _edge_key(
    component_key: ComponentKey,
    a: WorldCell,
    b: WorldCell,
    world_width: int,
) -> ClusterKey:
    first, second = sorted((a, b), key=_cell_key)
    direction = _direction(first, second, world_width)
    return (component_key, f"seam_{direction}", first[0], first[1])


def _shared_edges(
    graph: dict[WorldCell, tuple[WorldCell, ...]],
) -> tuple[tuple[WorldCell, WorldCell], ...]:
    edges = {
        tuple(sorted((cell, neighbour), key=_cell_key))
        for cell, neighbours in graph.items()
        for neighbour in neighbours
    }
    return tuple(sorted(edges, key=lambda edge: (_cell_key(edge[0]), _cell_key(edge[1]))))


def _edge_retreats(
    seed: int,
    cell: WorldCell,
    exposed_mask: int,
    tile_px: int,
    terrain: int,
    neighbour_terrains: tuple[int | None, int | None, int | None, int | None],
) -> tuple[int, int, int, int]:
    """Return material-aware N/E/S/W foot retreats.

    Grass and Plains are the only soft presentation boundaries.  Every other
    material (including a different woodland family) is treated as a hard
    boundary so a 25--35 px crown cannot visibly invade water, desert or
    relief.  The values are specified at the 96 px reference tile and scale
    with ``tile_px``.
    """

    result: list[int] = []
    for index, (_, bit) in enumerate(_DIRECTIONS):
        if not (exposed_mask & bit):
            result.append(0)
            continue
        neighbour = neighbour_terrains[index]
        soft = neighbour in {GRASSLAND, PLAINS}
        minimum = 14 if soft else 19
        reference_px = minimum + (
            _hash(seed, cell[0], cell[1], 6101 + terrain * 17 + index) % 5
        )
        result.append(max(1, int(round(reference_px * tile_px / 96.0))))
    return tuple(result)  # type: ignore[return-value]


def _clamp_to_retreats(
    x: int,
    y: int,
    retreats: tuple[int, int, int, int],
    tile_px: int,
) -> tuple[int, int]:
    north, east, south, west = retreats
    min_x = west if west else 1
    max_x = tile_px - 1 - (east if east else 0)
    min_y = north if north else 1
    max_y = tile_px - 1 - (south if south else 0)
    return (min(max(int(x), min_x), max_x), min(max(int(y), min_y), max_y))


def _mass_cluster_key(
    component_key: ComponentKey,
    distance: int,
) -> ClusterKey:
    # Bands span several graph-adjacent cells; crucially they do not restart in
    # every tile.  Three graph steps balance readable sub-groves and large mass.
    return (component_key, "mass", int(distance) // 3, 0)


def _point_style(
    *,
    seed: int,
    cell: WorldCell,
    terrain: int,
    role: PointRole,
    slot: int,
    world_height_hint: int,
) -> tuple[str, int, int, float, bool, float, int]:
    value = _hash(seed, cell[0], cell[1], 7101 + terrain * 101 + slot * 13)
    if terrain == JUNGLE:
        asset_key = "broadleaf"
        tint = 1.055 + ((value >> 24) & 7) * 0.009
    else:
        latitude_edge = cell[1] < max(7, int(world_height_hint * 0.27)) or cell[1] >= int(world_height_hint * 0.73)
        conifer_cutoff = 5 if latitude_edge else 2
        asset_key = "conifer" if (value & 7) < conifer_cutoff else "broadleaf"
        tint = 0.91 + ((value >> 24) & 7) * 0.018
    crown = 25 + ((value >> 8) % 11)
    if role == "cell_signature":
        crown = max(crown, 31)
    variant = (value >> 16) & 3
    height_scale = round(0.88 + ((value >> 18) & 15) / 15.0 * 0.24, 3)
    mirror = bool(value & 0x80000000)
    depth = {"shared_edge": 0, "edge_fill": 1, "interior_fill": 1, "cell_signature": 2}[role]
    return asset_key, int(variant), int(crown), height_scale, mirror, round(float(tint), 3), depth


def _make_placement(
    *,
    component_key: ComponentKey,
    cluster_id: ClusterKey,
    cell: WorldCell,
    terrain: int,
    cell_role: CellRole,
    role: PointRole,
    slot: int,
    xy: tuple[int, int],
    tile_px: int,
    world_width: int,
    world_height_hint: int,
    seed: int,
    neighbour_mask: int,
    retreats: tuple[int, int, int, int],
) -> TreePlacement:
    x, y = _clamp_to_retreats(xy[0], xy[1], retreats, tile_px)
    exposed_mask = (N | E | S | W) ^ neighbour_mask
    asset_key, variant, crown, height_scale, mirror, tint, depth = _point_style(
        seed=seed,
        cell=cell,
        terrain=terrain,
        role=role,
        slot=slot,
        world_height_hint=world_height_hint,
    )
    placement_id: PlacementId = (component_key, cell[0], cell[1], slot)
    return TreePlacement(
        placement_id=placement_id,
        component_key=component_key,
        cluster_id=cluster_id,
        owner_cell=cell,
        terrain=terrain,
        cell_role=cell_role,
        role=role,
        asset_key=asset_key,
        variant=variant,
        anchor_px=(x, y),
        anchor_uv=(round(x / float(tile_px), 4), round(y / float(tile_px), 4)),
        world_anchor_px=((cell[0] * tile_px + x) % (world_width * tile_px), cell[1] * tile_px + y),
        crown_diameter_px=crown,
        height_scale=height_scale,
        mirror=mirror,
        tint=tint,
        depth_layer=depth,
        neighbour_mask=neighbour_mask,
        exposed_mask=exposed_mask,
        edge_retreat_px=retreats,
        is_cell_signature=role == "cell_signature",
        clip_cells=(cell,),
    )


def _signature_xy(
    seed: int,
    cell: WorldCell,
    terrain: int,
    tile_px: int,
) -> tuple[int, int]:
    value = _hash(seed, cell[0], cell[1], 8101 + terrain)
    # +/- five reference pixels keeps the signature visibly at the exact Civ
    # centre while eliminating mechanical rows.
    jitter_x = (((value >> 8) & 0xFF) / 255.0 - 0.5) * (10.0 * tile_px / 96.0)
    jitter_y = (((value >> 16) & 0xFF) / 255.0 - 0.5) * (10.0 * tile_px / 96.0)
    return (int(round(tile_px * 0.5 + jitter_x)), int(round(tile_px * 0.5 + jitter_y)))


def _seam_xy(
    seed: int,
    cell: WorldCell,
    neighbour: WorldCell,
    direction: Direction,
    tile_px: int,
    world_width: int,
) -> tuple[int, int]:
    first, second = sorted((cell, neighbour), key=_cell_key)
    value = _hash(seed, first[0] ^ (second[0] << 7), first[1] ^ (second[1] << 7), 8209)
    edge_distance = max(2, int(round((4 + (value & 3)) * tile_px / 96.0)))
    tangent = int(round(tile_px * (0.28 + ((value >> 8) & 0xFF) / 255.0 * 0.44)))
    if direction == "N":
        return (tangent, edge_distance)
    if direction == "E":
        return (tile_px - 1 - edge_distance, tangent)
    if direction == "S":
        return (tangent, tile_px - 1 - edge_distance)
    if direction == "W":
        return (edge_distance, tangent)
    raise AssertionError(f"unknown direction {direction!r}")  # pragma: no cover


def _seam_has_third_tree(
    seed: int,
    cell: WorldCell,
    neighbour: WorldCell,
) -> bool:
    """Let exactly one endpoint author an optional third seam crown."""

    first, second = sorted((cell, neighbour), key=_cell_key)
    if cell != first:
        return False
    value = _hash(seed, first[0] ^ (second[0] << 7), first[1] ^ (second[1] << 7), 8273)
    return bool(value & 1)


def _seam_extra_xy(
    seed: int,
    cell: WorldCell,
    neighbour: WorldCell,
    direction: Direction,
    tile_px: int,
    world_width: int,
) -> tuple[int, int]:
    """Second foot on one side of a shared edge, offset along its tangent."""

    base_x, base_y = _seam_xy(seed, cell, neighbour, direction, tile_px, world_width)
    first, second = sorted((cell, neighbour), key=_cell_key)
    value = _hash(seed, first[0] ^ (second[0] << 9), first[1] ^ (second[1] << 9), 8291)
    offset = int(round((16 + ((value >> 4) % 7)) * tile_px / 96.0))
    if value & 0x200:
        offset = -offset
    margin = max(3, int(round(8 * tile_px / 96.0)))
    edge_step = max(2, int(round((4 + ((value >> 12) % 4)) * tile_px / 96.0)))
    if direction in {"N", "S"}:
        return (min(max(base_x + offset, margin), tile_px - 1 - margin), base_y + edge_step if direction == "N" else base_y - edge_step)
    return (base_x + edge_step if direction == "W" else base_x - edge_step, min(max(base_y + offset, margin), tile_px - 1 - margin))


def _target_count(
    *,
    seed: int,
    cell: WorldCell,
    terrain: int,
    role: CellRole,
) -> int:
    """Return the V4.1 population contract for one exact Civ cell."""

    value = _hash(seed, cell[0], cell[1], 8911 + terrain * 43)
    if role == "isolated":
        count = 6 + value % 2
    elif role in {"edge", "corner", "corridor"}:
        count = 6 + value % 3
    else:
        count = 8 + value % 3
    return int(count + (1 if terrain == JUNGLE else 0))


def _fill_candidates(
    *,
    seed: int,
    cell: WorldCell,
    terrain: int,
    tile_px: int,
    retreats: tuple[int, int, int, int],
    count: int,
    occupied: list[tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    """Select a deterministic best-candidate scatter inside one exact cell."""

    north, east, south, west = retreats
    low_x = max(west if west else int(round(tile_px * 0.08)), 1)
    high_x = min(tile_px - 1 - (east if east else int(round(tile_px * 0.08))), tile_px - 1)
    low_y = max(north if north else int(round(tile_px * 0.08)), 1)
    high_y = min(tile_px - 1 - (south if south else int(round(tile_px * 0.08))), tile_px - 1)
    candidates: list[tuple[int, int, int]] = []
    # A larger candidate pool is needed for the 8--11-foot V4.1 interior
    # contract.  Candidate coordinates remain purely world/cell seeded.
    for index in range(160):
        value = _hash(seed, cell[0], cell[1], 9001 + terrain * 97 + index * 31)
        x = low_x + (value & 0xFFFF) % max(1, high_x - low_x + 1)
        y = low_y + ((value >> 16) & 0xFFFF) % max(1, high_y - low_y + 1)
        candidates.append((int(x), int(y), int(value)))

    chosen: list[tuple[int, int]] = []
    occupied_all = list(occupied)
    while len(chosen) < count and candidates:
        slot_value = _hash(seed, cell[0], cell[1], 9701 + terrain * 37 + len(chosen) * 53)
        desired = (18.0 + (slot_value % 11)) * tile_px / 96.0
        minimum = 13.0 * tile_px / 96.0
        maximum = 34.0 * tile_px / 96.0
        distances = [
            min(
                ((candidate[0] - ox) ** 2 + (candidate[1] - oy) ** 2) ** 0.5
                for ox, oy in occupied_all
            )
            for candidate in candidates
        ]
        eligible = [
            index
            for index, distance in enumerate(distances)
            if minimum <= distance <= maximum
        ]
        if not eligible:
            eligible = [index for index, distance in enumerate(distances) if distance >= minimum * 0.72]
        best_index = max(
            eligible,
            key=lambda index: (
                -abs(distances[index] - desired),
                candidates[index][2],
            ),
        )
        x, y, _ = candidates.pop(best_index)
        point = _clamp_to_retreats(x, y, retreats, tile_px)
        if point in occupied_all:
            continue
        chosen.append(point)
        occupied_all.append(point)
    if len(chosen) != count:  # pragma: no cover - 160 candidates make this defensive
        raise AssertionError(f"could only place {len(chosen)} of {count} forest fill feet")
    return tuple(chosen)


def _component_plan(
    terrain: int,
    cells: tuple[WorldCell, ...],
    *,
    seed: int,
    tile_px: int,
    world_width: int,
    world_height_hint: int,
    terrain_by_world: dict[WorldCell, int],
) -> WoodlandComponentPlan:
    graph = _graph(cells, world_width)
    canonical = min(cells, key=_cell_key)
    key: ComponentKey = (terrain, canonical[0], canonical[1])
    distance = _bfs_distances(graph, canonical)
    mode: ComponentMode = "copse" if len(cells) == 1 else "grove" if len(cells) <= 4 else "forest_mass"
    placements: list[TreePlacement] = []

    for cell in sorted(cells, key=_cell_key):
        neighbour_mask = _mask(cell, graph, world_width)
        exposed_mask = (N | E | S | W) ^ neighbour_mask
        neighbour_terrains = tuple(
            terrain_by_world.get(_neighbour(cell, direction, world_width))
            for direction, _ in _DIRECTIONS
        )
        retreats = _edge_retreats(
            seed,
            cell,
            exposed_mask,
            tile_px,
            terrain,
            neighbour_terrains,  # type: ignore[arg-type]
        )
        role = _cell_role(neighbour_mask)
        mass_cluster = _mass_cluster_key(key, distance[cell])
        slot = 0
        signature_xy = _signature_xy(seed, cell, terrain, tile_px)
        placements.append(
            _make_placement(
                component_key=key,
                cluster_id=mass_cluster,
                cell=cell,
                terrain=terrain,
                cell_role=role,
                role="cell_signature",
                slot=slot,
                xy=signature_xy,
                tile_px=tile_px,
                world_width=world_width,
                world_height_hint=world_height_hint,
                seed=seed,
                neighbour_mask=neighbour_mask,
                retreats=retreats,
            )
        )
        slot += 1

        occupied = [signature_xy]
        for direction, bit in _DIRECTIONS:
            if not (neighbour_mask & bit):
                continue
            neighbour = _neighbour(cell, direction, world_width)
            seam_xy = _seam_xy(seed, cell, neighbour, direction, tile_px, world_width)
            placements.append(
                _make_placement(
                    component_key=key,
                    cluster_id=_edge_key(key, cell, neighbour, world_width),
                    cell=cell,
                    terrain=terrain,
                    cell_role=role,
                    role="shared_edge",
                    slot=slot,
                    xy=seam_xy,
                    tile_px=tile_px,
                    world_width=world_width,
                    world_height_hint=world_height_hint,
                    seed=seed,
                    neighbour_mask=neighbour_mask,
                    retreats=retreats,
                )
            )
            occupied.append(seam_xy)
            slot += 1

            if _seam_has_third_tree(seed, cell, neighbour):
                extra_xy = _seam_extra_xy(
                    seed,
                    cell,
                    neighbour,
                    direction,
                    tile_px,
                    world_width,
                )
                placements.append(
                    _make_placement(
                        component_key=key,
                        cluster_id=_edge_key(key, cell, neighbour, world_width),
                        cell=cell,
                        terrain=terrain,
                        cell_role=role,
                        role="shared_edge",
                        slot=slot,
                        xy=extra_xy,
                        tile_px=tile_px,
                        world_width=world_width,
                        world_height_hint=world_height_hint,
                        seed=seed,
                        neighbour_mask=neighbour_mask,
                        retreats=retreats,
                    )
                )
                occupied.append(extra_xy)
                slot += 1

        fill_role: PointRole = "interior_fill" if role in {"junction", "interior"} else "edge_fill"
        target = max(
            len(occupied),
            _target_count(seed=seed, cell=cell, terrain=terrain, role=role),
        )
        fill_points = _fill_candidates(
            seed=seed,
            cell=cell,
            terrain=terrain,
            tile_px=tile_px,
            retreats=retreats,
            count=target - len(occupied),
            occupied=occupied,
        )
        for xy in fill_points:
            placements.append(
                _make_placement(
                    component_key=key,
                    cluster_id=mass_cluster,
                    cell=cell,
                    terrain=terrain,
                    cell_role=role,
                    role=fill_role,
                    slot=slot,
                    xy=xy,
                    tile_px=tile_px,
                    world_width=world_width,
                    world_height_hint=world_height_hint,
                    seed=seed,
                    neighbour_mask=neighbour_mask,
                    retreats=retreats,
                )
            )
            slot += 1

    placements.sort(key=lambda point: (point.owner_cell[1], point.owner_cell[0], point.depth_layer, point.placement_id[-1]))
    grouped: dict[ClusterKey, list[TreePlacement]] = defaultdict(list)
    for placement in placements:
        grouped[placement.cluster_id].append(placement)
    clusters: list[WoodlandCluster] = []
    for cluster_id, points in grouped.items():
        cluster_cells = tuple(sorted({point.owner_cell for point in points}, key=_cell_key))
        kind: ClusterKind = "seam_grove" if cluster_id[1].startswith("seam_") else "mass"
        clusters.append(
            WoodlandCluster(
                cluster_id=cluster_id,
                component_key=key,
                kind=kind,
                cells=cluster_cells,
                placement_ids=tuple(point.placement_id for point in points),
                clip_cells=cluster_cells,
            )
        )
    clusters.sort(key=lambda cluster: (cluster.kind, cluster.cluster_id[1], cluster.cluster_id[3], cluster.cluster_id[2]))
    ordered_cells = tuple(sorted(cells, key=_cell_key))
    return WoodlandComponentPlan(
        key=key,
        terrain=terrain,
        mode=mode,
        cells=ordered_cells,
        placements=tuple(placements),
        clusters=tuple(clusters),
        shared_edges=_shared_edges(graph),
        clip_cells=ordered_cells,
    )


def plan_forest_regions_v3(
    raw_grid: np.ndarray,
    *,
    seed: int,
    tile_px: int = 96,
    world_width: int | None = None,
    world_x0: int = 0,
    world_y0: int = 0,
) -> tuple[WoodlandComponentPlan, ...]:
    """Plan complete FOREST/JUNGLE components in absolute world coordinates.

    Every horizontal world column must be present exactly once.  A cyclically
    rolled full world is accepted when ``world_x0`` identifies local column
    zero.  Partial chunks are intentionally rejected; use
    :func:`select_forest_metadata_v3` on the immutable full plan instead.
    """

    grid = np.asarray(raw_grid)
    if grid.ndim != 2:
        raise ValueError(f"raw_grid must be 2-D, got {grid.shape}")
    if grid.shape[0] <= 0 or grid.shape[1] <= 0:
        raise ValueError("raw_grid must not be empty")
    width = grid.shape[1] if world_width is None else int(world_width)
    if width <= 0:
        raise ValueError("world_width must be positive")
    if tile_px < 24:
        raise ValueError("tile_px must be at least 24 for the forest scatter contract")
    if grid.shape[1] != width:
        raise ValueError(
            "component-wide forest grammar requires the complete horizontal world: "
            f"grid width {grid.shape[1]} != world_width {width}"
        )

    terrain_by_world: dict[WorldCell, int] = {}
    all_terrain_by_world: dict[WorldCell, int] = {}
    for local_y in range(grid.shape[0]):
        for local_x in range(grid.shape[1]):
            terrain = int(grid[local_y, local_x])
            world = ((int(world_x0) + local_x) % width, int(world_y0) + local_y)
            all_terrain_by_world[world] = terrain
            if terrain not in WOODLAND_TERRAINS:
                continue
            if world in terrain_by_world:  # pragma: no cover - guarded by full width
                raise ValueError(f"duplicate world coordinate {world}")
            terrain_by_world[world] = terrain

    unseen = set(terrain_by_world)
    components: list[tuple[int, tuple[WorldCell, ...]]] = []
    while unseen:
        start = min(unseen, key=_cell_key)
        terrain = terrain_by_world[start]
        unseen.remove(start)
        queue: deque[WorldCell] = deque((start,))
        cells: list[WorldCell] = []
        while queue:
            cell = queue.popleft()
            cells.append(cell)
            for direction, _ in _DIRECTIONS:
                neighbour = _neighbour(cell, direction, width)
                if neighbour in unseen and terrain_by_world.get(neighbour) == terrain:
                    unseen.remove(neighbour)
                    queue.append(neighbour)
        components.append((terrain, tuple(sorted(cells, key=_cell_key))))

    plans = (
        _component_plan(
            terrain,
            cells,
            seed=int(seed),
            tile_px=int(tile_px),
            world_width=width,
            world_height_hint=max(int(world_y0) + grid.shape[0], grid.shape[0]),
            terrain_by_world=all_terrain_by_world,
        )
        for terrain, cells in components
    )
    return tuple(sorted(plans, key=lambda plan: (plan.key[2], plan.key[1], plan.terrain)))


def select_forest_metadata_v3(
    plans: Iterable[WoodlandComponentPlan],
    render_cells: Iterable[WorldCell],
) -> WoodlandSelection:
    """Select full-plan point records for a render core plus halo.

    Clusters are returned as their immutable full-world records when any of
    their cells intersects the request.  Placements remain restricted to their
    exact requested owner cells.
    """

    requested = set(render_cells)
    component_keys: list[ComponentKey] = []
    placements: list[TreePlacement] = []
    clusters: list[WoodlandCluster] = []
    for plan in plans:
        if not requested.intersection(plan.cells):
            continue
        component_keys.append(plan.key)
        placements.extend(point for point in plan.placements if point.owner_cell in requested)
        clusters.extend(cluster for cluster in plan.clusters if requested.intersection(cluster.cells))
    return WoodlandSelection(
        component_keys=tuple(sorted(component_keys, key=lambda key: (key[2], key[1], key[0]))),
        placements=tuple(sorted(placements, key=lambda point: point.placement_id)),
        clusters=tuple(sorted(clusters, key=lambda cluster: cluster.cluster_id)),
    )


def _layout_signature(points: Iterable[TreePlacement]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                point.role,
                point.asset_key,
                point.anchor_px,
                point.crown_diameter_px,
                point.variant,
            )
            for point in points
        )
    )


def forest_statistics_v3(
    plans: Iterable[WoodlandComponentPlan],
    *,
    world_width: int,
) -> dict[str, object]:
    """Return JSON-friendly coverage, density and anti-wallpaper evidence."""

    plan_tuple = tuple(plans)
    placements = [point for plan in plan_tuple for point in plan.placements]
    cells = [cell for plan in plan_tuple for cell in plan.cells]
    by_cell: dict[WorldCell, list[TreePlacement]] = defaultdict(list)
    for point in placements:
        by_cell[point.owner_cell].append(point)
    layout_signatures = {_layout_signature(points) for points in by_cell.values()}
    terrain_components = Counter("forest" if plan.terrain == FOREST else "jungle" for plan in plan_tuple)
    terrain_cells = Counter("forest" if plan.terrain == FOREST else "jungle" for plan in plan_tuple for _ in plan.cells)
    modes = Counter(plan.mode for plan in plan_tuple)
    roles = Counter(point.role for point in placements)
    assets = Counter(point.asset_key for point in placements)
    cell_roles = Counter(point.cell_role for point in placements if point.is_cell_signature)
    size_classes = Counter(
        "1" if plan.size == 1 else "2-4" if plan.size <= 4 else "5+"
        for plan in plan_tuple
    )
    wrap_components = sum(
        any((world_width - 1, y) in set(plan.cells) and (0, y) in set(plan.cells) for _, y in plan.cells)
        for plan in plan_tuple
    )
    positive_retreats = [value for point in placements for value in point.edge_retreat_px if value > 0]
    seam_clusters = [cluster for plan in plan_tuple for cluster in plan.clusters if cluster.kind == "seam_grove"]
    mass_clusters = [cluster for plan in plan_tuple for cluster in plan.clusters if cluster.kind == "mass"]
    return {
        "components": len(plan_tuple),
        "cells": len(cells),
        "unique_cells": len(set(cells)),
        "placements": len(placements),
        "cell_signatures": sum(point.is_cell_signature for point in placements),
        "shared_edges": sum(len(plan.shared_edges) for plan in plan_tuple),
        "seam_clusters": len(seam_clusters),
        "mass_clusters": len(mass_clusters),
        "cross_cell_seam_clusters": sum(len(cluster.cells) == 2 for cluster in seam_clusters),
        "max_component_size": max((plan.size for plan in plan_tuple), default=0),
        "wrap_components": wrap_components,
        "average_points_per_cell": round(len(placements) / max(1, len(cells)), 4),
        "unique_cell_layouts": len(layout_signatures),
        "layout_uniqueness_ratio": round(len(layout_signatures) / max(1, len(cells)), 4),
        "crown_min_px": min((point.crown_diameter_px for point in placements), default=0),
        "crown_max_px": max((point.crown_diameter_px for point in placements), default=0),
        "exposed_retreat_min_px": min(positive_retreats, default=0),
        "exposed_retreat_max_px": max(positive_retreats, default=0),
        "terrain_components": dict(sorted(terrain_components.items())),
        "terrain_cells": dict(sorted(terrain_cells.items())),
        "component_modes": dict(sorted(modes.items())),
        "component_size_classes": dict(sorted(size_classes.items())),
        "point_roles": dict(sorted(roles.items())),
        "cell_roles": dict(sorted(cell_roles.items())),
        "asset_keys": dict(sorted(assets.items())),
    }


def forest_point_proof_svg_v3(
    raw_grid: np.ndarray,
    plans: Iterable[WoodlandComponentPlan],
    *,
    x0: int,
    y0: int,
    width: int,
    height: int,
    world_width: int,
    tile_px: int = 96,
    cell_px: int = 34,
    title: str = "Forest/Jungle v3 authority proof",
) -> str:
    """Create an inspectable SVG mask/point proof without loading art assets."""

    grid = np.asarray(raw_grid)
    if grid.ndim != 2 or grid.shape[1] != world_width:
        raise ValueError("proof requires the complete horizontal world grid")
    if width <= 0 or height <= 0 or cell_px < 12:
        raise ValueError("proof dimensions must be positive")
    xs = [(x0 + offset) % world_width for offset in range(width)]
    requested = {(wx, y) for y in range(y0, y0 + height) for wx in xs}
    selection = select_forest_metadata_v3(plans, requested)
    x_index = {wx: index for index, wx in enumerate(xs)}
    header = 50
    canvas_w = width * cell_px
    canvas_h = header + height * cell_px + 34
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}">',
        '<rect width="100%" height="100%" fill="#10161a"/>',
        f'<text x="12" y="22" fill="#f0f4f1" font-family="Segoe UI, sans-serif" font-size="15">{escape(title)}</text>',
        '<text x="12" y="40" fill="#9eb1a6" font-family="Consolas, monospace" font-size="10">mask: forest / jungle | white ring: exact cell signature | gold: shared-edge grove</text>',
    ]
    terrain_by_cell: dict[WorldCell, int] = {}
    for row in range(height):
        wy = y0 + row
        if not (0 <= wy < grid.shape[0]):
            continue
        for column, wx in enumerate(xs):
            terrain = int(grid[wy, wx])
            terrain_by_cell[(wx, wy)] = terrain
            fill = "#284f31" if terrain == FOREST else "#176044" if terrain == JUNGLE else "#242b2e"
            lines.append(
                f'<rect x="{column * cell_px}" y="{header + row * cell_px}" width="{cell_px}" height="{cell_px}" fill="{fill}" stroke="#536067" stroke-width="0.55"/>'
            )
    for point in selection.placements:
        if point.owner_cell not in requested or point.owner_cell[0] not in x_index:
            continue
        column = x_index[point.owner_cell[0]]
        row = point.owner_cell[1] - y0
        cx = column * cell_px + point.anchor_px[0] / tile_px * cell_px
        cy = header + row * cell_px + point.anchor_px[1] / tile_px * cell_px
        radius = max(1.4, point.crown_diameter_px / tile_px * cell_px * 0.24)
        fill = "#82d56e" if point.asset_key == "broadleaf" else "#68b6b0"
        if point.role == "shared_edge":
            fill = "#e7b94c"
        lines.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" fill="{fill}" fill-opacity="0.82"/>')
        if point.is_cell_signature:
            lines.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius + 1.5:.2f}" fill="none" stroke="#ffffff" stroke-width="1.15"/>')
    for row in range(height):
        wy = y0 + row
        for column, wx in enumerate(xs):
            terrain = terrain_by_cell.get((wx, wy))
            if terrain not in WOODLAND_TERRAINS:
                continue
            same = {
                direction: terrain_by_cell.get(_neighbour((wx, wy), direction, world_width)) == terrain
                for direction, _ in _DIRECTIONS
            }
            x = column * cell_px
            y = header + row * cell_px
            if not same["N"]:
                lines.append(f'<line x1="{x}" y1="{y}" x2="{x + cell_px}" y2="{y}" stroke="#e88557" stroke-width="1.35"/>')
            if not same["E"]:
                lines.append(f'<line x1="{x + cell_px}" y1="{y}" x2="{x + cell_px}" y2="{y + cell_px}" stroke="#e88557" stroke-width="1.35"/>')
            if not same["S"]:
                lines.append(f'<line x1="{x}" y1="{y + cell_px}" x2="{x + cell_px}" y2="{y + cell_px}" stroke="#e88557" stroke-width="1.35"/>')
            if not same["W"]:
                lines.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + cell_px}" stroke="#e88557" stroke-width="1.35"/>')
    lines.append(
        f'<text x="12" y="{canvas_h - 12}" fill="#9eb1a6" font-family="Consolas, monospace" font-size="10">points={len(selection.placements)} components={len(selection.component_keys)} crop=x{x0} y{y0} {width}x{height}</text>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


__all__ = (
    "ASSET_KEYS",
    "ClusterKey",
    "ComponentKey",
    "TreePlacement",
    "WOODLAND_TERRAINS",
    "WoodlandCluster",
    "WoodlandComponentPlan",
    "WoodlandSelection",
    "WorldCell",
    "forest_point_proof_svg_v3",
    "forest_statistics_v3",
    "plan_forest_regions_v3",
    "select_forest_metadata_v3",
)
