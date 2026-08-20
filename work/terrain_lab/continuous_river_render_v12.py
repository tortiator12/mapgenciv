"""Terrain-integrated presentation for isolated Continuous Hydrology V12.

The renderer consumes V12's persisted world-space curves directly.  Civ
cells remain gameplay authority, but no cell centre or cardinal edge is used
to reconstruct presentation geometry.  All fields are evaluated in world
coordinates so full, crop and horizontally wrapped renders are bit exact.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
from PIL import Image

from .continuous_hydrology_v12 import (
    ContinuousHydrologyWorldV12,
    ContinuousTraceV12,
    JunctionPatchV12,
)
from . import river_presentation_v9 as v9


Point = tuple[float, float]


@dataclass(frozen=True)
class PixelWindowV12:
    x0: int
    y0: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("pixel window must be positive")


@dataclass(frozen=True)
class ContinuousRenderAuditV12:
    valid: bool
    errors: tuple[str, ...]
    traces: int
    illegal_centerline_samples: int
    width_regressions: int
    branches: int
    mouths: int
    junctions: int
    min_tributary_downstream_width_px: float
    max_tributary_downstream_width_px: float
    min_primary_downstream_width_px: float
    max_primary_downstream_width_px: float
    max_junction_angle: float


def _unit(vector: Point, fallback: Point = (1.0, 0.0)) -> Point:
    length = math.hypot(vector[0], vector[1])
    if length <= 1e-12:
        return fallback
    return vector[0] / length, vector[1] / length


def _wrapped_dx(first: float, second: float, width: int) -> float:
    raw = second - first
    return raw - round(raw / width) * width


def _nearest_sample_width(trace: ContinuousTraceV12, point: Point, world_width: int) -> float:
    sample = min(
        trace.samples,
        key=lambda item: _wrapped_dx(item.point[0], point[0], world_width) ** 2 + (item.point[1] - point[1]) ** 2,
    )
    return float(sample.width_px)


def _display_widths(world: ContinuousHydrologyWorldV12) -> dict[int, tuple[float, ...]]:
    """Blend tributary width into its parent before the shared Y point.

    This is a presentation interpolation only.  It does not move a sample or
    alter trace/raster authority.  The final tributary quarter approaches a
    restrained fraction of the local trunk width, avoiding both a hairline
    inlet and a bulbous T-pipe.
    """

    traces = {trace.trace_id: trace for trace in world.traces}
    result: dict[int, tuple[float, ...]] = {}
    for trace in world.traces:
        raw = np.asarray([sample.width_px for sample in trace.samples], dtype=np.float64)
        points = [sample.point for sample in trace.samples]
        lengths = np.zeros(len(points), dtype=np.float64)
        for index, (first, second) in enumerate(zip(points, points[1:]), start=1):
            lengths[index] = lengths[index - 1] + math.hypot(
                _wrapped_dx(first[0], second[0], world.world_width), second[1] - first[1]
            )
        fraction = lengths / max(float(lengths[-1]), 1e-9)
        spring_floor = 2.10 + 1.40 * np.clip(fraction / 0.10, 0.0, 1.0) ** 0.72
        raw = np.maximum.accumulate(np.maximum(raw, spring_floor))
        if trace.kind == "tributary" and trace.parent_trace is not None and trace.attachment_point is not None:
            parent_width = _nearest_sample_width(traces[trace.parent_trace], trace.attachment_point, world.world_width)
            target = max(float(raw[-1]), min(parent_width * 0.78, float(raw[-1]) + 1.35, 7.4))
            blend = np.clip((fraction - 0.72) / 0.28, 0.0, 1.0)
            blend = blend * blend * (3.0 - 2.0 * blend)
            raw = np.maximum.accumulate(raw + (target - raw[-1]) * blend)
        result[trace.trace_id] = tuple(float(value) for value in raw)
    return result


def _trace_pixels(trace: ContinuousTraceV12, widths: Sequence[float], tile_px: int) -> tuple[list[Point], list[float]]:
    return (
        [(sample.point[0] * tile_px, sample.point[1] * tile_px) for sample in trace.samples],
        list(widths),
    )


def _raster_trace_sdf(
    sdf: np.ndarray,
    trace: ContinuousTraceV12,
    widths: Sequence[float],
    world: ContinuousHydrologyWorldV12,
    window: PixelWindowV12,
) -> None:
    points, display_widths = _trace_pixels(trace, widths, world.tile_px)
    if len(points) < 2:
        return
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    margin = max(display_widths) + 20.0
    for cycle in v9._shift_range(min_x, max_x, window, world.world_width_px, margin):
        shift = cycle * world.world_width_px
        for index, (first, second) in enumerate(zip(points, points[1:])):
            midpoint_x = (first[0] + second[0]) * 0.5
            midpoint_y = (first[1] + second[1]) * 0.5
            # Very low amplitude breakup; the centreline itself remains the
            # smooth V12 authority rather than becoming a wobbly vector line.
            modulation = 1.0 + 0.024 * math.sin(
                midpoint_x / world.world_width_px * math.tau * 17.0
                + midpoint_y / (world.tile_px * 3.7)
                + (world.seed & 2047) * 0.009
            )
            v9._update_segment_sdf(
                sdf,
                window,
                (first[0] + shift, first[1]),
                (second[0] + shift, second[1]),
                display_widths[index] * modulation,
                display_widths[index + 1] * modulation,
                padding=17.0,
            )


def _update_ellipse_sdf(
    sdf: np.ndarray,
    window: PixelWindowV12,
    centre: Point,
    tangent: Point,
    major: float,
    minor: float,
    period: int,
) -> None:
    tangent = _unit(tangent)
    normal = (-tangent[1], tangent[0])
    radius = max(major, minor) + 14.0
    for cycle in v9._shift_range(centre[0], centre[0], window, period, radius):
        cx = centre[0] + cycle * period
        x0 = max(0, int(math.floor(cx - radius - window.x0)))
        x1 = min(window.width, int(math.ceil(cx + radius - window.x0)) + 1)
        y0 = max(0, int(math.floor(centre[1] - radius - window.y0)))
        y1 = min(window.height, int(math.ceil(centre[1] + radius - window.y0)) + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        xs = window.x0 + np.arange(x0, x1, dtype=np.float64) + 0.5 - cx
        ys = window.y0 + np.arange(y0, y1, dtype=np.float64) + 0.5 - centre[1]
        xx, yy = np.meshgrid(xs, ys)
        along = xx * tangent[0] + yy * tangent[1]
        across = xx * normal[0] + yy * normal[1]
        normalized = np.sqrt((along / major) ** 2 + (across / minor) ** 2)
        signed = (normalized - 1.0) * minor
        target = sdf[y0:y1, x0:x1]
        np.minimum(target, signed.astype(np.float32), out=target)


def _raster_junction_patch(
    sdf: np.ndarray,
    junction: JunctionPatchV12,
    world: ContinuousHydrologyWorldV12,
    widths: dict[int, tuple[float, ...]],
    window: PixelWindowV12,
) -> None:
    traces = {trace.trace_id: trace for trace in world.traces}
    parent = traces[junction.parent_trace]
    tributary = traces[junction.tributary_trace]
    parent_width = _nearest_sample_width(parent, junction.point, world.world_width)
    tributary_width = widths[tributary.trace_id][-1]
    tangent = _unit(junction.downstream_tangent)
    centre = (
        junction.point[0] * world.tile_px + tangent[0] * max(parent_width, tributary_width) * 0.18,
        junction.point[1] * world.tile_px + tangent[1] * max(parent_width, tributary_width) * 0.18,
    )
    # A short downstream teardrop joins both tangent-aligned corridors.  It is
    # deliberately smaller than a full channel width, so the Y remains acute.
    _update_ellipse_sdf(
        sdf,
        window,
        centre,
        tangent,
        max(parent_width, tributary_width) * 0.58 + 1.0,
        max(parent_width * 0.48, tributary_width * 0.46),
        world.world_width_px,
    )


def _source_geometry(trace: ContinuousTraceV12, tile_px: int) -> v9.SourceGeometryV9 | None:
    if len(trace.samples) < 2:
        return None
    first, second = trace.samples[0], trace.samples[min(3, len(trace.samples) - 1)]
    direction = _unit((second.point[0] - first.point[0], second.point[1] - first.point[1]))
    return v9.SourceGeometryV9(
        trace.source_cell,
        (first.point[0] * tile_px, first.point[1] * tile_px),
        direction,
        first.width_px,
        tile_px * 0.135,
        tile_px * 0.060,
    )


def _noise(world: ContinuousHydrologyWorldV12, window: PixelWindowV12) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0 : window.height, 0 : window.width]
    world_x = (window.x0 + xx) % world.world_width_px
    world_y = window.y0 + yy
    phase = (world.seed & 0xFFFF) / 65536.0 * math.tau
    broad = (
        np.sin(math.tau * (world_x / world.world_width_px * 13.0 + world_y / (world.tile_px * 5.9)) + phase) * 0.57
        + np.cos(math.tau * (world_x / world.world_width_px * 23.0 - world_y / (world.tile_px * 8.1)) - phase * 0.61) * 0.43
    )
    detail = (
        np.sin(math.tau * (world_x / world.world_width_px * 61.0 + world_y / (world.tile_px * 1.73)) + phase * 1.7) * 0.52
        + np.cos(math.tau * (world_x / world.world_width_px * 47.0 - world_y / (world.tile_px * 2.21)) - phase * 0.83) * 0.48
    )
    return broad.astype(np.float32), detail.astype(np.float32)


def _raster_mouth_fields(
    estuary: np.ndarray,
    sediment: np.ndarray,
    foam: np.ndarray,
    world: ContinuousHydrologyWorldV12,
    window: PixelWindowV12,
    water_fraction: np.ndarray,
    broad_noise: np.ndarray,
    detail_noise: np.ndarray,
) -> None:
    yy, xx = np.mgrid[0 : window.height, 0 : window.width]
    world_x = window.x0 + xx + 0.5
    world_y = window.y0 + yy + 0.5
    for mouth in world.mouths:
        margin = mouth.depth + mouth.end_width
        for cycle in v9._shift_range(
            mouth.shoreline_point[0], mouth.shoreline_point[0], window, world.world_width_px, margin
        ):
            shore_x = mouth.shoreline_point[0] + cycle * world.world_width_px
            dx, dy = world_x - shore_x, world_y - mouth.shoreline_point[1]
            along = dx * mouth.direction[0] + dy * mouth.direction[1]
            across = dx * mouth.normal[0] + dy * mouth.normal[1]
            q = np.clip(along / mouth.depth, 0.0, 1.0)
            active = (along >= -2.5) & (along <= mouth.depth)
            open_water = np.clip((water_fraction - 0.27) / 0.53, 0.0, 1.0)

            # Coast-SDF proxy: water_fraction bends and clips the fan at the
            # actual shoreline instead of drawing a symmetric nozzle.
            coast_bias = np.clip((water_fraction - 0.43) / 0.28, -0.55, 1.0)
            centre_shift = (
                mouth.asymmetry * q**1.16
                + mouth.end_width * 0.055 * np.sin(q * math.pi * 1.35 + world.seed * 0.013) * q
                + mouth.end_width * 0.035 * coast_bias * q
            )
            half_width = mouth.start_width * 0.52 + (
                mouth.end_width * 0.50 - mouth.start_width * 0.52
            ) * (q ** 0.70)
            half_width *= np.clip(1.0 + detail_noise * 0.045 * q, 0.90, 1.10)
            transverse = np.abs(across - centre_shift)
            body = np.exp(-((transverse / np.maximum(half_width, 0.7)) ** 3.4))
            longitudinal = np.clip(1.0 - q, 0.0, 1.0) ** 0.30
            estuary_strength = body * longitudinal * open_water * active
            np.maximum(estuary, estuary_strength.astype(np.float32), out=estuary)

            # Two overlapping, unequal sediment lobes read as a deposited fan
            # rather than a single cut-off vector cone.
            lobe_width = half_width * (1.42 + 0.12 * broad_noise)
            primary_lobe = np.exp(-((transverse / np.maximum(lobe_width, 0.8)) ** 2.35))
            secondary_shift = centre_shift - np.sign(mouth.asymmetry or 1.0) * half_width * (0.38 + 0.22 * q)
            secondary = np.exp(-((np.abs(across - secondary_shift) / np.maximum(lobe_width * 0.72, 0.8)) ** 2.1))
            deposit_profile = np.sin(np.clip(q, 0.0, 1.0) * math.pi) ** 0.58
            deposit_profile += 0.26 * (1.0 - q) ** 0.7
            breakup = np.clip(0.76 + broad_noise * 0.16 + detail_noise * 0.10, 0.32, 1.0)
            sediment_strength = (
                np.maximum(primary_lobe, secondary * 0.62)
                * deposit_profile
                * open_water
                * active
                * breakup
            )
            np.maximum(sediment, sediment_strength.astype(np.float32), out=sediment)

            coast_band = np.exp(-(((water_fraction - 0.50) / 0.060) ** 2))
            lip = np.exp(-((transverse / np.maximum(mouth.start_width * 1.55, 3.0)) ** 2.5))
            fan_rim = np.exp(-(((transverse - half_width * 0.84) / np.maximum(half_width * 0.16, 1.3)) ** 2))
            rim_fade = np.clip((0.68 - q) / 0.48, 0.0, 1.0)
            foam_strength = (
                coast_band * lip * np.clip(0.78 + detail_noise * 0.20, 0.25, 1.0)
                + 0.24 * fan_rim * rim_fade * open_water * active * np.clip(0.7 + detail_noise * 0.2, 0.2, 1.0)
            )
            np.maximum(foam, foam_strength.astype(np.float32), out=foam)


def _raster_mouth_connectors(
    sdf: np.ndarray,
    world: ContinuousHydrologyWorldV12,
    window: PixelWindowV12,
) -> None:
    """Carry the land channel through the visual coastline into the fan."""

    for mouth in world.mouths:
        start = mouth.shoreline_point
        end = (
            start[0] + mouth.direction[0] * mouth.depth * 0.30,
            start[1] + mouth.direction[1] * mouth.depth * 0.30,
        )
        min_x, max_x = min(start[0], end[0]), max(start[0], end[0])
        for cycle in v9._shift_range(min_x, max_x, window, world.world_width_px, mouth.end_width + 16.0):
            shift = cycle * world.world_width_px
            v9._update_segment_sdf(
                sdf,
                window,
                (start[0] + shift, start[1]),
                (end[0] + shift, end[1]),
                mouth.start_width,
                max(mouth.start_width * 1.24, mouth.end_width * 0.50),
                padding=18.0,
            )


def render_continuous_river_layer_v12(
    world: ContinuousHydrologyWorldV12,
    window: PixelWindowV12,
) -> Image.Image:
    shape = (window.height, window.width)
    river_sdf = np.full(shape, np.inf, dtype=np.float32)
    source_wet_sdf = np.full(shape, np.inf, dtype=np.float32)
    widths = _display_widths(world)
    for trace in world.traces:
        _raster_trace_sdf(river_sdf, trace, widths[trace.trace_id], world, window)
        source = _source_geometry(trace, world.tile_px)
        if source is not None:
            v9._update_source_wet_sdf(source_wet_sdf, source, window, world.world_width_px)
    for junction in world.junctions:
        _raster_junction_patch(river_sdf, junction, world, widths, window)
    _raster_mouth_connectors(river_sdf, world, window)

    broad_noise, detail_noise = _noise(world, window)
    water_fraction = v9._water_fraction(world, window)
    estuary = np.zeros(shape, dtype=np.float32)
    sediment = np.zeros(shape, dtype=np.float32)
    foam = np.zeros(shape, dtype=np.float32)
    _raster_mouth_fields(estuary, sediment, foam, world, window, water_fraction, broad_noise, detail_noise)

    rgb = np.zeros((window.height, window.width, 3), dtype=np.float32)
    alpha = np.zeros(shape, dtype=np.float32)

    # Spring seepage is an irregular wet patch, not a circular source icon.
    spring_distance = np.maximum(source_wet_sdf, 0.0)
    spring_alpha = 0.15 * np.exp(-((spring_distance / 7.8) ** 2)) * np.clip(
        0.72 + broad_noise * 0.18 + detail_noise * 0.08, 0.34, 1.0
    )
    spring_alpha[~np.isfinite(source_wet_sdf)] = 0.0
    spring_color = np.stack(
        (55.0 + broad_noise * 4.0, 69.0 + broad_noise * 5.0, 44.0 + broad_noise * 3.0), axis=-1
    )
    rgb, alpha = v9._alpha_over(rgb, alpha, spring_color, spring_alpha)

    # Wet soil and a shallow eroded bed integrate the water into the ground.
    outside = np.maximum(river_sdf, 0.0)
    bank_alpha = 0.18 * np.exp(-((outside / 9.2) ** 2)) * np.clip(
        0.76 + broad_noise * 0.15 + detail_noise * 0.06, 0.42, 1.0
    )
    bank_alpha[~np.isfinite(river_sdf)] = 0.0
    bank_color = np.stack(
        (54.0 + broad_noise * 5.0, 67.0 + broad_noise * 5.0, 43.0 + broad_noise * 3.0), axis=-1
    )
    rgb, alpha = v9._alpha_over(rgb, alpha, bank_color, bank_alpha)

    bed_alpha = 0.30 * np.clip((5.2 - river_sdf) / 5.8, 0.0, 1.0) * np.clip(
        0.82 + broad_noise * 0.10 + detail_noise * 0.08, 0.50, 1.0
    )
    bed_alpha[~np.isfinite(river_sdf)] = 0.0
    bed_color = np.stack(
        (91.0 + broad_noise * 7.0, 84.0 + broad_noise * 5.0, 58.0 + broad_noise * 5.0), axis=-1
    )
    rgb, alpha = v9._alpha_over(rgb, alpha, bed_color, bed_alpha)

    broken_sdf = river_sdf + detail_noise * 0.34
    water_alpha = 0.88 * np.clip(0.50 - broken_sdf / 1.75, 0.0, 1.0)
    water_alpha[~np.isfinite(river_sdf)] = 0.0
    combined_water_alpha = np.maximum(water_alpha, 0.67 * estuary)
    depth = np.clip(-broken_sdf / 4.5, 0.0, 1.0)
    water_color = np.stack(
        (
            18.0 + broad_noise * 5.0 + detail_noise * 2.0 - depth * 3.0,
            88.0 + broad_noise * 8.0 + detail_noise * 4.0 - depth * 4.0,
            119.0 + broad_noise * 10.0 + detail_noise * 5.0 - depth * 2.0,
        ),
        axis=-1,
    )
    rgb, alpha = v9._alpha_over(rgb, alpha, water_color, combined_water_alpha)

    # Deposits tint the receiving water after the core has been integrated;
    # this keeps the asymmetric fan legible instead of hiding it underneath.
    plume_alpha = 0.25 * sediment
    plume_color = np.stack(
        (145.0 + broad_noise * 11.0, 129.0 + broad_noise * 8.0, 76.0 + detail_noise * 5.0), axis=-1
    )
    rgb, alpha = v9._alpha_over(rgb, alpha, plume_color, plume_alpha)

    foam_alpha = 0.34 * foam
    foam_color = np.stack(
        (204.0 + detail_noise * 3.0, 220.0 + detail_noise * 2.0, 207.0 + broad_noise * 2.0), axis=-1
    )
    rgb, alpha = v9._alpha_over(rgb, alpha, foam_color, foam_alpha)

    rgba = np.concatenate(
        (np.clip(rgb, 0.0, 255.0), np.clip(alpha[..., None] * 255.0, 0.0, 255.0)), axis=-1
    )
    return Image.fromarray(np.rint(rgba).astype(np.uint8), "RGBA")


def composite_continuous_rivers_v12(
    base: Image.Image,
    world: ContinuousHydrologyWorldV12,
    window: PixelWindowV12,
) -> Image.Image:
    if base.size != (window.width, window.height):
        raise ValueError("base image size must equal pixel window")
    result = base.convert("RGBA")
    result.alpha_composite(render_continuous_river_layer_v12(world, window))
    return result


def validate_continuous_render_v12(world: ContinuousHydrologyWorldV12) -> ContinuousRenderAuditV12:
    errors: list[str] = []
    illegal = 0
    regressions = 0
    primary_widths: list[float] = []
    tributary_widths: list[float] = []
    for trace in world.traces:
        allowed = set(trace.raster_cells)
        samples = trace.samples[:-1] if trace.kind == "primary" else trace.samples
        for sample in samples:
            cell = (int(math.floor(sample.point[0])) % world.world_width, int(math.floor(sample.point[1])))
            if cell not in allowed:
                illegal += 1
        sample_widths = [sample.width_px for sample in trace.samples]
        regressions += sum(second + 1e-9 < first for first, second in zip(sample_widths, sample_widths[1:]))
        if trace.kind == "primary":
            primary_widths.append(sample_widths[-1])
        else:
            tributary_widths.append(sample_widths[-1])
    branches = sum(trace.kind == "tributary" for trace in world.traces)
    if illegal:
        errors.append("continuous centerline leaves raster authority")
    if regressions:
        errors.append("downstream width regresses")
    if branches != len(world.junctions):
        errors.append("valid tributary branch lost from junction presentation")
    if len(world.mouths) != sum(trace.kind == "primary" for trace in world.traces):
        errors.append("mouth coverage mismatch")
    if tributary_widths and not 7.0 <= min(tributary_widths) <= 9.0:
        errors.append("tributary downstream width outside V12 band")
    if primary_widths and not 12.0 <= min(primary_widths) <= 18.0:
        errors.append("primary downstream width outside V12 band")
    max_angle = max((junction.approach_degrees for junction in world.junctions), default=0.0)
    if max_angle > 70.0:
        errors.append("junction presentation is not an acute Y")
    return ContinuousRenderAuditV12(
        not errors,
        tuple(errors),
        len(world.traces),
        illegal,
        regressions,
        branches,
        len(world.mouths),
        len(world.junctions),
        min(tributary_widths, default=0.0),
        max(tributary_widths, default=0.0),
        min(primary_widths, default=0.0),
        max(primary_widths, default=0.0),
        max_angle,
    )


__all__ = [
    "ContinuousRenderAuditV12",
    "PixelWindowV12",
    "composite_continuous_rivers_v12",
    "render_continuous_river_layer_v12",
    "validate_continuous_render_v12",
]
