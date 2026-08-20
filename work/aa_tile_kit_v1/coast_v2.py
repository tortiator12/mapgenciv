"""Global, horizontally periodic coastline fields for Civ-style square maps.

The logical map is deliberately kept separate from its presentation.  Civ cells
define the land topology, but no rounded rectangle is drawn per cell.  Instead the
whole occupancy field is filtered once, varied by deterministic world-space noise,
resolved into an eight-neighbour hard contour, and converted to a signed distance
field (SDF).  The SDF then drives antialiased land coverage and the shallow-water,
beach, and foam bands.

The builder renders finite windows with a private analysis halo.  Distances are
clipped at ``max_distance_px``; consequently a window is pixel-identical to the
same wrapped crop of a full render while avoiding a roughly 7,680 x 4,800 set of
temporary arrays for the default 80 x 50, 96-pixel Civ world.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Final

import numpy as np
from scipy.ndimage import convolve, distance_transform_edt, gaussian_filter


CIV1_GRID_SIZE: Final[tuple[int, int]] = (80, 50)
DEFAULT_TILE_PX: Final[int] = 96

PORT_N: Final[int] = 1
PORT_E: Final[int] = 2
PORT_S: Final[int] = 4
PORT_W: Final[int] = 8
_VALID_PORT_BITS: Final[int] = PORT_N | PORT_E | PORT_S | PORT_W


@dataclass(frozen=True)
class PixelWindow:
    """A world-pixel output rectangle.

    ``x`` may be negative or cross the right edge: the world wraps horizontally.
    The vertical axis does not wrap and must stay inside the logical map.
    """

    x: int
    y: int
    width: int
    height: int

    def validate(self, world_height: int) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("window dimensions must be positive")
        if self.y < 0 or self.y + self.height > world_height:
            raise ValueError("window must stay inside the non-wrapping vertical world")


@dataclass(frozen=True)
class CoastV2Config:
    """Visual and numerical coastline controls, in world pixels."""

    tile_px: int = DEFAULT_TILE_PX
    blur_sigma_px: float = 10.5
    gaussian_truncate: float = 4.0
    contour_variation_px: float = 3.0
    contour_seed: int = 1991
    max_distance_px: float = 48.0
    shallow_width_px: float = 24.0
    beach_width_px: float = 8.0
    foam_width_px: float = 3.5
    diagonal_bridge_px: float = 2.5
    mouth_width_px: float = 11.0
    mouth_length_px: float = 24.0

    def __post_init__(self) -> None:
        positive = {
            "tile_px": self.tile_px,
            "blur_sigma_px": self.blur_sigma_px,
            "gaussian_truncate": self.gaussian_truncate,
            "max_distance_px": self.max_distance_px,
            "shallow_width_px": self.shallow_width_px,
            "beach_width_px": self.beach_width_px,
            "foam_width_px": self.foam_width_px,
            "mouth_width_px": self.mouth_width_px,
            "mouth_length_px": self.mouth_length_px,
        }
        if any(value <= 0 for value in positive.values()):
            invalid = ", ".join(name for name, value in positive.items() if value <= 0)
            raise ValueError(f"coast dimensions must be positive: {invalid}")
        if self.contour_variation_px < 0 or self.diagonal_bridge_px < 0:
            raise ValueError("variation and diagonal bridge widths cannot be negative")
        required_distance = max(
            self.shallow_width_px,
            self.beach_width_px,
            self.foam_width_px * 2.0,
        )
        if self.max_distance_px < required_distance + 2.0:
            raise ValueError(
                "max_distance_px must cover all visible coast bands plus two pixels"
            )


@dataclass(frozen=True)
class CoastFields:
    """Pixel fields returned for one output window.

    All arrays are ``float32`` in the range 0..1 except ``land_hard`` (boolean)
    and ``signed_distance`` (pixels, positive on land and negative in water).
    ``mouth_opening`` is the alpha used to interrupt beach and foam at declared
    river exits; the terrain SDF itself is intentionally not cut by this overlay.
    """

    window: PixelWindow
    world_size: tuple[int, int]
    land_coverage: np.ndarray
    land_hard: np.ndarray
    signed_distance: np.ndarray
    shallow: np.ndarray
    beach: np.ndarray
    foam: np.ndarray
    mouth_opening: np.ndarray

    def __post_init__(self) -> None:
        expected = (self.window.height, self.window.width)
        arrays = (
            self.land_coverage,
            self.land_hard,
            self.signed_distance,
            self.shallow,
            self.beach,
            self.foam,
            self.mouth_opening,
        )
        if any(array.shape != expected for array in arrays):
            raise ValueError("every coast field must match the output window")


def _smoothstep(edge0: float, edge1: float, values: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        raise ValueError("smoothstep edge1 must be greater than edge0")
    unit = np.clip((values - edge0) / (edge1 - edge0), 0.0, 1.0)
    return unit * unit * (3.0 - 2.0 * unit)


def _lattice_hash(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """Portable integer hash returning deterministic values in -1..1."""

    x = np.asarray(ix, dtype=np.int64).astype(np.uint64, copy=False)
    y = np.asarray(iy, dtype=np.int64).astype(np.uint64, copy=False)
    seed_value = np.uint64(seed & 0xFFFFFFFFFFFFFFFF)
    with np.errstate(over="ignore"):
        value = (
            x * np.uint64(0x9E3779B185EBCA87)
            ^ y * np.uint64(0xC2B2AE3D27D4EB4F)
            ^ seed_value * np.uint64(0x165667B19E3779F9)
        )
        value ^= value >> np.uint64(30)
        value *= np.uint64(0xBF58476D1CE4E5B9)
        value ^= value >> np.uint64(27)
        value *= np.uint64(0x94D049BB133111EB)
        value ^= value >> np.uint64(31)
    mantissa = (value >> np.uint64(40)).astype(np.float32)
    return mantissa * np.float32(2.0 / float(1 << 24)) - np.float32(1.0)


def _periodic_value_noise(
    xs: np.ndarray,
    ys: np.ndarray,
    *,
    world_width: int,
    scale_px: float,
    seed: int,
) -> np.ndarray:
    """Smooth value noise whose x period is exactly ``world_width`` pixels."""

    lattice_width = max(4, int(round(world_width / scale_px)))
    x_phase = (np.mod(xs, world_width).astype(np.float64) * lattice_width) / float(
        world_width
    )
    y_phase = ys.astype(np.float64) / float(scale_px)

    x0_raw = np.floor(x_phase).astype(np.int64)
    y0 = np.floor(y_phase).astype(np.int64)
    x0 = np.mod(x0_raw, lattice_width)
    x1 = (x0 + 1) % lattice_width
    y1 = y0 + 1

    fx = (x_phase - x0_raw).astype(np.float32)
    fy = (y_phase - y0).astype(np.float32)
    fx = fx * fx * (np.float32(3.0) - np.float32(2.0) * fx)
    fy = fy * fy * (np.float32(3.0) - np.float32(2.0) * fy)

    top = _lattice_hash(x0[None, :], y0[:, None], seed)
    top += (_lattice_hash(x1[None, :], y0[:, None], seed) - top) * fx[None, :]
    bottom = _lattice_hash(x0[None, :], y1[:, None], seed)
    bottom += (
        _lattice_hash(x1[None, :], y1[:, None], seed) - bottom
    ) * fx[None, :]
    return (top + (bottom - top) * fy[:, None]).astype(np.float32, copy=False)


def _contour_noise(
    xs: np.ndarray,
    ys: np.ndarray,
    *,
    world_width: int,
    tile_px: int,
    seed: int,
) -> np.ndarray:
    broad = _periodic_value_noise(
        xs,
        ys,
        world_width=world_width,
        scale_px=tile_px * 1.65,
        seed=seed,
    )
    detail = _periodic_value_noise(
        xs,
        ys,
        world_width=world_width,
        scale_px=tile_px * 0.57,
        seed=seed ^ 0x6D2B79F5,
    )
    broad *= np.float32(0.72)
    broad += detail * np.float32(0.28)
    return broad


def _sample_logical_land(
    land_cells: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    tile_px: int,
) -> np.ndarray:
    grid_height, grid_width = land_cells.shape
    cell_x = np.mod(np.floor_divide(xs, tile_px), grid_width)
    cell_y = np.floor_divide(ys, tile_px)
    valid_y = (cell_y >= 0) & (cell_y < grid_height)
    safe_y = np.clip(cell_y, 0, grid_height - 1)
    sampled = land_cells[safe_y[:, None], cell_x[None, :]]
    return (sampled & valid_y[:, None]).astype(np.float32)


def _remove_single_pixel_defects(hard: np.ndarray) -> np.ndarray:
    kernel = np.ones((3, 3), dtype=np.uint8)
    kernel[1, 1] = 0
    neighbours = convolve(
        hard.astype(np.uint8), kernel, mode="constant", cval=0
    )
    cleaned = hard.copy()
    cleaned[(~hard) & (neighbours == 8)] = True
    cleaned[hard & (neighbours == 0)] = False
    return cleaned


def _enforce_diagonal_bridges(
    hard: np.ndarray,
    land_cells: np.ndarray,
    *,
    x_start: int,
    y_start: int,
    tile_px: int,
    radius: float,
) -> None:
    """Choose land connectivity for ambiguous checkerboard vertices.

    A Civ map treats diagonally touching land as eight-neighbour connected.  A tiny
    bridge at an exact checkerboard saddle makes that choice explicit and stable
    against contour noise without visibly moving ordinary coast edges.
    """

    if radius <= 0:
        return
    grid_height, grid_width = land_cells.shape
    world_width = grid_width * tile_px
    height, width = hard.shape
    x_end = x_start + width
    y_end = y_start + height
    first_kx = math.floor((x_start - radius) / tile_px)
    last_kx = math.ceil((x_end + radius) / tile_px)
    first_ky = max(1, math.floor((y_start - radius) / tile_px))
    last_ky = min(grid_height - 1, math.ceil((y_end + radius) / tile_px))

    for ky in range(first_ky, last_ky + 1):
        vertex_y = ky * tile_px
        for kx in range(first_kx, last_kx + 1):
            vertex_x = kx * tile_px
            canonical_x = (vertex_x % world_width) // tile_px
            west_x = (canonical_x - 1) % grid_width
            east_x = canonical_x % grid_width
            north_y = ky - 1
            south_y = ky
            nw = bool(land_cells[north_y, west_x])
            ne = bool(land_cells[north_y, east_x])
            sw = bool(land_cells[south_y, west_x])
            se = bool(land_cells[south_y, east_x])
            checkerboard = (nw and se and not ne and not sw) or (
                ne and sw and not nw and not se
            )
            if not checkerboard:
                continue

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


def _signed_distance(hard: np.ndarray, clip_at: float) -> np.ndarray:
    """Return a half-pixel-centered, clipped SDF for an analysis-halo mask."""

    padded_land = np.pad(hard, 1, mode="constant", constant_values=False)
    inside = distance_transform_edt(padded_land)[1:-1, 1:-1]
    del padded_land
    padded_water = np.pad(~hard, 1, mode="constant", constant_values=False)
    outside = distance_transform_edt(padded_water)[1:-1, 1:-1]
    del padded_water
    signed = np.where(hard, inside - 0.5, -(outside - 0.5))
    del inside, outside
    return np.clip(signed, -clip_at, clip_at).astype(np.float32)


def _port_faces_water(
    land_cells: np.ndarray, cell_x: int, cell_y: int, port: int
) -> bool:
    height, width = land_cells.shape
    if port == PORT_N:
        return cell_y == 0 or not bool(land_cells[cell_y - 1, cell_x])
    if port == PORT_S:
        return cell_y == height - 1 or not bool(land_cells[cell_y + 1, cell_x])
    if port == PORT_E:
        return not bool(land_cells[cell_y, (cell_x + 1) % width])
    if port == PORT_W:
        return not bool(land_cells[cell_y, (cell_x - 1) % width])
    raise ValueError(f"unknown port bit {port}")


def _mouth_openings(
    land_cells: np.ndarray,
    port_masks: np.ndarray | None,
    window: PixelWindow,
    config: CoastV2Config,
) -> np.ndarray:
    result = np.zeros((window.height, window.width), dtype=np.float32)
    if port_masks is None or not np.any(port_masks):
        return result

    grid_height, grid_width = land_cells.shape
    world_width = grid_width * config.tile_px
    active = np.argwhere(port_masks != 0)
    for cell_y_raw, cell_x_raw in active:
        cell_y = int(cell_y_raw)
        cell_x = int(cell_x_raw)
        bits = int(port_masks[cell_y, cell_x])
        for port in (PORT_N, PORT_E, PORT_S, PORT_W):
            if not bits & port or not _port_faces_water(
                land_cells, cell_x, cell_y, port
            ):
                continue
            if port == PORT_N:
                center_x = (cell_x + 0.5) * config.tile_px
                center_y = cell_y * config.tile_px
                radius_x = config.mouth_width_px * 0.5
                radius_y = config.mouth_length_px * 0.5
            elif port == PORT_S:
                center_x = (cell_x + 0.5) * config.tile_px
                center_y = (cell_y + 1) * config.tile_px
                radius_x = config.mouth_width_px * 0.5
                radius_y = config.mouth_length_px * 0.5
            elif port == PORT_E:
                center_x = (cell_x + 1) * config.tile_px
                center_y = (cell_y + 0.5) * config.tile_px
                radius_x = config.mouth_length_px * 0.5
                radius_y = config.mouth_width_px * 0.5
            else:
                center_x = cell_x * config.tile_px
                center_y = (cell_y + 0.5) * config.tile_px
                radius_x = config.mouth_length_px * 0.5
                radius_y = config.mouth_width_px * 0.5

            first_repeat = math.floor(
                (window.x - radius_x - center_x) / world_width
            )
            last_repeat = math.ceil(
                (window.x + window.width + radius_x - center_x) / world_width
            )
            for repeat in range(first_repeat, last_repeat + 1):
                repeated_x = center_x + repeat * world_width
                left = max(
                    0, int(math.floor(repeated_x - radius_x - window.x))
                )
                right = min(
                    window.width,
                    int(math.ceil(repeated_x + radius_x - window.x)),
                )
                top = max(0, int(math.floor(center_y - radius_y - window.y)))
                bottom = min(
                    window.height,
                    int(math.ceil(center_y + radius_y - window.y)),
                )
                if left >= right or top >= bottom:
                    continue
                px = window.x + np.arange(left, right, dtype=np.float32) + 0.5
                py = window.y + np.arange(top, bottom, dtype=np.float32) + 0.5
                ellipse = (
                    ((px[None, :] - repeated_x) / radius_x) ** 2
                    + ((py[:, None] - center_y) / radius_y) ** 2
                )
                strength = np.clip(1.0 - ellipse, 0.0, 1.0).astype(np.float32)
                strength = strength * strength * (3.0 - 2.0 * strength)
                target = result[top:bottom, left:right]
                np.maximum(target, strength, out=target)
    return result


class GlobalCoastSDF:
    """Build continuous coastline fields for a complete logical world or a crop."""

    def __init__(self, config: CoastV2Config | None = None):
        self.config = config or CoastV2Config()

    def build(
        self,
        land_cells: np.ndarray,
        *,
        window: PixelWindow | None = None,
        mouth_ports: np.ndarray | None = None,
    ) -> CoastFields:
        logical = np.asarray(land_cells, dtype=bool)
        if logical.ndim != 2 or logical.shape[0] == 0 or logical.shape[1] == 0:
            raise ValueError("land_cells must be a non-empty 2D array")
        grid_height, grid_width = logical.shape
        world_width = grid_width * self.config.tile_px
        world_height = grid_height * self.config.tile_px
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
            math.ceil(
                self.config.blur_sigma_px * self.config.gaussian_truncate
            )
        )
        # One pixel is consumed by defect cleanup.  The second is a numerical
        # guard separating the finite Gaussian support from the SDF analysis area.
        prefilter_guard = blur_radius + 2
        distance_halo = int(math.ceil(self.config.max_distance_px)) + 3
        total_halo = prefilter_guard + distance_halo

        x_start = output.x - total_halo
        y_start = output.y - total_halo
        work_width = output.width + total_halo * 2
        work_height = output.height + total_halo * 2
        xs = np.arange(x_start, x_start + work_width, dtype=np.int64)
        ys = np.arange(y_start, y_start + work_height, dtype=np.int64)

        occupancy = _sample_logical_land(logical, xs, ys, self.config.tile_px)
        smoothed = gaussian_filter(
            occupancy,
            sigma=self.config.blur_sigma_px,
            mode="constant",
            cval=0.0,
            radius=blur_radius,
            output=np.float32,
        )
        del occupancy

        if self.config.contour_variation_px:
            noise = _contour_noise(
                xs,
                ys,
                world_width=world_width,
                tile_px=self.config.tile_px,
                seed=self.config.contour_seed,
            )
            # A blurred step has slope 1/(sqrt(2*pi)*sigma) at its midpoint.
            # This converts a requested displacement in pixels to field amplitude.
            field_amplitude = self.config.contour_variation_px / (
                math.sqrt(2.0 * math.pi) * self.config.blur_sigma_px
            )
            smoothed += noise * np.float32(field_amplitude)
            del noise
        hard_work = smoothed >= 0.5
        del smoothed
        hard_work = _remove_single_pixel_defects(hard_work)
        _enforce_diagonal_bridges(
            hard_work,
            logical,
            x_start=x_start,
            y_start=y_start,
            tile_px=self.config.tile_px,
            radius=self.config.diagonal_bridge_px,
        )
        hard_work = _remove_single_pixel_defects(hard_work)

        analysis_start = prefilter_guard
        analysis_end_y = work_height - prefilter_guard
        analysis_end_x = work_width - prefilter_guard
        hard_analysis = hard_work[
            analysis_start:analysis_end_y,
            analysis_start:analysis_end_x,
        ]
        signed_analysis = _signed_distance(
            hard_analysis, self.config.max_distance_px
        )

        crop = distance_halo
        crop_y = slice(crop, crop + output.height)
        crop_x = slice(crop, crop + output.width)
        hard = hard_analysis[crop_y, crop_x].copy()
        signed = signed_analysis[crop_y, crop_x].copy()

        coverage = _smoothstep(-0.75, 0.75, signed).astype(np.float32)
        water_gate = np.float32(1.0) - coverage
        shallow = _smoothstep(
            -self.config.shallow_width_px, -0.5, signed
        ) * water_gate

        beach_inner = _smoothstep(-0.6, 0.8, signed)
        beach_outer = np.float32(1.0) - _smoothstep(
            self.config.beach_width_px * 0.62,
            self.config.beach_width_px,
            signed,
        )
        beach = beach_inner * beach_outer

        foam_center = -0.85
        foam_distance = np.abs(signed - foam_center)
        foam = np.float32(1.0) - _smoothstep(
            self.config.foam_width_px * 0.32,
            self.config.foam_width_px,
            foam_distance,
        )
        foam *= np.float32(1.0) - _smoothstep(0.35, 1.35, signed)

        mouth_opening = _mouth_openings(logical, ports, output, self.config)
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


def build_global_coast(
    land_cells: np.ndarray,
    *,
    window: PixelWindow | None = None,
    mouth_ports: np.ndarray | None = None,
    config: CoastV2Config | None = None,
) -> CoastFields:
    """Convenience wrapper around :class:`GlobalCoastSDF`."""

    return GlobalCoastSDF(config).build(
        land_cells, window=window, mouth_ports=mouth_ports
    )


def wrapped_crop(array: np.ndarray, window: PixelWindow) -> np.ndarray:
    """Extract a horizontally wrapped crop from a full-world 2D field."""

    if array.ndim != 2:
        raise ValueError("wrapped_crop expects a 2D array")
    window.validate(array.shape[0])
    x_indices = np.mod(
        np.arange(window.x, window.x + window.width, dtype=np.int64),
        array.shape[1],
    )
    return array[window.y : window.y + window.height][:, x_indices]


__all__ = [
    "CIV1_GRID_SIZE",
    "DEFAULT_TILE_PX",
    "PORT_N",
    "PORT_E",
    "PORT_S",
    "PORT_W",
    "PixelWindow",
    "CoastV2Config",
    "CoastFields",
    "GlobalCoastSDF",
    "build_global_coast",
    "wrapped_crop",
]
