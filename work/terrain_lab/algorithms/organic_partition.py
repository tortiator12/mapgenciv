"""World-stable organic material boundaries for a discrete Civ map.

The save-game grid remains the authority.  Only the *pixel contour* between
neighbouring cells is displaced.  A periodic coordinate warp is strongest at
cell borders and fades to zero at cell centres, so every logical Civ cell
keeps a guaranteed material core while long borders stop reading as 96 px
rectangles.

The implementation is intentionally texture-agnostic: it returns the same
normalised material weights as the other terrain-lab algorithms.  Consumers
can therefore keep using world-space material samplers and chunk rendering.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter

from ..contract import TransitionContext, normalize_weights, smoothstep01


NAME = "D — Weltorganische Zellkontur"


def _signed_distance(mask: np.ndarray, radius: int, periodic_x: bool) -> np.ndarray:
    """Return a bounded signed EDT without inventing a crop-edge wrap."""
    pad = max(2, int(radius) + 2)
    x_mode = "wrap" if periodic_x else "edge"
    padded = np.pad(mask, ((pad, pad), (pad, pad)), mode=x_mode)
    inside = distance_transform_edt(padded)
    outside = distance_transform_edt(~padded)
    return (inside - outside)[pad:-pad, pad:-pad].astype(np.float32, copy=False)


def _periodic_warp(
    context: TransitionContext,
    amplitude: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return absolute-coordinate dx/dy fields, periodic in world x.

    The envelope is zero at every cell centre and one at the corresponding
    pair of cell borders.  This is the crucial authority contract: even a
    deliberately strong production-scale contour warp cannot move a logical
    cell's visual centre into a neighbour.
    """
    tile = float(context.tile_px)
    height, width = context.height_px, context.width_px
    world_px = max(1.0, float(context.world_width * context.tile_px))

    absolute_x = context.world_x0 * tile + np.arange(width, dtype=np.float32) + 0.5
    absolute_y = context.world_y0 * tile + np.arange(height, dtype=np.float32) + 0.5
    wrapped_x = np.mod(absolute_x, world_px)
    x_angle = (2.0 * math.pi / world_px) * wrapped_x[None, :]
    y = absolute_y[:, None]

    seed_phase = (int(context.seed) * 0.61803398875) % (2.0 * math.pi)
    # Broad harmonics make a border bend over several tiles.  The smaller
    # term prevents every inlet/biome edge from sharing one identical arc.
    dx_field = (
        0.56 * np.sin(5.0 * x_angle + y / (tile * 2.35) + seed_phase)
        + 0.29 * np.sin(11.0 * x_angle - y / (tile * 0.93) + seed_phase * 1.71)
        + 0.15 * np.sin(17.0 * x_angle + y / (tile * 0.57) - seed_phase * 0.43)
    )
    dy_field = (
        0.55 * np.sin(4.0 * x_angle - y / (tile * 2.70) + seed_phase * 1.23)
        + 0.30 * np.sin(9.0 * x_angle + y / (tile * 1.07) - seed_phase * 0.81)
        + 0.15 * np.sin(15.0 * x_angle - y / (tile * 0.63) + seed_phase * 0.37)
    )

    frac_x = np.mod(absolute_x / tile, 1.0)
    frac_y = np.mod(absolute_y / tile, 1.0)
    border_x = np.square(np.cos(math.pi * frac_x))[None, :]
    border_y = np.square(np.cos(math.pi * frac_y))[:, None]

    dx = (dx_field * border_x * amplitude).astype(np.float32, copy=False)
    dy = (dy_field * border_y * amplitude).astype(np.float32, copy=False)
    return dx, dy


def warped_material_labels(context: TransitionContext) -> np.ndarray:
    """Rasterise the discrete material grid through the authority-safe warp."""
    material_grid = np.asarray(context.material_grid)
    if material_grid.ndim != 2 or material_grid.size == 0:
        raise ValueError("material_grid must be a non-empty 2D array")
    if int(context.tile_px) <= 0:
        raise ValueError("tile_px must be positive")
    if int(context.world_width) <= 0:
        raise ValueError("world_width must be positive")

    tile = float(context.tile_px)
    transition = min(
        max(0.0, float(context.transition_px)),
        max(0.0, tile * 0.45),
    )
    # At 96 px this permits about 17 px of meaningful contour motion.  The
    # bound leaves transition+warp comfortably short of the 48 px centre
    # distance, preserving a hard core.  Tiny lab tiles scale proportionally.
    amplitude = min(tile * 0.185, max(0.0, transition * 0.72))
    dx, dy = _periodic_warp(context, amplitude)

    height, width = context.height_px, context.width_px
    absolute_x = (
        context.world_x0 * tile
        + np.arange(width, dtype=np.float32)[None, :]
        + 0.5
    )
    absolute_y = (
        context.world_y0 * tile
        + np.arange(height, dtype=np.float32)[:, None]
        + 0.5
    )
    source_cell_x = np.floor((absolute_x + dx) / tile).astype(np.int64)
    source_cell_y = np.floor((absolute_y + dy) / tile).astype(np.int64)
    local_x = source_cell_x - int(context.world_x0)
    local_y = source_cell_y - int(context.world_y0)

    grid_h, grid_w = material_grid.shape
    # A complete world strip is genuinely periodic.  A smaller chunk already
    # carries its real halo, so wrapping its own edge would be incorrect.
    if int(grid_w) == int(context.world_width):
        local_x %= grid_w
    else:
        np.clip(local_x, 0, grid_w - 1, out=local_x)
    np.clip(local_y, 0, grid_h - 1, out=local_y)
    return material_grid[local_y, local_x]


