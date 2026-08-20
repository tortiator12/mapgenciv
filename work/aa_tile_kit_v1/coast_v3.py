"""Organic production preset for the global Civ coastline field.

``coast_v2`` already supplies the important topology contract: one global SDF,
exact horizontal periodicity, deterministic world-space noise, crop equality,
diagonal bridges, and defect cleanup.  The remaining visual problem in the v7
maps is not topology but amplitude.  A seven-pixel displacement on a 96-pixel
cell leaves long shore runs visibly parallel to the logical square grid.

V3 adds a smooth, horizontally periodic coordinate warp *before* the proven v2
filter/SDF pipeline.  The warp bends the source grid itself, so long cardinal
shores no longer read as rounded rectangles.  Its amplitude is capped below one
quarter cell, preserving a generous safety corridor around every logical cell
centre.  A restrained eight-pixel contour perturbation adds smaller variation
afterward.  Logical cell centres are covered by tests.

Integration::

    coast = OrganicGlobalCoast(CoastV3Config(contour_seed=seed)).build(...)

V3.1 is the stronger production candidate.  It reconstructs a monotone field
through cell centres (a smooth marching-squares interpretation), applies a
topology-safe concave/convex corner correction, and adds an orientation-aware
tangent wave so long cardinal runs visibly bow::

    coast = TangentGlobalCoast(CoastV31Config(contour_seed=seed)).build(...)

The class names are separate from v2 so this remains an opt-in experiment; no
existing renderer changes merely by importing this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.ndimage import gaussian_filter

from .coast_v2 import (
    DEFAULT_TILE_PX,
    _VALID_PORT_BITS,
    _contour_noise,
    _enforce_diagonal_bridges,
    _mouth_openings,
    _periodic_value_noise,
    _remove_single_pixel_defects,
    _signed_distance,
    _smoothstep,
    CoastFields,
    CoastV2Config,
    GlobalCoastSDF,
    PixelWindow,
)


@dataclass(frozen=True)
class CoastV3Config(CoastV2Config):
    """The opt-in 96 px organic-coast calibration.

    Band widths remain compatible with the v7 compositor.  The new coordinate
    warp and broader rounding are the material silhouette changes; the river
    mouth length matches the current render rather than the older v2 default.
    """

    tile_px: int = DEFAULT_TILE_PX
    blur_sigma_px: float = 22.0
    gaussian_truncate: float = 4.0
    contour_variation_px: float = 8.0
    contour_seed: int = 1991
    max_distance_px: float = 48.0
    shallow_width_px: float = 30.0
    beach_width_px: float = 7.0
    foam_width_px: float = 2.0
    diagonal_bridge_px: float = 3.0
    mouth_width_px: float = 11.0
    mouth_length_px: float = 28.0
    warp_amplitude_px: float = 20.0
    warp_broad_scale_tiles: float = 2.1
    warp_detail_scale_tiles: float = 0.70
    warp_detail_mix: float = 0.32

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.warp_amplitude_px < 0:
            raise ValueError("warp_amplitude_px cannot be negative")
        if self.warp_amplitude_px >= self.tile_px * 0.24:
            raise ValueError("warp amplitude must stay below 24% of a logical cell")
        if self.warp_broad_scale_tiles <= 0 or self.warp_detail_scale_tiles <= 0:
            raise ValueError("warp scales must be positive")
        if not 0 <= self.warp_detail_mix <= 0.5:
            raise ValueError("warp_detail_mix must be between 0 and 0.5")
        # coast_v2 converts requested pixel displacement into a scalar addition
        # to the blurred occupancy field.  Keeping this strictly below 0.5 means
        # contour noise alone cannot flip pixels where occupancy is wholly 0/1.
        field_amplitude = self.contour_variation_px / (
            math.sqrt(2.0 * math.pi) * self.blur_sigma_px
        )
        if field_amplitude >= 0.46:
            raise ValueError(
                "organic contour variation is too strong for the solid-interior "
                "safety margin (field amplitude must stay below 0.46)"
            )


@dataclass(frozen=True)
class CoastV31Config(CoastV3Config):
    """V3.1 centre-interpolating coastline calibration.

    Rather than filtering a union of square cell footprints, V3.1 reconstructs
    a C1 field through the authoritative Civ cell centres.  Three-land/one-water
    marching-squares corners therefore become broad arcs instead of ninety-degree
    puzzle notches.  A shoreline-gated scalar perturbation bends long tangents
    without touching uniform interiors.
    """

    blur_sigma_px: float = 10.0
    contour_variation_px: float = 0.0
    warp_amplitude_px: float = 0.0
    tangent_variation_field: float = 0.30
    tangent_broad_scale_tiles: float = 1.80
    tangent_detail_scale_tiles: float = 0.60
    tangent_detail_mix: float = 0.35
    tangent_noise_gain: float = 1.55
    tangent_wave_field: float = 0.11
    tangent_wave_period_tiles: float = 2.6
    corner_bias_field: float = 0.12
    connection_radius_px: float = 2.5

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 <= self.tangent_variation_field <= 0.30:
            raise ValueError("tangent_variation_field must be between 0 and 0.30")
        if self.tangent_broad_scale_tiles <= 0 or self.tangent_detail_scale_tiles <= 0:
            raise ValueError("tangent noise scales must be positive")
        if not 0 <= self.tangent_detail_mix <= 0.5:
            raise ValueError("tangent_detail_mix must be between 0 and 0.5")
        if not 1.0 <= self.tangent_noise_gain <= 2.0:
            raise ValueError("tangent_noise_gain must be between 1.0 and 2.0")
        if not 0 <= self.tangent_wave_field <= 0.16:
            raise ValueError("tangent_wave_field must be between 0 and 0.16")
        if self.tangent_wave_period_tiles < 1.5:
            raise ValueError("tangent_wave_period_tiles must be at least 1.5")
        if not 0 <= self.corner_bias_field <= 0.22:
            raise ValueError("corner_bias_field must be between 0 and 0.22")
        if not 0 < self.connection_radius_px <= self.tile_px * 0.06:
            raise ValueError("connection_radius_px must be positive and at most 6% of a cell")


class OrganicGlobalCoast(GlobalCoastSDF):
    """Global coast builder with a bounded periodic coordinate warp."""

    def __init__(self, config: CoastV3Config | None = None):
        super().__init__(config or CoastV3Config())

    @property
    def organic_config(self) -> CoastV3Config:
        return self.config  # type: ignore[return-value]

    def _sample_source_field(
        self,
        logical: np.ndarray,
        xs: np.ndarray,
        ys: np.ndarray,
        *,
        world_width: int,
    ) -> np.ndarray:
        return _sample_warped_logical_land(
            logical,
            xs,
            ys,
            config=self.organic_config,
            world_width=world_width,
        )

    def _apply_contour_variation(
        self,
        smoothed: np.ndarray,
        xs: np.ndarray,
        ys: np.ndarray,
        *,
        world_width: int,
    ) -> None:
        config = self.organic_config
        if not config.contour_variation_px:
            return
        noise = _contour_noise(
            xs,
            ys,
            world_width=world_width,
            tile_px=config.tile_px,
            seed=config.contour_seed,
        )
        field_amplitude = config.contour_variation_px / (
            math.sqrt(2.0 * math.pi) * config.blur_sigma_px
        )
        smoothed += noise * np.float32(field_amplitude)

    def _enforce_topology(
        self,
        hard: np.ndarray,
        logical: np.ndarray,
        *,
        x_start: int,
        y_start: int,
        world_width: int,
    ) -> None:
        _enforce_warped_diagonal_bridges(
            hard,
            logical,
            x_start=x_start,
            y_start=y_start,
            config=self.organic_config,
            world_width=world_width,
        )

    def _visual_bands(
        self,
        signed: np.ndarray,
        coverage: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        config = self.organic_config
        water_gate = np.float32(1.0) - coverage
        shallow = _smoothstep(-config.shallow_width_px, -0.5, signed) * water_gate
        beach_inner = _smoothstep(-0.6, 0.8, signed)
        beach_outer = np.float32(1.0) - _smoothstep(
            config.beach_width_px * 0.62,
            config.beach_width_px,
            signed,
        )
        beach = beach_inner * beach_outer
        foam_center = -0.85
        foam_distance = np.abs(signed - foam_center)
        foam = np.float32(1.0) - _smoothstep(
            config.foam_width_px * 0.32,
            config.foam_width_px,
            foam_distance,
        )
        foam *= np.float32(1.0) - _smoothstep(0.35, 1.35, signed)
        return shallow, beach, foam

    def build(
        self,
        land_cells: np.ndarray,
        *,
        window: PixelWindow | None = None,
        mouth_ports: np.ndarray | None = None,
    ) -> CoastFields:
        """Build fields using the v2 contract after warping logical occupancy."""

        config = self.organic_config
        logical = np.asarray(land_cells, dtype=bool)
        if logical.ndim != 2 or logical.shape[0] == 0 or logical.shape[1] == 0:
            raise ValueError("land_cells must be a non-empty 2D array")
        grid_height, grid_width = logical.shape
        world_width = grid_width * config.tile_px
        world_height = grid_height * config.tile_px
        output = window or PixelWindow(0, 0, world_width, world_height)
        output.validate(world_height)

        ports: np.ndarray | None
        if mouth_ports is None:
            ports = None
        else:
            raw_ports = np.asarray(mouth_ports)
            if raw_ports.shape != logical.shape:
                raise ValueError("mouth_ports must match land_cells")
            if not np.issubdtype(raw_ports.dtype, np.integer):
                raise ValueError("mouth_ports must contain integer NESW bit masks")
            validation_ports = raw_ports.astype(np.int64, copy=False)
            if np.any(validation_ports < 0) or np.any(
                validation_ports & ~_VALID_PORT_BITS
            ):
                raise ValueError("mouth_ports may only contain NESW bits 1,2,4,8")
            ports = raw_ports.astype(np.uint8, copy=False)

        blur_radius = int(
            math.ceil(config.blur_sigma_px * config.gaussian_truncate)
        )
        prefilter_guard = blur_radius + 2
        distance_halo = int(math.ceil(config.max_distance_px)) + 3
        total_halo = prefilter_guard + distance_halo

        x_start = output.x - total_halo
        y_start = output.y - total_halo
        work_width = output.width + total_halo * 2
        work_height = output.height + total_halo * 2
        xs = np.arange(x_start, x_start + work_width, dtype=np.int64)
        ys = np.arange(y_start, y_start + work_height, dtype=np.int64)

        occupancy = self._sample_source_field(
            logical, xs, ys, world_width=world_width
        )
        smoothed = gaussian_filter(
            occupancy,
            sigma=config.blur_sigma_px,
            mode="constant",
            cval=0.0,
            radius=blur_radius,
            output=np.float32,
        )
        del occupancy

        self._apply_contour_variation(
            smoothed, xs, ys, world_width=world_width
        )
        hard_work = smoothed >= 0.5
        del smoothed
        hard_work = _remove_single_pixel_defects(hard_work)
        self._enforce_topology(
            hard_work,
            logical,
            x_start=x_start,
            y_start=y_start,
            world_width=world_width,
        )
        hard_work = _remove_single_pixel_defects(hard_work)

        analysis_start = prefilter_guard
        hard_analysis = hard_work[
            analysis_start : work_height - prefilter_guard,
            analysis_start : work_width - prefilter_guard,
        ]
        signed_analysis = _signed_distance(hard_analysis, config.max_distance_px)

        crop = distance_halo
        crop_y = slice(crop, crop + output.height)
        crop_x = slice(crop, crop + output.width)
        hard = hard_analysis[crop_y, crop_x].copy()
        signed = signed_analysis[crop_y, crop_x].copy()

        coverage = _smoothstep(-0.75, 0.75, signed).astype(np.float32)
        shallow, beach, foam = self._visual_bands(signed, coverage)

        mouth_opening = _mouth_openings(logical, ports, output, config)
        if np.any(mouth_opening):
            keep_shore = np.float32(1.0) - mouth_opening
            beach *= keep_shore
            foam *= keep_shore

        return CoastFields(
            window=output,
            world_size=(world_width, world_height),
            land_coverage=coverage.astype(np.float32, copy=False),
            land_hard=hard,
            signed_distance=signed,
            shallow=shallow.astype(np.float32, copy=False),
            beach=beach.astype(np.float32, copy=False),
            foam=foam.astype(np.float32, copy=False),
            mouth_opening=mouth_opening,
        )


class TangentGlobalCoast(OrganicGlobalCoast):
    """V3.1 marching-centre reconstruction with visibly curved tangents."""

    def __init__(self, config: CoastV31Config | None = None):
        super().__init__(config or CoastV31Config())

    @property
    def tangent_config(self) -> CoastV31Config:
        return self.config  # type: ignore[return-value]

    def _sample_source_field(
        self,
        logical: np.ndarray,
        xs: np.ndarray,
        ys: np.ndarray,
        *,
        world_width: int,
    ) -> np.ndarray:
        del world_width
        return _sample_cell_centre_field(
            logical,
            xs,
            ys,
            tile_px=self.tangent_config.tile_px,
            corner_bias_field=self.tangent_config.corner_bias_field,
        )

    def _apply_contour_variation(
        self,
        smoothed: np.ndarray,
        xs: np.ndarray,
        ys: np.ndarray,
        *,
        world_width: int,
    ) -> None:
        config = self.tangent_config
        if not (config.tangent_variation_field or config.tangent_wave_field):
            return
        # Exactly zero in uniform interiors and strongest at the 0.5 contour.
        # The gate makes the perturbation a tangent deformation, not a source of
        # detached islands or inland pinholes.
        shore_gate = np.clip(
            np.float32(4.0) * smoothed * (np.float32(1.0) - smoothed),
            0.0,
            1.0,
        )
        shore_gate *= shore_gate
        if config.tangent_variation_field:
            broad = _periodic_value_noise(
                xs,
                ys,
                world_width=world_width,
                scale_px=config.tile_px * config.tangent_broad_scale_tiles,
                seed=config.contour_seed ^ 0xA4093822,
            )
            detail = _periodic_value_noise(
                xs,
                ys,
                world_width=world_width,
                scale_px=config.tile_px * config.tangent_detail_scale_tiles,
                seed=config.contour_seed ^ 0x299F31D0,
            )
            noise = broad * np.float32(1.0 - config.tangent_detail_mix)
            noise += detail * np.float32(config.tangent_detail_mix)
            noise *= np.float32(config.tangent_noise_gain)
            np.clip(noise, -1.0, 1.0, out=noise)
            smoothed += (
                noise
                * shore_gate
                * np.float32(config.tangent_variation_field)
            )
        if config.tangent_wave_field:
            # Orientation-aware harmonic guarantees that an otherwise uniform
            # run of cardinal marching squares bows over several cells.  X uses
            # an integer cycle count, retaining exact horizontal periodicity.
            gradient_y, gradient_x = np.gradient(smoothed)
            abs_x = np.abs(gradient_x)
            abs_y = np.abs(gradient_y)
            vertical_weight = abs_x / (abs_x + abs_y + np.float32(1e-6))
            cycles_x = max(
                1,
                int(round(
                    world_width
                    / (config.tile_px * config.tangent_wave_period_tiles)
                )),
            )
            phase_x = (
                np.mod(xs, world_width).astype(np.float64)
                * (2.0 * math.pi * cycles_x / world_width)
            )
            phase_y = (
                ys.astype(np.float64)
                * (2.0 * math.pi / (
                    config.tile_px * config.tangent_wave_period_tiles
                ))
            )
            vertical_wave = np.sin(
                phase_y[:, None]
                + 0.55 * np.sin(phase_x[None, :] * 2.0)
            )
            horizontal_wave = np.sin(
                phase_x[None, :]
                + 0.55 * np.sin(phase_y[:, None] * 0.5)
            )
            tangent_wave = (
                vertical_weight * vertical_wave
                + (np.float32(1.0) - vertical_weight) * horizontal_wave
            )
            smoothed += (
                tangent_wave.astype(np.float32)
                * shore_gate
                * np.float32(config.tangent_wave_field)
            )
        np.clip(smoothed, 0.0, 1.0, out=smoothed)

    def _enforce_topology(
        self,
        hard: np.ndarray,
        logical: np.ndarray,
        *,
        x_start: int,
        y_start: int,
        world_width: int,
    ) -> None:
        del world_width
        _enforce_diagonal_bridges(
            hard,
            logical,
            x_start=x_start,
            y_start=y_start,
            tile_px=self.tangent_config.tile_px,
            radius=self.tangent_config.diagonal_bridge_px,
        )
        _enforce_logical_connections(
            hard,
            logical,
            x_start=x_start,
            y_start=y_start,
            tile_px=self.tangent_config.tile_px,
            radius=self.tangent_config.connection_radius_px,
        )

    def _visual_bands(
        self,
        signed: np.ndarray,
        coverage: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        del coverage
        config = self.tangent_config
        shallow = _smoothstep(-config.shallow_width_px, -0.5, signed)
        shallow = np.where(signed < 0.0, shallow, 0.0)
        beach = np.float32(1.0) - _smoothstep(
            config.beach_width_px * 0.62,
            config.beach_width_px,
            signed,
        )
        beach = np.where(signed > 0.0, beach, 0.0)
        foam_distance = np.abs(signed + np.float32(0.85))
        foam = np.float32(1.0) - _smoothstep(
            config.foam_width_px * 0.32,
            config.foam_width_px,
            foam_distance,
        )
        foam = np.where(signed < 0.0, foam, 0.0)
        return (
            shallow.astype(np.float32, copy=False),
            beach.astype(np.float32, copy=False),
            foam.astype(np.float32, copy=False),
        )


def _sample_cell_centre_field(
    land_cells: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    *,
    tile_px: int,
    corner_bias_field: float,
) -> np.ndarray:
    """C1 monotone interpolation through authoritative logical cell centres."""

    grid_height, grid_width = land_cells.shape
    grid_x = xs.astype(np.float64) / float(tile_px) - 0.5
    x0_raw = np.floor(grid_x).astype(np.int64)
    x1_raw = x0_raw + 1
    x0 = np.mod(x0_raw, grid_width)
    x1 = np.mod(x1_raw, grid_width)
    fx = (grid_x - x0_raw).astype(np.float32)
    sx = fx * fx * (np.float32(3.0) - np.float32(2.0) * fx)

    result = np.empty((ys.size, xs.size), dtype=np.float32)
    for row_start in range(0, ys.size, 128):
        row_end = min(row_start + 128, ys.size)
        grid_y = ys[row_start:row_end].astype(np.float64) / float(tile_px) - 0.5
        y0 = np.floor(grid_y).astype(np.int64)
        y1 = y0 + 1
        fy = (grid_y - y0).astype(np.float32)
        sy = fy * fy * (np.float32(3.0) - np.float32(2.0) * fy)

        valid0 = (y0 >= 0) & (y0 < grid_height)
        valid1 = (y1 >= 0) & (y1 < grid_height)
        safe0 = np.clip(y0, 0, grid_height - 1)
        safe1 = np.clip(y1, 0, grid_height - 1)
        v00 = land_cells[safe0[:, None], x0[None, :]] & valid0[:, None]
        v10 = land_cells[safe0[:, None], x1[None, :]] & valid0[:, None]
        v01 = land_cells[safe1[:, None], x0[None, :]] & valid1[:, None]
        v11 = land_cells[safe1[:, None], x1[None, :]] & valid1[:, None]
        top = v00.astype(np.float32)
        top += (v10.astype(np.float32) - top) * sx[None, :]
        bottom = v01.astype(np.float32)
        bottom += (v11.astype(np.float32) - bottom) * sx[None, :]
        field = top + (bottom - top) * sy[:, None]
        if corner_bias_field:
            # Marching-square curvature correction: a three-land corner fills a
            # concave puzzle notch, while a one-land corner trims the matching
            # convex elbow.  The shoreline gate is exactly zero at authoritative
            # 0/1 centres, so rule classification cannot move.
            count = (
                v00.astype(np.int8)
                + v10.astype(np.int8)
                + v01.astype(np.int8)
                + v11.astype(np.int8)
            )
            curvature = np.zeros_like(field)
            curvature[count == 3] = np.float32(1.0)
            curvature[count == 1] = np.float32(-1.0)
            gate = np.clip(
                np.float32(4.0) * field * (np.float32(1.0) - field),
                0.0,
                1.0,
            )
            field += (
                curvature
                * gate
                * np.float32(corner_bias_field)
            )
            np.clip(field, 0.0, 1.0, out=field)
        result[row_start:row_end] = field
    return result


def _enforce_logical_connections(
    hard: np.ndarray,
    land_cells: np.ndarray,
    *,
    x_start: int,
    y_start: int,
    tile_px: int,
    radius: float,
) -> None:
    """Keep every logical eight-neighbour land edge in the raster component.

    Centre interpolation can turn an ambiguous diagonal saddle into water after
    tangent deformation.  A sub-six-percent capsule along only declared logical
    neighbour links is invisible inside ordinary land but makes component
    preservation exact.  No capsule is ever drawn between distinct components.
    """

    grid_height, grid_width = land_cells.shape
    world_width = grid_width * tile_px
    height, width = hard.shape
    for cell_y_raw, cell_x_raw in np.argwhere(land_cells):
        cell_y = int(cell_y_raw)
        cell_x = int(cell_x_raw)
        for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
            neighbour_y = cell_y + dy
            if not 0 <= neighbour_y < grid_height:
                continue
            neighbour_x = (cell_x + dx) % grid_width
            if not land_cells[neighbour_y, neighbour_x]:
                continue
            base_x = (cell_x + 0.5) * tile_px
            base_y = (cell_y + 0.5) * tile_px
            first_repeat = math.floor(
                (x_start - radius - base_x - abs(dx) * tile_px) / world_width
            )
            last_repeat = math.ceil(
                (x_start + width + radius - base_x + abs(dx) * tile_px)
                / world_width
            )
            for repeat in range(first_repeat, last_repeat + 1):
                ax = base_x + repeat * world_width
                ay = base_y
                bx = ax + dx * tile_px
                by = ay + dy * tile_px
                left = max(0, int(math.floor(min(ax, bx) - radius - x_start)))
                right = min(width, int(math.ceil(max(ax, bx) + radius - x_start)))
                top = max(0, int(math.floor(min(ay, by) - radius - y_start)))
                bottom = min(height, int(math.ceil(max(ay, by) + radius - y_start)))
                if left >= right or top >= bottom:
                    continue
                px = x_start + np.arange(left, right, dtype=np.float32) + 0.5
                py = y_start + np.arange(top, bottom, dtype=np.float32) + 0.5
                vx, vy = bx - ax, by - ay
                length_squared = float(vx * vx + vy * vy)
                projection = (
                    (px[None, :] - ax) * vx
                    + (py[:, None] - ay) * vy
                ) / length_squared
                projection = np.clip(projection, 0.0, 1.0)
                nearest_x = ax + projection * vx
                nearest_y = ay + projection * vy
                capsule = (
                    (px[None, :] - nearest_x) ** 2
                    + (py[:, None] - nearest_y) ** 2
                    <= radius * radius
                )
                hard[top:bottom, left:right][capsule] = True


def _warp_offsets(
    xs: np.ndarray,
    ys: np.ndarray,
    *,
    config: CoastV3Config,
    world_width: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return smooth periodic source-coordinate offsets for one row block."""

    broad_scale = config.tile_px * config.warp_broad_scale_tiles
    detail_scale = config.tile_px * config.warp_detail_scale_tiles
    detail_mix = np.float32(config.warp_detail_mix)
    broad_mix = np.float32(1.0 - config.warp_detail_mix)

    dx = _periodic_value_noise(
        xs,
        ys,
        world_width=world_width,
        scale_px=broad_scale,
        seed=config.contour_seed ^ 0x243F6A88,
    )
    dx *= broad_mix
    dx += _periodic_value_noise(
        xs,
        ys,
        world_width=world_width,
        scale_px=detail_scale,
        seed=config.contour_seed ^ 0x85A308D3,
    ) * detail_mix
    dx *= np.float32(config.warp_amplitude_px)

    dy = _periodic_value_noise(
        xs,
        ys,
        world_width=world_width,
        scale_px=broad_scale,
        seed=config.contour_seed ^ 0x13198A2E,
    )
    dy *= broad_mix
    dy += _periodic_value_noise(
        xs,
        ys,
        world_width=world_width,
        scale_px=detail_scale,
        seed=config.contour_seed ^ 0x03707344,
    ) * detail_mix
    dy *= np.float32(config.warp_amplitude_px)
    return dx, dy


