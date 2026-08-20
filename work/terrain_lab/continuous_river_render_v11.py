"""World-space presentation for the isolated V11 corridor-first hydrology.

V11 does not reconstruct a line from Civ cells.  It paints the persisted
continuous traces directly, using the raster cells only as gameplay authority
and as an audit boundary.  Rendering is window-independent and horizontally
periodic, so full/crop/wrap pixels are exact.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
from PIL import Image

from .continuous_hydrology_v11 import ContinuousHydrologyWorldV11, ContinuousMouthV11, ContinuousTraceV11
from . import river_presentation_v9 as v9


Point = tuple[float, float]


@dataclass(frozen=True)
class PixelWindowV11:
    x0: int
    y0: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("pixel window must be positive")


@dataclass(frozen=True)
class ContinuousRenderAuditV11:
    valid: bool
    errors: tuple[str, ...]
    traces: int
    illegal_centerline_samples: int
    width_regressions: int
    min_tributary_downstream_width_px: float
    max_tributary_downstream_width_px: float
    min_primary_downstream_width_px: float
    max_primary_downstream_width_px: float
    mouths: int
    confluences: int


@dataclass(frozen=True)
class _MouthAdapter:
    river_cell: tuple[int, int]
    water_cell: tuple[int, int]
    shoreline_port: Point
    direction: Point
    normal: Point
    start_width: float
    end_width: float
    depth: float
    asymmetry: float
    upstream_area: float
    strahler: int


def _mouth_adapter(mouth: ContinuousMouthV11) -> _MouthAdapter:
    return _MouthAdapter(
        mouth.river_cell,
        mouth.water_cell,
        mouth.shoreline_point,
        mouth.direction,
        mouth.normal,
        mouth.start_width,
        mouth.end_width,
        mouth.depth,
        mouth.asymmetry,
        mouth.upstream_area,
        mouth.strahler,
    )


def _trace_pixels(trace: ContinuousTraceV11, tile_px: int) -> tuple[list[Point], list[float]]:
    points = [(sample.point[0] * tile_px, sample.point[1] * tile_px) for sample in trace.samples]
    widths = [sample.width_px for sample in trace.samples]
    if trace.terminal_spec is not None and len(points) >= 3:
        # The continuous body owns the river only up to the authored branch
        # split.  Drawing it onward to the shoreline produced a round hose cap
        # on top of the delta.  Find the nearest route segment and terminate
        # the body exactly at the generator-provided split instead.
        split = (
            float(trace.terminal_spec.split_point[0]) * tile_px,
            float(trace.terminal_spec.split_point[1]) * tile_px,
        )
        best = None
        for index, (first, second) in enumerate(zip(points, points[1:])):
            vx, vy = second[0] - first[0], second[1] - first[1]
            denom = max(vx * vx + vy * vy, 1e-9)
            q = max(0.0, min(1.0, ((split[0] - first[0]) * vx + (split[1] - first[1]) * vy) / denom))
            px, py = first[0] + vx * q, first[1] + vy * q
            distance2 = (px - split[0]) ** 2 + (py - split[1]) ** 2
            candidate = (distance2, index, q)
            if best is None or candidate < best:
                best = candidate
        assert best is not None
        _distance2, split_index, split_q = best
        split_width = widths[split_index] * (1.0 - split_q) + widths[split_index + 1] * split_q
        points = [*points[: split_index + 1], split]
        widths = [*widths[: split_index + 1], max(split_width, float(trace.terminal_spec.width_px))]
        # V27 owns a continuous corridor before rasterisation.  Two bounded
        # corner-cutting passes remove the fine A* angle rhythm while keeping
        # source and shoreline endpoints exact.
        for _round in range(2):
            smooth_points = [points[0]]
            smooth_widths = [widths[0]]
            for first, second, wa, wb in zip(points, points[1:], widths, widths[1:]):
                smooth_points.extend((
                    (first[0] * 0.75 + second[0] * 0.25, first[1] * 0.75 + second[1] * 0.25),
                    (first[0] * 0.25 + second[0] * 0.75, first[1] * 0.25 + second[1] * 0.75),
                ))
                smooth_widths.extend((wa * 0.75 + wb * 0.25, wa * 0.25 + wb * 0.75))
            smooth_points.append(points[-1])
            smooth_widths.append(widths[-1])
            points, widths = smooth_points, smooth_widths
        # Component-wide long-wave meander.  It is evaluated over continuous
        # arc length, not restarted per tile; source and final coast port stay
        # exact.  The 0.09T cap keeps the curve inside its Civ corridor while
        # removing the remaining ruler-straight pipe impression.
        segment_lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
        station = [0.0]
        for length in segment_lengths:
            station.append(station[-1] + length)
        total = max(station[-1], 1.0)
        phase = trace.trace_id * 1.713 + 0.41
        displaced = []
        for index, point in enumerate(points):
            before = points[max(0, index - 1)]
            after = points[min(len(points) - 1, index + 1)]
            tx, ty = after[0] - before[0], after[1] - before[1]
            length = max(math.hypot(tx, ty), 1e-9)
            nx, ny = -ty / length, tx / length
            end_fade = min(station[index] / (tile_px * 0.52), (total - station[index]) / (tile_px * 0.72), 1.0)
            end_fade = max(0.0, end_fade)
            end_fade = end_fade * end_fade * (3.0 - 2.0 * end_fade)
            wave = math.sin(station[index] / (tile_px * 1.42) * math.tau + phase)
            offset = tile_px * 0.088 * end_fade * wave
            displaced.append((point[0] + nx * offset, point[1] + ny * offset))
        points = displaced
    return points, widths


def _raster_trace_sdf(
    sdf: np.ndarray,
    trace: ContinuousTraceV11,
    world: ContinuousHydrologyWorldV11,
    window: PixelWindowV11,
) -> None:
    points, widths = _trace_pixels(trace, world.tile_px)
    if len(points) < 2:
        return
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    margin = max(widths) + 18.0
    for cycle in v9._shift_range(min_x, max_x, window, world.world_width_px, margin):
        shift = cycle * world.world_width_px
        for index, (first, second) in enumerate(zip(points, points[1:])):
            midpoint_x = (first[0] + second[0]) * 0.5
            midpoint_y = (first[1] + second[1]) * 0.5
            modulation = 1.0 + 0.045 * math.sin(
                midpoint_x / world.world_width_px * math.tau * 23.0
                + midpoint_y / (world.tile_px * 2.9)
                + (world.seed & 2047) * 0.009
            )
            v9._update_segment_sdf(
                sdf,
                window,
                (first[0] + shift, first[1]),
                (second[0] + shift, second[1]),
                widths[index] * modulation,
                widths[index + 1] * modulation,
                padding=14.0,
            )


def _source_geometry(trace: ContinuousTraceV11, tile_px: int) -> v9.SourceGeometryV9 | None:
    if len(trace.samples) < 2:
        return None
    first, second = trace.samples[0], trace.samples[1]
    direction = v9._unit((second.point[0] - first.point[0], second.point[1] - first.point[1]))
    return v9.SourceGeometryV9(
        trace.source_cell,
        (first.point[0] * tile_px, first.point[1] * tile_px),
        direction,
        first.width_px,
        tile_px * 0.105,
        tile_px * 0.048,
    )


def _noise(world: ContinuousHydrologyWorldV11, window: PixelWindowV11) -> np.ndarray:
    yy, xx = np.mgrid[0 : window.height, 0 : window.width]
    world_x = (window.x0 + xx) % world.world_width_px
    world_y = window.y0 + yy
    phase = (world.seed & 0xFFFF) / 65536.0 * math.tau
    return (
        np.sin(math.tau * (world_x / world.world_width_px * 19.0 + world_y / (world.tile_px * 4.7)) + phase) * 0.56
        + np.cos(math.tau * (world_x / world.world_width_px * 31.0 - world_y / (world.tile_px * 7.3)) - phase * 0.61) * 0.44
    ).astype(np.float32)


def render_continuous_river_layer_v11(
    world: ContinuousHydrologyWorldV11,
    window: PixelWindowV11,
    *,
    include_procedural_mouths: bool = True,
) -> Image.Image:
    shape = (window.height, window.width)
    river_sdf = np.full(shape, np.inf, dtype=np.float32)
    source_wet_sdf = np.full(shape, np.inf, dtype=np.float32)
    for trace in world.traces:
        _raster_trace_sdf(river_sdf, trace, world, window)
        source = _source_geometry(trace, world.tile_px)
        if source is not None:
            v9._update_source_wet_sdf(source_wet_sdf, source, window, world.world_width_px)

    noise = _noise(world, window)
    water_fraction = v9._water_fraction(world, window)
    estuary = np.zeros(shape, dtype=np.float32)
    plume = np.zeros(shape, dtype=np.float32)
    foam = np.zeros(shape, dtype=np.float32)
    if include_procedural_mouths:
        for mouth in world.mouths:
            v9._raster_mouth_fields(
                estuary,
                plume,
                foam,
                _mouth_adapter(mouth),
                world,
                window,
                water_fraction,
                noise,
            )

    rgb = np.zeros((window.height, window.width, 3), dtype=np.float32)
    alpha = np.zeros(shape, dtype=np.float32)

    wet_alpha = 0.15 * np.exp(-((np.maximum(source_wet_sdf, 0.0) / 6.2) ** 2))
    wet_alpha[~np.isfinite(source_wet_sdf)] = 0.0
    wet_color = np.stack((63.0 + noise * 4.0, 76.0 + noise * 5.0, 46.0 + noise * 3.0), axis=-1)
    rgb, alpha = v9._alpha_over(rgb, alpha, wet_color, wet_alpha)

    outside = np.maximum(river_sdf, 0.0)
    bank_alpha = 0.22 * np.exp(-((outside / 6.4) ** 2)) * np.clip(0.77 + noise * 0.17, 0.46, 1.0)
    bank_alpha[~np.isfinite(river_sdf)] = 0.0
    bank_color = np.stack((57.0 + noise * 4.0, 69.0 + noise * 4.5, 45.0 + noise * 3.0), axis=-1)
    rgb, alpha = v9._alpha_over(rgb, alpha, bank_color, bank_alpha)

    # A broad translucent sediment transition replaces the old dark outline.
    sediment_alpha = 0.075 * np.exp(-(((river_sdf - 0.6) / 4.2) ** 2)) * np.clip(0.75 + noise * 0.20, 0.35, 1.0)
    sediment_alpha[~np.isfinite(river_sdf)] = 0.0
    sediment_color = np.stack((123.0 + noise * 7.0, 110.0 + noise * 5.0, 73.0 + noise * 4.0), axis=-1)
    rgb, alpha = v9._alpha_over(rgb, alpha, sediment_color, sediment_alpha)

    plume_alpha = 0.34 * plume
    plume_color = np.stack((169.0 + noise * 9.0, 143.0 + noise * 6.0, 81.0 + noise * 4.0), axis=-1)
    rgb, alpha = v9._alpha_over(rgb, alpha, plume_color, plume_alpha)

    water_alpha = np.clip(0.54 - river_sdf / 1.28, 0.0, 1.0)
    water_alpha[~np.isfinite(river_sdf)] = 0.0
    combined_water_alpha = np.maximum(water_alpha, 0.54 * estuary)
    soft_boundary = np.exp(-((river_sdf / 3.2) ** 2))
    soft_boundary[~np.isfinite(river_sdf)] = 0.0
    if any(trace.terminal_spec is not None for trace in world.traces):
        water_color = np.stack(
            (9.0 + noise * 5.5 + soft_boundary * 4.0,
             86.0 + noise * 9.0 + soft_boundary * 8.0,
             125.0 + noise * 10.5 + soft_boundary * 10.0),
            axis=-1,
        )
    else:
        water_color = np.stack(
            (
                16.0 + noise * 4.5 + soft_boundary * 5.0,
                102.0 + noise * 7.0 + soft_boundary * 10.0,
                145.0 + noise * 8.0 + soft_boundary * 10.0,
            ),
            axis=-1,
        )
    rgb, alpha = v9._alpha_over(rgb, alpha, water_color, combined_water_alpha)

    foam_alpha = 0.43 * foam
    foam_color = np.stack((207.0 + noise * 3.0, 226.0 + noise * 2.0, 216.0 + noise * 2.0), axis=-1)
    rgb, alpha = v9._alpha_over(rgb, alpha, foam_color, foam_alpha)

    rgba = np.concatenate((np.clip(rgb, 0.0, 255.0), np.clip(alpha[..., None] * 255.0, 0.0, 255.0)), axis=-1)
    return Image.fromarray(np.rint(rgba).astype(np.uint8), "RGBA")


def composite_continuous_rivers_v11(
    base: Image.Image,
    world: ContinuousHydrologyWorldV11,
    window: PixelWindowV11,
) -> Image.Image:
    if base.size != (window.width, window.height):
        raise ValueError("base image size must equal pixel window")
    result = base.convert("RGBA")
    result.alpha_composite(render_continuous_river_layer_v11(world, window))
    return result


def validate_continuous_render_v11(world: ContinuousHydrologyWorldV11) -> ContinuousRenderAuditV11:
    errors = []
    illegal = 0
    regressions = 0
    primary_widths = []
    tributary_widths = []
    width = world.world_width
    for trace in world.traces:
        allowed = set(trace.raster_cells)
        samples = trace.samples[:-1] if trace.kind == "primary" else trace.samples
        for sample in samples:
            cell = (int(math.floor(sample.point[0])) % width, int(math.floor(sample.point[1])))
            if cell not in allowed:
                illegal += 1
        widths = [sample.width_px for sample in trace.samples]
        regressions += sum(second + 1e-9 < first for first, second in zip(widths, widths[1:]))
        if trace.kind == "primary":
            primary_widths.append(widths[-1])
        else:
            tributary_widths.append(widths[-1])
    if illegal:
        errors.append("continuous centerline leaves raster authority")
    if regressions:
        errors.append("downstream width regresses")
    if len(world.mouths) != sum(trace.kind == "primary" for trace in world.traces):
        errors.append("mouth coverage mismatch")
    if tributary_widths and not 3.8 <= min(tributary_widths) <= 6.1:
        errors.append("tributary downstream width outside pilot band")
    if primary_widths and not 6.5 <= min(primary_widths) <= 11.0:
        errors.append("primary downstream width outside pilot band")
    return ContinuousRenderAuditV11(
        not errors,
        tuple(errors),
        len(world.traces),
        illegal,
        regressions,
        min(tributary_widths, default=0.0),
        max(tributary_widths, default=0.0),
        min(primary_widths, default=0.0),
        max(primary_widths, default=0.0),
        len(world.mouths),
        sum(trace.kind == "tributary" for trace in world.traces),
    )


__all__ = [
    "ContinuousRenderAuditV11",
    "PixelWindowV11",
    "composite_continuous_rivers_v11",
    "render_continuous_river_layer_v11",
    "validate_continuous_render_v11",
]
