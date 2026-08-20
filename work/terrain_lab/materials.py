"""Shared world-space materials and coastline for all three proposals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter

from .contract import TransitionContext, smoothstep01
from .world import (
    ARCTIC,
    DESERT,
    FOREST,
    GRASSLAND,
    HILLS,
    JUNGLE,
    MOUNTAINS,
    PLAINS,
    RIVER,
    SWAMP,
    TUNDRA,
    WATER,
)


BASE_COLORS: dict[int, tuple[int, int, int]] = {
    DESERT: (186, 149, 76),
    PLAINS: (142, 139, 72),
    GRASSLAND: (72, 119, 61),
    FOREST: (47, 94, 52),
    HILLS: (117, 104, 70),
    MOUNTAINS: (99, 100, 91),
    TUNDRA: (124, 137, 112),
    ARCTIC: (201, 213, 207),
    SWAMP: (57, 86, 66),
    JUNGLE: (39, 94, 50),
}

BEACH = np.asarray((194, 166, 99), dtype=np.float32)
FOAM = np.asarray((210, 226, 218), dtype=np.float32)
SHALLOW = np.asarray((37, 105, 132), dtype=np.float32)
DEEP = np.asarray((14, 54, 91), dtype=np.float32)


@dataclass
class Surface:
    image: np.ndarray
    land_coverage: np.ndarray
    land_hard: np.ndarray
    coast_signed: np.ndarray


def _hash_lattice(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    with np.errstate(over="ignore"):
        value = (
            ix.astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
            + iy.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
            + np.uint64(int(seed) & 0xFFFFFFFFFFFFFFFF)
        )
        value ^= value >> np.uint64(30)
        value *= np.uint64(0xBF58476D1CE4E5B9)
        value ^= value >> np.uint64(27)
        value *= np.uint64(0x94D049BB133111EB)
        value ^= value >> np.uint64(31)
    return (value >> np.uint64(40)).astype(np.float32) / np.float32(1 << 24)


def value_noise(
    context: TransitionContext,
    scale_px: float,
    salt: int,
) -> np.ndarray:
    """Periodic-X value noise sampled from absolute world pixel coordinates."""
    h, w = context.height_px, context.width_px
    scale = max(float(scale_px), 1.0)
    world_px = context.world_width * context.tile_px
    period = max(1, int(round(world_px / scale)))
    xs = context.world_x0 * context.tile_px + np.arange(w, dtype=np.float32) + 0.5
    ys = context.world_y0 * context.tile_px + np.arange(h, dtype=np.float32) + 0.5
    # Sample x in an integer lattice period over the *exact* world width.
    # Using ``xs / scale`` here would shift by ``world_px / scale`` after one
    # wrap, which is generally not the rounded integer ``period`` and would
    # therefore reintroduce a subtle seam at column 79 -> 0.
    wrapped_x = np.mod(xs, float(world_px))
    gx = wrapped_x / float(world_px) * float(period)
    gy = ys / scale
    x0 = np.floor(gx).astype(np.int64)
    y0 = np.floor(gy).astype(np.int64)
    tx = smoothstep01(gx - x0).astype(np.float32)
    ty = smoothstep01(gy - y0).astype(np.float32)
    x0w = np.mod(x0, period)
    x1w = np.mod(x0 + 1, period)
    seed = int(context.seed) * 1000003 + int(salt) * 9176
    yy0 = y0[:, None]
    yy1 = (y0 + 1)[:, None]
    xx0 = x0w[None, :]
    xx1 = x1w[None, :]
    n00 = _hash_lattice(xx0, yy0, seed)
    n10 = _hash_lattice(xx1, yy0, seed)
    n01 = _hash_lattice(xx0, yy1, seed)
    n11 = _hash_lattice(xx1, yy1, seed)
    top = n00 * (1.0 - tx[None, :]) + n10 * tx[None, :]
    bottom = n01 * (1.0 - tx[None, :]) + n11 * tx[None, :]
    return (top * (1.0 - ty[:, None]) + bottom * ty[:, None]).astype(np.float32)


def compose_land(weights: dict[int, np.ndarray], context: TransitionContext) -> np.ndarray:
    image = np.zeros((context.height_px, context.width_px, 3), dtype=np.float32)
    macro_common = value_noise(context, context.tile_px * 1.75, 31)
    fine_common = value_noise(context, max(4.0, context.tile_px / 11.0), 37)
    for terrain, weight in weights.items():
        base = np.asarray(BASE_COLORS.get(int(terrain), BASE_COLORS[GRASSLAND]), dtype=np.float32)
        macro = 0.58 * macro_common + 0.42 * value_noise(
            context, context.tile_px * (0.72 + (int(terrain) % 4) * 0.11), 101 + int(terrain)
        )
        fine = 0.55 * fine_common + 0.45 * value_noise(
            context, max(3.0, context.tile_px / (15.0 + int(terrain) % 3)), 211 + int(terrain)
        )
        strength = 0.20 if int(terrain) in (DESERT, PLAINS, TUNDRA) else 0.15
        luminance = 0.89 + macro * strength + (fine - 0.5) * 0.075
        material = base[None, None, :] * luminance[..., None]
        if int(terrain) == DESERT:
            material[..., 0] += (fine - 0.5) * 10.0
            material[..., 2] -= (macro - 0.5) * 8.0
        elif int(terrain) in (FOREST, JUNGLE, SWAMP):
            material[..., 1] += (macro - 0.5) * 12.0
        elif int(terrain) in (HILLS, MOUNTAINS):
            ridge = 1.0 - np.abs(value_noise(context, context.tile_px / 5.5, 307 + int(terrain)) * 2.0 - 1.0)
            material *= (0.92 + ridge[..., None] * 0.15)
        image += material * weight[..., None]

    height = np.zeros((context.height_px, context.width_px), dtype=np.float32)
    if HILLS in weights:
        height += weights[HILLS] * 0.35
    if MOUNTAINS in weights:
        height += weights[MOUNTAINS] * 0.65
    if float(height.max()) > 0:
        height = gaussian_filter(height, sigma=max(1.0, context.tile_px * 0.055), mode="nearest")
        gy, gx = np.gradient(height)
        shade = np.clip(1.0 + gx * -1.9 + gy * -1.35, 0.77, 1.22)
        image *= shade[..., None]
    return image


def _pixel_mask(raw_grid: np.ndarray, tile_px: int, predicate) -> np.ndarray:
    cells = predicate(raw_grid)
    return np.repeat(np.repeat(cells, tile_px, axis=0), tile_px, axis=1)


def apply_coast(
    land_image: np.ndarray,
    raw_grid: np.ndarray,
    context: TransitionContext,
) -> Surface:
    land_hard = _pixel_mask(raw_grid, context.tile_px, lambda grid: grid != WATER).astype(bool)
    # Coast is a separate global contour, not a land-material transition.
    # Smoothing the binary union rounds stair-steps while the halo keeps crop
    # edges truthful to their world neighbours.
    coast_soft = gaussian_filter(
        land_hard.astype(np.float32),
        sigma=max(1.0, context.tile_px * 0.145),
        mode="nearest",
    )
    coast_noise = value_noise(context, context.tile_px * 0.34, 491) - 0.5
    coast_macro = value_noise(context, context.tile_px * 1.12, 497) - 0.5
    land_hard = (coast_soft + coast_noise * 0.22 + coast_macro * 0.10) >= 0.5
    pad = context.tile_px
    padded = np.pad(land_hard, ((pad, pad), (pad, pad)), mode="edge")
    inside = distance_transform_edt(padded)
    outside = distance_transform_edt(~padded)
    signed = (inside - outside)[pad:-pad, pad:-pad].astype(np.float32)
    edge_noise = value_noise(context, context.tile_px * 0.44, 503) - 0.5
    signed += edge_noise * context.tile_px * 0.078
    edge_width = max(2.0, context.tile_px * 0.042)
    land_cov = smoothstep01(0.5 + signed / (2.0 * edge_width)).astype(np.float32)

    water_distance = np.maximum(-signed, 0.0)
    shallow = smoothstep01(water_distance / (context.tile_px * 0.72)).astype(np.float32)
    sea_noise = value_noise(context, context.tile_px * 0.55, 601)
    ripple = value_noise(context, max(5.0, context.tile_px / 7.0), 607)
    sea = SHALLOW[None, None, :] * (1.0 - shallow[..., None]) + DEEP[None, None, :] * shallow[..., None]
    sea *= (0.90 + sea_noise[..., None] * 0.18 + (ripple[..., None] - 0.5) * 0.035)

    beach_width = context.tile_px * 0.115
    beach_amount = np.clip(1.0 - np.maximum(signed, 0.0) / beach_width, 0.0, 1.0)
    beach_amount *= (signed > -edge_width).astype(np.float32)
    beach_amount *= 0.72
    ground = land_image * (1.0 - beach_amount[..., None]) + BEACH[None, None, :] * beach_amount[..., None]

    image = sea * (1.0 - land_cov[..., None]) + ground * land_cov[..., None]
    foam_width = max(1.5, context.tile_px * 0.037)
    foam_amount = np.exp(-((signed + foam_width * 0.45) / foam_width) ** 2)
    foam_amount *= (signed < edge_width * 0.45).astype(np.float32) * 0.30
    image = image * (1.0 - foam_amount[..., None]) + FOAM[None, None, :] * foam_amount[..., None]
    return Surface(
        image=np.clip(image, 0, 255).astype(np.float32),
        land_coverage=land_cov,
        land_hard=land_hard,
        coast_signed=signed,
    )