def _hash01(seed: int, world_x: int, world_y: int, salt: int) -> float:
    """Small stable integer hash mapped to [0, 1)."""
    value = (
        int(seed)
        ^ (int(world_x) * 0x9E3779B1)
        ^ (int(world_y) * 0x85EBCA77)
        ^ (int(salt) * 0xC2B2AE3D)
    ) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return float(value) / float(1 << 32)


def organic_material_labels(context: TransitionContext) -> np.ndarray:
    """Build an organic weighted-cell partition with exact Civ ownership.

    Every logical cell contributes one slightly irregular radial field.  The
    nearest field wins each presentation pixel.  Seeds remain close to their
    authoritative cell centres, so centres cannot change class, while the
    resulting borders are curved/slanted rather than four softened tile
    edges.  Same-material neighbours naturally merge into one large mass.
    """
    material_grid = np.asarray(context.material_grid)
    if material_grid.ndim != 2 or material_grid.size == 0:
        raise ValueError("material_grid must be a non-empty 2D array")
    if int(context.tile_px) <= 0:
        raise ValueError("tile_px must be positive")
    if int(context.world_width) <= 0:
        raise ValueError("world_width must be positive")

    tile = float(context.tile_px)
    grid_h, grid_w = material_grid.shape
    height, width = context.height_px, context.width_px
    best = np.full((height, width), np.inf, dtype=np.float32)
    labels = np.empty((height, width), dtype=material_grid.dtype)
    complete_world = int(grid_w) == int(context.world_width)
    reach = tile * 1.68

    for gy in range(grid_h):
        world_y = int(context.world_y0) + gy
        for gx in range(grid_w):
            world_x_unwrapped = int(context.world_x0) + gx
            world_x = world_x_unwrapped % int(context.world_width)
            jitter_x = (_hash01(context.seed, world_x, world_y, 301) - 0.5) * tile * 0.30
            jitter_y = (_hash01(context.seed, world_x, world_y, 307) - 0.5) * tile * 0.30
            scale_x = 0.91 + _hash01(context.seed, world_x, world_y, 311) * 0.18
            scale_y = 0.91 + _hash01(context.seed, world_x, world_y, 313) * 0.18
            angle = (_hash01(context.seed, world_x, world_y, 317) - 0.5) * math.pi
            phase = _hash01(context.seed, world_x, world_y, 331) * 2.0 * math.pi
            power = (_hash01(context.seed, world_x, world_y, 337) - 0.5) * tile * tile * 0.16
            cos_a, sin_a = math.cos(angle), math.sin(angle)

            # Full-world buffers need ghost copies at both periodic edges.
            # Halo crops already contain those columns in unwrapped order.
            copies = (-grid_w, 0, grid_w) if complete_world else (0,)
            for copy in copies:
                centre_x = (gx + copy + 0.5) * tile + jitter_x
                centre_y = (gy + 0.5) * tile + jitter_y
                left = max(0, int(math.floor(centre_x - reach)))
                right = min(width, int(math.ceil(centre_x + reach)))
                top = max(0, int(math.floor(centre_y - reach)))
                bottom = min(height, int(math.ceil(centre_y + reach)))
                if left >= right or top >= bottom:
                    continue

                px = np.arange(left, right, dtype=np.float32)[None, :] + 0.5 - centre_x
                py = np.arange(top, bottom, dtype=np.float32)[:, None] + 0.5 - centre_y
                rx = (px * cos_a + py * sin_a) / scale_x
                ry = (-px * sin_a + py * cos_a) / scale_y
                radius2 = rx * rx + ry * ry
                theta = np.arctan2(ry, rx)
                ripple = (
                    1.0
                    + 0.120 * np.sin(theta * 3.0 + phase)
                    + 0.055 * np.sin(theta * 5.0 - phase * 1.37)
                )
                score = radius2 * ripple - power
                target = best[top:bottom, left:right]
                wins = score < target
                if not np.any(wins):
                    continue
                target[wins] = score[wins]
                label_target = labels[top:bottom, left:right]
                label_target[wins] = material_grid[gy, gx]

    if not np.isfinite(best).all():
        raise AssertionError("organic partition left uncovered presentation pixels")
    return labels


