"""Curvature-regularized continuous refinement of the immutable V11 pilot.

V12 stays new-world and corridor-first.  It consumes V11's continuous
subcell corridors and hierarchy, fits relief-aware elastic splines in world
space, and only then derives its own Civ River cells and ordered edges.  V11,
legacy snapshots and the fixed-port fallback remain untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.interpolate import PchipInterpolator

from .continuous_hydrology_v11 import (
    Cell,
    ContinuousHydrologyWorldV11,
    ContinuousMouthV11,
    Edge,
    FineCell,
    FlowSampleV11,
    Point,
    _expected_undirected,
    _raw_adjacencies,
    _sample_potential,
    _stable_hash,
    generate_continuous_hydrology_v11,
    rasterize_centerline_v11,
)


@dataclass(frozen=True)
class ContinuousHydrologyConfigV12:
    control_spacing_cells: float = 0.64
    sample_spacing_cells: float = 0.045
    elastic_iterations: int = 22
    mountain_clearance_cells: float = 0.44
    hill_clearance_cells: float = 0.34
    max_uphill_fraction: float = 0.34

    def __post_init__(self) -> None:
        if not 0.45 <= self.control_spacing_cells <= 0.9:
            raise ValueError("V12 control spacing must remain in the pilot band")
        if not 0.025 <= self.sample_spacing_cells <= 0.08:
            raise ValueError("V12 sample spacing must remain in the pilot band")
        if self.elastic_iterations < 4:
            raise ValueError("V12 elastic fit needs at least four iterations")


@dataclass(frozen=True)
class JunctionPatchV12:
    parent_trace: int
    tributary_trace: int
    point: Point
    downstream_tangent: Point
    incoming_tangent: Point
    approach_degrees: float
    offcentre_cells: float


@dataclass(frozen=True)
class ContinuousTraceV12:
    trace_id: int
    kind: str
    parent_trace: int | None
    attachment_point: Point | None
    source_cell: Cell
    termination: str
    mouth_water_cell: Cell | None
    shoreline_point: Point | None
    corridor_fine_path: tuple[FineCell, ...]
    samples: tuple[FlowSampleV11, ...]
    raster_cells: tuple[Cell, ...]
    raster_edges: tuple[Edge, ...]
    uphill_fraction: float
    angular_energy: float
    min_relief_clearance: float

    @property
    def points(self) -> tuple[Point, ...]:
        return tuple(sample.point for sample in self.samples)


@dataclass(frozen=True)
class ContinuousHydrologyWorldV12:
    stage4_terrain: tuple[tuple[int, ...], ...]
    terrain: tuple[tuple[int, ...], ...]
    traces: tuple[ContinuousTraceV12, ...]
    river_cells: tuple[Cell, ...]
    river_edges: tuple[Edge, ...]
    mouths: tuple[ContinuousMouthV11, ...]
    junctions: tuple[JunctionPatchV12, ...]
    fields: Any
    water_mask: tuple[tuple[bool, ...], ...]
    tile_px: int
    world_width: int
    world_height: int
    seed: int
    subcells_per_cell: int
    derivative_label: str
    source_v11: ContinuousHydrologyWorldV11

    @property
    def world_width_px(self) -> int:
        return self.world_width * self.tile_px

    def snapshot_extension(self) -> dict[str, Any]:
        return {
            "schema": "project1991.continuous-hydrology/v12",
            "generator": "modern-v12-elastic-corridor",
            "derivative": True,
            "source_schema": "project1991.continuous-hydrology/v11",
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
                    "shoreline_point": list(trace.shoreline_point) if trace.shoreline_point else None,
                    "points": [[round(sample.point[0], 7), round(sample.point[1], 7)] for sample in trace.samples],
                    "upstream_area": [round(sample.upstream_area, 5) for sample in trace.samples],
                    "strahler": [sample.strahler for sample in trace.samples],
                    "width_px": [round(sample.width_px, 5) for sample in trace.samples],
                    "raster_cells": [[x, y] for x, y in trace.raster_cells],
                    "angular_energy": round(trace.angular_energy, 7),
                    "min_relief_clearance": round(trace.min_relief_clearance, 7),
                }
                for trace in self.traces
            ],
            "junctions": [
                {
                    "parent_trace": item.parent_trace,
                    "tributary_trace": item.tributary_trace,
                    "point": [round(item.point[0], 7), round(item.point[1], 7)],
                    "approach_degrees": round(item.approach_degrees, 5),
                    "offcentre_cells": round(item.offcentre_cells, 5),
                }
                for item in self.junctions
            ],
        }


@dataclass(frozen=True)
class ContinuousAuditV12:
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
    continuous_self_touches: int
    raster_authority_mismatches: int
    max_uphill_fraction: float
    mean_angular_energy: float
    source_mean_angular_energy: float
    angular_energy_reduction: float
    min_relief_clearance: float
    max_junction_angle: float


def _unit(vector: Point, fallback: Point = (1.0, 0.0)) -> Point:
    length = math.hypot(vector[0], vector[1])
    if length <= 1e-12:
        return fallback
    return vector[0] / length, vector[1] / length


def _wrapped_dx(first: float, second: float, width: int) -> float:
    raw = second - first
    return raw - round(raw / width) * width


def _unwrap_points(points: Sequence[Point], width: int) -> list[Point]:
    if not points:
        return []
    result = [points[0]]
    for point in points[1:]:
        previous = result[-1]
        result.append((previous[0] + _wrapped_dx(previous[0], point[0], width), point[1]))
    return result


def _arc_lengths(points: Sequence[Point]) -> np.ndarray:
    if not points:
        return np.zeros(0, dtype=np.float64)
    lengths = [0.0]
    for first, second in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.hypot(second[0] - first[0], second[1] - first[1]))
    return np.asarray(lengths, dtype=np.float64)


def _polyline_point(points: Sequence[Point], arc: np.ndarray, fraction: float) -> Point:
    if len(points) == 1 or arc[-1] <= 1e-12:
        return points[0]
    target = max(0.0, min(1.0, fraction)) * arc[-1]
    index = min(len(points) - 2, int(np.searchsorted(arc, target, side="right") - 1))
    span = max(1e-12, float(arc[index + 1] - arc[index]))
    local = (target - arc[index]) / span
    return (
        points[index][0] + (points[index + 1][0] - points[index][0]) * local,
        points[index][1] + (points[index + 1][1] - points[index][1]) * local,
    )


def _point_fraction(points: Sequence[Point], wanted: Point, width: int) -> float:
    points = _unwrap_points(points, width)
    wanted_x = wanted[0] + round((points[0][0] - wanted[0]) / width) * width
    arc = _arc_lengths(points)
    best = (math.inf, 0.0)
    for index, (first, second) in enumerate(zip(points, points[1:])):
        vx, vy = second[0] - first[0], second[1] - first[1]
        denominator = vx * vx + vy * vy
        t = 0.0 if denominator <= 1e-12 else max(0.0, min(1.0, ((wanted_x - first[0]) * vx + (wanted[1] - first[1]) * vy) / denominator))
        px, py = first[0] + vx * t, first[1] + vy * t
        candidate = ((px - wanted_x) ** 2 + (py - wanted[1]) ** 2, (arc[index] + t * (arc[index + 1] - arc[index])) / max(arc[-1], 1e-12))
        if candidate < best:
            best = candidate
    return float(best[1])


def _source_foot(points: Sequence[Point], source_cell: Cell, seed: int, width: int) -> Point:
    arc = _arc_lengths(points)
    probe = _polyline_point(points, arc, min(1.0, 0.72 / max(arc[-1], 1e-12)))
    center_x = source_cell[0] + 0.5
    center_x += round((points[0][0] - center_x) / width) * width
    center = (center_x, source_cell[1] + 0.5)
    direction = _unit((probe[0] - center[0], probe[1] - center[1]))
    normal = (-direction[1], direction[0])
    jitter = ((_stable_hash(seed, source_cell[0], source_cell[1], 2503) / 2**32) - 0.5) * 0.10
    point = (center[0] + direction[0] * 0.43 + normal[0] * jitter, center[1] + direction[1] * 0.43 + normal[1] * jitter)
    # The source stays inside its authoritative highland cell, at the downhill
    # foot rather than beneath the centre of the relief stamp.
    return (
        min(center_x + 0.47, max(center_x - 0.47, point[0])),
        min(source_cell[1] + 0.97, max(source_cell[1] + 0.03, point[1])),
    )


def _relocate_source_start(points: Sequence[Point], source_cell: Cell, seed: int, width: int) -> list[Point]:
    result = list(points)
    original_arc = _arc_lengths(result)
    if len(result) < 2 or original_arc[-1] <= 1e-12:
        return result
    foot = _source_foot(result, source_cell, seed, width)
    anchor_distance = min(0.68, max(0.38, original_arc[-1] * 0.22))
    anchor_fraction = anchor_distance / original_arc[-1]
    anchor = _polyline_point(result, original_arc, anchor_fraction)
    for index, distance in enumerate(original_arc):
        if distance > anchor_distance:
            break
        t = float(distance / max(anchor_distance, 1e-12))
        # Cubic easing gives the source one clean downhill tangent and rejoins
        # the terrain-routed corridor without the previous backtracking hook.
        eased = t * t * (3.0 - 2.0 * t)
        result[index] = (foot[0] + (anchor[0] - foot[0]) * eased, foot[1] + (anchor[1] - foot[1]) * eased)
    result[0] = foot
    return result


def _relief_obstacles(stage4: np.ndarray, authority) -> tuple[tuple[Cell, float], ...]:
    mountains = int(authority.Terrain.MOUNTAINS)
    hills = int(authority.Terrain.HILLS)
    result = []
    for y, x in np.argwhere((stage4 == mountains) | (stage4 == hills)):
        code = int(stage4[int(y), int(x)])
        result.append(((int(x), int(y)), 1.0 if code == mountains else 0.0))
    return tuple(result)


def _push_relief(
    point: Point,
    obstacles: Sequence[tuple[Cell, float]],
    source_cell: Cell,
    width: int,
    config: ContinuousHydrologyConfigV12,
) -> Point:
    px, py = point
    push_x = push_y = 0.0
    for cell, mountain in obstacles:
        if cell == source_cell:
            continue
        cx = cell[0] + 0.5
        cx += round((px - cx) / width) * width
        cy = cell[1] + 0.54
        dx, dy = px - cx, py - cy
        distance = math.hypot(dx, dy)
        radius = config.mountain_clearance_cells if mountain else config.hill_clearance_cells
        if distance >= radius:
            continue
        ux, uy = _unit((dx, dy), (0.0, -1.0))
        strength = (radius - distance) * 0.72
        push_x += ux * strength
        push_y += uy * strength
    return px + push_x, py + push_y


def _land_point(point: Point, stage4: np.ndarray, water_code: int, *, boundary: bool = False) -> bool:
    if boundary:
        point = (point[0], point[1] - 1e-8 if abs(point[1] - round(point[1])) < 1e-9 else point[1])
    x, y = int(math.floor(point[0])) % stage4.shape[1], int(math.floor(point[1]))
    return 0 <= y < stage4.shape[0] and int(stage4[y, x]) != water_code


def _build_controls(
    source_points: Sequence[Point],
    source_cell: Cell,
    stage4: np.ndarray,
    water_code: int,
    obstacles: Sequence[tuple[Cell, float]],
    seed: int,
    config: ContinuousHydrologyConfigV12,
    *,
    final_point: Point,
) -> tuple[list[Point], list[Point]]:
    width = stage4.shape[1]
    original = _relocate_source_start(_unwrap_points(source_points, width), source_cell, seed, width)
    final_x = final_point[0] + round((original[-1][0] - final_point[0]) / width) * width
    original[-1] = (final_x, final_point[1])
    arc = _arc_lengths(original)
    count = max(4, int(math.ceil(arc[-1] / config.control_spacing_cells)) + 1)
    controls = [_polyline_point(original, arc, index / (count - 1)) for index in range(count)]
    baseline = list(controls)
    for _ in range(config.elastic_iterations):
        updated = [controls[0]]
        for index in range(1, len(controls) - 1):
            fraction = index / (len(controls) - 1)
            data = _polyline_point(original, arc, fraction)
            laplace = ((controls[index - 1][0] + controls[index + 1][0]) * 0.5, (controls[index - 1][1] + controls[index + 1][1]) * 0.5)
            candidate = (
                controls[index][0] * 0.42 + laplace[0] * 0.44 + data[0] * 0.14,
                controls[index][1] * 0.42 + laplace[1] * 0.44 + data[1] * 0.14,
            )
            candidate = _push_relief(candidate, obstacles, source_cell, width, config)
            if not _land_point(candidate, stage4, water_code):
                candidate = ((candidate[0] + controls[index][0]) * 0.5, (candidate[1] + controls[index][1]) * 0.5)
            if not _land_point(candidate, stage4, water_code):
                candidate = controls[index]
            updated.append(candidate)
        updated.append(controls[-1])
        controls = updated
    phase = _stable_hash(seed, source_cell[0], source_cell[1], 2563) / 2**32 * math.tau
    meandered = [controls[0]]
    for index in range(1, len(controls) - 1):
        fraction = index / (len(controls) - 1)
        tangent = _unit((controls[index + 1][0] - controls[index - 1][0], controls[index + 1][1] - controls[index - 1][1]))
        normal = (-tangent[1], tangent[0])
        wave = math.sin(math.pi * fraction) * (
            0.130 * math.sin(math.tau * fraction + phase)
            + 0.045 * math.sin(math.tau * 2.0 * fraction - phase * 0.57)
        )
        candidate = (controls[index][0] + normal[0] * wave, controls[index][1] + normal[1] * wave)
        if not _land_point(candidate, stage4, water_code):
            candidate = controls[index]
        meandered.append(candidate)
    meandered.append(controls[-1])
    controls = meandered
    return baseline, controls


def _catmull_point(controls: Sequence[Point], fraction: float) -> Point:
    if len(controls) == 1:
        return controls[0]
    scaled = max(0.0, min(1.0, fraction)) * (len(controls) - 1)
    index = min(len(controls) - 2, int(math.floor(scaled)))
    t = scaled - index
    p0 = controls[max(0, index - 1)]
    p1 = controls[index]
    p2 = controls[index + 1]
    p3 = controls[min(len(controls) - 1, index + 2)]
    tension = 0.28
    m1 = ((p2[0] - p0[0]) * (1.0 - tension) * 0.5, (p2[1] - p0[1]) * (1.0 - tension) * 0.5)
    m2 = ((p3[0] - p1[0]) * (1.0 - tension) * 0.5, (p3[1] - p1[1]) * (1.0 - tension) * 0.5)
    t2, t3 = t * t, t * t * t
    h00, h10, h01, h11 = 2 * t3 - 3 * t2 + 1, t3 - 2 * t2 + t, -2 * t3 + 3 * t2, t3 - t2
    return (
        h00 * p1[0] + h10 * m1[0] + h01 * p2[0] + h11 * m2[0],
        h00 * p1[1] + h10 * m1[1] + h01 * p2[1] + h11 * m2[1],
    )


def _sample_controls(
    controls: Sequence[Point],
    spacing: float,
    extra_fractions: Iterable[float] = (),
) -> tuple[list[Point], tuple[float, ...]]:
    coarse = [_catmull_point(controls, index / 120.0) for index in range(121)]
    length = float(_arc_lengths(coarse)[-1])
    count = max(12, int(math.ceil(length / spacing)) + 1)
    fractions = {index / (count - 1) for index in range(count)}
    fractions.update(max(0.0, min(1.0, float(value))) for value in extra_fractions)
    ordered = tuple(sorted(fractions))
    return [_catmull_point(controls, fraction) for fraction in ordered], ordered


def _sample_pinned_controls(
    controls: Sequence[Point],
    spacing: float,
    pins: Sequence[tuple[float, Point]],
    width: int,
) -> tuple[list[Point], tuple[float, ...]]:
    knot_count = max(4, int(math.ceil(len(controls) / 2.0)) + 1)
    knot_fractions = {index / (knot_count - 1) for index in range(knot_count)}
    knot_fractions.update(float(fraction) for fraction, _point in pins)
    knots = tuple(sorted(knot_fractions))
    values = [_catmull_point(controls, fraction) for fraction in knots]
    for pin_fraction, pin in pins:
        index = min(range(len(knots)), key=lambda item: abs(knots[item] - pin_fraction))
        pin_x = pin[0] + round((values[index][0] - pin[0]) / width) * width
        values[index] = (pin_x, pin[1])
    x_spline = PchipInterpolator(knots, [point[0] for point in values])
    y_spline = PchipInterpolator(knots, [point[1] for point in values])
    probe_fractions = np.linspace(0.0, 1.0, 161)
    probe = [(float(x_spline(value)), float(y_spline(value))) for value in probe_fractions]
    length = float(_arc_lengths(probe)[-1])
    count = max(12, int(math.ceil(length / spacing)) + 1)
    fractions = {index / (count - 1) for index in range(count)}
    fractions.update(float(fraction) for fraction, _point in pins)
    ordered = tuple(sorted(fractions))
    return [(float(x_spline(value)), float(y_spline(value))) for value in ordered], ordered


def _clear_attachment(
    point: Point,
    cell: Cell,
    stage4: np.ndarray,
    authority,
    seed: int,
    config: ContinuousHydrologyConfigV12,
) -> Point:
    code = int(stage4[cell[1], cell[0]])
    if code not in (int(authority.Terrain.HILLS), int(authority.Terrain.MOUNTAINS)):
        base = round((point[0] - (cell[0] + 0.5)) / stage4.shape[1]) * stage4.shape[1]
        return (
            min(cell[0] + base + 0.76, max(cell[0] + base + 0.24, point[0])),
            min(cell[1] + 0.76, max(cell[1] + 0.24, point[1])),
        )
    radius = config.mountain_clearance_cells if code == int(authority.Terrain.MOUNTAINS) else config.hill_clearance_cells
    cx = cell[0] + 0.5
    cx += round((point[0] - cx) / stage4.shape[1]) * stage4.shape[1]
    cy = cell[1] + 0.54
    dx, dy = point[0] - cx, point[1] - cy
    distance = math.hypot(dx, dy)
    wanted = radius + 0.055
    if distance >= wanted:
        candidate = point
    else:
        if distance <= 1e-8:
            angle = _stable_hash(seed, cell[0], cell[1], 2521) / 2**32 * math.tau
            dx, dy = math.cos(angle), math.sin(angle)
        else:
            dx, dy = dx / distance, dy / distance
        candidate = (cx + dx * wanted, cy + dy * wanted)
    base = round((cx - (cell[0] + 0.5)) / stage4.shape[1]) * stage4.shape[1]
    return (
        min(cell[0] + 0.82 + base, max(cell[0] + 0.18 + base, candidate[0])),
        min(cell[1] + 0.82, max(cell[1] + 0.18, candidate[1])),
    )


def _flow_attachment(
    parent_trace,
    child_trace,
    fraction: float,
    stage4: np.ndarray,
    authority,
    seed: int,
    config: ContinuousHydrologyConfigV12,
) -> Point:
    cell = child_trace.raster_cells[-1]
    parent_points = _unwrap_points(parent_trace.points, stage4.shape[1])
    arc = _arc_lengths(parent_points)
    before = _polyline_point(parent_points, arc, max(0.0, fraction - 0.035))
    after = _polyline_point(parent_points, arc, min(1.0, fraction + 0.035))
    tangent = _unit((after[0] - before[0], after[1] - before[1]))
    normal = (-tangent[1], tangent[0])
    side = -1.0 if _stable_hash(seed, parent_trace.trace_id, 0, 2539) & 1 else 1.0
    code = int(stage4[cell[1], cell[0]])
    if code == int(authority.Terrain.MOUNTAINS):
        normal_offset = config.mountain_clearance_cells + 0.045
    elif code == int(authority.Terrain.HILLS):
        normal_offset = config.hill_clearance_cells + 0.045
    else:
        normal_offset = 0.12
    tangent_jitter = ((_stable_hash(seed, child_trace.trace_id, cell[0], 2543) / 2**32) - 0.5) * 0.10
    centre_x = cell[0] + 0.5
    reference = child_trace.attachment_point[0]
    centre_x += round((reference - centre_x) / stage4.shape[1]) * stage4.shape[1]
    candidate = (
        centre_x + normal[0] * side * normal_offset + tangent[0] * tangent_jitter,
        cell[1] + 0.5 + normal[1] * side * normal_offset + tangent[1] * tangent_jitter,
    )
    return (
        min(centre_x + 0.43, max(centre_x - 0.43, candidate[0])),
        min(cell[1] + 0.93, max(cell[1] + 0.07, candidate[1])),
    )


def _pin_curve(
    points: list[Point],
    fractions: Sequence[float],
    pins: Sequence[tuple[float, Point]],
    width: int,
) -> list[Point]:
    result = list(points)
    for pin_fraction, pin in pins:
        index = min(range(len(fractions)), key=lambda item: abs(fractions[item] - pin_fraction))
        pin_x = pin[0] + round((result[index][0] - pin[0]) / width) * width
        dx, dy = pin_x - result[index][0], pin[1] - result[index][1]
        # Move the whole local arc, not just one sample. A narrow correction
        # creates an S-kink even when the attachment itself is legal.
        radius = 0.30
        for item, fraction in enumerate(fractions):
            distance = abs(fraction - pin_fraction)
            if distance >= radius:
                continue
            weight = 0.5 + 0.5 * math.cos(math.pi * distance / radius)
            result[item] = (result[item][0] + dx * weight, result[item][1] + dy * weight)
        result[index] = (pin_x, pin[1])
    return result


def _relax_pinned_curve(
    points: Sequence[Point],
    fractions: Sequence[float],
    pins: Sequence[tuple[float, Point]],
    stage4: np.ndarray,
    water_code: int,
    iterations: int = 36,
) -> list[Point]:
    result = list(points)
    fixed = {0, len(result) - 1}
    for pin_fraction, pin in pins:
        index = min(range(len(fractions)), key=lambda item: abs(fractions[item] - pin_fraction))
        fixed.add(index)
        pin_x = pin[0] + round((result[index][0] - pin[0]) / stage4.shape[1]) * stage4.shape[1]
        result[index] = (pin_x, pin[1])
    for _ in range(iterations):
        updated = list(result)
        for index in range(1, len(result) - 1):
            if index in fixed:
                continue
            candidate = (
                result[index - 1][0] * 0.24 + result[index][0] * 0.52 + result[index + 1][0] * 0.24,
                result[index - 1][1] * 0.24 + result[index][1] * 0.52 + result[index + 1][1] * 0.24,
            )
            if _land_point(candidate, stage4, water_code):
                updated[index] = candidate
        result = updated
    return result


def _fraction_point_tangent(points: Sequence[Point], fractions: Sequence[float], fraction: float) -> tuple[Point, Point]:
    index = min(range(len(fractions)), key=lambda item: abs(fractions[item] - fraction))
    before = points[max(0, index - 3)]
    after = points[min(len(points) - 1, index + 3)]
    return points[index], _unit((after[0] - before[0], after[1] - before[1]))


def _select_parent_attachment(
    points: Sequence[Point],
    target_cell: Cell,
    preferred_fraction: float,
    width: int,
) -> tuple[Point, Point]:
    arc = _arc_lengths(points)
    candidates = []
    for index in range(2, len(points) - 2):
        point = points[index]
        cell = (int(math.floor(point[0])) % width, int(math.floor(point[1])))
        if cell != target_cell:
            continue
        local_x = point[0] - math.floor(point[0])
        local_y = point[1] - math.floor(point[1])
        margin = min(local_x, 1.0 - local_x, local_y, 1.0 - local_y)
        fraction = arc[index] / max(arc[-1], 1e-12)
        score = abs(fraction - preferred_fraction) * 0.34 - margin
        candidates.append((score, index))
    if not candidates:
        raise ValueError(f"smoothed parent misses attachment cell {target_cell}")
    _score, index = min(candidates)
    before = points[max(0, index - 3)]
    after = points[min(len(points) - 1, index + 3)]
    return points[index], _unit((after[0] - before[0], after[1] - before[1]))


def _segment_land(points: Sequence[Point], stage4: np.ndarray, water_code: int, *, primary: bool) -> bool:
    for index, (first, second) in enumerate(zip(points, points[1:])):
        length = math.hypot(second[0] - first[0], second[1] - first[1])
        count = max(2, int(math.ceil(length / 0.025)))
        endpoint = not (primary and index == len(points) - 2)
        for t in np.linspace(0.0, 1.0, count, endpoint=endpoint):
            point = (first[0] + (second[0] - first[0]) * float(t), first[1] + (second[1] - first[1]) * float(t))
            if not _land_point(point, stage4, water_code):
                return False
    return True


def _blend_controls(baseline: Sequence[Point], smooth: Sequence[Point], amount: float) -> list[Point]:
    result = []
    for first, second in zip(baseline, smooth):
        result.append((first[0] + (second[0] - first[0]) * amount, first[1] + (second[1] - first[1]) * amount))
    return result


def _dense_elastic_fallback(
    source_points: Sequence[Point],
    source_cell: Cell,
    final_point: Point,
    stage4: np.ndarray,
    water_code: int,
    obstacles: Sequence[tuple[Cell, float]],
    seed: int,
    config: ContinuousHydrologyConfigV12,
    rounds: int,
) -> list[Point]:
    """Narrow-corridor fallback when a broad spline would invent a chord."""

    width = stage4.shape[1]
    points = _relocate_source_start(_unwrap_points(source_points, width), source_cell, seed, width)
    final_x = final_point[0] + round((points[-1][0] - final_point[0]) / width) * width
    old_final = points[-1]
    delta = (final_x - old_final[0], final_point[1] - old_final[1])
    arc = _arc_lengths(points)
    for index in range(len(points)):
        fraction = arc[index] / max(arc[-1], 1e-12)
        blend = max(0.0, min(1.0, (fraction - 0.72) / 0.28))
        blend = blend * blend * (3.0 - 2.0 * blend)
        points[index] = (points[index][0] + delta[0] * blend, points[index][1] + delta[1] * blend)
    points[-1] = (final_x, final_point[1])
    for _ in range(rounds):
        updated = [points[0]]
        for index in range(1, len(points) - 1):
            candidate = (
                points[index - 1][0] * 0.22 + points[index][0] * 0.56 + points[index + 1][0] * 0.22,
                points[index - 1][1] * 0.22 + points[index][1] * 0.56 + points[index + 1][1] * 0.22,
            )
            candidate = _push_relief(candidate, obstacles, source_cell, width, config)
            if not _land_point(candidate, stage4, water_code):
                candidate = points[index]
            updated.append(candidate)
        updated.append(points[-1])
        points = updated
    return points


def _junction_controls(controls: list[Point], attachment: Point, downstream: Point) -> list[Point]:
    controls = list(controls)
    attachment_x = attachment[0] + round((controls[-1][0] - attachment[0]) / 80.0) * 80.0
    attachment = (attachment_x, attachment[1])
    incoming = _unit((attachment[0] - controls[-2][0], attachment[1] - controls[-2][1]))
    downstream = _unit(downstream)
    blended = _acute_merge_direction(incoming, downstream)
    handle = min(0.46, max(0.24, math.hypot(attachment[0] - controls[-2][0], attachment[1] - controls[-2][1])))
    controls[-2] = (attachment[0] - blended[0] * handle, attachment[1] - blended[1] * handle)
    controls[-1] = attachment
    return controls


def _acute_merge_direction(incoming: Point, downstream: Point, max_degrees: float = 44.0) -> Point:
    incoming = _unit(incoming)
    downstream = _unit(downstream)
    dot = max(-1.0, min(1.0, incoming[0] * downstream[0] + incoming[1] * downstream[1]))
    angle = math.degrees(math.acos(dot))
    if angle <= max_degrees:
        return incoming
    cross = downstream[0] * incoming[1] - downstream[1] * incoming[0]
    side = -1.0 if cross < 0.0 else 1.0
    normal = (-downstream[1] * side, downstream[0] * side)
    radians = math.radians(max_degrees)
    return _unit(
        (downstream[0] * math.cos(radians) + normal[0] * math.sin(radians), downstream[1] * math.cos(radians) + normal[1] * math.sin(radians))
    )


def _align_junction_points(points: Sequence[Point], downstream: Point, radius: float = 0.66) -> list[Point]:
    result = list(points)
    if len(result) < 4:
        return result
    arc = _arc_lengths(result)
    incoming = _unit((result[-1][0] - result[max(0, len(result) - 8)][0], result[-1][1] - result[max(0, len(result) - 8)][1]))
    downstream = _unit(downstream)
    desired = _acute_merge_direction(incoming, downstream)
    target = result[-1]
    for index in range(len(result) - 1):
        remaining = arc[-1] - arc[index]
        if remaining >= radius:
            continue
        weight = 1.0 - remaining / radius
        weight = weight * weight * (3.0 - 2.0 * weight)
        ideal = (target[0] - desired[0] * remaining, target[1] - desired[1] * remaining)
        result[index] = (
            result[index][0] + (ideal[0] - result[index][0]) * weight,
            result[index][1] + (ideal[1] - result[index][1]) * weight,
        )
    return result


def _project_to_cell_corridor(
    candidate: Sequence[Point],
    reference: Sequence[Point],
    allowed_cells: set[Cell],
    width: int,
) -> list[Point]:
    result = []
    for point, fallback in zip(candidate, reference):
        chosen = fallback
        for amount in (1.0, 0.78, 0.56, 0.34, 0.16, 0.0):
            trial = (fallback[0] + (point[0] - fallback[0]) * amount, fallback[1] + (point[1] - fallback[1]) * amount)
            cell = (int(math.floor(trial[0])) % width, int(math.floor(trial[1])))
            if cell in allowed_cells:
                chosen = trial
                break
        result.append(chosen)
    return result


def _clear_curve_relief(
    points: Sequence[Point],
    obstacles: Sequence[tuple[Cell, float]],
    source_cell: Cell,
    stage4: np.ndarray,
    water_code: int,
    config: ContinuousHydrologyConfigV12,
) -> list[Point]:
    result = list(points)
    kernel = np.asarray((1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0), dtype=np.float64)
    kernel /= kernel.sum()
    for _pass in range(4):
        arc = _arc_lengths(result)
        displacements = np.zeros((len(result), 2), dtype=np.float64)
        for index in range(1, len(result) - 1):
            if arc[-1] > 0.0 and arc[index] / arc[-1] < 0.10:
                continue
            candidate = result[index]
            for _ in range(5):
                candidate = _push_relief(candidate, obstacles, source_cell, stage4.shape[1], config)
            displacements[index] = (candidate[0] - result[index][0], candidate[1] - result[index][1])
        smooth_x = np.convolve(displacements[:, 0], kernel, mode="same")
        smooth_y = np.convolve(displacements[:, 1], kernel, mode="same")
        updated = list(result)
        for index in range(1, len(result) - 1):
            candidate = (result[index][0] + float(smooth_x[index]), result[index][1] + float(smooth_y[index]))
            if _land_point(candidate, stage4, water_code):
                updated[index] = candidate
        result = updated
    return result


def _tangent(controls: Sequence[Point], fraction: float) -> Point:
    epsilon = 1e-4
    first = _catmull_point(controls, max(0.0, fraction - epsilon))
    second = _catmull_point(controls, min(1.0, fraction + epsilon))
    return _unit((second[0] - first[0], second[1] - first[1]))


def _resample_for_angles(points: Sequence[Point], spacing: float = 0.18) -> list[Point]:
    arc = _arc_lengths(points)
    if len(points) < 2 or arc[-1] <= 1e-12:
        return list(points)
    count = max(3, int(math.ceil(arc[-1] / spacing)) + 1)
    return [_polyline_point(points, arc, index / (count - 1)) for index in range(count)]


def _angular_energy(points: Sequence[Point]) -> float:
    points = _resample_for_angles(points)
    if len(points) < 3:
        return 0.0
    total = 0.0
    for first, middle, last in zip(points, points[1:], points[2:]):
        a = _unit((middle[0] - first[0], middle[1] - first[1]))
        b = _unit((last[0] - middle[0], last[1] - middle[1]))
        angle = math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1])))
        total += angle * angle
    return total / max(1, len(points) - 2)


def _continuous_self_touch(points: Sequence[Point], width: int) -> bool:
    sampled = _resample_for_angles(points, 0.11)
    for index, point in enumerate(sampled):
        for other_index in range(index + 7, len(sampled)):
            other = sampled[other_index]
            dx = _wrapped_dx(point[0], other[0], width)
            if dx * dx + (other[1] - point[1]) ** 2 < 0.075**2:
                return True
    return False


def _relief_clearance(
    points: Sequence[Point],
    obstacles: Sequence[tuple[Cell, float]],
    source_cell: Cell,
    width: int,
) -> float:
    result = math.inf
    arc = _arc_lengths(points)
    for index, point in enumerate(points):
        if arc[-1] > 0 and arc[index] / arc[-1] < 0.10:
            continue
        for cell, _mountain in obstacles:
            if cell == source_cell:
                continue
            cx = cell[0] + 0.5
            cx += round((point[0] - cx) / width) * width
            result = min(result, math.hypot(point[0] - cx, point[1] - (cell[1] + 0.54)))
    return result if math.isfinite(result) else 99.0


def _metadata_samples(source_trace, points: Sequence[Point], fields, width: int) -> tuple[FlowSampleV11, ...]:
    source_points = _unwrap_points(source_trace.points, width)
    source_arc = _arc_lengths(source_points)
    target_arc = _arc_lengths(points)
    source_fractions = source_arc / max(source_arc[-1], 1e-12)
    areas = np.asarray([sample.upstream_area for sample in source_trace.samples], dtype=np.float64)
    widths = np.asarray([sample.width_px for sample in source_trace.samples], dtype=np.float64)
    orders = np.asarray([sample.strahler for sample in source_trace.samples], dtype=np.int16)
    result = []
    previous_width = 0.0
    previous_area = 0.0
    previous_order = 1
    for index, point in enumerate(points):
        fraction = float(target_arc[index] / max(target_arc[-1], 1e-12))
        area = max(previous_area, float(np.interp(fraction, source_fractions, areas)))
        base_width = float(np.interp(fraction, source_fractions, widths))
        if source_trace.kind == "tributary":
            base_width = min(8.8, max(7.0, base_width * 1.22 + 1.20))
            taper_end = 0.10
            source_width = 1.40
        else:
            base_width = min(17.6, max(12.0, base_width * 1.48 + 1.10))
            taper_end = 0.12
            source_width = 1.65
        taper = min(1.0, max(0.0, fraction / taper_end))
        taper = taper * taper * (3.0 - 2.0 * taper)
        local_width = source_width + (base_width - source_width) * taper
        local_width = max(previous_width, local_width)
        source_index = min(len(orders) - 1, int(np.searchsorted(source_fractions, fraction, side="right") - 1))
        order = max(previous_order, int(orders[max(0, source_index)]))
        result.append(FlowSampleV11(point, area, order, local_width, _sample_potential(fields, point, width)))
        previous_area, previous_width, previous_order = area, local_width, order
    return tuple(result)


def _uphill_fraction(samples: Sequence[FlowSampleV11]) -> float:
    rises = sum(second.potential > first.potential + 0.004 for first, second in zip(samples, samples[1:]))
    return rises / max(1, len(samples) - 1)


def _stronger_mouths(traces: Sequence[ContinuousTraceV12], source_mouths: Sequence[ContinuousMouthV11], tile_px: int, seed: int):
    result = []
    by_trace = {trace.trace_id: trace for trace in traces}
    for mouth in source_mouths:
        trace = by_trace[mouth.trace_id]
        last = trace.samples[-1]
        sign = -1.0 if _stable_hash(seed, mouth.river_cell[0], mouth.river_cell[1], 2551) & 1 else 1.0
        asymmetry = mouth.asymmetry * 1.45 + sign * tile_px * 0.055
        result.append(
            replace(
                mouth,
                shoreline_point=(trace.shoreline_point[0] * tile_px, trace.shoreline_point[1] * tile_px),
                start_width=max(mouth.start_width, last.width_px * 1.22),
                end_width=min(tile_px * 0.62, max(tile_px * 0.34, last.width_px * 4.15)),
                depth=max(tile_px * 0.76, mouth.depth * 1.22),
                asymmetry=asymmetry,
                upstream_area=last.upstream_area,
                strahler=last.strahler,
            )
        )
    return tuple(result)


def generate_continuous_hydrology_v12(
    authority,
    seed: int,
    land_mass: int = 1,
    temperature: int = 1,
    climate: int = 1,
    age: int = 1,
    *,
    config: ContinuousHydrologyConfigV12 | None = None,
    tile_px: int = 96,
) -> ContinuousHydrologyWorldV12:
    config = config or ContinuousHydrologyConfigV12()
    source_world = generate_continuous_hydrology_v11(authority, seed, land_mass, temperature, climate, age, tile_px=tile_px)
    stage4 = np.asarray(source_world.stage4_terrain, dtype=np.int16)
    water_code, river_code = int(authority.Terrain.WATER), int(authority.Terrain.RIVER)
    width = source_world.world_width
    obstacles = _relief_obstacles(stage4, authority)
    source_by_id = {trace.trace_id: trace for trace in source_world.traces}
    attachment_fraction: dict[int, float] = {}
    children: dict[int, list[int]] = {}
    for trace in source_world.traces:
        if trace.parent_trace is None or trace.attachment_point is None:
            continue
        attachment_fraction[trace.trace_id] = _point_fraction(source_by_id[trace.parent_trace].points, trace.attachment_point, width)
        children.setdefault(trace.parent_trace, []).append(trace.trace_id)

    accepted_controls: dict[int, list[Point]] = {}
    accepted_fractions: dict[int, tuple[float, ...]] = {}
    accepted_points: dict[int, list[Point]] = {}
    accepted_attachment_points: dict[int, Point] = {}
    accepted_attachment_tangents: dict[int, Point] = {}
    accepted_cells: set[Cell] = set()
    accepted_edges: set[Edge] = set()
    traces: list[ContinuousTraceV12] = []
    junction_points: dict[int, Point] = {}

    order = [trace.trace_id for trace in source_world.traces if trace.kind == "primary"] + [
        trace.trace_id for trace in source_world.traces if trace.kind == "tributary"
    ]
    for trace_id in order:
        source_trace = source_by_id[trace_id]
        extra: list[float] = []
        if source_trace.kind == "primary":
            final_point = source_trace.shoreline_point
        else:
            parent_id = source_trace.parent_trace
            final_point = accepted_attachment_points[trace_id]
            junction_points[trace_id] = final_point
        baseline, smooth = _build_controls(
            source_trace.points,
            source_trace.source_cell,
            stage4,
            water_code,
            obstacles,
            seed,
            config,
            final_point=final_point,
        )
        if source_trace.kind == "tributary":
            parent_tangent = accepted_attachment_tangents[trace_id]
            smooth = _junction_controls(smooth, final_point, parent_tangent)
            baseline = _junction_controls(baseline, final_point, parent_tangent)

        accepted = None
        rejection_counts = {"land": 0, "self": 0, "raster": 0, "attach": 0, "conflict": 0, "uphill": 0}
        last_conflict = None
        last_uphill = None
        amounts = (1.0, 0.82, 0.64, 0.46, 0.28, 0.0)
        fit_options = (
            [(amount, radius) for amount in amounts for radius in (0.92, 0.78, 0.66, 0.52, 0.40, 0.30)]
            if source_trace.kind == "tributary"
            else [(amount, None) for amount in amounts]
        )
        for amount, junction_radius in fit_options:
            controls = _blend_controls(baseline, smooth, amount)
            if source_trace.kind == "tributary":
                parent_tangent = accepted_attachment_tangents[trace_id]
                controls = _junction_controls(controls, final_point, parent_tangent)
            points, fractions = _sample_controls(controls, config.sample_spacing_cells, extra)
            points = _clear_curve_relief(points, obstacles, source_trace.source_cell, stage4, water_code, config)
            if source_trace.kind == "tributary":
                reference_points = list(points)
                points = _align_junction_points(points, accepted_attachment_tangents[trace_id], radius=junction_radius)
                points = _project_to_cell_corridor(points, reference_points, set(source_trace.raster_cells), width)
            points[0] = controls[0]
            points[-1] = controls[-1]
            if not _segment_land(points, stage4, water_code, primary=source_trace.kind == "primary"):
                rejection_counts["land"] += 1
                continue
            if _continuous_self_touch(points, width):
                rejection_counts["self"] += 1
                continue
            try:
                cells, edges = rasterize_centerline_v11(
                    points,
                    source_world.stage4_terrain,
                    source_world.fields,
                    water_code,
                    boundary_end=source_trace.kind == "primary",
                )
            except ValueError:
                rejection_counts["raster"] += 1
                continue
            if source_trace.kind == "tributary" and cells[-1] not in set(traces[source_trace.parent_trace].raster_cells):
                rejection_counts["attach"] += 1
                continue
            candidate_edges = accepted_edges | _expected_undirected(edges)
            raw_candidate = _raw_adjacencies(set(cells) | accepted_cells, width)
            if raw_candidate != candidate_edges:
                rejection_counts["conflict"] += 1
                last_conflict = (tuple(cells), raw_candidate - candidate_edges, candidate_edges - raw_candidate)
                continue
            if source_trace.kind == "primary":
                wanted_attachment_cells = {source_by_id[child].raster_cells[-1] for child in children.get(trace_id, [])}
                sampled_cells = {(int(math.floor(point[0])) % width, int(math.floor(point[1]))) for point in points}
                if not wanted_attachment_cells.issubset(sampled_cells):
                    rejection_counts["attach"] += 1
                    continue
            samples = _metadata_samples(source_trace, points, source_world.fields, width)
            uphill = _uphill_fraction(samples)
            if uphill > config.max_uphill_fraction:
                rejection_counts["uphill"] += 1
                last_uphill = uphill
                continue
            accepted = controls, fractions, points, cells, edges, samples, uphill
            break
        if accepted is None and source_trace.kind == "tributary":
            for rounds in (12, 8, 4, 0):
                fallback_accepted = False
                for junction_radius in (0.92, 0.78, 0.66, 0.52, 0.40, 0.30):
                    points = _dense_elastic_fallback(
                        source_trace.points,
                        source_trace.source_cell,
                        final_point,
                        stage4,
                        water_code,
                        obstacles,
                        seed,
                        config,
                        rounds,
                    )
                    points = _clear_curve_relief(points, obstacles, source_trace.source_cell, stage4, water_code, config)
                    reference_points = list(points)
                    points = _align_junction_points(points, accepted_attachment_tangents[trace_id], radius=junction_radius)
                    points = _project_to_cell_corridor(points, reference_points, set(source_trace.raster_cells), width)
                    if not _segment_land(points, stage4, water_code, primary=False) or _continuous_self_touch(points, width):
                        continue
                    try:
                        cells, edges = rasterize_centerline_v11(
                            points,
                            source_world.stage4_terrain,
                            source_world.fields,
                            water_code,
                            boundary_end=False,
                        )
                    except ValueError:
                        continue
                    if cells[-1] not in set(traces[source_trace.parent_trace].raster_cells):
                        continue
                    candidate_edges = accepted_edges | _expected_undirected(edges)
                    if _raw_adjacencies(set(cells) | accepted_cells, width) != candidate_edges:
                        continue
                    samples = _metadata_samples(source_trace, points, source_world.fields, width)
                    uphill = _uphill_fraction(samples)
                    if uphill > config.max_uphill_fraction:
                        continue
                    fractions = tuple(index / max(1, len(points) - 1) for index in range(len(points)))
                    accepted = smooth, fractions, points, cells, edges, samples, uphill
                    fallback_accepted = True
                    break
                if fallback_accepted:
                    break
        if accepted is None:
            raise RuntimeError(
                f"V12 could not fit legal elastic trace {trace_id}: {rejection_counts}; "
                f"conflict={last_conflict}; uphill={last_uphill}"
            )
        controls, fractions, points, cells, edges, samples, uphill = accepted
        attachment = junction_points.get(trace_id)
        v12_trace = ContinuousTraceV12(
            trace_id,
            source_trace.kind,
            source_trace.parent_trace,
            attachment,
            source_trace.source_cell,
            source_trace.termination,
            source_trace.mouth_water_cell,
            source_trace.shoreline_point,
            source_trace.fine_path,
            samples,
            tuple(cells),
            tuple(edges),
            uphill,
            _angular_energy(points),
            _relief_clearance(points, obstacles, source_trace.source_cell, width),
        )
        traces.append(v12_trace)
        accepted_controls[trace_id] = controls
        accepted_fractions[trace_id] = fractions
        accepted_points[trace_id] = points
        if source_trace.kind == "primary":
            for child in children.get(trace_id, []):
                child_trace = source_by_id[child]
                point, tangent = _select_parent_attachment(
                    points,
                    child_trace.raster_cells[-1],
                    attachment_fraction[child],
                    width,
                )
                accepted_attachment_points[child] = point
                accepted_attachment_tangents[child] = tangent
        accepted_cells.update(cells)
        accepted_edges.update(_expected_undirected(edges))

    # Ordered construction above matches trace ids because V11 stores all
    # primaries before tributaries. Assert this instead of silently reindexing.
    if [trace.trace_id for trace in traces] != list(range(len(traces))):
        raise AssertionError("V12 trace order diverged from V11 hierarchy")

    junctions = []
    for trace in traces:
        if trace.kind != "tributary":
            continue
        parent_tangent = accepted_attachment_tangents[trace.trace_id]
        incoming = _unit((trace.points[-1][0] - trace.points[-5][0], trace.points[-1][1] - trace.points[-5][1]))
        angle = math.degrees(math.acos(max(-1.0, min(1.0, incoming[0] * parent_tangent[0] + incoming[1] * parent_tangent[1]))))
        point = trace.attachment_point
        cell = trace.raster_cells[-1]
        center = (cell[0] + 0.5, cell[1] + 0.5)
        point_x = point[0] + round((center[0] - point[0]) / width) * width
        offcentre = math.hypot(point_x - center[0], point[1] - center[1])
        junctions.append(JunctionPatchV12(trace.parent_trace, trace.trace_id, point, parent_tangent, incoming, angle, offcentre))

    terrain = stage4.copy()
    for x, y in accepted_cells:
        terrain[y, x] = river_code
    edge_list = tuple(sorted({edge for trace in traces for edge in trace.raster_edges}, key=lambda edge: (edge[0][1], edge[0][0], edge[1][1], edge[1][0])))
    mouths = _stronger_mouths(traces, source_world.mouths, tile_px, seed)
    world = ContinuousHydrologyWorldV12(
        source_world.stage4_terrain,
        tuple(tuple(int(value) for value in row) for row in terrain),
        tuple(traces),
        tuple(sorted(accepted_cells, key=lambda cell: (cell[1], cell[0]))),
        edge_list,
        mouths,
        tuple(junctions),
        source_world.fields,
        source_world.water_mask,
        tile_px,
        source_world.world_width,
        source_world.world_height,
        seed,
        source_world.subcells_per_cell,
        f"modern-v12-elastic-derivative-seed-{seed}",
        source_world,
    )
    audit = validate_continuous_hydrology_v12(world, authority)
    if not audit.valid:
        raise AssertionError("invalid continuous hydrology V12: " + "; ".join(audit.errors))
    return world


def validate_continuous_hydrology_v12(world: ContinuousHydrologyWorldV12, authority) -> ContinuousAuditV12:
    errors = []
    cycles = 0
    self_touches = 0
    mismatches = 0
    by_id = {trace.trace_id: trace for trace in world.traces}
    for trace in world.traces:
        if trace.kind == "tributary":
            seen = {trace.trace_id}
            parent = trace.parent_trace
            while parent is not None:
                if parent in seen or parent not in by_id:
                    cycles += 1
                    break
                seen.add(parent)
                parent = by_id[parent].parent_trace
        if _continuous_self_touch(trace.points, world.world_width):
            self_touches += 1
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
    if expected_cells != set(world.river_cells) or expected_edges != set(world.river_edges):
        mismatches += 1
    terrain = np.asarray(world.terrain, dtype=np.int16)
    actual = {(int(x), int(y)) for y, x in np.argwhere(terrain == int(authority.Terrain.RIVER))}
    if actual != expected_cells:
        mismatches += 1
    raw = _raw_adjacencies(world.river_cells, world.world_width)
    recorded = _expected_undirected(world.river_edges)
    if raw != recorded:
        mismatches += 1
    if cycles:
        errors.append("trace hierarchy contains a cycle")
    if self_touches:
        errors.append("continuous spline contains self-touch")
    if mismatches:
        errors.append("trace-to-raster authority mismatch")
    uphill = [trace.uphill_fraction for trace in world.traces]
    if uphill and max(uphill) > 0.34:
        errors.append("trace has excessive uphill flow")
    source_energy = float(np.mean([_angular_energy(trace.points) for trace in world.source_v11.traces]))
    energy = float(np.mean([trace.angular_energy for trace in world.traces]))
    reduction = 0.0 if source_energy <= 1e-12 else 1.0 - energy / source_energy
    if reduction < 0.18:
        errors.append("curvature cadence was not materially reduced")
    if len(world.junctions) != sum(trace.kind == "tributary" for trace in world.traces):
        errors.append("junction patch coverage mismatch")
    junction_angles = [item.approach_degrees for item in world.junctions]
    if junction_angles and max(junction_angles) > 82.0:
        errors.append("junction remains a mechanical T merge")
    primaries = sum(trace.kind == "primary" for trace in world.traces)
    tributaries = sum(trace.kind == "tributary" for trace in world.traces)
    if (primaries, tributaries, len(world.mouths)) != (3, 3, 3):
        errors.append("pilot hierarchy is incomplete")
    return ContinuousAuditV12(
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
        self_touches,
        mismatches,
        max(uphill, default=0.0),
        energy,
        source_energy,
        reduction,
        min((trace.min_relief_clearance for trace in world.traces), default=99.0),
        max(junction_angles, default=0.0),
    )


__all__ = [
    "ContinuousAuditV12",
    "ContinuousHydrologyConfigV12",
    "ContinuousHydrologyWorldV12",
    "ContinuousTraceV12",
    "JunctionPatchV12",
    "generate_continuous_hydrology_v12",
    "validate_continuous_hydrology_v12",
]
