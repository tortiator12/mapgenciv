"""Corridor-first continuous hydrology pilot for new derivative worlds.

This module does not consume or modify a legacy river graph.  It starts from
an exact Civ-I Stage-4 terrain, routes trunks and tributaries on a horizontally
periodic 6x subcell field, smooths those world-space centerlines, and only then
rasterizes the touched Civ cells and ordered gameplay edges.

The pilot is deliberately isolated.  C:\\Fraps, legacy snapshots, V7 and the
V10 fallback are read-only authorities; no production integration occurs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import heapq
import math
from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image

from .modern_hydrology_v6 import HydrologyFields, _stable_hash, build_hydrology_fields, build_stage4
from . import river_presentation_v9 as v9
from .terminal_aware_hydrology_v27 import (
    RiverTerminalSpecV27,
    SourceTerminalSpecV27,
    TerminalReservationV27,
    audit_terminal_spec_v27,
    build_round_spring_source_v27,
    reserve_terminal_before_rasterization_v27,
)


Cell = tuple[int, int]
FineCell = tuple[int, int]
Point = tuple[float, float]
Edge = tuple[Cell, Cell]

_DIR8 = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)


@dataclass(frozen=True)
class ContinuousHydrologyConfigV11:
    subcells_per_cell: int = 6
    primary_goal: int = 3
    tributary_goal: int = 3
    max_search_states: int = 60_000
    min_primary_cells: int = 4
    min_tributary_cells: int = 3
    max_cardinal_fine_run: int = 6
    terminal_aware: bool = False
    mouth_quality_first: bool = False
    tributary_min_parent_progress: float = 0.0
    tributary_max_parent_progress: float = 1.0
    max_tributaries_per_primary: int = 0
    tributary_min_alignment: float = -1.0
    tributary_min_source_parent_distance: int = 0

    def __post_init__(self) -> None:
        if not 4 <= self.subcells_per_cell <= 8:
            raise ValueError("V11 subcell scale must stay in the 4..8 pilot band")
        if self.primary_goal < 1 or self.tributary_goal < 1:
            raise ValueError("V11 pilot requires trunks and tributaries")
        if self.max_search_states <= 0:
            raise ValueError("max_search_states must be positive")
        if not 0.0 <= self.tributary_min_parent_progress < self.tributary_max_parent_progress <= 1.0:
            raise ValueError("tributary parent progress must be an ordered subset of 0..1")
        if self.max_tributaries_per_primary < 0:
            raise ValueError("max_tributaries_per_primary must be nonnegative")
        if not -1.0 <= self.tributary_min_alignment <= 1.0:
            raise ValueError("tributary_min_alignment must be in -1..1")
        if self.tributary_min_source_parent_distance < 0:
            raise ValueError("tributary_min_source_parent_distance must be nonnegative")


@dataclass(frozen=True)
class FlowSampleV11:
    point: Point
    upstream_area: float
    strahler: int
    width_px: float
    potential: float


@dataclass(frozen=True)
class ContinuousTraceV11:
    trace_id: int
    kind: str
    parent_trace: int | None
    attachment_point: Point | None
    source_cell: Cell
    termination: str
    mouth_water_cell: Cell | None
    shoreline_point: Point | None
    fine_path: tuple[FineCell, ...]
    samples: tuple[FlowSampleV11, ...]
    raster_cells: tuple[Cell, ...]
    raster_edges: tuple[Edge, ...]
    uphill_fraction: float
    max_cardinal_run: int
    terminal_spec: RiverTerminalSpecV27 | None = None
    source_spec: SourceTerminalSpecV27 | None = None

    @property
    def points(self) -> tuple[Point, ...]:
        return tuple(sample.point for sample in self.samples)


@dataclass(frozen=True)
class ContinuousMouthV11:
    trace_id: int
    river_cell: Cell
    water_cell: Cell
    shoreline_point: Point
    direction: Point
    normal: Point
    start_width: float
    end_width: float
    depth: float
    asymmetry: float
    upstream_area: float
    strahler: int


@dataclass(frozen=True)
class ContinuousHydrologyWorldV11:
    stage4_terrain: tuple[tuple[int, ...], ...]
    terrain: tuple[tuple[int, ...], ...]
    traces: tuple[ContinuousTraceV11, ...]
    river_cells: tuple[Cell, ...]
    river_edges: tuple[Edge, ...]
    mouths: tuple[ContinuousMouthV11, ...]
    fields: HydrologyFields
    water_mask: tuple[tuple[bool, ...], ...]
    tile_px: int
    world_width: int
    world_height: int
    seed: int
    subcells_per_cell: int
    derivative_label: str

    @property
    def world_width_px(self) -> int:
        return self.world_width * self.tile_px

    def snapshot_extension(self) -> dict[str, Any]:
        terminal_aware = any(trace.terminal_spec is not None for trace in self.traces)
        return {
            "schema": (
                "project1991.continuous-hydrology/v27"
                if terminal_aware
                else "project1991.continuous-hydrology/v11"
            ),
            "generator": (
                "modern-v27-terminal-aware"
                if terminal_aware
                else "modern-v11-corridor-first"
            ),
            "derivative": True,
            "subcells_per_cell": self.subcells_per_cell,
            "river_cells": [[x, y] for x, y in self.river_cells],
            "river_edges": [[[a[0], a[1]], [b[0], b[1]]] for a, b in self.river_edges],
            "traces": [
                {
                    "trace_id": trace.trace_id,
                    "kind": trace.kind,
                    "parent_trace": trace.parent_trace,
                    "attachment_point": list(trace.attachment_point) if trace.attachment_point else None,
                    "source_cell": list(trace.source_cell),
                    "termination": trace.termination,
                    "mouth_water_cell": list(trace.mouth_water_cell) if trace.mouth_water_cell else None,
                    "points": [[round(sample.point[0], 7), round(sample.point[1], 7)] for sample in trace.samples],
                    "upstream_area": [round(sample.upstream_area, 5) for sample in trace.samples],
                    "strahler": [sample.strahler for sample in trace.samples],
                    "width_px": [round(sample.width_px, 5) for sample in trace.samples],
                    "raster_cells": [[x, y] for x, y in trace.raster_cells],
                    "terminal": asdict(trace.terminal_spec) if trace.terminal_spec is not None else None,
                    "source_terminal": asdict(trace.source_spec) if trace.source_spec is not None else None,
                }
                for trace in self.traces
            ],
            "mouths": [
                {
                    "trace_id": mouth.trace_id,
                    "river_cell": list(mouth.river_cell),
                    "water_cell": list(mouth.water_cell),
                    "shoreline_point": [round(mouth.shoreline_point[0], 7), round(mouth.shoreline_point[1], 7)],
                    "upstream_area": round(mouth.upstream_area, 5),
                    "strahler": mouth.strahler,
                }
                for mouth in self.mouths
            ],
        }


@dataclass(frozen=True)
class ContinuousAuditV11:
    valid: bool
    errors: tuple[str, ...]
    traces: int
    primaries: int
    tributaries: int
    mouths: int
    river_cells: int
    recorded_edges: int
    raw_adjacencies: int
    cycles: int
    fine_self_touches: int
    raster_authority_mismatches: int
    max_cardinal_fine_run: int
    mean_uphill_fraction: float
    max_uphill_fraction: float
    confluences: int


@dataclass
class _TraceDraft:
    kind: str
    parent_trace: int | None
    source_cell: Cell
    fine_path: list[FineCell]
    points: list[Point]
    mouth_water_cell: Cell | None = None
    shoreline_point: Point | None = None
    attachment_point: Point | None = None
    raster_cells: list[Cell] | None = None
    raster_edges: list[Edge] | None = None
    terminal_spec: RiverTerminalSpecV27 | None = None
    terminal_tail_start: int | None = None


@dataclass(frozen=True)
class _AttachmentOption:
    parent_trace: int
    target_cell: Cell
    approach_cell: Cell
    target_point: Point
    target_fine: FineCell
    approach_fine: FineCell
    parent_progress: float = 0.0
    merge_alignment: float = 0.0


def _upsample_field(field: np.ndarray, scale: int, world_width: int) -> np.ndarray:
    height, width = field.shape
    xs = (np.arange(width * scale, dtype=np.float64) + 0.5) / scale - 0.5
    ys = (np.arange(height * scale, dtype=np.float64) + 0.5) / scale - 0.5
    x0, y0 = np.floor(xs).astype(np.int64), np.floor(ys).astype(np.int64)
    tx, ty = xs - x0, ys - y0
    xa, xb = x0 % world_width, (x0 + 1) % world_width
    ya, yb = np.clip(y0, 0, height - 1), np.clip(y0 + 1, 0, height - 1)
    top = field[ya[:, None], xa[None, :]] * (1.0 - tx[None, :]) + field[ya[:, None], xb[None, :]] * tx[None, :]
    bottom = field[yb[:, None], xa[None, :]] * (1.0 - tx[None, :]) + field[yb[:, None], xb[None, :]] * tx[None, :]
    return top * (1.0 - ty[:, None]) + bottom * ty[:, None]


def _fine_fields(stage4: np.ndarray, fields: HydrologyFields, seed: int, scale: int, water_code: int):
    height, potential, distance = fields.arrays()
    fine_height = _upsample_field(height, scale, stage4.shape[1])
    fine_potential = _upsample_field(potential, scale, stage4.shape[1])
    fine_distance = _upsample_field(distance.astype(np.float64), scale, stage4.shape[1])
    yy, xx = np.mgrid[0 : stage4.shape[0] * scale, 0 : stage4.shape[1] * scale]
    x = (xx + 0.5) / scale
    y = (yy + 0.5) / scale
    phase1 = _stable_hash(seed, 0, 0, 2303) / 2**32 * math.tau
    phase2 = _stable_hash(seed, 0, 0, 2311) / 2**32 * math.tau
    noise = (
        np.sin(math.tau * (11.0 * x / stage4.shape[1] + y / 4.9) + phase1) * 0.61
        + np.cos(math.tau * (17.0 * x / stage4.shape[1] - y / 7.1) + phase2) * 0.39
    )
    fine_potential = fine_potential + noise * 0.038
    fine_height = fine_height + noise * 0.025
    land = np.repeat(np.repeat(stage4 != water_code, scale, axis=0), scale, axis=1)
    return fine_height.astype(np.float32), fine_potential.astype(np.float32), fine_distance.astype(np.float32), land


def _coast_goals(stage4: np.ndarray, water_code: int, scale: int) -> dict[FineCell, tuple[Cell, tuple[int, int], float]]:
    height, width = stage4.shape
    goals: dict[FineCell, tuple[Cell, tuple[int, int], float]] = {}
    directions = ((0, -1), (1, 0), (0, 1), (-1, 0))
    for y in range(height):
        for x in range(width):
            if int(stage4[y, x]) == water_code:
                continue
            for dx, dy in directions:
                nx, ny = (x + dx) % width, y + dy
                if not 0 <= ny < height or int(stage4[ny, nx]) != water_code:
                    continue
                for offset in range(1, scale - 1):
                    fraction = (offset + 0.5) / scale
                    if dx == 1:
                        fine = ((x + 1) * scale - 1, y * scale + offset)
                    elif dx == -1:
                        fine = (x * scale, y * scale + offset)
                    elif dy == 1:
                        fine = (x * scale + offset, (y + 1) * scale - 1)
                    else:
                        fine = (x * scale + offset, y * scale)
                    key = ((fine[0] % (width * scale)), fine[1])
                    candidate = ((nx, ny), (dx, dy), fraction)
                    prior = goals.get(key)
                    if prior is None or candidate < prior:
                        goals[key] = candidate
    return goals


def _source_candidates(
    stage4: np.ndarray,
    fields: HydrologyFields,
    authority,
    seed: int,
    *,
    min_coast_distance: int = 4,
) -> list[Cell]:
    _height, potential, distance = fields.arrays()
    terrain = authority.Terrain
    candidates = []
    for y in range(2, stage4.shape[0] - 2):
        for x in range(stage4.shape[1]):
            code = int(stage4[y, x])
            if code not in (int(terrain.HILLS), int(terrain.MOUNTAINS)) or int(distance[y, x]) < min_coast_distance:
                continue
            bonus = 0.28 if code == int(terrain.MOUNTAINS) else 0.12
            jitter = _stable_hash(seed, x, y, 2327) / 2**32 * 0.08
            candidates.append((-(float(potential[y, x]) + bonus + jitter), y, x))
    candidates.sort()
    return [(x, y) for _score, y, x in candidates]


def _source_fine(cell: Cell, fine_potential: np.ndarray, scale: int, seed: int) -> FineCell:
    x, y = cell
    choices = []
    for oy in range(1, scale - 1):
        for ox in range(1, scale - 1):
            sx, sy = x * scale + ox, y * scale + oy
            score = -float(fine_potential[sy, sx])
            choices.append((score, _stable_hash(seed, sx, sy, 2333), sx, sy))
    _score, _hash, sx, sy = min(choices)
    return sx, sy


def _octile(a: FineCell, b: FineCell, width: int) -> float:
    dx_raw = abs(a[0] - b[0])
    dx = min(dx_raw, width - dx_raw)
    dy = abs(a[1] - b[1])
    diagonal = min(dx, dy)
    return max(dx, dy) + (math.sqrt(2.0) - 1.0) * diagonal


def _reconstruct_fine(came: dict[tuple[int, int, int, int], tuple[int, int, int, int] | None], state) -> list[FineCell]:
    result = []
    current = state
    while current is not None:
        result.append((current[0], current[1]))
        current = came[current]
    result.reverse()
    return result


def _astar_fine(
    start: FineCell,
    *,
    fine_potential: np.ndarray,
    fine_distance: np.ndarray,
    land: np.ndarray,
    blocked: np.ndarray,
    coast_goals: dict[FineCell, tuple[Cell, tuple[int, int], float]] | None,
    target: FineCell | None,
    scale: int,
    max_states: int,
) -> list[FineCell] | None:
    height, width = land.shape
    if blocked[start[1], start[0]] or not land[start[1], start[0]]:
        return None
    start_state = (start[0], start[1], 8, 0)
    best = {start_state: 0.0}
    came = {start_state: None}
    counter = 0
    heuristic = (
        # Every move costs at least ~1.0, so 0.90 remains conservative while
        # avoiding the near-Dijkstra explosion around a single merge port.
        (lambda cell: _octile(cell, target, width) * 0.90)
        if target is not None
        else (lambda cell: max(0.0, float(fine_distance[cell[1], cell[0]]) - 0.8) * scale * 0.34)
    )
    heap = [(heuristic(start), 0.0, 0, start_state)]
    expanded = 0
    while heap and expanded < max_states:
        _priority, cost, _serial, state = heapq.heappop(heap)
        if cost != best.get(state):
            continue
        x, y, previous, run = state
        expanded += 1
        cell = (x, y)
        if target is not None:
            if cell == target and expanded > scale * 2:
                return _reconstruct_fine(came, state)
        elif coast_goals is not None and cell in coast_goals and expanded > scale * 4:
            return _reconstruct_fine(came, state)
        for heading, (dx, dy) in enumerate(_DIR8):
            if previous < 8 and (heading - previous) % 8 == 4:
                continue
            nx, ny = (x + dx) % width, y + dy
            if not 0 <= ny < height or not land[ny, nx]:
                continue
            is_goal = (target is not None and (nx, ny) == target) or (coast_goals is not None and (nx, ny) in coast_goals)
            if blocked[ny, nx] and not is_goal:
                continue
            new_run = run + 1 if heading == previous else 1
            length = math.sqrt(2.0) if dx and dy else 1.0
            rise = max(0.0, float(fine_potential[ny, nx] - fine_potential[y, x]))
            away = max(0.0, float(fine_distance[ny, nx] - fine_distance[y, x]))
            step = length + rise * 24.0 + away * 1.15
            if previous < 8:
                delta = min((heading - previous) % 8, (previous - heading) % 8)
                step += (0.025, 0.045, 0.16, 0.52, 5.0)[min(delta, 4)]
            if new_run > 3:
                step += (new_run - 3) ** 2 * (0.23 if dx == 0 or dy == 0 else 0.15)
            if dx == 0 or dy == 0:
                step += 0.045
            step += max(0.0, float(fine_potential[ny, nx])) * 0.018
            next_state = (nx, ny, heading, min(new_run, 8))
            next_cost = cost + step
            if next_cost + 1e-12 >= best.get(next_state, math.inf):
                continue
            best[next_state] = next_cost
            came[next_state] = state
            counter += 1
            heapq.heappush(heap, (next_cost + heuristic((nx, ny)), next_cost, counter, next_state))
    return None


def _fine_self_touch(path: Sequence[FineCell], world_width: int) -> bool:
    locations: dict[FineCell, int] = {}
    for index, cell in enumerate(path):
        if cell in locations:
            return True
        locations[cell] = index
    for index, (x, y) in enumerate(path):
        for dx, dy in _DIR8:
            other = ((x + dx) % world_width, y + dy)
            other_index = locations.get(other)
            if other_index is not None and abs(other_index - index) > 2:
                return True
    return False


def _max_heading_run(path: Sequence[FineCell], world_width: int) -> int:
    best = run = 0
    previous = None
    for first, second in zip(path, path[1:]):
        dx = (second[0] - first[0]) % world_width
        if dx == world_width - 1:
            dx = -1
        heading = (dx, second[1] - first[1])
        run = run + 1 if heading == previous else 1
        previous = heading
        best = max(best, run)
    return best


def _unwrap_fine(path: Sequence[FineCell], scale: int, fine_width: int) -> list[Point]:
    if not path:
        return []
    current_x = path[0][0]
    result = [((current_x + 0.5) / scale, (path[0][1] + 0.5) / scale)]
    for previous, current in zip(path, path[1:]):
        dx = (current[0] - previous[0]) % fine_width
        if dx == 1:
            current_x += 1
        elif dx == fine_width - 1:
            current_x -= 1
        else:
            current_x += current[0] - previous[0]
        result.append(((current_x + 0.5) / scale, (current[1] + 0.5) / scale))
    return result


def _shoreline_from_goal(last_point: Point, goal_info, scale: int) -> tuple[Point, Cell]:
    water_cell, (dx, dy), fraction = goal_info
    cell_x, cell_y = math.floor(last_point[0]), math.floor(last_point[1])
    if dx == 1:
        point = (cell_x + 1.0, cell_y + fraction)
    elif dx == -1:
        point = (float(cell_x), cell_y + fraction)
    elif dy == 1:
        point = (cell_x + fraction, cell_y + 1.0)
    else:
        point = (cell_x + fraction, float(cell_y))
    return point, water_cell


def _chaikin(points: Sequence[Point], iterations: int = 2) -> list[Point]:
    result = list(points)
    for _ in range(iterations):
        if len(result) < 3:
            break
        refined = [result[0]]
        for first, second in zip(result, result[1:]):
            refined.append((first[0] * 0.75 + second[0] * 0.25, first[1] * 0.75 + second[1] * 0.25))
            refined.append((first[0] * 0.25 + second[0] * 0.75, first[1] * 0.25 + second[1] * 0.75))
        refined.append(result[-1])
        result = refined
    return result


def _points_stay_land(points: Sequence[Point], stage4: np.ndarray, water_code: int, *, allow_last_boundary: bool) -> bool:
    limit = len(points) - 1 if allow_last_boundary else len(points)
    for point in points[:limit]:
        x, y = int(math.floor(point[0])) % stage4.shape[1], int(math.floor(point[1]))
        if not 0 <= y < stage4.shape[0] or int(stage4[y, x]) == water_code:
            return False
    return True


def _smooth_land_path(points: Sequence[Point], stage4: np.ndarray, water_code: int, *, boundary_end: bool) -> list[Point]:
    for iterations in (2, 1, 0):
        candidate = _chaikin(points, iterations)
        if _points_stay_land(candidate, stage4, water_code, allow_last_boundary=boundary_end):
            return candidate
    return list(points)


def _wrapped_cell_distance(a: Cell, b: Cell, width: int) -> int:
    dx = min((a[0] - b[0]) % width, (b[0] - a[0]) % width)
    return int(dx + abs(a[1] - b[1]))


def _cardinal(a: Cell, b: Cell, width: int) -> bool:
    return _wrapped_cell_distance(a, b, width) == 1


def _insert_diagonal_bridge(a: Cell, b: Cell, stage4: np.ndarray, water_code: int, potential: np.ndarray) -> Cell | None:
    width = stage4.shape[1]
    dx = (b[0] - a[0]) % width
    signed_dx = 1 if dx == 1 else -1 if dx == width - 1 else 0
    if signed_dx == 0 or abs(b[1] - a[1]) != 1:
        return None
    choices = (((a[0] + signed_dx) % width, a[1]), (a[0], b[1]))
    land = [cell for cell in choices if int(stage4[cell[1], cell[0]]) != water_code]
    if not land:
        return None
    return min(land, key=lambda cell: (float(potential[cell[1], cell[0]]), cell[1], cell[0]))


def rasterize_centerline_v11(
    points: Sequence[Point],
    stage4_terrain: Sequence[Sequence[int]],
    fields: HydrologyFields,
    water_code: int,
    *,
    boundary_end: bool,
) -> tuple[tuple[Cell, ...], tuple[Edge, ...]]:
    stage4 = np.asarray(stage4_terrain, dtype=np.int16)
    _height, potential, _distance = fields.arrays()
    sampled = []
    for segment_index, (first, second) in enumerate(zip(points, points[1:])):
        distance = math.hypot(second[0] - first[0], second[1] - first[1])
        count = max(2, int(math.ceil(distance / 0.035)))
        endpoint = not (boundary_end and segment_index == len(points) - 2)
        for t in np.linspace(0.0, 1.0, count, endpoint=endpoint):
            x = (first[0] + (second[0] - first[0]) * float(t)) % stage4.shape[1]
            y = first[1] + (second[1] - first[1]) * float(t)
            cell = (int(math.floor(x)) % stage4.shape[1], min(stage4.shape[0] - 1, max(0, int(math.floor(y)))))
            if int(stage4[cell[1], cell[0]]) == water_code:
                continue
            if not sampled or sampled[-1] != cell:
                sampled.append(cell)
    if not boundary_end and points:
        final = (int(math.floor(points[-1][0])) % stage4.shape[1], int(math.floor(points[-1][1])))
        if int(stage4[final[1], final[0]]) != water_code and (not sampled or sampled[-1] != final):
            sampled.append(final)
    bridged = []
    for cell in sampled:
        if bridged and not _cardinal(bridged[-1], cell, stage4.shape[1]) and bridged[-1] != cell:
            bridge = _insert_diagonal_bridge(bridged[-1], cell, stage4, water_code, potential)
            if bridge is None:
                raise ValueError("continuous segment skipped non-cardinal raster cells")
            if bridge != bridged[-1]:
                bridged.append(bridge)
        if not bridged or bridged[-1] != cell:
            bridged.append(cell)
    if len(set(bridged)) != len(bridged):
        raise ValueError("continuous centerline revisits a Civ cell")
    edges = tuple((a, b) for a, b in zip(bridged, bridged[1:]))
    return tuple(bridged), edges


def _raw_adjacencies(cells: Iterable[Cell], width: int) -> set[Edge]:
    cells = set(cells)
    edges = set()
    for x, y in cells:
        for dx, dy in ((1, 0), (0, 1)):
            neighbor = ((x + dx) % width, y + dy)
            if neighbor in cells:
                edges.add(tuple(sorted(((x, y), neighbor))))
    return edges


def _expected_undirected(edges: Iterable[Edge]) -> set[Edge]:
    return {tuple(sorted(edge)) for edge in edges}


def _dilate_fine(path_nodes: Iterable[FineCell], shape: tuple[int, int], radius: int = 2) -> np.ndarray:
    height, width = shape
    mask = np.zeros(shape, dtype=bool)
    for x, y in path_nodes:
        for dy in range(-radius, radius + 1):
            ny = y + dy
            if not 0 <= ny < height:
                continue
            for dx in range(-radius, radius + 1):
                mask[ny, (x + dx) % width] = True
    return mask


def _coarse_conflicts(candidate_cells: Sequence[Cell], existing_cells: set[Cell], expected_edges: set[Edge], width: int) -> bool:
    union = set(candidate_cells) | existing_cells
    return _raw_adjacencies(union, width) != expected_edges


def _signed_wrapped_delta(start: int, end: int, width: int) -> int:
    delta = (end - start) % width
    return delta - width if delta > width // 2 else delta


def _line_fine(start: FineCell, end: FineCell, fine_width: int) -> list[FineCell]:
    """Deterministic 8-connected line, with x unwrapped across the seam."""

    dx = _signed_wrapped_delta(start[0], end[0], fine_width)
    target_x = start[0] + dx
    x0, y0 = start
    x1, y1 = target_x, end[1]
    steps = max(abs(x1 - x0), abs(y1 - y0))
    if steps == 0:
        return [start]
    result = []
    for index in range(steps + 1):
        t = index / steps
        cell = (int(round(x0 + (x1 - x0) * t)) % fine_width, int(round(y0 + (y1 - y0) * t)))
        if not result or result[-1] != cell:
            result.append(cell)
    return result


def _fine_cell_center_v27(cell: Cell, scale: int) -> FineCell:
    return cell[0] * scale + scale // 2, cell[1] * scale + scale // 2


def _terminal_boundary_fine_v27(
    reservation: TerminalReservationV27,
    scale: int,
    fine_width: int,
) -> FineCell:
    mouth_x, mouth_y = reservation.spec.river_cell
    port = reservation.spec.exit_port
    middle = scale // 2
    if port == "east":
        return ((mouth_x + 1) * scale - 1) % fine_width, mouth_y * scale + middle
    if port == "west":
        return (mouth_x * scale) % fine_width, mouth_y * scale + middle
    if port == "south":
        return mouth_x * scale + middle, (mouth_y + 1) * scale - 1
    if port == "north":
        return mouth_x * scale + middle, mouth_y * scale
    raise ValueError(f"V27 terminal requires a cardinal exit, got {port!r}")


def _terminal_fine_tail_v27(
    reservation: TerminalReservationV27,
    scale: int,
    fine_width: int,
) -> list[FineCell]:
    """Fine route through the already-owned coarse terminal corridor."""

    centers = [_fine_cell_center_v27(cell, scale) for cell in reservation.route_tail]
    centers.append(_terminal_boundary_fine_v27(reservation, scale, fine_width))
    result: list[FineCell] = []
    for first, second in zip(centers, centers[1:]):
        segment = _line_fine(first, second, fine_width)
        if result and segment and result[-1] == segment[0]:
            segment = segment[1:]
        result.extend(segment)
    return result


def _block_reserved_coarse_v27(
    blocked: np.ndarray,
    cells: Iterable[Cell],
    scale: int,
) -> None:
    """Keep routes out of terminal ownership allocated to other trunks."""

    height, width = blocked.shape
    coarse_width = width // scale
    for x, y in cells:
        x = int(x) % coarse_width
        y = int(y)
        if not 0 <= y < height // scale:
            continue
        blocked[y * scale : (y + 1) * scale, x * scale : (x + 1) * scale] = True


def _align_terminal_point_x_v27(point: Point, anchor_x: float, width: int) -> Point:
    return point[0] + round((anchor_x - point[0]) / float(width)) * float(width), point[1]


def _route_terminal_primary_v27(
    *,
    stage4_tuple: Sequence[Sequence[int]],
    stage4: np.ndarray,
    fields: HydrologyFields,
    water_code: int,
    source_cell: Cell,
    source: FineCell,
    seed: int,
    tile_px: int,
    scale: int,
    config: ContinuousHydrologyConfigV11,
    fine_potential: np.ndarray,
    fine_distance: np.ndarray,
    land: np.ndarray,
    base_blocked: np.ndarray,
    occupied_cells: set[Cell],
    expected_edges: set[Edge],
    reserved_terminal_cells: set[Cell],
    relief_codes: tuple[int, int],
) -> tuple[
    TerminalReservationV27,
    list[FineCell],
    list[Point],
    Point,
    Cell,
    int,
    tuple[Cell, ...],
    tuple[Edge, ...],
    set[Edge],
] | None:
    """Try successive pre-raster coast reservations for one source.

    A failed nearest corridor is not evidence that the source is unusable.
    Rejected mouth cells are added to the deterministic reservation query and
    the next ranked corridor is attempted, while already accepted ownership
    remains immutable.
    """

    fine_width = stage4.shape[1] * scale
    rejected_mouths: set[Cell] = set()
    for _attempt in range(32 if config.mouth_quality_first else 18):
        try:
            reservation_kwargs = dict(
                stage4_terrain=stage4_tuple,
                water_code=water_code,
                source_id=f"modern-v27-seed-{seed}-source-{source_cell[0]}-{source_cell[1]}",
                width_px=tile_px * 0.18,
                stream_order=1,
                seed=seed,
                blocked_cells=occupied_cells | reserved_terminal_cells | rejected_mouths,
                preferred_near=source_cell,
            )
            if config.mouth_quality_first:
                from .mouth_first_terminal_v53 import reserve_mouth_first_terminal_v53

                reservation = reserve_mouth_first_terminal_v53(
                    relief_codes=relief_codes,
                    **reservation_kwargs,
                )
            else:
                reservation = reserve_terminal_before_rasterization_v27(**reservation_kwargs)
        except ValueError:
            return None
        rejected_mouths.add(reservation.spec.river_cell)
        target = _fine_cell_center_v27(reservation.route_tail[0], scale)
        blocked = base_blocked.copy()
        current_forbidden = set(reservation.reserved_cells) - {reservation.route_tail[0]}
        _block_reserved_coarse_v27(blocked, reserved_terminal_cells | current_forbidden, scale)
        blocked[target[1], target[0] % fine_width] = False
        prefix = _astar_fine(
            source,
            fine_potential=fine_potential,
            fine_distance=fine_distance,
            land=land,
            blocked=blocked,
            coast_goals=None,
            target=(target[0] % fine_width, target[1]),
            scale=scale,
            max_states=config.max_search_states,
        )
        if prefix is None or len(prefix) < scale * 2 or _fine_self_touch(prefix, fine_width):
            continue
        if _max_heading_run(prefix, fine_width) > config.max_cardinal_fine_run:
            continue
        terminal_tail = _terminal_fine_tail_v27(reservation, scale, fine_width)
        path = [*prefix, *terminal_tail[1:]]
        terminal_tail_start = len(prefix) - 1
        if _fine_self_touch(path, fine_width):
            continue
        prefix_points = _unwrap_fine(prefix, scale, fine_width)
        smoothed_prefix = _smooth_land_path(prefix_points, stage4, water_code, boundary_end=False)
        tail_points = _unwrap_fine(path[terminal_tail_start:], scale, fine_width)
        if smoothed_prefix and tail_points:
            shift = round((smoothed_prefix[-1][0] - tail_points[0][0]) / stage4.shape[1]) * stage4.shape[1]
            tail_points = [(point[0] + shift, point[1]) for point in tail_points]
        shoreline = _align_terminal_point_x_v27(
            reservation.spec.shoreline_point,
            tail_points[-1][0],
            stage4.shape[1],
        )
        points = [*smoothed_prefix[:-1], *tail_points, shoreline]
        try:
            cells, edges = rasterize_centerline_v11(
                points,
                stage4_tuple,
                fields,
                water_code,
                boundary_end=True,
            )
        except ValueError:
            continue
        if tuple(cells[-len(reservation.route_tail):]) != reservation.route_tail or len(cells) < config.min_primary_cells:
            continue
        candidate_expected = expected_edges | _expected_undirected(edges)
        if _coarse_conflicts(cells, occupied_cells, candidate_expected, stage4.shape[1]):
            continue
        return (
            reservation,
            path,
            points,
            shoreline,
            reservation.spec.sea_cell,
            terminal_tail_start,
            cells,
            edges,
            candidate_expected,
        )
    return None


def _point_in_wrapped_cell(point: Point, cell: Cell, width: int) -> bool:
    return int(math.floor(point[0])) % width == cell[0] and int(math.floor(point[1])) == cell[1]


def _attachment_options(
    drafts: Sequence[_TraceDraft],
    primary_ids: Sequence[int],
    occupied_cells: set[Cell],
    stage4: np.ndarray,
    water_code: int,
    scale: int,
    seed: int,
    *,
    min_parent_progress: float = 0.0,
    max_parent_progress: float = 1.0,
    min_alignment: float = -1.0,
) -> list[_AttachmentOption]:
    """Find clean one-contact approach cells and an exact point on each trunk.

    The coarse one-contact rule is intentionally stronger than the visual
    renderer needs: a tributary may enter the graph through exactly one clean
    side cell, so rasterizing the continuous corridor cannot silently invent a
    second gameplay adjacency.
    """

    height, width = stage4.shape
    fine_width = width * scale
    options: list[_AttachmentOption] = []
    for parent_id in primary_ids:
        parent = drafts[parent_id]
        parent_cells = tuple(parent.raster_cells or ())
        if len(parent_cells) < 3:
            continue
        for target_index, target_cell in enumerate(parent_cells[1:-1], 1):
            parent_progress = target_index / max(1, len(parent_cells) - 1)
            if not min_parent_progress <= parent_progress <= max_parent_progress:
                continue
            points_here = [point for point in parent.points if _point_in_wrapped_cell(point, target_cell, width)]
            if not points_here:
                continue
            center = (target_cell[0] + 0.5, target_cell[1] + 0.5)

            def centered(point: Point) -> tuple[float, float, float]:
                wrapped_x = point[0] + round((center[0] - point[0]) / width) * width
                margin = min(wrapped_x % 1.0, 1.0 - wrapped_x % 1.0, point[1] % 1.0, 1.0 - point[1] % 1.0)
                return (-margin, (wrapped_x - center[0]) ** 2 + (point[1] - center[1]) ** 2, point[1])

            target_point = min(points_here, key=centered)
            target_mod_x = target_point[0] % width
            target_fine = (
                int(round(target_mod_x * scale - 0.5)) % fine_width,
                max(0, min(height * scale - 1, int(round(target_point[1] * scale - 0.5)))),
            )
            point_index = min(
                range(len(parent.points)),
                key=lambda index: (parent.points[index][0] - target_point[0]) ** 2 + (parent.points[index][1] - target_point[1]) ** 2,
            )
            before = parent.points[max(0, point_index - 2)]
            after = parent.points[min(len(parent.points) - 1, point_index + 2)]
            tangent_x = after[0] - before[0]
            tangent_x -= round(tangent_x / width) * width
            tangent_y = after[1] - before[1]
            tangent_length = max(math.hypot(tangent_x, tangent_y), 1e-9)
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                approach = ((target_cell[0] + dx) % width, target_cell[1] + dy)
                if not 0 <= approach[1] < height or int(stage4[approach[1], approach[0]]) == water_code:
                    continue
                if approach in occupied_cells:
                    continue
                contacts = sum(_cardinal(approach, cell, width) for cell in occupied_cells)
                if contacts != 1:
                    continue
                cross_x = target_fine[0]
                cross_y = target_fine[1]
                if dx == 1:
                    approach_fine = (approach[0] * scale + 1, min((approach[1] + 1) * scale - 2, max(approach[1] * scale + 1, cross_y)))
                elif dx == -1:
                    approach_fine = (((approach[0] + 1) * scale - 2) % fine_width, min((approach[1] + 1) * scale - 2, max(approach[1] * scale + 1, cross_y)))
                elif dy == 1:
                    approach_fine = (min((approach[0] + 1) * scale - 2, max(approach[0] * scale + 1, cross_x)) % fine_width, approach[1] * scale + 1)
                else:
                    approach_fine = (min((approach[0] + 1) * scale - 2, max(approach[0] * scale + 1, cross_x)) % fine_width, (approach[1] + 1) * scale - 2)
                approach_center_x = approach[0] + 0.5
                approach_center_x += round((target_point[0] - approach_center_x) / width) * width
                incoming_x = target_point[0] - approach_center_x
                incoming_y = target_point[1] - (approach[1] + 0.5)
                incoming_length = max(math.hypot(incoming_x, incoming_y), 1e-9)
                alignment = (incoming_x * tangent_x + incoming_y * tangent_y) / (incoming_length * tangent_length)
                if alignment < min_alignment:
                    continue
                options.append(
                    _AttachmentOption(
                        parent_id,
                        target_cell,
                        approach,
                        target_point,
                        target_fine,
                        approach_fine,
                        parent_progress,
                        float(alignment),
                    )
                )
    options.sort(
        key=lambda option: (
            option.parent_trace,
            option.target_cell[1],
            option.target_cell[0],
            _stable_hash(seed, option.approach_cell[0], option.approach_cell[1], 2371),
        )
    )
    return options


def _tributary_blocked_mask(
    option: _AttachmentOption,
    occupied_cells: set[Cell],
    occupied_fine: set[FineCell],
    land: np.ndarray,
    scale: int,
) -> np.ndarray:
    """Reserve all graph contacts except one narrow, shared merge throat."""

    height, fine_width = land.shape
    width = fine_width // scale
    blocked = _dilate_fine(occupied_fine, land.shape, radius=1)
    contact_cells: set[Cell] = set(occupied_cells)
    for cell in occupied_cells:
        x, y = cell
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            neighbor = ((x + dx) % width, y + dy)
            if 0 <= neighbor[1] < height // scale:
                contact_cells.add(neighbor)
    contact_cells.discard(option.approach_cell)
    for x, y in contact_cells:
        blocked[y * scale : (y + 1) * scale, x * scale : (x + 1) * scale] = True
    throat = _line_fine(option.approach_fine, option.target_fine, fine_width)
    for index, (x, y) in enumerate(throat):
        blocked[y, x] = False
        # A two-subcell opening at the approach end avoids an artificial
        # single-pixel nozzle while keeping the trunk cell itself protected.
        if index < max(2, len(throat) // 2):
            for dx, dy in _DIR8:
                nx, ny = (x + dx) % fine_width, y + dy
                if 0 <= ny < height:
                    coarse = (nx // scale, ny // scale)
                    if coarse == option.approach_cell:
                        blocked[ny, nx] = False
    return blocked


def _sample_potential(fields: HydrologyFields, point: Point, width: int) -> float:
    _height, potential, _distance = fields.arrays()
    return v9._field_sample(potential, (point[0] * 96.0, point[1] * 96.0), 96, width)


def _uphill_fraction_points(points: Sequence[Point], fields: HydrologyFields, width: int) -> float:
    values = [_sample_potential(fields, point, width) for point in points]
    rises = sum(second > first + 0.004 for first, second in zip(values, values[1:]))
    return rises / max(1, len(values) - 1)


def _finalize_traces(
    drafts: Sequence[_TraceDraft],
    fields: HydrologyFields,
    seed: int,
    width: int,
    scale: int,
    *,
    terminal_aware: bool = False,
) -> tuple[ContinuousTraceV11, ...]:
    attachments: dict[int, list[tuple[int, int]]] = {}
    for index, draft in enumerate(drafts):
        if draft.parent_trace is None or draft.attachment_point is None:
            continue
        parent_points = drafts[draft.parent_trace].points
        attachment_index = min(
            range(len(parent_points)),
            key=lambda item: (parent_points[item][0] - draft.attachment_point[0]) ** 2 + (parent_points[item][1] - draft.attachment_point[1]) ** 2,
        )
        attachments.setdefault(draft.parent_trace, []).append((attachment_index, len(draft.points)))
    result = []
    for trace_id, draft in enumerate(drafts):
        samples = []
        count = max(1, len(draft.points) - 1)
        for index, point in enumerate(draft.points):
            progress = index / count
            if draft.kind == "primary":
                contribution = sum(length * 0.22 for attach, length in attachments.get(trace_id, []) if index >= attach)
                area = 1.0 + index * 0.34 + contribution
                strahler = 2 if any(index >= attach for attach, _length in attachments.get(trace_id, [])) else 1
                width_px = min(10.8, 2.50 + math.sqrt(area) * 1.10 + (strahler - 1) * 1.35)
                if terminal_aware:
                    # V27 keeps the fine source but gives the established
                    # lower river the 18..22 px body required by the approved
                    # delta family and target-zoom readability.
                    downstream = min(22.0, 14.5 + math.sqrt(area) * 1.60 + (strahler - 1) * 1.80)
                    blend = progress * progress * (3.0 - 2.0 * progress)
                    width_px = width_px * (1.0 - blend) + downstream * blend
            else:
                area = 1.0 + index * 0.25
                strahler = 1
                width_px = min(6.0, 1.20 + math.sqrt(area) * 0.84)
            if index == 0:
                width_px = min(width_px, 1.05)
            potential = _sample_potential(fields, point, width)
            samples.append(FlowSampleV11(point, area, strahler, width_px, potential))
        rises = sum(b.potential > a.potential + 0.004 for a, b in zip(samples, samples[1:]))
        uphill = rises / max(1, len(samples) - 1)
        terminal_spec = draft.terminal_spec
        if terminal_spec is not None:
            terminal_spec = replace(
                terminal_spec,
                trace_id=trace_id,
                width_px=float(samples[-1].width_px),
                stream_order=int(samples[-1].strahler),
            )
        source_spec = None
        if terminal_aware and draft.kind == "primary" and len(draft.raster_cells or ()) >= 2:
            source_cell = tuple(draft.raster_cells[0])
            outflow_cell = tuple(draft.raster_cells[1])
            radius_jitter = ((_stable_hash(seed ^ (trace_id * 0x9E37), source_cell[0], source_cell[1], 0x51A7) >> 17) & 0xFFFF) / 65535.0
            source_spec = build_round_spring_source_v27(
                source_id=f"v27-source-{seed}-{trace_id}",
                source_cell=source_cell,
                outflow_cell=outflow_cell,
                world_width=width,
                world_height=len(fields.height),
                width_px=float(samples[0].width_px),
                stream_order=int(samples[0].strahler),
                lake_radius_cells=0.12 + radius_jitter * 0.025,
            )
        run_path = draft.fine_path
        if draft.terminal_tail_start is not None:
            # The reserved final corridor is intentionally cardinal.  The
            # anti-grid run gate applies to the freely routed interior, not to
            # the authored terminal's required straight attachment.
            run_path = draft.fine_path[: max(2, draft.terminal_tail_start + 1)]
        result.append(
            ContinuousTraceV11(
                trace_id=trace_id,
                kind=draft.kind,
                parent_trace=draft.parent_trace,
                attachment_point=draft.attachment_point,
                source_cell=draft.source_cell,
                termination="coast" if draft.kind == "primary" else "confluence",
                mouth_water_cell=draft.mouth_water_cell,
                shoreline_point=draft.shoreline_point,
                fine_path=tuple(draft.fine_path),
                samples=tuple(samples),
                raster_cells=tuple(draft.raster_cells or ()),
                raster_edges=tuple(draft.raster_edges or ()),
                uphill_fraction=uphill,
                max_cardinal_run=_max_heading_run(run_path, width * scale),
                terminal_spec=terminal_spec,
                source_spec=source_spec,
            )
        )
    return tuple(result)


def _build_mouths(traces: Sequence[ContinuousTraceV11], water_mask: np.ndarray, seed: int, tile_px: int, width: int):
    mouths = []
    for trace in traces:
        if trace.kind != "primary" or trace.shoreline_point is None or trace.mouth_water_cell is None:
            continue
        shoreline_px = (trace.shoreline_point[0] * tile_px, trace.shoreline_point[1] * tile_px)
        river_cell = trace.raster_cells[-1]
        dx_raw = (trace.mouth_water_cell[0] - river_cell[0]) % width
        dx = 1 if dx_raw == 1 else -1 if dx_raw == width - 1 else 0
        dy = trace.mouth_water_cell[1] - river_cell[1]
        cardinal = v9._unit((float(dx), float(dy)))
        direction, normal, asymmetry = v9._coast_fan_parameters(
            shoreline_px,
            cardinal,
            water_mask.astype(np.float32),
            seed=seed,
            mouth_cell=river_cell,
            tile_px=tile_px,
            world_width=width,
        )
        last = trace.samples[-1]
        mouths.append(
            ContinuousMouthV11(
                trace.trace_id,
                river_cell,
                trace.mouth_water_cell,
                shoreline_px,
                direction,
                normal,
                last.width_px * 1.12,
                min(tile_px * 0.48, last.width_px * 2.7 + math.sqrt(last.upstream_area) * 0.9),
                tile_px * (0.52 + min(0.20, math.sqrt(last.upstream_area) * 0.015)),
                asymmetry,
                last.upstream_area,
                last.strahler,
            )
        )
    return tuple(mouths)


def generate_continuous_hydrology_v11(
    authority,
    seed: int,
    land_mass: int = 1,
    temperature: int = 1,
    climate: int = 1,
    age: int = 1,
    *,
    config: ContinuousHydrologyConfigV11 | None = None,
    tile_px: int = 96,
) -> ContinuousHydrologyWorldV11:
    config = config or ContinuousHydrologyConfigV11()
    stage4_tuple, _rng = build_stage4(authority, seed, land_mass, temperature, climate, age)
    stage4 = np.asarray(stage4_tuple, dtype=np.int16)
    fields = build_hydrology_fields(stage4_tuple, authority, seed)
    water_code, river_code = int(authority.Terrain.WATER), int(authority.Terrain.RIVER)
    scale = config.subcells_per_cell
    fine_height, fine_potential, fine_distance, land = _fine_fields(stage4, fields, seed, scale, water_code)
    goals = _coast_goals(stage4, water_code, scale)
    candidates = _source_candidates(stage4, fields, authority, seed)
    drafts: list[_TraceDraft] = []
    used_source_cells: list[Cell] = []
    occupied_fine: set[FineCell] = set()
    occupied_cells: set[Cell] = set()
    expected_edges: set[Edge] = set()
    reserved_terminal_cells: set[Cell] = set()
    fine_width = stage4.shape[1] * scale

    for source_cell in candidates:
        if len([draft for draft in drafts if draft.kind == "primary"]) >= config.primary_goal:
            break
        if any(_wrapped_cell_distance(source_cell, prior, stage4.shape[1]) < 9 for prior in used_source_cells):
            continue
        source = _source_fine(source_cell, fine_potential, scale, seed)
        blocked = _dilate_fine(occupied_fine, land.shape, radius=2) if occupied_fine else np.zeros_like(land)
        reservation: TerminalReservationV27 | None = None
        terminal_tail_start: int | None = None
        if config.terminal_aware:
            routed = _route_terminal_primary_v27(
                stage4_tuple=stage4_tuple,
                stage4=stage4,
                fields=fields,
                water_code=water_code,
                source_cell=source_cell,
                source=source,
                seed=seed,
                tile_px=tile_px,
                scale=scale,
                config=config,
                fine_potential=fine_potential,
                fine_distance=fine_distance,
                land=land,
                base_blocked=blocked,
                occupied_cells=occupied_cells,
                expected_edges=expected_edges,
                reserved_terminal_cells=reserved_terminal_cells,
                relief_codes=(int(authority.Terrain.HILLS), int(authority.Terrain.MOUNTAINS)),
            )
            if routed is None:
                continue
            (
                reservation,
                path,
                points,
                shoreline,
                water_cell,
                terminal_tail_start,
                cells,
                edges,
                candidate_expected,
            ) = routed
        else:
            path = _astar_fine(
                source,
                fine_potential=fine_potential,
                fine_distance=fine_distance,
                land=land,
                blocked=blocked,
                coast_goals=goals,
                target=None,
                scale=scale,
                max_states=config.max_search_states,
            )
            if path is None or len(path) < scale * 2 or _fine_self_touch(path, fine_width):
                continue
            if _max_heading_run(path, fine_width) > config.max_cardinal_fine_run:
                continue
            unwrapped = _unwrap_fine(path, scale, fine_width)
            shoreline, water_cell = _shoreline_from_goal(unwrapped[-1], goals[path[-1]], scale)
            points = _smooth_land_path((*unwrapped, shoreline), stage4, water_code, boundary_end=True)
            try:
                cells, edges = rasterize_centerline_v11(points, stage4_tuple, fields, water_code, boundary_end=True)
            except ValueError:
                continue
            if len(cells) < config.min_primary_cells:
                continue
            candidate_expected = expected_edges | _expected_undirected(edges)
            if _coarse_conflicts(cells, occupied_cells, candidate_expected, stage4.shape[1]):
                continue
        drafts.append(
            _TraceDraft(
                "primary",
                None,
                source_cell,
                list(path),
                list(points),
                water_cell,
                shoreline,
                None,
                list(cells),
                list(edges),
                reservation.spec if reservation is not None else None,
                terminal_tail_start,
            )
        )
        used_source_cells.append(source_cell)
        occupied_fine.update(path)
        occupied_cells.update(cells)
        expected_edges = candidate_expected
        if reservation is not None:
            reserved_terminal_cells.update(reservation.reserved_cells)

    primaries = [index for index, draft in enumerate(drafts) if draft.kind == "primary"]
    if len(primaries) < config.primary_goal:
        raise RuntimeError(f"V11 pilot placed only {len(primaries)}/{config.primary_goal} primary trunks")

    # Pass 2 is still corridor-first.  Each accepted primary exposes clean
    # one-contact approach cells.  We rank *pairs* globally so the pilot does
    # not run a broad search against every remote trunk for each source.  The
    # extra distance-3 highlands are valid source terrain but are reserved for
    # tributaries; primary selection above remains the stricter distance-4 set.
    tributary_sources = _source_candidates(stage4, fields, authority, seed, min_coast_distance=3)
    while sum(draft.kind == "tributary" for draft in drafts) < config.tributary_goal:
        parent_tributary_counts = {
            primary_id: sum(
                draft.kind == "tributary" and draft.parent_trace == primary_id
                for draft in drafts
            )
            for primary_id in primaries
        }
        target_options = _attachment_options(
            drafts,
            primaries,
            occupied_cells,
            stage4,
            water_code,
            scale,
            seed,
            min_parent_progress=config.tributary_min_parent_progress,
            max_parent_progress=config.tributary_max_parent_progress,
            min_alignment=config.tributary_min_alignment,
        )
        if config.max_tributaries_per_primary:
            target_options = [
                option for option in target_options
                if parent_tributary_counts[option.parent_trace] < config.max_tributaries_per_primary
            ]
        pair_options = []
        for source_cell in tributary_sources:
            if source_cell in used_source_cells or source_cell in occupied_cells:
                continue
            source = _source_fine(source_cell, fine_potential, scale, seed)
            for option in target_options:
                if config.tributary_min_source_parent_distance:
                    parent_cells = drafts[option.parent_trace].raster_cells or ()
                    nearest_parent = min(
                        (_wrapped_cell_distance(source_cell, cell, stage4.shape[1]) for cell in parent_cells),
                        default=10**9,
                    )
                    if nearest_parent < config.tributary_min_source_parent_distance:
                        continue
                coarse_distance = _wrapped_cell_distance(source_cell, option.approach_cell, stage4.shape[1])
                if not 2 <= coarse_distance <= 15:
                    continue
                distance = _octile(source, option.approach_fine, fine_width)
                # Prefer an unused trunk strongly, but allow a second branch
                # when another primary has no legal downstream merge throat.
                if config.max_tributaries_per_primary:
                    distance += parent_tributary_counts[option.parent_trace] * scale * 24.0
                pair_options.append(
                    (
                        distance,
                        _stable_hash(seed, option.approach_fine[0], option.approach_fine[1], source_cell[0] * 71 + source_cell[1] * 131),
                        source_cell,
                        source,
                        option,
                    )
                )
        pair_options.sort(key=lambda item: (item[0], item[1], item[2][1], item[2][0]))
        accepted = None
        for _distance, _hash, source_cell, source, option in pair_options[:36]:
            blocked = _tributary_blocked_mask(option, occupied_cells, occupied_fine, land, scale)
            if blocked[source[1], source[0]]:
                continue
            path = _astar_fine(
                source,
                fine_potential=fine_potential,
                fine_distance=fine_distance,
                land=land,
                blocked=blocked,
                coast_goals=None,
                target=option.target_fine,
                scale=scale,
                max_states=min(12_000, config.max_search_states // 4),
            )
            if path is None or len(path) < scale * 2 or _fine_self_touch(path, fine_width):
                continue
            if _max_heading_run(path, fine_width) > config.max_cardinal_fine_run:
                continue
            unwrapped = _unwrap_fine(path, scale, fine_width)
            parent_point = option.target_point
            parent_point = (
                parent_point[0] + round((unwrapped[-1][0] - parent_point[0]) / stage4.shape[1]) * stage4.shape[1],
                parent_point[1],
            )
            unwrapped[-1] = parent_point
            points = _smooth_land_path(unwrapped, stage4, water_code, boundary_end=False)
            points[-1] = parent_point
            if _uphill_fraction_points(points, fields, stage4.shape[1]) > 0.32:
                continue
            try:
                cells, edges = rasterize_centerline_v11(points, stage4_tuple, fields, water_code, boundary_end=False)
            except ValueError:
                continue
            parent = drafts[option.parent_trace]
            if len(cells) < config.min_tributary_cells or cells[-1] != option.target_cell or cells[-1] not in set(parent.raster_cells or ()):
                continue
            candidate_expected = expected_edges | _expected_undirected(edges)
            if _coarse_conflicts(cells, occupied_cells, candidate_expected, stage4.shape[1]):
                continue
            accepted = source_cell, option.parent_trace, path, points, cells, edges, parent_point
            break
        if accepted is None:
            break
        source_cell, parent_id, path, points, cells, edges, parent_point = accepted
        drafts.append(_TraceDraft("tributary", parent_id, source_cell, list(path), list(points), None, None, parent_point, list(cells), list(edges)))
        used_source_cells.append(source_cell)
        occupied_fine.update(path[:-1])
        occupied_cells.update(cells)
        expected_edges |= _expected_undirected(edges)

    tributaries = [draft for draft in drafts if draft.kind == "tributary"]
    if len(tributaries) < config.tributary_goal:
        raise RuntimeError(f"V11 pilot placed only {len(tributaries)}/{config.tributary_goal} tributaries")

    traces = _finalize_traces(
        drafts,
        fields,
        seed,
        stage4.shape[1],
        scale,
        terminal_aware=config.terminal_aware,
    )
    river_cells = tuple(sorted(occupied_cells, key=lambda cell: (cell[1], cell[0])))
    river_edges = tuple(sorted({edge for trace in traces for edge in trace.raster_edges}, key=lambda edge: (edge[0][1], edge[0][0], edge[1][1], edge[1][0])))
    terrain = stage4.copy()
    for x, y in river_cells:
        terrain[y, x] = river_code
    water_mask = stage4 == water_code
    mouths = _build_mouths(traces, water_mask, seed, tile_px, stage4.shape[1])
    world = ContinuousHydrologyWorldV11(
        stage4_tuple,
        tuple(tuple(int(value) for value in row) for row in terrain),
        traces,
        river_cells,
        river_edges,
        mouths,
        fields,
        tuple(tuple(bool(value) for value in row) for row in water_mask),
        int(tile_px),
        int(stage4.shape[1]),
        int(stage4.shape[0]),
        int(seed),
        int(scale),
        (
            f"modern-v27-terminal-aware-derivative-seed-{seed}"
            if config.terminal_aware
            else f"modern-v11-derivative-seed-{seed}"
        ),
    )
    audit = validate_continuous_hydrology_v11(
        world,
        authority,
        minimum_primaries=config.primary_goal,
        minimum_tributaries=config.tributary_goal,
    )
    if not audit.valid:
        raise AssertionError("invalid continuous hydrology V11: " + "; ".join(audit.errors))
    return world


def validate_continuous_hydrology_v11(
    world: ContinuousHydrologyWorldV11,
    authority,
    *,
    minimum_primaries: int = 3,
    minimum_tributaries: int = 3,
) -> ContinuousAuditV11:
    errors = []
    cycles = 0
    fine_self_touches = 0
    mismatches = 0
    trace_by_id = {trace.trace_id: trace for trace in world.traces}
    for trace in world.traces:
        if trace.kind == "tributary":
            seen = {trace.trace_id}
            parent = trace.parent_trace
            while parent is not None:
                if parent in seen or parent not in trace_by_id:
                    cycles += 1
                    break
                seen.add(parent)
                parent = trace_by_id[parent].parent_trace
        if _fine_self_touch(trace.fine_path, world.world_width * world.subcells_per_cell):
            fine_self_touches += 1
        if trace.terminal_spec is not None:
            terminal_audit = audit_terminal_spec_v27(
                trace.terminal_spec,
                world.world_width,
                world.world_height,
            )
            if not terminal_audit.valid:
                errors.extend(f"terminal trace {trace.trace_id}: {item}" for item in terminal_audit.errors)
            expected_tail = (*trace.terminal_spec.approach_cells, trace.terminal_spec.river_cell)
            if tuple(trace.raster_cells[-len(expected_tail):]) != expected_tail:
                errors.append(f"terminal trace {trace.trace_id} lost its reserved coarse tail")
            if trace.mouth_water_cell != trace.terminal_spec.sea_cell:
                errors.append(f"terminal trace {trace.trace_id} sea-cell metadata disagrees")
            if trace.shoreline_point is None:
                errors.append(f"terminal trace {trace.trace_id} has no shoreline point")
            else:
                shoreline_dx = trace.shoreline_point[0] - trace.terminal_spec.shoreline_point[0]
                shoreline_dx -= round(shoreline_dx / world.world_width) * world.world_width
                shoreline_dy = trace.shoreline_point[1] - trace.terminal_spec.shoreline_point[1]
                if math.hypot(shoreline_dx, shoreline_dy) > 1e-8:
                    errors.append(f"terminal trace {trace.trace_id} shoreline metadata disagrees")
        try:
            cells, edges = rasterize_centerline_v11(
                trace.points,
                world.stage4_terrain,
                world.fields,
                int(authority.Terrain.WATER),
                boundary_end=trace.kind == "primary",
            )
        except ValueError:
            mismatches += 1
            continue
        if cells != trace.raster_cells or edges != trace.raster_edges:
            mismatches += 1
    expected_cells = {cell for trace in world.traces for cell in trace.raster_cells}
    expected_edges = {edge for trace in world.traces for edge in trace.raster_edges}
    if expected_cells != set(world.river_cells):
        mismatches += 1
    if expected_edges != set(world.river_edges):
        mismatches += 1
    terrain = np.asarray(world.terrain, dtype=np.int16)
    actual_cells = {(int(x), int(y)) for y, x in np.argwhere(terrain == int(authority.Terrain.RIVER))}
    if actual_cells != expected_cells:
        mismatches += 1
    raw = _raw_adjacencies(world.river_cells, world.world_width)
    recorded = _expected_undirected(world.river_edges)
    if raw != recorded:
        mismatches += 1
    for trace in world.traces:
        if trace.terminal_spec is None:
            continue
        mouth = trace.terminal_spec.river_cell
        degree = sum(mouth in edge for edge in recorded)
        if degree != 1:
            errors.append(f"terminal trace {trace.trace_id} final mouth degree is {degree}, expected 1")
    if cycles:
        errors.append("trace hierarchy contains a cycle")
    if fine_self_touches:
        errors.append("fine trace contains self-touch")
    if mismatches:
        errors.append("trace-to-raster authority mismatch")
    max_run = max((trace.max_cardinal_run for trace in world.traces), default=0)
    if max_run > 6:
        errors.append("fine trace retains a long cardinal run")
    uphill = [trace.uphill_fraction for trace in world.traces]
    if uphill and max(uphill) > 0.34:
        errors.append("trace has excessive uphill flow")
    primaries = sum(trace.kind == "primary" for trace in world.traces)
    tributaries = sum(trace.kind == "tributary" for trace in world.traces)
    if primaries < minimum_primaries or tributaries < minimum_tributaries:
        errors.append("pilot hierarchy is incomplete")
    if len(world.mouths) != primaries:
        errors.append("primary/mouth count mismatch")
    return ContinuousAuditV11(
        not errors,
        tuple(errors),
        len(world.traces),
        primaries,
        tributaries,
        len(world.mouths),
        len(world.river_cells),
        len(recorded),
        len(raw),
        cycles,
        fine_self_touches,
        mismatches,
        max_run,
        float(np.mean(uphill)) if uphill else 0.0,
        max(uphill, default=0.0),
        tributaries,
    )


__all__ = [
    "ContinuousAuditV11",
    "ContinuousHydrologyConfigV11",
    "ContinuousHydrologyWorldV11",
    "ContinuousMouthV11",
    "ContinuousTraceV11",
    "FlowSampleV11",
    "generate_continuous_hydrology_v11",
    "rasterize_centerline_v11",
    "validate_continuous_hydrology_v11",
]