def _sample_warped_logical_land(
    land_cells: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    *,
    config: CoastV3Config,
    world_width: int,
) -> np.ndarray:
    """Sample the logical grid through the organic warp with bounded memory."""

    grid_height, grid_width = land_cells.shape
    result = np.empty((ys.size, xs.size), dtype=np.float32)
    # A full 80x50 world remains practical: only occupancy is world-sized;
    # transient float coordinate/noise matrices are limited to 128 rows.
    for row_start in range(0, ys.size, 128):
        row_end = min(row_start + 128, ys.size)
        block_y = ys[row_start:row_end]
        dx, dy = _warp_offsets(
            xs,
            block_y,
            config=config,
            world_width=world_width,
        )
        warped_x = xs[None, :].astype(np.float32) + dx
        warped_y = block_y[:, None].astype(np.float32) + dy
        cell_x = np.mod(np.floor(warped_x / config.tile_px).astype(np.int64), grid_width)
        cell_y = np.floor(warped_y / config.tile_px).astype(np.int64)
        valid_y = (cell_y >= 0) & (cell_y < grid_height)
        safe_y = np.clip(cell_y, 0, grid_height - 1)
        sampled = land_cells[safe_y, cell_x] & valid_y
        result[row_start:row_end] = sampled.astype(np.float32)
    return result


