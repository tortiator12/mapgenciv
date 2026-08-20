"""Two-pass basin/trunk hydrology experiment built on the V6 stage boundary.

V7 leaves both the legacy generator and Modern Hydrology V6 untouched.  Pass 1
routes a small set of high-quality primary trunks from the strongest highland
sources to explicit mouths.  Their internal cells expose reserved attachment
ports.  Pass 2 routes additional highland sources to exactly one free port,
producing real tributaries rather than visually snapped or inferred junctions.

All rules terrain remains ordinary cardinal Civ-I ``RIVER`` cells.  Ordered
downstream edges are the presentation authority and carry accumulated upstream
area plus Strahler order for renderer width hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import heapq
from typing import Any, Iterable, Sequence

import numpy as np

from . import modern_hydrology_v6 as v6


Cell = tuple[int, int]
Edge = tuple[Cell, Cell]


@dataclass(frozen=True)
class BasinHydrologyConfigV7:
    min_path_cells: int = 5
    primary_min_cells: int = 9
    primary_extra_cells: int = 4
    max_path_cells: int = 18
    max_search_states: int = 10_000
    primary_fraction: float = 0.43
    min_primary_trunks: int = 3
    max_primary_trunks: int = 5
    uphill_weight: float = 8.5
    away_from_sink_weight: float = 0.72
    turn_penalty: float = 0.08
    same_turn_penalty: float = 1.6
    mountain_entry_penalty: float = 0.45

    def __post_init__(self) -> None:
        if self.min_path_cells < 5:
            raise ValueError("tributaries must contain at least five cells")
        if self.primary_min_cells < self.min_path_cells:
            raise ValueError("primary trunks cannot be shorter than tributaries")
        if self.max_path_cells < self.primary_min_cells + self.primary_extra_cells:
            raise ValueError("max_path_cells does not cover primary range")
        if not 0.0 < self.primary_fraction < 1.0:
            raise ValueError("primary_fraction must be between zero and one")
        if self.min_primary_trunks < 1 or self.max_primary_trunks < self.min_primary_trunks:
            raise ValueError("invalid primary trunk bounds")


@dataclass(frozen=True)
class ReservedPortV7:
    cell: Cell
    trunk_id: int
    status: str
    used_by_trace: int | None


@dataclass(frozen=True)
class ExplicitMouthV7:
    river_cell: Cell
    water_cell: Cell
    direction: str
    trunk_id: int
    upstream_area: int
    strahler: int


@dataclass(frozen=True)
class BasinTraceV7:
    trace_id: int
    kind: str
    trunk_id: int
    cells: tuple[Cell, ...]
    edges: tuple[Edge, ...]
    termination: str
    attachment_port: Cell | None
    mouth_direction: str | None
    source_terrain: int
    source_potential: float
    end_potential: float
    route_cost: float


@dataclass(frozen=True)
class FlowCellV7:
    cell: Cell
    downstream: Cell | None
    upstream_area: int
    strahler: int
    role: str
    trunk_id: int


@dataclass(frozen=True)
class FlowEdgeV7:
    start: Cell
    end: Cell
    upstream_area: int
    strahler: int
    trunk_id: int
    role: str


@dataclass(frozen=True)
class BasinHydrologyWorldV7:
    stage4_terrain: tuple[tuple[int, ...], ...]
    terrain: tuple[tuple[int, ...], ...]
    traces: tuple[BasinTraceV7, ...]
    river_edges: tuple[Edge, ...]
    flow_cells: tuple[FlowCellV7, ...]
    flow_edges: tuple[FlowEdgeV7, ...]
    mouths: tuple[ExplicitMouthV7, ...]
    reserved_ports: tuple[ReservedPortV7, ...]
    fields: v6.HydrologyFields
    river_target: int
    desired_traces: int
    primary_goal: int
    seed: int

    def snapshot_extension(self) -> dict[str, Any]:
        """V1-compatible ordered edges plus optional V7 flow hierarchy."""

        return {
            "schema": "project1991.river-traces/v1",
            "generator": "modern-hydrology-v7",
            "river_edges": [
                [[int(a[0]), int(a[1])], [int(b[0]), int(b[1])]]
                for a, b in self.river_edges
            ],
            "traces": [
                {
                    "trace_id": trace.trace_id,
                    "kind": trace.kind,
                    "trunk_id": trace.trunk_id,
                    "cells": [[x, y] for x, y in trace.cells],
                    "termination": trace.termination,
                    "confluence": (
                        list(trace.attachment_port)
                        if trace.attachment_port is not None
                        else None
                    ),
                    "mouth_candidates": (
                        [trace.mouth_direction]
                        if trace.mouth_direction is not None
                        else []
                    ),
                }
                for trace in self.traces
            ],
            "flow_hierarchy": {
                "schema": "project1991.flow-hierarchy/v1",
                "cells": [
                    {
                        "cell": list(item.cell),
                        "downstream": list(item.downstream) if item.downstream else None,
                        "upstream_area": item.upstream_area,
                        "strahler": item.strahler,
                        "role": item.role,
                        "trunk_id": item.trunk_id,
                    }
                    for item in self.flow_cells
                ],
                "edges": [
                    {
                        "start": list(item.start),
                        "end": list(item.end),
                        "upstream_area": item.upstream_area,
                        "strahler": item.strahler,
                        "role": item.role,
                        "trunk_id": item.trunk_id,
                    }
                    for item in self.flow_edges
                ],
                "mouths": [
                    {
                        "river_cell": list(item.river_cell),
                        "water_cell": list(item.water_cell),
                        "direction": item.direction,
                        "trunk_id": item.trunk_id,
                        "upstream_area": item.upstream_area,
                        "strahler": item.strahler,
                    }
                    for item in self.mouths
                ],
            },
        }


@dataclass(frozen=True)
class BasinValidationV7:
    valid: bool
    errors: tuple[str, ...]
    river_cells: int
    recorded_edges: int
    raw_adjacencies: int
    primaries: int
    tributaries: int
    confluences: int
    max_straight: int


@dataclass(frozen=True)
class _Route:
    cells: tuple[Cell, ...]
    termination: str
    attachment_port: Cell | None
    mouth_direction: str | None
    cost: float


def _wrapped_manhattan(a: Cell, b: Cell, width: int) -> int:
    dx = min((a[0] - b[0]) % width, (b[0] - a[0]) % width)
    return int(dx + abs(a[1] - b[1]))


def _max_straight(cells: Sequence[Cell], width: int) -> int:
    best = run = 0
    previous = None
    for start, end in zip(cells, cells[1:]):
        dx = (end[0] - start[0]) % width
        heading = 1 if dx == 1 else 3 if dx == width - 1 else 2 if end[1] > start[1] else 0
        run = run + 1 if heading == previous else 1
        previous = heading
        best = max(best, run)
    return best


def _mouth(stage4: np.ndarray, cell: Cell, water_code: int, seed: int) -> tuple[str, Cell] | None:
    candidates = []
    for neighbor, _heading, name in v6._neighbors(cell, stage4.shape[1], stage4.shape[0]):
        if int(stage4[neighbor[1], neighbor[0]]) == water_code:
            candidates.append((v6._stable_hash(seed, neighbor[0], neighbor[1], 1201), name, neighbor))
    if not candidates:
        return None
    _key, name, water_cell = min(candidates)
    return name, water_cell


def _turn_sign(previous: int, current: int) -> int:
    if previous < 0 or previous == current:
        return 0
    return 1 if (current - previous) & 3 == 1 else -1


def _reconstruct(came: dict[tuple[int, ...], tuple[int, ...] | None], state: tuple[int, ...]) -> tuple[Cell, ...]:
    cells = []
    current: tuple[int, ...] | None = state
    while current is not None:
        cells.append((int(current[0]), int(current[1])))
        current = came[current]
    cells.reverse()
    return tuple(cells)


def _candidate_valid(
    cells: Sequence[Cell],
    *,
    stage4: np.ndarray,
    existing: set[Cell],
    water_code: int,
    termination: str,
    port: Cell | None,
    min_cells: int,
) -> bool:
    width, height = stage4.shape[1], stage4.shape[0]
    if len(cells) < min_cells or len(set(cells)) != len(cells):
        return False
    if _max_straight(cells, width) > 4 or v6._path_has_chord(cells, width):
        return False
    for start, end in zip(cells, cells[1:]):
        if not v6._is_cardinal(start, end, width):
            return False
    for index, cell in enumerate(cells):
        if not 0 <= cell[1] < height or int(stage4[cell[1], cell[0]]) == water_code:
            return False
        touching = {
            other
            for other, _heading, _name in v6._neighbors(cell, width, height)
            if other in existing
        }
        if termination == "coast":
            if touching:
                return False
        elif index == len(cells) - 1:
            if port is None or touching != {port}:
                return False
        elif touching:
            return False
    if termination == "coast":
        if _mouth(stage4, cells[-1], water_code, 0) is None:
            return False
        if any(_mouth(stage4, cell, water_code, 0) is not None for cell in cells[:-1]):
            return False
    elif termination == "river":
        if port is None or port not in existing or not v6._is_cardinal(cells[-1], port, width):
            return False
        if any(_mouth(stage4, cell, water_code, 0) is not None for cell in cells):
            return False
    else:
        return False
    return True


def _step_cost(
    state: tuple[int, ...],
    next_cell: Cell,
    next_heading: int,
    *,
    potential: np.ndarray,
    sink_distance: np.ndarray,
    stage4: np.ndarray,
    mountain_code: int,
    config: BasinHydrologyConfigV7,
) -> tuple[float, int, int]:
    x, y, heading, straight_run, _length, last_turn = state
    nx, ny = next_cell
    turn = _turn_sign(heading, next_heading)
    next_run = straight_run + 1 if heading == next_heading else 1
    delta_potential = float(potential[ny, nx] - potential[y, x])
    distance_delta = int(sink_distance[ny, nx]) - int(sink_distance[y, x])
    cost = 1.0 + max(0.0, delta_potential) * config.uphill_weight
    if distance_delta > 0:
        cost += config.away_from_sink_weight * distance_delta
    elif distance_delta == 0:
        cost += 0.05
    if heading >= 0 and next_heading != heading:
        cost += config.turn_penalty
    if turn and turn == last_turn:
        cost += config.same_turn_penalty
    if int(stage4[ny, nx]) == mountain_code:
        cost += config.mountain_entry_penalty
    return cost, next_run, turn


def _search_coast(
    source: Cell,
    *,
    stage4: np.ndarray,
    current_grid: Sequence[Sequence[int]],
    existing: set[Cell],
    potential: np.ndarray,
    distance_to_sea: np.ndarray,
    authority,
    seed: int,
    min_cells: int,
    config: BasinHydrologyConfigV7,
) -> _Route | None:
    height, width = stage4.shape
    terrain = authority.Terrain
    water_code, river_code = int(terrain.WATER), int(terrain.RIVER)
    sx, sy = source
    if int(distance_to_sea[sy, sx]) <= 1:
        return None
    if any(cell in existing for cell, _h, _n in v6._neighbors(source, width, height)):
        return None
    start = (sx, sy, -1, 0, 1, 0)
    costs = {start: 0.0}
    came = {start: None}
    initial_heuristic = max(0, int(distance_to_sea[sy, sx]) - 1)
    queue = [(float(initial_heuristic), 0.0, 0, start)]
    serial = 1
    expanded = 0
    best_terminal = None
    rotation = v6._stable_hash(seed, sx, sy, 1301) & 3
    headings = tuple((rotation + offset) & 3 for offset in range(4))
    while queue and expanded < config.max_search_states:
        priority, cost, _serial, state = heapq.heappop(queue)
        if cost != costs.get(state):
            continue
        if best_terminal is not None and priority >= best_terminal[0]:
            break
        expanded += 1
        x, y, heading, straight_run, length, _last_turn = state
        if length >= config.max_path_cells:
            continue
        for next_heading in headings:
            if heading >= 0 and next_heading == (heading + 2) & 3:
                continue
            dx, dy, _name = v6._CARDINAL[next_heading]
            nx, ny = (x + dx) % width, y + dy
            if not 0 <= ny < height:
                continue
            next_cell = (nx, ny)
            if int(current_grid[ny][nx]) in (water_code, river_code):
                continue
            if any(cell in existing for cell, _h, _n in v6._neighbors(next_cell, width, height)):
                continue
            step, next_run, turn = _step_cost(
                state,
                next_cell,
                next_heading,
                potential=potential,
                sink_distance=distance_to_sea,
                stage4=stage4,
                mountain_code=int(terrain.MOUNTAINS),
                config=config,
            )
            if next_run > 4:
                continue
            next_length = length + 1
            mouth = _mouth(stage4, next_cell, water_code, seed)
            if mouth is not None:
                if next_length < min_cells:
                    continue
                path = _reconstruct(came, state) + (next_cell,)
                if _candidate_valid(
                    path,
                    stage4=stage4,
                    existing=existing,
                    water_code=water_code,
                    termination="coast",
                    port=None,
                    min_cells=min_cells,
                ):
                    candidate = (cost + step, path, mouth[0])
                    if best_terminal is None or candidate < best_terminal:
                        best_terminal = candidate
                continue
            next_state = (nx, ny, next_heading, next_run, next_length, turn)
            next_cost = cost + step
            if next_cost >= costs.get(next_state, float("inf")) - 1e-12:
                continue
            costs[next_state] = next_cost
            came[next_state] = state
            heuristic = max(0, int(distance_to_sea[ny, nx]) - 1)
            heapq.heappush(queue, (next_cost + heuristic, next_cost, serial, next_state))
            serial += 1
    if best_terminal is None:
        return None
    cost, cells, mouth_direction = best_terminal
    return _Route(tuple(cells), "coast", None, mouth_direction, float(cost))


def _port_approaches(
    port: Cell,
    *,
    stage4: np.ndarray,
    existing: set[Cell],
    water_code: int,
) -> tuple[Cell, ...]:
    width, height = stage4.shape[1], stage4.shape[0]
    result = []
    for cell, _heading, _name in v6._neighbors(port, width, height):
        if cell in existing or int(stage4[cell[1], cell[0]]) == water_code:
            continue
        touching = {
            other
            for other, _h, _n in v6._neighbors(cell, width, height)
            if other in existing
        }
        if touching == {port} and _mouth(stage4, cell, water_code, 0) is None:
            result.append(cell)
    return tuple(result)


def _distance_to_targets(shape: tuple[int, int], targets: Sequence[Cell]) -> np.ndarray:
    return v6._distance_to_cells(shape, targets)


def _reachable_port_distances(
    port: Cell,
    *,
    stage4: np.ndarray,
    current_grid: Sequence[Sequence[int]],
    existing: set[Cell],
    water_code: int,
    river_code: int,
) -> dict[Cell, int]:
    """Cheap exact reachability filter for the stricter tributary corridor."""

    approaches = _port_approaches(port, stage4=stage4, existing=existing, water_code=water_code)
    distance = {cell: 0 for cell in approaches}
    queue = list(approaches)
    cursor = 0
    while cursor < len(queue):
        cell = queue[cursor]
        cursor += 1
        if distance[cell] >= 18:
            continue
        for neighbor, _heading, _name in v6._neighbors(cell, stage4.shape[1], stage4.shape[0]):
            if neighbor in distance:
                continue
            nx, ny = neighbor
            if int(current_grid[ny][nx]) in (water_code, river_code):
                continue
            if _mouth(stage4, neighbor, water_code, 0) is not None:
                continue
            touching = {
                other
                for other, _h, _n in v6._neighbors(neighbor, stage4.shape[1], stage4.shape[0])
                if other in existing
            }
            if touching:
                continue
            distance[neighbor] = distance[cell] + 1
            queue.append(neighbor)
    return distance


def _search_port(
    source: Cell,
    port: Cell,
    *,
    stage4: np.ndarray,
    current_grid: Sequence[Sequence[int]],
    existing: set[Cell],
    potential: np.ndarray,
    authority,
    seed: int,
    config: BasinHydrologyConfigV7,
) -> _Route | None:
    height, width = stage4.shape
    terrain = authority.Terrain
    water_code, river_code = int(terrain.WATER), int(terrain.RIVER)
    approaches = _port_approaches(port, stage4=stage4, existing=existing, water_code=water_code)
    if not approaches or float(potential[port[1], port[0]]) >= float(potential[source[1], source[0]]) - 0.01:
        return None
    sink_distance = _distance_to_targets(stage4.shape, approaches)
    sx, sy = source
    start = (sx, sy, -1, 0, 1, 0)
    costs = {start: 0.0}
    came = {start: None}
    heuristic0 = int(sink_distance[sy, sx]) * 1.0
    queue = [(heuristic0, 0.0, 0, start)]
    serial = 1
    expanded = 0
    rotation = v6._stable_hash(seed, sx, sy, port[0] * 97 + port[1] * 193 + 1409) & 3
    headings = tuple((rotation + offset) & 3 for offset in range(4))
    while queue and expanded < config.max_search_states:
        _priority, cost, _serial, state = heapq.heappop(queue)
        if cost != costs.get(state):
            continue
        expanded += 1
        x, y, heading, straight_run, length, _last_turn = state
        if length >= config.max_path_cells:
            continue
        for next_heading in headings:
            if heading >= 0 and next_heading == (heading + 2) & 3:
                continue
            dx, dy, _name = v6._CARDINAL[next_heading]
            nx, ny = (x + dx) % width, y + dy
            if not 0 <= ny < height:
                continue
            next_cell = (nx, ny)
            if int(current_grid[ny][nx]) in (water_code, river_code):
                continue
            if _mouth(stage4, next_cell, water_code, 0) is not None:
                continue
            touching = {
                other
                for other, _h, _n in v6._neighbors(next_cell, width, height)
                if other in existing
            }
            if touching and not (next_cell in approaches and touching == {port}):
                continue
            step, next_run, turn = _step_cost(
                state,
                next_cell,
                next_heading,
                potential=potential,
                sink_distance=sink_distance,
                stage4=stage4,
                mountain_code=int(terrain.MOUNTAINS),
                config=config,
            )
            if next_run > 4:
                continue
            next_length = length + 1
            if next_cell in approaches:
                if next_length < config.min_path_cells:
                    continue
                path = _reconstruct(came, state) + (next_cell,)
                if _candidate_valid(
                    path,
                    stage4=stage4,
                    existing=existing,
                    water_code=water_code,
                    termination="river",
                    port=port,
                    min_cells=config.min_path_cells,
                ):
                    return _Route(path, "river", port, None, float(cost + step))
                continue
            next_state = (nx, ny, next_heading, next_run, next_length, turn)
            next_cost = cost + step
            if next_cost >= costs.get(next_state, float("inf")) - 1e-12:
                continue
            costs[next_state] = next_cost
            came[next_state] = state
            heuristic = int(sink_distance[ny, nx]) * 1.0
            heapq.heappush(queue, (next_cost + heuristic, next_cost, serial, next_state))
            serial += 1
    return None


def _dedupe_edges(traces: Iterable[BasinTraceV7]) -> tuple[Edge, ...]:
    result = []
    seen = set()
    for trace in traces:
        for edge in trace.edges:
            key = frozenset(edge)
            if key not in seen:
                seen.add(key)
                result.append(edge)
    return tuple(result)


def _build_flow_hierarchy(
    traces: Sequence[BasinTraceV7],
    mouths_raw: Sequence[tuple[Cell, str, Cell, int]],
) -> tuple[tuple[FlowCellV7, ...], tuple[FlowEdgeV7, ...], tuple[ExplicitMouthV7, ...]]:
    downstream: dict[Cell, Cell | None] = {}
    cell_trunk: dict[Cell, int] = {}
    cell_role: dict[Cell, str] = {}
    for trace in traces:
        for cell in trace.cells:
            cell_trunk[cell] = trace.trunk_id
            if trace.kind == "primary":
                cell_role.setdefault(cell, "trunk")
            else:
                cell_role.setdefault(cell, "tributary")
        for start, end in trace.edges:
            downstream[start] = end
        if trace.termination == "coast":
            downstream[trace.cells[-1]] = None
    incoming: dict[Cell, list[Cell]] = {cell: [] for cell in downstream}
    for start, end in downstream.items():
        if end is not None:
            incoming.setdefault(end, []).append(start)
            downstream.setdefault(end, None)
    indegree = {cell: len(incoming.get(cell, ())) for cell in downstream}
    queue = sorted((cell for cell, degree in indegree.items() if degree == 0), key=lambda cell: (cell[1], cell[0]))
    area = {cell: 1 for cell in downstream}
    order = {cell: 1 for cell in downstream}
    processed = []
    while queue:
        cell = queue.pop(0)
        processed.append(cell)
        nxt = downstream[cell]
        if nxt is None:
            continue
        area[nxt] = area.get(nxt, 1) + area[cell]
        parents = incoming[nxt]
        ready_orders = [order[parent] for parent in parents if parent in order]
        indegree[nxt] -= 1
        if indegree[nxt] == 0:
            maximum = max(ready_orders, default=1)
            order[nxt] = maximum + 1 if ready_orders.count(maximum) >= 2 else maximum
            queue.append(nxt)
            queue.sort(key=lambda item: (item[1], item[0]))
    if len(processed) != len(downstream):
        raise AssertionError("directed river graph contains a cycle")
    flow_cells = []
    for cell in sorted(downstream, key=lambda item: (item[1], item[0])):
        role = cell_role.get(cell, "trunk")
        if len(incoming.get(cell, ())) >= 2:
            role = "confluence"
        if downstream[cell] is None:
            role = "mouth"
        flow_cells.append(
            FlowCellV7(cell, downstream[cell], int(area[cell]), int(order[cell]), role, int(cell_trunk[cell]))
        )
    flow_edges = []
    for trace in traces:
        for start, end in trace.edges:
            flow_edges.append(
                FlowEdgeV7(
                    start,
                    end,
                    int(area[start]),
                    int(order[start]),
                    trace.trunk_id,
                    "trunk" if trace.kind == "primary" else "tributary",
                )
            )
    mouths = tuple(
        ExplicitMouthV7(cell, water, direction, trunk_id, int(area[cell]), int(order[cell]))
        for cell, direction, water, trunk_id in mouths_raw
    )
    return tuple(flow_cells), tuple(flow_edges), mouths


def _primary_goal(desired: int, config: BasinHydrologyConfigV7) -> int:
    return max(
        config.min_primary_trunks,
        min(config.max_primary_trunks, int(round(desired * config.primary_fraction))),
    )


def generate_basin_hydrology_v7(
    authority,
    seed: int,
    land_mass: int = 1,
    temperature: int = 1,
    climate: int = 1,
    age: int = 1,
    *,
    config: BasinHydrologyConfigV7 | None = None,
) -> BasinHydrologyWorldV7:
    config = config or BasinHydrologyConfigV7()
    stage4, _rng = v6.build_stage4(authority, seed, land_mass, temperature, climate, age)
    stage4_array = np.asarray(stage4, dtype=np.int16)
    fields = v6.build_hydrology_fields(stage4, authority, int(seed))
    _height, potential, distance = fields.arrays()
    terrain = authority.Terrain
    river_code = int(terrain.RIVER)
    forest_code, jungle_code = int(terrain.FOREST), int(terrain.JUNGLE)
    water_code = int(terrain.WATER)
    grid = [list(row) for row in stage4]
    existing: set[Cell] = set()
    traces: list[BasinTraceV7] = []
    mouths_raw: list[tuple[Cell, str, Cell, int]] = []
    river_target = (int(land_mass) + int(climate)) * 2 + 6
    desired = river_target + 1
    primary_goal = _primary_goal(desired, config)

    # Pass 1: independent primary trunks.  Existing networks are exclusion
    # zones, never alternative sinks during this pass.
    trunk_id = 0
    while trunk_id < primary_goal:
        candidates = v6._source_candidates(stage4_array, grid, existing, fields, authority, int(seed))
        selected = None
        for source in candidates:
            minimum = config.primary_min_cells + (
                v6._stable_hash(seed, source[0], source[1], 1501) % (config.primary_extra_cells + 1)
            )
            route = _search_coast(
                source,
                stage4=stage4_array,
                current_grid=grid,
                existing=existing,
                potential=potential,
                distance_to_sea=distance,
                authority=authority,
                seed=int(seed),
                min_cells=minimum,
                config=config,
            )
            if route is not None:
                selected = source, route
                break
        if selected is None:
            break
        source, route = selected
        trace_id = len(traces)
        edges = tuple(zip(route.cells, route.cells[1:]))
        trace = BasinTraceV7(
            trace_id,
            "primary",
            trunk_id,
            route.cells,
            edges,
            "coast",
            None,
            route.mouth_direction,
            int(stage4_array[source[1], source[0]]),
            float(potential[source[1], source[0]]),
            float(potential[route.cells[-1][1], route.cells[-1][0]]),
            route.cost,
        )
        traces.append(trace)
        for x, y in route.cells:
            grid[y][x] = river_code
        existing.update(route.cells)
        mouth = _mouth(stage4_array, route.cells[-1], water_code, int(seed))
        if mouth is None:
            raise AssertionError("primary trunk lost its mouth")
        mouths_raw.append((route.cells[-1], mouth[0], mouth[1], trunk_id))
        trunk_id += 1

    ports: list[ReservedPortV7] = []
    for trace in traces:
        # Exclude the highland source and coastal mouth; every remaining cell
        # is reserved only if it owns a clean land-side approach.
        for cell in trace.cells[1:-1]:
            if _port_approaches(cell, stage4=stage4_array, existing=existing, water_code=water_code):
                ports.append(ReservedPortV7(cell, trace.trunk_id, "free", None))
    ports.sort(key=lambda port: (port.trunk_id, potential[port.cell[1], port.cell[0]], port.cell[1], port.cell[0]))

    # Pass 2: strongest available highland -> a deliberate free primary port.
    while len(traces) < desired:
        sources = v6._source_candidates(stage4_array, grid, existing, fields, authority, int(seed))
        free_ports = [port for port in ports if port.status == "free"]
        reachable_by_port = {
            (port.trunk_id, port.cell): _reachable_port_distances(
                port.cell,
                stage4=stage4_array,
                current_grid=grid,
                existing=existing,
                water_code=water_code,
                river_code=river_code,
            )
            for port in free_ports
        }
        pairs = []
        for source in sources:
            for port in free_ports:
                approaches = _port_approaches(
                    port.cell,
                    stage4=stage4_array,
                    existing=existing,
                    water_code=water_code,
                )
                if not approaches:
                    continue
                reachable = reachable_by_port[(port.trunk_id, port.cell)]
                if source not in reachable:
                    continue
                distance_hint = int(reachable[source])
                if distance_hint >= config.max_path_cells:
                    continue
                if float(potential[source[1], source[0]]) <= float(potential[port.cell[1], port.cell[0]]) + 0.01:
                    continue
                source_strength = float(potential[source[1], source[0]])
                pairs.append(
                    (
                        -source_strength,
                        abs(distance_hint - 7),
                        v6._stable_hash(seed, source[0], source[1], port.cell[0] * 83 + port.cell[1] * 179 + 1601),
                        source,
                        port,
                    )
                )
        pairs.sort(key=lambda item: item[:3])
        selected = None
        for _strength, _distance, _hash, source, port in pairs:
            route = _search_port(
                source,
                port.cell,
                stage4=stage4_array,
                current_grid=grid,
                existing=existing,
                potential=potential,
                authority=authority,
                seed=int(seed),
                config=config,
            )
            if route is not None:
                selected = source, port, route
                break
        if selected is None:
            break
        source, port, route = selected
        trace_id = len(traces)
        edges = tuple(list(zip(route.cells, route.cells[1:])) + [(route.cells[-1], port.cell)])
        traces.append(
            BasinTraceV7(
                trace_id,
                "tributary",
                port.trunk_id,
                route.cells,
                edges,
                "river",
                port.cell,
                None,
                int(stage4_array[source[1], source[0]]),
                float(potential[source[1], source[0]]),
                float(potential[port.cell[1], port.cell[0]]),
                route.cost,
            )
        )
        for x, y in route.cells:
            grid[y][x] = river_code
        existing.update(route.cells)
        ports = [
            replace(item, status="used", used_by_trace=trace_id)
            if item.cell == port.cell and item.trunk_id == port.trunk_id
            else item
            for item in ports
        ]

    # Preserve the stage-5 forest-to-jungle ecology rule at actual sinks.
    for trace in traces:
        sink = trace.attachment_port if trace.attachment_port is not None else trace.cells[-1]
        for neighbor, _heading, _name in v6._neighbors(sink, stage4_array.shape[1], stage4_array.shape[0]):
            nx, ny = neighbor
            if int(grid[ny][nx]) == forest_code:
                grid[ny][nx] = jungle_code

    flow_cells, flow_edges, mouths = _build_flow_hierarchy(traces, mouths_raw)
    world = BasinHydrologyWorldV7(
        stage4,
        tuple(tuple(int(value) for value in row) for row in grid),
        tuple(traces),
        _dedupe_edges(traces),
        flow_cells,
        flow_edges,
        mouths,
        tuple(ports),
        fields,
        river_target,
        desired,
        primary_goal,
        int(seed),
    )
    audit = validate_basin_world_v7(world, authority)
    if not audit.valid:
        raise AssertionError("invalid basin hydrology V7: " + "; ".join(audit.errors))
    return world


def validate_basin_world_v7(world: BasinHydrologyWorldV7, authority) -> BasinValidationV7:
    width, height = int(authority.MAP_W), int(authority.MAP_H)
    river_code, water_code = int(authority.Terrain.RIVER), int(authority.Terrain.WATER)
    stage4 = np.asarray(world.stage4_terrain, dtype=np.int16)
    terrain = np.asarray(world.terrain, dtype=np.int16)
    errors = []
    river_cells = {(int(x), int(y)) for y, x in np.argwhere(terrain == river_code)}
    recorded = {frozenset(edge) for edge in world.river_edges}
    raw = set()
    for x, y in river_cells:
        for dx, dy in ((1, 0), (0, 1)):
            other = ((x + dx) % width, y + dy)
            if other in river_cells:
                raw.add(frozenset(((x, y), other)))
    if raw != recorded:
        errors.append(f"raw/recorded mismatch missing={len(raw-recorded)} invented={len(recorded-raw)}")
    if len(recorded) != len(world.river_edges):
        errors.append("duplicate river edge")
    highland = {int(authority.Terrain.HILLS), int(authority.Terrain.MOUNTAINS)}
    seen_cells = set()
    max_straight = 0
    for trace in world.traces:
        if len(trace.cells) < 5 or len(set(trace.cells)) != len(trace.cells):
            errors.append(f"trace {trace.trace_id} invalid length/reuse")
        if trace.source_terrain not in highland:
            errors.append(f"trace {trace.trace_id} source not highland")
        if seen_cells.intersection(trace.cells):
            errors.append(f"trace {trace.trace_id} reuses older cells")
        seen_cells.update(trace.cells)
        if v6._path_has_chord(trace.cells, width):
            errors.append(f"trace {trace.trace_id} self-touch/chord")
        straight = _max_straight(trace.cells, width)
        max_straight = max(max_straight, straight)
        if straight > 4:
            errors.append(f"trace {trace.trace_id} has >4 straight run")
        if trace.source_potential <= trace.end_potential:
            errors.append(f"trace {trace.trace_id} does not descend")
        expected = list(zip(trace.cells, trace.cells[1:]))
        if trace.attachment_port is not None:
            expected.append((trace.cells[-1], trace.attachment_port))
        if tuple(expected) != trace.edges:
            errors.append(f"trace {trace.trace_id} ordered edges invalid")
        for start, end in trace.edges:
            if not v6._is_cardinal(start, end, width) or start not in river_cells or end not in river_cells:
                errors.append(f"trace {trace.trace_id} invalid edge")
        if trace.kind == "primary":
            if trace.termination != "coast" or trace.attachment_port is not None or trace.mouth_direction is None:
                errors.append(f"primary {trace.trace_id} has invalid mouth")
        elif trace.kind == "tributary":
            if trace.termination != "river" or trace.attachment_port is None:
                errors.append(f"tributary {trace.trace_id} has invalid port")
        else:
            errors.append(f"trace {trace.trace_id} invalid kind")

    flow_by_cell = {item.cell: item for item in world.flow_cells}
    if set(flow_by_cell) != river_cells:
        errors.append("flow cell coverage mismatch")
    downstream = {item.cell: item.downstream for item in world.flow_cells}
    for edge in world.flow_edges:
        if downstream.get(edge.start) != edge.end:
            errors.append("flow edge disagrees with cell downstream")
        start, end = flow_by_cell.get(edge.start), flow_by_cell.get(edge.end)
        if start is None or end is None:
            errors.append("flow edge missing metadata endpoint")
        elif end.upstream_area <= start.upstream_area or end.strahler < start.strahler:
            errors.append("flow accumulation/Strahler is not monotonic")
    # Directed cycle audit.
    for origin in river_cells:
        visited = set()
        current = origin
        while current is not None:
            if current in visited:
                errors.append("directed flow cycle")
                break
            visited.add(current)
            current = downstream.get(current)

    mouth_cells = {mouth.river_cell for mouth in world.mouths}
    expected_mouths = {trace.cells[-1] for trace in world.traces if trace.kind == "primary"}
    if mouth_cells != expected_mouths:
        errors.append("explicit mouth coverage mismatch")
    for mouth in world.mouths:
        if int(stage4[mouth.water_cell[1], mouth.water_cell[0]]) != water_code:
            errors.append("mouth water port is not WATER")
        if not v6._is_cardinal(mouth.river_cell, mouth.water_cell, width):
            errors.append("mouth port is not cardinal")
        cell_meta = flow_by_cell.get(mouth.river_cell)
        if cell_meta is None or mouth.upstream_area != cell_meta.upstream_area or mouth.strahler != cell_meta.strahler:
            errors.append("mouth hierarchy metadata mismatch")

    allowed_nonriver = {(int(authority.Terrain.FOREST), int(authority.Terrain.JUNGLE))}
    for y in range(height):
        for x in range(width):
            before, after = int(stage4[y, x]), int(terrain[y, x])
            if after == river_code:
                if before == water_code:
                    errors.append("river overwrote water")
            elif before != after and (before, after) not in allowed_nonriver:
                errors.append(f"illegal terrain mutation {before}->{after}")

    return BasinValidationV7(
        not errors,
        tuple(errors),
        len(river_cells),
        len(recorded),
        len(raw),
        sum(trace.kind == "primary" for trace in world.traces),
        sum(trace.kind == "tributary" for trace in world.traces),
        sum(trace.attachment_port is not None for trace in world.traces),
        max_straight,
    )


__all__ = [
    "BasinHydrologyConfigV7",
    "BasinHydrologyWorldV7",
    "BasinTraceV7",
    "BasinValidationV7",
    "ExplicitMouthV7",
    "FlowCellV7",
    "FlowEdgeV7",
    "ReservedPortV7",
    "generate_basin_hydrology_v7",
    "validate_basin_world_v7",
]