def component_material_labels(context: TransitionContext) -> np.ndarray:
    """Rasterise component-wide material fields instead of per-cell tiles.

    Each authoritative Civ cell contributes a world-stable Gaussian seed to
    its material.  Equal-material neighbours reinforce one another before the
    winning material is selected, so a forest/plain/desert mass receives one
    coherent contour rather than a row of individually rounded rectangles.
    A small centre core is imposed last as the non-negotiable save authority.
    """
    material_grid = np.asarray(context.material_grid)
    if material_grid.ndim != 2 or material_grid.size == 0:
        raise ValueError("material_grid must be a non-empty 2D array")
    if int(context.tile_px) <= 0:
        raise ValueError("tile_px must be positive")
    if int(context.world_width) <= 0:
        raise ValueError("world_width must be positive")

    tile = int(context.tile_px)
    height, width = context.height_px, context.width_px
    grid_h, grid_w = material_grid.shape
    complete_world = int(grid_w) == int(context.world_width)
    mode = ("nearest", "wrap") if complete_world else ("nearest", "nearest")
    sigma = max(1.0, tile * 0.43)

    best = np.full((height, width), -np.inf, dtype=np.float32)
    labels = np.empty((height, width), dtype=material_grid.dtype)
    for material in (int(value) for value in np.unique(material_grid)):
        impulses = np.zeros((height, width), dtype=np.float32)
        for gy, gx in np.argwhere(material_grid == material):
            gy, gx = int(gy), int(gx)
            world_x = (int(context.world_x0) + gx) % int(context.world_width)
            world_y = int(context.world_y0) + gy
            jitter_x = (_hash01(context.seed, world_x, world_y, 601) - 0.5) * tile * 0.30
            jitter_y = (_hash01(context.seed, world_x, world_y, 607) - 0.5) * tile * 0.30
            px = int(round((gx + 0.5) * tile + jitter_x - 0.5))
            py = int(round((gy + 0.5) * tile + jitter_y - 0.5))
            if complete_world:
                px %= width
            else:
                px = min(width - 1, max(0, px))
            py = min(height - 1, max(0, py))
            strength = 0.92 + _hash01(context.seed, world_x, world_y, 613) * 0.16
            impulses[py, px] += strength
        field = gaussian_filter(
            impulses,
            sigma=(sigma, sigma),
            mode=mode,
            truncate=3.5,
        ).astype(np.float32, copy=False)
        wins = field > best
        best[wins] = field[wins]
        labels[wins] = material

    # Save authority is a protected core, not a rectangular presentation
    # footprint.  Ten percent of a tile is enough to guarantee selection and
    # still leaves almost the complete cell available for organic neighbours.
    core_radius = max(1, round(tile * 0.10))
    yy, xx = np.ogrid[-core_radius:core_radius + 1, -core_radius:core_radius + 1]
    core = xx * xx + yy * yy <= core_radius * core_radius
    for gy in range(grid_h):
        cy = gy * tile + tile // 2
        top, bottom = max(0, cy - core_radius), min(height, cy + core_radius + 1)
        mask_y0 = top - (cy - core_radius)
        mask_y1 = mask_y0 + (bottom - top)
        for gx in range(grid_w):
            cx = gx * tile + tile // 2
            left, right = max(0, cx - core_radius), min(width, cx + core_radius + 1)
            mask_x0 = left - (cx - core_radius)
            mask_x1 = mask_x0 + (right - left)
            patch = core[mask_y0:mask_y1, mask_x0:mask_x1]
            target = labels[top:bottom, left:right]
            target[patch] = material_grid[gy, gx]
    return labels


def render_weights(context: TransitionContext) -> dict[int, np.ndarray]:
    """Return compact, normalised weights over organically warped labels."""
    labels = component_material_labels(context)
    materials = [int(value) for value in np.unique(np.asarray(context.material_grid))]
    transition = min(
        max(0.0, float(context.transition_px)),
        max(0.0, float(context.tile_px) * 0.45),
    )

    if transition < 0.5 or len(materials) == 1:
        return {
            material: (labels == material).astype(np.float32)
            for material in materials
        }

    periodic_x = int(context.material_grid.shape[1]) == int(context.world_width)
    radius = int(math.ceil(transition + 2.0))
    weights: dict[int, np.ndarray] = {}
    for material in materials:
        signed = _signed_distance(labels == material, radius, periodic_x)
        ramp = 0.5 + signed / (2.0 * transition)
        weights[material] = smoothstep01(ramp).astype(np.float32, copy=False)
    return normalize_weights(weights)
