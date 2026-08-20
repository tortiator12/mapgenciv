"""Civ-I authority rendered through a Civ-III-style 2x2 corner field.

The logical terrain value at every Civ cell centre remains exact.  Between
centres, the four surrounding cells contribute through a compact bilinear
band.  A small deterministic world-space warp moves only the transition band;
it is attenuated to zero around cell centres and is exactly periodic at the
horizontal world wrap.

This module is intentionally renderer-neutral.  It returns material weights
and can optionally composite world-coordinate material sources.  Relief,
forests, coast bands and rivers remain separate layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from PIL import Image

from .contract import normalize_weights, smoothstep01


@dataclass(frozen=True)
class CornerWeightConfig:
    tile_px: int = 96
    transition_px: float = 15.0
    warp_px: float = 13.0
    world_width: int = 80
    seed: int = 1991

    def validate(self) -> None:
        if self.tile_px <= 0:
            raise ValueError("tile_px must be positive")
        if not 0.0 < self.transition_px < self.tile_px * 0.34:
            raise ValueError("transition_px must be between 0 and 34% of a tile")
        if not 0.0 <= self.warp_px < self.tile_px * 0.24:
            raise ValueError("warp_px must be between 0 and 24% of a tile")
        if self.world_width <= 1:
            raise ValueError("world_width must be greater than one")


@dataclass(frozen=True)
class CornerWeightResult:
    weights: dict[int, np.ndarray]
    dominant: np.ndarray
    world_x_px: int
    world_y_px: int
    width_px: int
    height_px: int


def _seed_phase(seed: int, channel: int) -> float:
    """Stable phase in radians without relying on Python's randomized hash."""

    value = (int(seed) * 0x9E3779B1 + int(channel) * 0x85EBCA77) & 0xFFFFFFFF
    return (value / 4294967296.0) * (2.0 * np.pi)


def _centre_guard(coordinate: np.ndarray, tile_px: int) -> np.ndarray:
    """Return zero near cell centres and one near inter-cell boundaries."""

    local = np.mod(coordinate, float(tile_px))
    distance = np.abs(local - tile_px * 0.5)
    # No displacement in the central 36% of a cell; full displacement starts
    # at 72%.  This protects rule readability while leaving a broad contour
    # corridor near every shared boundary.
    return smoothstep01(
        (distance - tile_px * 0.18) / (tile_px * (0.36 - 0.18))
    ).astype(np.float64)


