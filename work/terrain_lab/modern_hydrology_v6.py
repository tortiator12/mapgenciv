"""Isolated 2026 hydrology planner for the exact Civ-I stage-4 world.

This module is intentionally *not* wired into the production renderer or the
1991 generator.  :func:`generate_modern_hydrology` delegates stages 1--4 to
the supplied Civ-I authority, then replaces only stage 5 with a deterministic
cardinal river planner.  The immutable stage-4 terrain is returned alongside
the resulting rules grid so that this boundary stays directly testable.

The planner uses a horizontally periodic height/potential field, terrain
elevation, distance to sea and low-frequency noise.  It routes highland
sources toward a coast or an older river while retaining the exact ordered
edges.  A new trace may attach to an older trace at one endpoint, but may not
touch it anywhere else; internal chords and cycles are rejected.  Therefore
the terrain's raw cardinal RIVER adjacency is exactly the recorded graph --
the renderer never has to invent a connection.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import heapq
import math
import random
from typing import Any, Iterable, Sequence

import numpy as np


Cell = tuple[int, int]
Edge = tuple[Cell, Cell]

_CARDINAL = ((0, -1, "N"), (1, 0, "E"), (0, 1, "S"), (-1, 0, "W"))
_OPPOSITE_HEADING = {0: 2, 1: 3, 2: 0, 3: 1}


@dataclass(frozen=True)
class ModernHydrologyConfig:
    """Stable tuning surface for the isolated hydrology experiment."""

    min_path_cells: int = 5
    preferred_extra_cells: int = 3
    max_path_cells: int = 26
    max_search_states: int = 24_000
    # Civ-I's loop stops at ``rivers_placed > river_target``.  Keeping the
    # historical extra accepted run makes the population directly comparable.
    preserve_target_plus_one: bool = True
    uphill_weight: float = 8.5
    away_from_sea_weight: float = 0.62
    turn_penalty: float = 0.10
    same_turn_penalty: float = 1.35
    long_straight_penalty: float = 1.55
    mountain_entry_penalty: float = 0.45

    def __post_init__(self) -> None:
        if self.min_path_cells < 5:
            raise ValueError("modern river traces must contain at least five cells")
        if self.max_path_cells < self.min_path_cells:
            raise ValueError("max_path_cells must cover min_path_cells")
        if self.preferred_extra_cells < 0:
            raise ValueError("preferred_extra_cells cannot be negative")
        if self.max_path_cells < self.min_path_cells + self.preferred_extra_cells:
            raise ValueError("max_path_cells must cover the preferred length range")
        if self.max_search_states <= 0:
            raise ValueError("max_search_states must be positive")


@dataclass(frozen=True)
class HydrologyFields:
    """Renderer-independent world fields, stored as immutable tuples."""

    height: tuple[tuple[float, ...], ...]
    potential: tuple[tuple[float, ...], ...]
    distance_to_sea: tuple[tuple[int, ...], ...]

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (
            np.asarray(self.height, dtype=np.float64),
            np.asarray(self.potential, dtype=np.float64),
            np.asarray(self.distance_to_sea, dtype=np.int16),
        )


@dataclass(frozen=True)
class ModernRiverTrace:
    """One accepted source-to-coast or source-to-confluence run."""

    cells: tuple[Cell, ...]
    edges: tuple[Edge, ...]
    termination: str
    confluence: Cell | None
    mouth_candidates: tuple[str, ...]
    source_terrain: int
    source_potential: float
    end_potential: float
    route_cost: float


@dataclass(frozen=True)
class ModernHydrologyWorld:
    """Exact stage-4 input, modern stage-5 rules grid and trace authority."""

    stage4_terrain: tuple[tuple[int, ...], ...]
    terrain: tuple[tuple[int, ...], ...]
    traces: tuple[ModernRiverTrace, ...]
    river_edges: tuple[Edge, ...]
    fields: HydrologyFields
    river_target: int
    desired_traces: int
    seed: int

    def snapshot_extension(self) -> dict[str, Any]:
        """Return the V1 trace shape already consumed by the current renderer."""

        return {
            "schema": "project1991.river-traces/v1",
            "generator": "modern-hydrology-v6",
            "river_edges": [
                [[int(a[0]), int(a[1])], [int(b[0]), int(b[1])]]
                for a, b in self.river_edges
            ],
            "traces": [
                {
                    "cells": [[int(x), int(y)] for x, y in trace.cells],
                    "termination": trace.termination,
                    "confluence": (
                        [int(trace.confluence[0]), int(trace.confluence[1])]
                        if trace.confluence is not None
                        else None
                    ),
                    "mouth_candidates": list(trace.mouth_candidates),
                    "source_terrain": int(trace.source_terrain),
                    "source_potential": round(float(trace.source_potential), 8),
                    "end_potential": round(float(trace.end_potential), 8),
                    "route_cost": round(float(trace.route_cost), 8),
                }
                for trace in self.traces
            ],
        }


@dataclass(frozen=True)
class HydrologyValidation:
    valid: bool
    errors: tuple[str, ...]
    river_cells: int
    recorded_edges: int
    raw_adjacencies: int
    coast_terminations: int
    confluences: int


@dataclass(frozen=True)
class _Route:
    cells: tuple[Cell, ...]
    termination: str
    confluence: Cell | None
    mouths: tuple[str, ...]
    cost: float


def _stable_hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    value = (
        int(seed)
        ^ (int(x) * 0x9E3779B1)
        ^ (int(y) * 0x85EBCA77)
        ^ (int(salt) * 0xC2B2AE3D)
    ) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def world_periodic_noise(seed: int, x: int | float, y: int | float, world_width: int) -> float:
    """Low-frequency analytic noise with an exact horizontal world period."""

    if world_width <= 0:
        raise ValueError("world_width must be positive")
    # Integer x harmonics make f(x + world_width, y) exactly equal in the
    # mathematical field.  Phases are seed-derived and independent of Python's
    # process-randomized hash implementation.
    phase1 = (_stable_hash(seed, 0, 0, 101) / 2**32) * math.tau
    phase2 = (_stable_hash(seed, 0, 0, 103) / 2**32) * math.tau
    phase3 = (_stable_hash(seed, 0, 0, 107) / 2**32) * math.tau
    xf = (float(x) % int(world_width)) / float(world_width)
    yf = float(y)
    value = (
        0.52 * math.sin(math.tau * (2.0 * xf + yf / 19.0) + phase1)
        + 0.31 * math.cos(math.tau * (3.0 * xf - yf / 27.0) + phase2)
        + 0.17 * math.sin(math.tau * (5.0 * xf + yf / 11.0) + phase3)
    )
    return float(value)


def build_stage4(
    authority,
    seed: int,
    land_mass: int = 1,
    temperature: int = 1,
    climate: int = 1,
    age: int = 1,
) -> tuple[tuple[tuple[int, ...], ...], object]:
    """Run the authority through stage 4 only and return its live RNG state.

    Returning the RNG object is useful for audits against the legacy stage 5;
    the modern planner deliberately does not consume it.
    """

    rng = random.Random(int(seed))
    grid = [
        [authority.Terrain.WATER] * int(authority.MAP_W)
        for _ in range(int(authority.MAP_H))
    ]
    authority._stage1_continents(grid, rng, int(land_mass))
    authority._stage2_latitude(grid, rng, int(temperature))
    authority._stage3_climate(grid, rng, int(climate))
    authority._stage4_age(grid, rng, int(age))
    frozen = tuple(tuple(int(value) for value in row) for row in grid)
    return frozen, rng


def _distance_to_water(grid: np.ndarray, water_code: int) -> np.ndarray:
    height, width = grid.shape
    distance = np.full((height, width), -1, dtype=np.int16)
    queue: deque[Cell] = deque()
    for y, x in np.argwhere(grid == int(water_code)):
        x, y = int(x), int(y)
        distance[y, x] = 0
        queue.append((x, y))
    if not queue:
        raise ValueError("stage-4 world has no water sink")
    while queue:
        x, y = queue.popleft()
        next_distance = int(distance[y, x]) + 1
        for dx, dy, _ in _CARDINAL:
            nx, ny = (x + dx) % width, y + dy
            if 0 <= ny < height and distance[ny, nx] < 0:
                distance[ny, nx] = next_distance
                queue.append((nx, ny))
    return distance


def _distance_to_cells(shape: tuple[int, int], cells: Iterable[Cell]) -> np.ndarray:
    """Cardinal distance to arbitrary sinks with the Civ horizontal wrap."""

    height, width = shape
    distance = np.full(shape, 32_767, dtype=np.int16)
    queue: deque[Cell] = deque()
    for x, y in sorted(set(cells), key=lambda cell: (cell[1], cell[0])):
        distance[y, x] = 0
        queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        next_distance = int(distance[y, x]) + 1
        for dx, dy, _name in _CARDINAL:
            nx, ny = (x + dx) % width, y + dy
            if 0 <= ny < height and next_distance < int(distance[ny, nx]):
                distance[ny, nx] = next_distance
                queue.append((nx, ny))
    return distance


def build_hydrology_fields(stage4_terrain: Sequence[Sequence[int]], authority, seed: int) -> HydrologyFields:
    """Build deterministic terrain elevation and coast-flow potential."""

    grid = np.asarray(stage4_terrain, dtype=np.int16)
    if grid.ndim != 2 or grid.shape != (int(authority.MAP_H), int(authority.MAP_W)):
        raise ValueError(f"unexpected stage-4 shape {grid.shape}")
    terrain = authority.Terrain
    distance = _distance_to_water(grid, int(terrain.WATER))
    elevation_by_code = {
        int(terrain.WATER): 0.00,
        int(terrain.SWAMP): 0.14,
        int(terrain.JUNGLE): 0.24,
        int(terrain.GRASSLAND): 0.26,
        int(terrain.PLAINS): 0.29,
        int(terrain.DESERT): 0.32,
        int(terrain.FOREST): 0.35,
        int(terrain.TUNDRA): 0.38,
        int(terrain.ARCTIC): 0.42,
        int(terrain.HILLS): 0.72,
        int(terrain.MOUNTAINS): 1.00,
    }
    elevation = np.zeros(grid.shape, dtype=np.float64)
    for code, value in elevation_by_code.items():
        elevation[grid == code] = value
    noise = np.empty(grid.shape, dtype=np.float64)
    for y in range(grid.shape[0]):
        for x in range(grid.shape[1]):
            noise[y, x] = world_periodic_noise(int(seed), x, y, grid.shape[1])
    max_land_distance = max(1.0, float(distance[grid != int(terrain.WATER)].max(initial=1)))
    coast_rise = distance.astype(np.float64) / max_land_distance
    height_field = elevation + coast_rise * 0.34 + noise * 0.085
    # Potential emphasizes basin direction slightly more than physical relief;
    # elevation and noise still break ties into stable drainage corridors.
    potential = coast_rise * 0.68 + elevation * 0.25 + noise * 0.07
    height_field[grid == int(terrain.WATER)] = -0.25 + noise[grid == int(terrain.WATER)] * 0.02
    potential[grid == int(terrain.WATER)] = -0.25
    return HydrologyFields(
        height=tuple(tuple(float(value) for value in row) for row in height_field),
        potential=tuple(tuple(float(value) for value in row) for row in potential),
        distance_to_sea=tuple(tuple(int(value) for value in row) for row in distance),
    )


def _neighbors(cell: Cell, width: int, height: int) -> Iterable[tuple[Cell, int, str]]:
    x, y = cell
    for heading, (dx, dy, name) in enumerate(_CARDINAL):
        nx, ny = (x + dx) % width, y + dy
        if 0 <= ny < height:
            yield (nx, ny), heading, name


def _mouth_names(stage4: np.ndarray, cell: Cell, water_code: int) -> tuple[str, ...]:
    width, height = stage4.shape[1], stage4.shape[0]
    result = []
    for neighbor, _heading, name in _neighbors(cell, width, height):
        if int(stage4[neighbor[1], neighbor[0]]) == int(water_code):
            result.append(name)
    return tuple(result)


def _is_cardinal(a: Cell, b: Cell, width: int) -> bool:
    dx = min((a[0] - b[0]) % width, (b[0] - a[0]) % width)
    return dx + abs(a[1] - b[1]) == 1


def _path_has_chord(path: Sequence[Cell], width: int) -> bool:
    index = {cell: position for position, cell in enumerate(path)}
    if len(index) != len(path):
        return True
    for position, (x, y) in enumerate(path):
        for dx, dy, _ in _CARDINAL:
            other = ((x + dx) % width, y + dy)
            other_position = index.get(other)
            if other_position is not None and abs(other_position - position) != 1:
                return True
    return False


def _reconstruct(came_from: dict[tuple[int, ...], tuple[int, ...] | None], state: tuple[int, ...]) -> tuple[Cell, ...]:
    cells: list[Cell] = []
    current: tuple[int, ...] | None = state
    while current is not None:
        cells.append((int(current[0]), int(current[1])))
        current = came_from[current]
    cells.reverse()
    return tuple(cells)


def _valid_candidate_path(
    path: Sequence[Cell],
    *,
    stage4: np.ndarray,
    existing: set[Cell],
    water_code: int,
    min_cells: int,
    termination: str,
    confluence: Cell | None,
) -> bool:
    width, height = stage4.shape[1], stage4.shape[0]
    if len(path) < min_cells or len(set(path)) != len(path):
        return False
    if _path_has_chord(path, width):
        return False
    for first, second in zip(path, path[1:]):
        if not _is_cardinal(first, second, width):
            return False
    for cell in path:
        if not (0 <= cell[1] < height) or int(stage4[cell[1], cell[0]]) == water_code:
            return False
        touching_existing = {
            other
            for other, _heading, _name in _neighbors(cell, width, height)
            if other in existing
        }
        if cell != path[-1] and touching_existing:
            return False
        if cell == path[-1]:
            if termination == "river":
                if confluence is None or touching_existing != {confluence}:
                    return False
            elif touching_existing:
                return False
    if termination == "coast":
        if not _mouth_names(stage4, path[-1], water_code):
            return False
        # The route must not silently run along a coast it already reached.
        if any(_mouth_names(stage4, cell, water_code) for cell in path[:-1]):
            return False
    elif termination == "river":
        if confluence is None or confluence not in existing:
            return False
        if not _is_cardinal(path[-1], confluence, width):
            return False
    else:
        return False
    return True


def _route_source(
    source: Cell,
    *,
    stage4: np.ndarray,
    current_grid: list[list[int]],
    existing: set[Cell],
    potential: np.ndarray,
    distance_to_sea: np.ndarray,
    authority,
    seed: int,
    config: ModernHydrologyConfig,
) -> _Route | None:
    """Dijkstra route with momentum, diagonal cadence and graph safeguards."""

    height, width = stage4.shape
    terrain = authority.Terrain
    water_code = int(terrain.WATER)
    mountain_code = int(terrain.MOUNTAINS)
    sx, sy = source
    if int(distance_to_sea[sy, sx]) <= 1 or source in existing:
        return None
    if any(neighbor in existing for neighbor, _h, _n in _neighbors(source, width, height)):
        return None

    # A fixed five-cell cutoff produces a visibly uniform family of short
    # stubs.  Seed/source-stable 5--8-cell minimums retain Civ's population
    # while matching its observed mean course length much more closely.
    route_min_cells = config.min_path_cells + (
        _stable_hash(seed, sx, sy, 683) % (config.preferred_extra_cells + 1)
    )
    flow_distance = distance_to_sea
    if existing:
        # An established river is a legitimate lower sink.  Using the minimum
        # distance makes tributary convergence part of the same cost model as
        # coastal drainage instead of a post-process snap.
        river_distance = _distance_to_cells(stage4.shape, existing)
        flow_distance = np.minimum(distance_to_sea, river_distance)

    # state = x, y, heading, straight_run, path_length, previous_turn_sign.
    start = (sx, sy, -1, 0, 1, 0)
    best_cost: dict[tuple[int, ...], float] = {start: 0.0}
    came_from: dict[tuple[int, ...], tuple[int, ...] | None] = {start: None}
    queue: list[tuple[float, int, tuple[int, ...]]] = [(0.0, 0, start)]
    serial = 1
    expansions = 0
    best_terminal: tuple[float, tuple[Cell, ...], str, Cell | None, tuple[str, ...]] | None = None
    # Rotate equal-cost heading order per source without weakening determinism.
    rotation = _stable_hash(seed, sx, sy, 701) & 3
    heading_order = tuple((rotation + offset) & 3 for offset in range(4))

    while queue and expansions < config.max_search_states:
        cost, _order, state = heapq.heappop(queue)
        if cost != best_cost.get(state):
            continue
        if best_terminal is not None and cost + 1.0 >= best_terminal[0]:
            break
        expansions += 1
        x, y, heading, straight_run, path_length, last_turn = state
        if path_length >= config.max_path_cells:
            continue

        for next_heading in heading_order:
            if heading >= 0 and next_heading == _OPPOSITE_HEADING[heading]:
                # A U-turn is never a river meander; it is a graph defect.
                continue
            dx, dy, _name = _CARDINAL[next_heading]
            nx, ny = (x + dx) % width, y + dy
            if not (0 <= ny < height):
                continue
            next_cell = (nx, ny)
            cell_code = int(current_grid[ny][nx])
            if cell_code in (water_code, int(terrain.RIVER)):
                continue
            next_length = path_length + 1
            next_mouths = _mouth_names(stage4, next_cell, water_code)
            touching_existing = {
                neighbor
                for neighbor, _h, _n in _neighbors(next_cell, width, height)
                if neighbor in existing
            }

            # Reaching coast/confluence before five cells cannot be hidden by
            # walking alongside it.  Such a candidate source is simply poor.
            if (next_mouths or touching_existing) and next_length < route_min_cells:
                continue
            if len(touching_existing) > 1:
                continue
            if touching_existing:
                candidate_sink = next(iter(touching_existing))
                if float(potential[candidate_sink[1], candidate_sink[0]]) >= float(potential[sy, sx]) - 0.01:
                    # A tributary may join an older highland course only after
                    # descending below its own source potential.
                    continue

            if heading < 0 or next_heading == heading:
                turn_sign = 0
                next_run = straight_run + 1
            else:
                delta_heading = (next_heading - heading) & 3
                turn_sign = 1 if delta_heading == 1 else -1
                next_run = 1

            delta_potential = float(potential[ny, nx] - potential[y, x])
            step_cost = 1.0
            step_cost += max(0.0, delta_potential) * config.uphill_weight
            distance_delta = int(flow_distance[ny, nx]) - int(flow_distance[y, x])
            if distance_delta > 0:
                step_cost += config.away_from_sea_weight * distance_delta
            elif distance_delta == 0:
                step_cost += 0.055
            if heading >= 0 and next_heading != heading:
                # A small momentum term avoids jitter.  When the terrain
                # gradient is diagonal, alternating axes remains cheaper than
                # accumulating the long-straight penalty: Bresenham-like flow.
                step_cost += config.turn_penalty
            if turn_sign and last_turn == turn_sign:
                # Consecutive same-side corners are the signature of a square
                # return.  Chords are rejected later; this cost prevents them
                # from dominating the search in the first place.
                step_cost += config.same_turn_penalty
            if next_run > 4:
                step_cost += config.long_straight_penalty * float((next_run - 4) ** 2)
            if int(stage4[ny, nx]) == mountain_code and next_cell != source:
                step_cost += config.mountain_entry_penalty
            new_cost = cost + step_cost

            terminal_type: str | None = None
            confluence: Cell | None = None
            mouths: tuple[str, ...] = ()
            if touching_existing:
                terminal_type = "river"
                confluence = next(iter(touching_existing))
            elif next_mouths:
                terminal_type = "coast"
                mouths = next_mouths

            next_state = (
                nx,
                ny,
                next_heading,
                next_run,
                next_length,
                turn_sign,
            )
            if terminal_type is not None:
                path = _reconstruct(came_from, state) + (next_cell,)
                if _valid_candidate_path(
                    path,
                    stage4=stage4,
                    existing=existing,
                    water_code=water_code,
                    min_cells=route_min_cells,
                    termination=terminal_type,
                    confluence=confluence,
                ):
                    candidate = (new_cost, path, terminal_type, confluence, mouths)
                    if best_terminal is None or candidate[:2] < best_terminal[:2]:
                        best_terminal = candidate
                continue

            old_cost = best_cost.get(next_state)
            if old_cost is not None and new_cost >= old_cost - 1e-12:
                continue
            best_cost[next_state] = new_cost
            came_from[next_state] = state
            heapq.heappush(queue, (new_cost, serial, next_state))
            serial += 1

    if best_terminal is None:
        return None
    cost, path, termination, confluence, mouths = best_terminal
    return _Route(
        cells=path,
        termination=termination,
        confluence=confluence,
        mouths=mouths,
        cost=float(cost),
    )


def _dedupe_edges(traces: Iterable[ModernRiverTrace]) -> tuple[Edge, ...]:
    result: list[Edge] = []
    seen: set[frozenset[Cell]] = set()
    for trace in traces:
        for edge in trace.edges:
            key = frozenset(edge)
            if key in seen:
                continue
            seen.add(key)
            result.append(edge)
    return tuple(result)


def _source_candidates(
    stage4: np.ndarray,
    current_grid: Sequence[Sequence[int]],
    existing: set[Cell],
    fields: HydrologyFields,
    authority,
    seed: int,
) -> list[Cell]:
    height_field, potential, distance = fields.arrays()
    terrain = authority.Terrain
    highland = {int(terrain.HILLS), int(terrain.MOUNTAINS)}
    height, width = stage4.shape
    scored = []
    for y in range(height):
        for x in range(width):
            if int(current_grid[y][x]) not in highland or int(distance[y, x]) <= 1:
                continue
            cell = (x, y)
            if cell in existing:
                continue
            if any(other in existing for other, _h, _n in _neighbors(cell, width, height)):
                continue
            # Distance helps the few true interior headwaters lead the order;
            # terrain height/potential and stable hash break broad plateaus.
            source_score = (
                float(height_field[y, x]) * 1.4
                + float(potential[y, x]) * 0.7
                + min(8.0, float(distance[y, x])) * 0.055
            )
            scored.append(
                (
                    -source_score,
                    _stable_hash(seed, x, y, 907),
                    y,
                    x,
                )
            )
    scored.sort()
    return [(x, y) for _score, _hash, y, x in scored]


def generate_modern_hydrology(
    authority,
    seed: int,
    land_mass: int = 1,
    temperature: int = 1,
    climate: int = 1,
    age: int = 1,
    *,
    config: ModernHydrologyConfig | None = None,
) -> ModernHydrologyWorld:
    """Generate exact Civ-I stages 1--4 plus an isolated modern stage 5."""

    config = config or ModernHydrologyConfig()
    stage4, _legacy_rng = build_stage4(
        authority,
        seed,
        land_mass,
        temperature,
        climate,
        age,
    )
    stage4_array = np.asarray(stage4, dtype=np.int16)
    fields = build_hydrology_fields(stage4, authority, int(seed))
    _height_field, potential, distance = fields.arrays()
    grid = [list(row) for row in stage4]
    terrain = authority.Terrain
    river_code = int(terrain.RIVER)
    forest_code = int(terrain.FOREST)
    jungle_code = int(terrain.JUNGLE)
    river_target = (int(land_mass) + int(climate)) * 2 + 6
    desired = river_target + int(config.preserve_target_plus_one)
    accepted: list[ModernRiverTrace] = []
    existing: set[Cell] = set()

    # Rebuild the candidate list after every accepted trace so tributaries and
    # exclusion zones are always evaluated against the current network.
    while len(accepted) < desired:
        candidates = _source_candidates(stage4_array, grid, existing, fields, authority, int(seed))
        route: _Route | None = None
        source: Cell | None = None
        # Testing all highlands is still cheap on the fixed 80x50 world and
        # avoids an arbitrary attempt cap changing sparse maps' population.
        for candidate in candidates:
            route = _route_source(
                candidate,
                stage4=stage4_array,
                current_grid=grid,
                existing=existing,
                potential=potential,
                distance_to_sea=distance,
                authority=authority,
                seed=int(seed),
                config=config,
            )
            if route is not None:
                source = candidate
                break
        if route is None or source is None:
            break

        for x, y in route.cells:
            grid[y][x] = river_code
        edges: list[Edge] = list(zip(route.cells, route.cells[1:]))
        if route.confluence is not None:
            edges.append((route.cells[-1], route.confluence))
        source_code = int(stage4_array[source[1], source[0]])
        end_cell = route.confluence if route.confluence is not None else route.cells[-1]
        accepted.append(
            ModernRiverTrace(
                cells=route.cells,
                edges=tuple(edges),
                termination=route.termination,
                confluence=route.confluence,
                mouth_candidates=route.mouths,
                source_terrain=source_code,
                source_potential=float(potential[source[1], source[0]]),
                end_potential=float(potential[end_cell[1], end_cell[0]]),
                route_cost=float(route.cost),
            )
        )
        existing.update(route.cells)

        # Preserve the rules-visible ecology mutation of Civ-I stage 5, but
        # anchor it to the actual modern termination rather than the legacy
        # walk's post-terminal cursor quirk.
        for neighbor, _heading, _name in _neighbors(end_cell, stage4_array.shape[1], stage4_array.shape[0]):
            nx, ny = neighbor
            if int(grid[ny][nx]) == forest_code:
                grid[ny][nx] = jungle_code

    world = ModernHydrologyWorld(
        stage4_terrain=stage4,
        terrain=tuple(tuple(int(value) for value in row) for row in grid),
        traces=tuple(accepted),
        river_edges=_dedupe_edges(accepted),
        fields=fields,
        river_target=river_target,
        desired_traces=desired,
        seed=int(seed),
    )
    validation = validate_modern_world(world, authority)
    if not validation.valid:
        raise AssertionError("invalid modern hydrology: " + "; ".join(validation.errors))
    return world


def validate_modern_world(world: ModernHydrologyWorld, authority) -> HydrologyValidation:
    """Audit every graph/rules invariant without inferring missing edges."""

    width, height = int(authority.MAP_W), int(authority.MAP_H)
    river_code = int(authority.Terrain.RIVER)
    water_code = int(authority.Terrain.WATER)
    terrain = np.asarray(world.terrain, dtype=np.int16)
    stage4 = np.asarray(world.stage4_terrain, dtype=np.int16)
    errors: list[str] = []
    river_cells = {
        (int(x), int(y))
        for y, x in np.argwhere(terrain == river_code)
    }
    recorded = {frozenset(edge) for edge in world.river_edges}
    if len(recorded) != len(world.river_edges):
        errors.append("duplicate recorded river edge")
    raw: set[frozenset[Cell]] = set()
    for x, y in river_cells:
        for dx, dy in ((1, 0), (0, 1)):
            other = ((x + dx) % width, y + dy)
            if other in river_cells:
                raw.add(frozenset(((x, y), other)))
    if raw != recorded:
        missing = len(raw - recorded)
        invented = len(recorded - raw)
        errors.append(f"raw/recorded adjacency mismatch missing={missing} invented={invented}")

    highland = {int(authority.Terrain.HILLS), int(authority.Terrain.MOUNTAINS)}
    all_trace_cells: set[Cell] = set()
    for index, trace in enumerate(world.traces):
        if len(trace.cells) < 5:
            errors.append(f"trace {index} shorter than five cells")
        if not trace.cells or int(stage4[trace.cells[0][1], trace.cells[0][0]]) not in highland:
            errors.append(f"trace {index} source is not hills/mountains")
        if _path_has_chord(trace.cells, width):
            errors.append(f"trace {index} self-touches or contains a chord")
        expected_edges = list(zip(trace.cells, trace.cells[1:]))
        if trace.confluence is not None:
            expected_edges.append((trace.cells[-1], trace.confluence))
        if tuple(expected_edges) != trace.edges:
            errors.append(f"trace {index} ordered edges do not match ordered cells")
        for start, end in trace.edges:
            if not _is_cardinal(start, end, width):
                errors.append(f"trace {index} contains non-cardinal edge")
            if start not in river_cells or end not in river_cells:
                errors.append(f"trace {index} edge endpoint is not RIVER")
        overlap = all_trace_cells.intersection(trace.cells)
        if overlap:
            errors.append(f"trace {index} reuses {len(overlap)} older cells")
        all_trace_cells.update(trace.cells)
        if trace.termination == "coast":
            mouths = _mouth_names(stage4, trace.cells[-1], water_code)
            if not mouths or mouths != trace.mouth_candidates:
                errors.append(f"trace {index} has invalid coast ports")
        elif trace.termination == "river":
            if trace.confluence is None or trace.confluence not in river_cells:
                errors.append(f"trace {index} has invalid confluence")
        else:
            errors.append(f"trace {index} has invalid termination")

    # Undirected cycle check.  Each accepted tributary should attach to an
    # older forest at no more than one endpoint.
    adjacency: dict[Cell, set[Cell]] = {cell: set() for cell in river_cells}
    for start, end in world.river_edges:
        adjacency[start].add(end)
        adjacency[end].add(start)
    seen: set[Cell] = set()
    for root in sorted(river_cells, key=lambda cell: (cell[1], cell[0])):
        if root in seen:
            continue
        stack = [(root, None)]
        while stack:
            cell, parent = stack.pop()
            if cell in seen:
                errors.append("river graph contains a cycle")
                stack.clear()
                break
            seen.add(cell)
            for neighbor in adjacency[cell]:
                if neighbor != parent:
                    stack.append((neighbor, cell))

    # No stage-4 water may become river, and the only non-river mutation is
    # Civ-I's forest-to-jungle stage-5 ecology rule.
    allowed_nonriver = {
        (int(authority.Terrain.FOREST), int(authority.Terrain.JUNGLE)),
    }
    for y in range(height):
        for x in range(width):
            before, after = int(stage4[y, x]), int(terrain[y, x])
            if after == river_code:
                if before == water_code:
                    errors.append("river overwrote WATER")
            elif before != after and (before, after) not in allowed_nonriver:
                errors.append(f"illegal non-river terrain mutation {before}->{after}")

    return HydrologyValidation(
        valid=not errors,
        errors=tuple(errors),
        river_cells=len(river_cells),
        recorded_edges=len(recorded),
        raw_adjacencies=len(raw),
        coast_terminations=sum(trace.termination == "coast" for trace in world.traces),
        confluences=sum(trace.termination == "river" for trace in world.traces),
    )


__all__ = [
    "Cell",
    "Edge",
    "HydrologyFields",
    "HydrologyValidation",
    "ModernHydrologyConfig",
    "ModernHydrologyWorld",
    "ModernRiverTrace",
    "build_hydrology_fields",
    "build_stage4",
    "generate_modern_hydrology",
    "validate_modern_world",
    "world_periodic_noise",
]