def _deformed_vertex(
    vertex_x: float,
    vertex_y: float,
    *,
    config: CoastV3Config,
    world_width: int,
) -> tuple[float, float]:
    """Solve p + warp(p) = logical vertex using stable fixed-point steps."""

    px, py = vertex_x, vertex_y
    for _ in range(5):
        dx, dy = _warp_offsets(
            np.asarray([px], dtype=np.float64),
            np.asarray([py], dtype=np.float64),
            config=config,
            world_width=world_width,
        )
        px = vertex_x - float(dx[0, 0])
        py = vertex_y - float(dy[0, 0])
    return px, py


def _enforce_warped_diagonal_bridges(
    hard: np.ndarray,
    land_cells: np.ndarray,
    *,
    x_start: int,
    y_start: int,
    config: CoastV3Config,
    world_width: int,
) -> None:
    """Resolve checkerboard saddles at their deformed world-space vertex."""

    radius = config.diagonal_bridge_px
    if radius <= 0:
        return
    grid_height, grid_width = land_cells.shape
    height, width = hard.shape
    margin = radius + config.warp_amplitude_px
    first_kx = math.floor((x_start - margin) / config.tile_px)
    last_kx = math.ceil((x_start + width + margin) / config.tile_px)
    first_ky = max(1, math.floor((y_start - margin) / config.tile_px))
    last_ky = min(
        grid_height - 1,
        math.ceil((y_start + height + margin) / config.tile_px),
    )
    for ky in range(first_ky, last_ky + 1):
        for kx in range(first_kx, last_kx + 1):
            canonical_x = kx % grid_width
            west_x = (canonical_x - 1) % grid_width
            north_y, south_y = ky - 1, ky
            nw = bool(land_cells[north_y, west_x])
            ne = bool(land_cells[north_y, canonical_x])
            sw = bool(land_cells[south_y, west_x])
            se = bool(land_cells[south_y, canonical_x])
            if not ((nw and se and not ne and not sw) or (ne and sw and not nw and not se)):
                continue
            vertex_x, vertex_y = _deformed_vertex(
                kx * config.tile_px,
                ky * config.tile_px,
                config=config,
                world_width=world_width,
            )
            left = max(0, int(math.floor(vertex_x - radius - x_start)))
            right = min(width, int(math.ceil(vertex_x + radius - x_start)))
            top = max(0, int(math.floor(vertex_y - radius - y_start)))
            bottom = min(height, int(math.ceil(vertex_y + radius - y_start)))
            if left >= right or top >= bottom:
                continue
            pixel_x = x_start + np.arange(left, right, dtype=np.float32) + 0.5
            pixel_y = y_start + np.arange(top, bottom, dtype=np.float32) + 0.5
            disk = (
                (pixel_x[None, :] - vertex_x) ** 2
                + (pixel_y[:, None] - vertex_y) ** 2
                <= radius * radius
            )
            target = hard[top:bottom, left:right]
            target[disk] = True


def build_organic_coast(
    land_cells,
    *,
    window: PixelWindow | None = None,
    mouth_ports=None,
    config: CoastV3Config | None = None,
) -> CoastFields:
    """Build v3 coast fields without constructing the wrapper explicitly."""

    return OrganicGlobalCoast(config).build(
        land_cells,
        window=window,
        mouth_ports=mouth_ports,
    )


def build_tangent_coast(
    land_cells,
    *,
    window: PixelWindow | None = None,
    mouth_ports=None,
    config: CoastV31Config | None = None,
) -> CoastFields:
    """Build V3.1 tangent-rounded fields."""

    return TangentGlobalCoast(config).build(
        land_cells,
        window=window,
        mouth_ports=mouth_ports,
    )


__all__ = [
    "CoastV3Config",
    "CoastV31Config",
    "OrganicGlobalCoast",
    "TangentGlobalCoast",
    "build_organic_coast",
    "build_tangent_coast",
]
