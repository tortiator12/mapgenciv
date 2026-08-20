"""Snapshot-authoritative hydrology for production Civ/OpenCivOne maps.

OpenCivOne snapshots store River *cells* but no ordered flow edges.  This
adapter preserves every saved River cell and reconstructs a deterministic
mouth-rooted spanning forest.  It never asks a map to contain an arbitrary
number of rivers.  Continuous display traces are derived only after the saved
cell authority is fixed.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from .continuous_hydrology_v11 import (
    ContinuousHydrologyWorldV11,
    ContinuousMouthV11,
    ContinuousTraceV11,
    FlowSampleV11,
)
from .continuous_hydrology_v12 import (
    ContinuousHydrologyWorldV12,
    ContinuousTraceV12,
    JunctionPatchV12,
)
from .modern_hydrology_v6 import build_hydrology_fields


Cell = tuple[int, int]
Point = tuple[float, float]
Edge = tuple[Cell, Cell]
_CARDINAL = ((0, -1), (1, 0), (0, 1), (-1, 0))


class SnapshotHydrologyError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotHydrologyAuditV24:
    valid: bool
    errors: tuple[str, ...]
    river_cells: int
    traces: int
    primaries: int
    confluences: int
    mouths: int
    components: int
    discarded_cycle_edges: int


def _neighbor(cell: Cell, delta: tuple[int, int], width: int, height: int) -> Cell | None:
    x, y = cell
    dx, dy = delta
    ny = y + dy
    if not 0 <= ny < height:
        return None
    return (x + dx) % width, ny


def _neighbors(cell: Cell, width: int, height: int) -> Iterable[Cell]:
    for delta in _CARDINAL:
        item = _neighbor(cell, delta, width, height)
        if item is not None:
            yield item


def _components(cells: set[Cell], width: int, height: int) -> list[set[Cell]]:
    remaining = set(cells)
    result = []
    while remaining:
        start = min(remaining, key=lambda item: (item[1], item[0]))
        component = {start}
        queue = deque([start])
        remaining.remove(start)
        while queue:
            current = queue.popleft()
            for neighbor in _neighbors(current, width, height):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        result.append(component)
    return result


def _water_neighbors(cell: Cell, grid: np.ndarray, water_code: int) -> list[Cell]:
    height, width = grid.shape
    return [
        neighbor
        for neighbor in _neighbors(cell, width, height)
        if int(grid[neighbor[1], neighbor[0]]) == int(water_code)
    ]


def _forest(
    component: set[Cell],
    roots: Sequence[Cell],
    width: int,
    height: int,
) -> tuple[dict[Cell, Cell | None], dict[Cell, Cell], int]:
    """Return child->downstream parent, root ownership and cycle-edge count."""

    parent: dict[Cell, Cell | None] = {}
    owner: dict[Cell, Cell] = {}
    queue: deque[Cell] = deque()
    for root in sorted(set(roots), key=lambda item: (item[1], item[0])):
        parent[root] = None
        owner[root] = root
        queue.append(root)
    while queue:
        current = queue.popleft()
        candidates = sorted(
            (item for item in _neighbors(current, width, height) if item in component),
            key=lambda item: (item[1], item[0]),
        )
        for neighbor in candidates:
            if neighbor in parent:
                continue
            parent[neighbor] = current
            owner[neighbor] = owner[current]
            queue.append(neighbor)
    if set(parent) != component:
        raise SnapshotHydrologyError("mouth-rooted forest did not cover its River component")
    raw_edges = {
        frozenset((cell, neighbor))
        for cell in component
        for neighbor in _neighbors(cell, width, height)
        if neighbor in component and cell != neighbor
    }
    tree_edges = {frozenset((cell, downstream)) for cell, downstream in parent.items() if downstream is not None}
    return parent, owner, len(raw_edges - tree_edges)


def _shortest_path(start: Cell, goal: Cell, adjacency: Mapping[Cell, Sequence[Cell]]) -> list[Cell]:
    parent: dict[Cell, Cell | None] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == goal:
            break
        for neighbor in sorted(adjacency[current], key=lambda item: (item[1], item[0])):
            if neighbor not in parent:
                parent[neighbor] = current
                queue.append(neighbor)
    if goal not in parent:
        raise SnapshotHydrologyError("inland River cycle is disconnected")
    result = [goal]
    while result[-1] != start:
        result.append(parent[result[-1]])  # type: ignore[arg-type]
    result.reverse()
    return result


def _closed_walk(component: set[Cell], width: int, height: int) -> tuple[list[Cell], int]:
    """Eulerize a cyclic inland component and return one closed visual walk.

    Odd-degree branches are paired over shortest existing River paths.  Only
    edges are repeated; no new cell or connection is invented.
    """

    adjacency = {
        cell: sorted((item for item in _neighbors(cell, width, height) if item in component), key=lambda item: (item[1], item[0]))
        for cell in component
    }
    raw = {
        tuple(sorted((cell, neighbor), key=lambda item: (item[1], item[0])))
        for cell, values in adjacency.items()
        for neighbor in values
        if cell != neighbor
    }
    cycle_rank = len(raw) - len(component) + 1
    if cycle_rank < 1:
        raise SnapshotHydrologyError("mouthless River component is not cyclic")

    multiplicity: Counter[tuple[Cell, Cell]] = Counter(raw)
    odd = sorted((cell for cell, values in adjacency.items() if len(values) % 2), key=lambda item: (item[1], item[0]))
    while odd:
        start = odd.pop(0)
        candidates = [(_shortest_path(start, goal, adjacency), goal) for goal in odd]
        path, goal = min(candidates, key=lambda item: (len(item[0]), item[1][1], item[1][0]))
        odd.remove(goal)
        for first, second in zip(path, path[1:]):
            edge = tuple(sorted((first, second), key=lambda item: (item[1], item[0])))
            multiplicity[edge] += 1

    multi: dict[Cell, Counter[Cell]] = {cell: Counter() for cell in component}
    for (first, second), count in multiplicity.items():
        multi[first][second] += count
        multi[second][first] += count
    start = min(component, key=lambda item: (item[1], item[0]))
    stack, circuit = [start], []
    while stack:
        current = stack[-1]
        choices = [item for item, count in multi[current].items() if count]
        if choices:
            neighbor = min(choices, key=lambda item: (item[1], item[0]))
            multi[current][neighbor] -= 1
            multi[neighbor][current] -= 1
            stack.append(neighbor)
        else:
            circuit.append(stack.pop())
    circuit.reverse()
    if circuit[0] != circuit[-1] or set(circuit) != component:
        raise SnapshotHydrologyError("failed to build a closed inland River walk")
    return circuit, cycle_rank


def _children(parent: Mapping[Cell, Cell | None]) -> dict[Cell, list[Cell]]:
    result = {cell: [] for cell in parent}
    for cell, downstream in parent.items():
        if downstream is not None:
            result[downstream].append(cell)
    for values in result.values():
        values.sort(key=lambda item: (item[1], item[0]))
    return result


def _depth(cell: Cell, parent: Mapping[Cell, Cell | None]) -> int:
    result = 0
    while parent[cell] is not None:
        cell = parent[cell]  # type: ignore[assignment]
        result += 1
    return result


def _subtree_metrics(children: Mapping[Cell, Sequence[Cell]]) -> tuple[dict[Cell, int], dict[Cell, int]]:
    area: dict[Cell, int] = {}
    order: dict[Cell, int] = {}

    def visit(cell: Cell) -> tuple[int, int]:
        if cell in area:
            return area[cell], order[cell]
        values = [visit(child) for child in children[cell]]
        area[cell] = 1 + sum(item[0] for item in values)
        if not values:
            order[cell] = 1
        else:
            child_orders = [item[1] for item in values]
            maximum = max(child_orders)
            order[cell] = maximum + 1 if child_orders.count(maximum) >= 2 else maximum
        return area[cell], order[cell]

    for root in children:
        visit(root)
    return area, order


def _unwrap_path(path: Sequence[Cell], width: int) -> list[Point]:
    points: list[Point] = []
    for x, y in path:
        px = float(x) + 0.5
        if points:
            px += round((points[-1][0] - px) / width) * width
        points.append((px, float(y) + 0.5))
    return points


def _shoreline(root: Cell, water: Cell, width: int) -> tuple[Point, Point]:
    rx, ry = float(root[0]) + 0.5, float(root[1]) + 0.5
    wx = float(water[0]) + 0.5
    wx += round((rx - wx) / width) * width
    wy = float(water[1]) + 0.5
    dx, dy = wx - rx, wy - ry
    return (rx + dx * 0.5, ry + dy * 0.5), (dx, dy)


def _densify(points: Sequence[Point], spacing: float = 0.055) -> list[Point]:
    if len(points) < 2:
        return list(points)
    result = [points[0]]
    for first, second in zip(points, points[1:]):
        distance = math.hypot(second[0] - first[0], second[1] - first[1])
        count = max(1, int(math.ceil(distance / spacing)))
        for index in range(1, count + 1):
            q = index / count
            result.append((first[0] * (1.0 - q) + second[0] * q, first[1] * (1.0 - q) + second[1] * q))
    return result


def _angular_energy(points: Sequence[Point]) -> float:
    if len(points) < 3:
        return 0.0
    vector = np.diff(np.asarray(points, dtype=np.float64), axis=0)
    angle = np.unwrap(np.arctan2(vector[:, 1], vector[:, 0]))
    return float(np.mean(np.diff(angle) ** 2)) if len(angle) > 1 else 0.0


def _choose_water(root: Cell, candidates: Sequence[Cell], path: Sequence[Cell], width: int) -> Cell:
    if len(candidates) == 1:
        return candidates[0]
    if len(path) >= 2:
        previous = path[-2]
        incoming = ((root[0] - previous[0] + width // 2) % width - width // 2, root[1] - previous[1])
    else:
        incoming = (0, 1)

    def score(water: Cell) -> tuple[float, int, int]:
        outgoing = ((water[0] - root[0] + width // 2) % width - width // 2, water[1] - root[1])
        return (-(incoming[0] * outgoing[0] + incoming[1] * outgoing[1]), water[1], water[0])

    return min(candidates, key=score)


def _path_to_network(leaf: Cell, parent: Mapping[Cell, Cell | None], assigned: set[Cell]) -> list[Cell]:
    path = [leaf]
    current = leaf
    while parent[current] is not None:
        current = parent[current]  # type: ignore[assignment]
        path.append(current)
        if current in assigned:
            break
    return path


def _samples(
    points: Sequence[Point],
    start_area: int,
    end_area: int,
    strahler: int,
    primary: bool,
) -> tuple[FlowSampleV11, ...]:
    count = max(1, len(points) - 1)
    result = []
    for index, point in enumerate(points):
        q = index / count
        area = float(start_area) * (1.0 - q) + float(end_area) * q
        cap = 17.4 if primary else 11.4
        width = min(cap, 3.2 + math.sqrt(max(area, 1.0)) * 2.35)
        result.append(FlowSampleV11(point, area, max(1, int(strahler)), width, 1.0 - q))
    return tuple(result)


def _source_underlay(
    grid: np.ndarray,
    river_cells: set[Cell],
    source_cells: set[Cell],
    authority,
) -> np.ndarray:
    result = grid.copy()
    height, width = result.shape
    mountain = int(authority.Terrain.MOUNTAINS)
    hill = int(authority.Terrain.HILLS)
    grass = int(authority.Terrain.GRASSLAND)
    for cell in river_cells:
        result[cell[1], cell[0]] = grass
    for cell in source_cells:
        ring = [item for item in _neighbors(cell, width, height) if item not in river_cells]
        values = {int(grid[y, x]) for x, y in ring}
        if mountain in values:
            result[cell[1], cell[0]] = mountain
        elif hill in values:
            result[cell[1], cell[0]] = hill
    return result


def load_snapshot_hydrology_v24(
    path: str | Path,
    authority,
    *,
    tile_px: int = 96,
) -> ContinuousHydrologyWorldV12:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema") != "civ-mapproto.snapshot/v1":
        raise SnapshotHydrologyError("expected civ-mapproto.snapshot/v1")
    width, height = int(payload["width"]), int(payload["height"])
    grid = np.asarray(payload["terrain"], dtype=np.int16)
    if grid.shape != (height, width):
        raise SnapshotHydrologyError(f"snapshot shape {grid.shape} does not match {width}x{height}")
    river_code = int(authority.Terrain.RIVER)
    water_code = int(authority.Terrain.WATER)
    river_cells = {(int(x), int(y)) for y, x in np.argwhere(grid == river_code)}
    if not river_cells:
        raise SnapshotHydrologyError("snapshot contains no River cells")

    trace_specs: list[dict] = []
    mouth_specs: list[tuple[int, Cell, Cell, Point, Point, int, int]] = []
    discarded = 0
    component_count = 0
    for component in _components(river_cells, width, height):
        component_count += 1
        roots = sorted(
            (cell for cell in component if _water_neighbors(cell, grid, water_code)),
            key=lambda item: (item[1], item[0]),
        )
        if not roots:
            closed, cycle_rank = _closed_walk(component, width, height)
            discarded += cycle_rank
            trace_id = len(trace_specs)
            area = {cell: len(component) for cell in component}
            order = {cell: 1 for cell in component}
            trace_specs.append(
                {"trace_id": trace_id, "kind": "loop", "parent_trace": None, "path": closed,
                 "attachment": None, "shore": None, "water": None, "direction": None,
                 "area": area, "order": order}
            )
            continue
        parent, root_owner, dropped = _forest(component, roots, width, height)
        discarded += dropped
        children = _children(parent)
        area, order = _subtree_metrics(children)
        owner_to_cells: dict[Cell, set[Cell]] = {root: set() for root in roots}
        for cell, root in root_owner.items():
            owner_to_cells[root].add(cell)

        for root in roots:
            tree = owner_to_cells[root]
            leaves = sorted(
                (cell for cell in tree if not children[cell]),
                key=lambda cell: (-_depth(cell, parent), cell[1], cell[0]),
            )
            if not leaves:
                leaves = [root]
            assigned: set[Cell] = set()
            owner_trace: dict[Cell, int] = {}
            main = leaves[0]
            main_path = _path_to_network(main, parent, set())
            if main_path[-1] != root:
                raise SnapshotHydrologyError("primary path did not reach its mouth root")
            trace_id = len(trace_specs)
            for cell in main_path:
                assigned.add(cell)
                owner_trace.setdefault(cell, trace_id)
            water = _choose_water(root, _water_neighbors(root, grid, water_code), main_path, width)
            shore, direction = _shoreline(root, water, width)
            trace_specs.append(
                {"trace_id": trace_id, "kind": "primary", "parent_trace": None, "path": main_path,
                 "attachment": None, "shore": shore, "water": water, "direction": direction,
                 "area": area, "order": order}
            )
            mouth_specs.append((trace_id, root, water, shore, direction, area[root], order[root]))

            for leaf in leaves[1:]:
                if leaf in assigned:
                    continue
                branch = _path_to_network(leaf, parent, assigned)
                attachment = branch[-1]
                if attachment not in assigned:
                    raise SnapshotHydrologyError("confluence path did not reach the accepted network")
                branch_id = len(trace_specs)
                trace_specs.append(
                    {"trace_id": branch_id, "kind": "tributary", "parent_trace": owner_trace[attachment],
                     "path": branch, "attachment": (float(attachment[0]) + 0.5, float(attachment[1]) + 0.5),
                     "shore": None, "water": None, "direction": None, "area": area, "order": order}
                )
                for cell in branch[:-1]:
                    assigned.add(cell)
                    owner_trace.setdefault(cell, branch_id)
            if assigned != tree:
                missing = sorted(tree - assigned, key=lambda item: (item[1], item[0]))
                raise SnapshotHydrologyError(f"trace decomposition left {len(missing)} River cells uncovered")

    source_cells = {spec["path"][0] for spec in trace_specs if spec["kind"] != "loop"}
    stage4 = _source_underlay(grid, river_cells, source_cells, authority)
    fields = build_hydrology_fields(stage4, authority, int(payload["seed"]))
    v11_traces = []
    v12_traces = []
    for spec in trace_specs:
        path: list[Cell] = spec["path"]
        points = _unwrap_path(path, width)
        if spec["shore"] is not None:
            shore = spec["shore"]
            shore_x = shore[0] + round((points[-1][0] - shore[0]) / width) * width
            points.append((shore_x, shore[1]))
        dense = _densify(points)
        start_area = spec["area"][path[0]]
        end_area = spec["area"][path[-1]]
        samples = _samples(dense, start_area, end_area, spec["order"][path[-1]], spec["kind"] == "primary")
        edges = tuple((first, second) for first, second in zip(path, path[1:]))
        termination = "coast" if spec["kind"] == "primary" else ("loop" if spec["kind"] == "loop" else "confluence")
        common = dict(
            trace_id=spec["trace_id"], kind=spec["kind"], parent_trace=spec["parent_trace"],
            attachment_point=spec["attachment"], source_cell=path[0], termination=termination,
            mouth_water_cell=spec["water"], shoreline_point=spec["shore"], samples=samples,
            raster_cells=tuple(path), raster_edges=edges, uphill_fraction=0.0,
        )
        v11_traces.append(
            ContinuousTraceV11(**common, fine_path=(), max_cardinal_run=max(1, len(path) - 1))
        )
        v12_traces.append(
            ContinuousTraceV12(
                **common, corridor_fine_path=(), angular_energy=_angular_energy(dense), min_relief_clearance=0.0
            )
        )

    mouths = []
    for trace_id, river_cell, water_cell, shore, direction, area_value, order_value in mouth_specs:
        length = max(math.hypot(*direction), 1e-9)
        unit = (direction[0] / length, direction[1] / length)
        mouths.append(
            ContinuousMouthV11(
                trace_id, river_cell, water_cell,
                (shore[0] * tile_px, shore[1] * tile_px), unit, (-unit[1], unit[0]),
                8.0, tile_px * 0.55, tile_px * 0.82,
                -1.0 if ((trace_id * 1103515245 + int(payload["seed"])) & 1) else 1.0,
                float(area_value), int(order_value),
            )
        )

    junctions = []
    by_id = {trace.trace_id: trace for trace in v12_traces}
    for trace in v12_traces:
        if trace.parent_trace is None or trace.attachment_point is None:
            continue
        parent_trace = by_id[trace.parent_trace]
        point = trace.attachment_point
        parent_points = np.asarray(parent_trace.points, dtype=np.float64)
        px = point[0] + round((parent_points[0, 0] - point[0]) / width) * width
        index = int(np.argmin(np.sum((parent_points - np.asarray((px, point[1]))) ** 2, axis=1)))
        lo, hi = max(0, index - 3), min(len(parent_points) - 1, index + 3)
        downstream_vector = parent_points[hi] - parent_points[lo]
        incoming_points = np.asarray(trace.points, dtype=np.float64)
        incoming_vector = incoming_points[-1] - incoming_points[max(0, len(incoming_points) - 5)]
        def unit(vector: np.ndarray) -> Point:
            size = max(float(np.hypot(vector[0], vector[1])), 1e-9)
            return float(vector[0] / size), float(vector[1] / size)
        downstream_tangent, incoming_tangent = unit(downstream_vector), unit(incoming_vector)
        dot = max(-1.0, min(1.0, downstream_tangent[0] * incoming_tangent[0] + downstream_tangent[1] * incoming_tangent[1]))
        junctions.append(
            JunctionPatchV12(trace.parent_trace, trace.trace_id, point, downstream_tangent, incoming_tangent,
                             math.degrees(math.acos(dot)), 0.0)
        )

    terrain_rows = tuple(tuple(int(value) for value in row) for row in grid)
    stage4_rows = tuple(tuple(int(value) for value in row) for row in stage4)
    river_edges = tuple(edge for trace in v12_traces for edge in trace.raster_edges)
    water_mask = tuple(tuple(bool(value == water_code) for value in row) for row in grid)
    source_v11 = ContinuousHydrologyWorldV11(
        stage4_rows, terrain_rows, tuple(v11_traces), tuple(sorted(river_cells, key=lambda item: (item[1], item[0]))),
        river_edges, tuple(mouths), fields, water_mask, tile_px, width, height, int(payload["seed"]), 6,
        "snapshot-authoritative-v24-source",
    )
    return ContinuousHydrologyWorldV12(
        stage4_rows, terrain_rows, tuple(v12_traces), tuple(sorted(river_cells, key=lambda item: (item[1], item[0]))),
        river_edges, tuple(mouths), tuple(junctions), fields, water_mask, tile_px, width, height,
        int(payload["seed"]), 6, "snapshot-authoritative-v24", source_v11,
    )


def audit_snapshot_hydrology_v24(world: ContinuousHydrologyWorldV12, original_grid: Sequence[Sequence[int]], river_code: int) -> SnapshotHydrologyAuditV24:
    expected = {(int(x), int(y)) for y, x in np.argwhere(np.asarray(original_grid) == int(river_code))}
    actual = set(world.river_cells)
    errors = []
    if expected != actual:
        errors.append("saved River cell authority changed")
    covered = {cell for trace in world.traces for cell in trace.raster_cells}
    if covered != expected:
        errors.append("trace coverage differs from saved River cells")
    for trace in world.traces:
        if trace.termination == "coast" and (trace.mouth_water_cell is None or trace.shoreline_point is None):
            errors.append(f"trace {trace.trace_id} has no mouth")
        if trace.termination == "confluence" and (trace.parent_trace is None or trace.attachment_point is None):
            errors.append(f"trace {trace.trace_id} has no parent confluence")
        if trace.termination == "loop" and trace.points and trace.points[0] != trace.points[-1]:
            errors.append(f"trace {trace.trace_id} is not a closed inland loop")
    components = _components(expected, world.world_width, world.world_height)
    return SnapshotHydrologyAuditV24(
        not errors, tuple(errors), len(expected), len(world.traces),
        sum(trace.kind == "primary" for trace in world.traces),
        sum(trace.kind == "tributary" for trace in world.traces), len(world.mouths), len(components), 0,
    )


__all__ = [
    "SnapshotHydrologyAuditV24", "SnapshotHydrologyError",
    "audit_snapshot_hydrology_v24", "load_snapshot_hydrology_v24",
]
