"""Civ-III-style half-cell ground grammar for the current Project1991 stack.

The logical Civ-I world remains authoritative.  Feature terrain (forest,
hills, mountains and jungle) receives the shared grass underlay used by the
production renderer.  Water and river cells are filled periodically from the
nearest land material because coast and river layers are composited later.

V51 adapts the already proven crisp V2.1 half-cell lattice to the current
``TransitionContext`` callback.  Cell centres, shared edge midpoints and
four-cell vertices are reciprocal samples; no cell owns a rectangular stamp.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.ndimage import distance_transform_edt

from .contract import TransitionContext
from .corner_lattice_v2 import CornerLatticeConfig, render_corner_lattice_weights
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


NAME = "V51 — Civ-III crisp half-cell lattice"


def build_material_world_v51(terrain: np.ndarray) -> np.ndarray:
    """Return the periodic presentation underlay for one complete Civ world."""

    raw = np.asarray(terrain, dtype=np.int16)
    if raw.ndim != 2 or raw.size == 0:
        raise ValueError("terrain must be a non-empty 2D array")
    material = np.full(raw.shape, -1, dtype=np.int16)
    material[raw == DESERT] = DESERT
    material[raw == PLAINS] = PLAINS
    material[
        (raw == GRASSLAND)
        | (raw == FOREST)
        | (raw == HILLS)
        | (raw == MOUNTAINS)
        | (raw == JUNGLE)
    ] = GRASSLAND
    material[raw == TUNDRA] = TUNDRA
    material[raw == ARCTIC] = ARCTIC
    material[raw == SWAMP] = SWAMP

    valid = material >= 0
    if not valid.any():
        raise ValueError("world has no material-bearing land")
    if valid.all():
        return material

    # Triple tiling makes nearest-land extrapolation genuinely periodic in X.
    # Y remains non-wrapping, matching the Civ-I world poles.
    tiled_material = np.tile(material, (1, 3))
    tiled_valid = tiled_material >= 0
    _, nearest = distance_transform_edt(~tiled_valid, return_indices=True)
    filled = tiled_material.copy()
    filled[~tiled_valid] = tiled_material[tuple(nearest)][~tiled_valid]
    width = material.shape[1]
    return filled[:, width : 2 * width].copy()


def make_weight_renderer_v51(full_terrain: np.ndarray) -> Callable[[TransitionContext], dict[int, np.ndarray]]:
    """Create the current renderer callback from one immutable full world."""

    material_world = build_material_world_v51(full_terrain)
    world_height, world_width = material_world.shape

    def render(context: TransitionContext) -> dict[int, np.ndarray]:
        if int(context.world_width) != world_width:
            raise ValueError(
                f"context world width {context.world_width} != material world {world_width}"
            )
        window_h, window_w = context.material_grid.shape
        if context.world_y0 < 0 or context.world_y0 + window_h > world_height:
            raise ValueError("V51 ground window exceeds non-wrapping world Y")
        tile = int(context.tile_px)
        config = CornerLatticeConfig(
            tile_px=tile,
            transition_px=tile * (13.0 / 96.0),
            warp_px=tile * (16.5 / 96.0),
            world_width=world_width,
            seed=int(context.seed),
            sharpen=5.2,
            max_materials=4,
        )
        result = render_corner_lattice_weights(
            material_world,
            x0=int(context.world_x0),
            y0=int(context.world_y0),
            width=int(window_w),
            height=int(window_h),
            config=config,
        )
        return result.weights

    render.__name__ = "render_ground_corner_lattice_v51"
    return render


__all__ = ["NAME", "build_material_world_v51", "make_weight_renderer_v51"]