def _world_warp(
    world_x: np.ndarray,
    world_y: np.ndarray,
    config: CornerWeightConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Return crop-stable, horizontally periodic transition displacement."""

    period = float(config.world_width * config.tile_px)
    tx = world_x / period
    ty = world_y / float(config.tile_px)

    phase_x0 = _seed_phase(config.seed, 0)
    phase_x1 = _seed_phase(config.seed, 1)
    phase_y0 = _seed_phase(config.seed, 2)
    phase_y1 = _seed_phase(config.seed, 3)

    # Integer horizontal frequencies make x and x + world_period identical.
    # The two vertical wavelengths deliberately avoid a tile-sized rhythm.
    dx = (
        np.sin(2.0 * np.pi * (3.0 * tx + ty / 3.7) + phase_x0) * 0.68
        + np.sin(2.0 * np.pi * (7.0 * tx - ty / 1.43) + phase_x1) * 0.32
    )
    dy = (
        np.sin(2.0 * np.pi * (5.0 * tx - ty / 4.6) + phase_y0) * 0.70
        + np.sin(2.0 * np.pi * (11.0 * tx + ty / 1.91) + phase_y1) * 0.30
    )

    guard_x = _centre_guard(world_x, config.tile_px)
    guard_y = _centre_guard(world_y, config.tile_px)
    return (
        dx * float(config.warp_px) * guard_x,
        dy * float(config.warp_px) * guard_y,
    )


def _compact_axis_fraction(fraction: np.ndarray, config: CornerWeightConfig) -> np.ndarray:
    half_band = float(config.transition_px) / float(config.tile_px)
    low = 0.5 - half_band
    high = 0.5 + half_band
    return smoothstep01((fraction - low) / (high - low)).astype(np.float32)


def render_corner_weights(
    material_grid: np.ndarray,
    *,
    x0: int,
    y0: int,
    width: int,
    height: int,
    config: CornerWeightConfig = CornerWeightConfig(),
) -> CornerWeightResult:
    """Render a pixel window from the complete logical world.

    ``x0``/``y0``/``width``/``height`` are expressed in logical cells.  X may
    cross the horizontal world wrap.  Y is non-wrapping and must stay within
    the supplied world.
    """

    config.validate()
    grid = np.asarray(material_grid)
    if grid.ndim != 2 or grid.size == 0:
        raise ValueError("material_grid must be a non-empty 2D array")
    rows, columns = grid.shape
    if columns != config.world_width:
        raise ValueError(
            f"material_grid width {columns} does not match world_width {config.world_width}"
        )
    if width <= 0 or height <= 0:
        raise ValueError("window dimensions must be positive")
    if y0 < 0 or y0 + height > rows:
        raise ValueError("window exceeds the non-wrapping Y range")

    tile = config.tile_px
    width_px = width * tile
    height_px = height * tile
    world_x0 = int(x0 * tile)
    world_y0 = int(y0 * tile)

    px = world_x0 + np.arange(width_px, dtype=np.float64) + 0.5
    py = world_y0 + np.arange(height_px, dtype=np.float64) + 0.5
    world_x, world_y = np.meshgrid(px, py)
    warp_x, warp_y = _world_warp(world_x, world_y, config)
    sample_x = world_x + warp_x
    sample_y = world_y + warp_y

    qx = sample_x / float(tile) - 0.5
    qy = sample_y / float(tile) - 0.5
    left = np.floor(qx).astype(np.int64)
    top = np.floor(qy).astype(np.int64)
    fx = _compact_axis_fraction(qx - left, config)
    fy = _compact_axis_fraction(qy - top, config)

    right = left + 1
    bottom = top + 1
    left %= columns
    right %= columns
    top = np.clip(top, 0, rows - 1)
    bottom = np.clip(bottom, 0, rows - 1)

    wx0 = 1.0 - fx
    wx1 = fx
    wy0 = 1.0 - fy
    wy1 = fy

    source00 = grid[top, left]
    source10 = grid[top, right]
    source01 = grid[bottom, left]
    source11 = grid[bottom, right]
    materials = [int(value) for value in np.unique(grid)]
    weights = {
        material: np.zeros((height_px, width_px), dtype=np.float32)
        for material in materials
    }
    contributions = (
        (source00, wy0 * wx0),
        (source10, wy0 * wx1),
        (source01, wy1 * wx0),
        (source11, wy1 * wx1),
    )
    for source, contribution in contributions:
        for material in materials:
            weights[material] += contribution * (source == material)
    weights = normalize_weights(weights)

    material_ids = np.asarray(materials, dtype=np.int16)
    stack = np.stack([weights[material] for material in materials], axis=0)
    dominant = material_ids[np.argmax(stack, axis=0)]
    return CornerWeightResult(
        weights=weights,
        dominant=dominant,
        world_x_px=world_x0,
        world_y_px=world_y0,
        width_px=width_px,
        height_px=height_px,
    )


def compose_corner_materials(
    result: CornerWeightResult,
    textures: Mapping[int, Image.Image],
    *,
    world_period_x: int,
    repeats: Mapping[int, int] | None = None,
) -> np.ndarray:
    """Composite RGBA material sources using the rendered corner weights."""

    # Local import keeps the weight-only module lightweight for tests/tools.
    from work.aa_tile_kit_v1.materials import WorldMaterialSampler

    if world_period_x <= 0:
        raise ValueError("world_period_x must be positive")
    missing = sorted(set(result.weights) - set(int(key) for key in textures))
    if missing:
        raise KeyError(f"missing textures for materials {missing}")

    rgb = np.zeros((result.height_px, result.width_px, 3), dtype=np.float64)
    alpha = np.zeros((result.height_px, result.width_px), dtype=np.float64)
    for material, weight in result.weights.items():
        repeat_count = None if repeats is None else repeats.get(material)
        sampler = WorldMaterialSampler(
            textures[material],
            world_period_x=world_period_x,
            repeats=repeat_count,
        )
        sampled = np.asarray(
            sampler.sample(
                result.world_x_px,
                result.world_y_px,
                result.width_px,
                result.height_px,
            ),
            dtype=np.float64,
        )
        source_alpha = sampled[..., 3] / 255.0
        effective = weight.astype(np.float64) * source_alpha
        rgb += sampled[..., :3] * effective[..., None]
        alpha += effective

    safe = np.maximum(alpha, 1e-8)
    rgb /= safe[..., None]
    rgba = np.empty((result.height_px, result.width_px, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(np.rint(rgb), 0.0, 255.0).astype(np.uint8)
    rgba[..., 3] = np.clip(np.rint(alpha * 255.0), 0.0, 255.0).astype(np.uint8)
    return rgba

