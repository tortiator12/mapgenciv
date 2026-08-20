"""Half-cell corner lattice for Civ-I base-ground material weights.

V1 retained a rectangular one-hot plateau around each Civ cell centre.  This
variant instead constructs a shared half-cell lattice:

* cell centres are exact one-hot authority samples;
* shared edge midpoints average the two adjacent cells;
* grid vertices average the four adjacent cells;
* pixels interpolate between those reciprocal samples.

The result is the square-grid analogue of Civ III's quarter/corner grammar.
There is no per-cell rectangular mask and no internal material phase reset.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contract import normalize_weights
from .corner_weights_v1 import CornerWeightConfig, CornerWeightResult, _world_warp


@dataclass(frozen=True)
class CornerLatticeConfig(CornerWeightConfig):
    sharpen: float = 1.72
    max_materials: int = 4

    def validate(self) -> None:
        super().validate()
        if not 1.0 <= self.sharpen <= 8.0:
            raise ValueError("sharpen must be in [1, 8]")
        if not 1 <= self.max_materials <= 4:
            raise ValueError("max_materials must be in [1, 4]")


def _axis_cells(node: int, count: int, *, wrap: bool) -> tuple[tuple[int, float], ...]:
    """Logical cells contributing to one half-cell lattice coordinate."""

    if node & 1:
        index = node // 2
        if wrap:
            index %= count
        else:
            index = min(max(index, 0), count - 1)
        return ((index, 1.0),)

    candidates = (node // 2 - 1, node // 2)
    if wrap:
        return tuple((index % count, 0.5) for index in candidates)
    valid = tuple(index for index in candidates if 0 <= index < count)
    if not valid:
        index = 0 if node <= 0 else count - 1
        return ((index, 1.0),)
    weight = 1.0 / len(valid)
    return tuple((index, weight) for index in valid)


def build_corner_lattice(material_grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(material_ids, node_weights)`` for the complete world.

    X has ``2*columns`` periodic nodes; the omitted final node is identical to
    node zero.  Y has ``2*rows+1`` nodes because the world does not wrap there.
    """

    grid = np.asarray(material_grid)
    if grid.ndim != 2 or grid.size == 0:
        raise ValueError("material_grid must be a non-empty 2D array")
    rows, columns = grid.shape
    material_ids = np.asarray(sorted(int(value) for value in np.unique(grid)), dtype=np.int16)
    lookup = {int(material): index for index, material in enumerate(material_ids)}
    nodes = np.zeros((len(material_ids), 2 * rows + 1, 2 * columns), dtype=np.float32)

    for node_y in range(2 * rows + 1):
        ys = _axis_cells(node_y, rows, wrap=False)
        for node_x in range(2 * columns):
            xs = _axis_cells(node_x, columns, wrap=True)
            for y, wy in ys:
                for x, wx in xs:
                    nodes[lookup[int(grid[y, x])], node_y, node_x] += np.float32(wy * wx)
    return material_ids, nodes


def _prune_top_k(stack: np.ndarray, top_k: int) -> np.ndarray:
    if stack.shape[0] <= top_k:
        return stack
    order = np.argsort(stack, axis=0, kind="stable")
    keep = order[-top_k:]
    mask = np.zeros(stack.shape, dtype=bool)
    np.put_along_axis(mask, keep, True, axis=0)
    return np.where(mask, stack, 0.0)


def render_corner_lattice_weights(
    material_grid: np.ndarray,
    *,
    x0: int,
    y0: int,
    width: int,
    height: int,
    config: CornerLatticeConfig = CornerLatticeConfig(),
) -> CornerWeightResult:
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
    world_x0 = x0 * tile
    world_y0 = y0 * tile
    width_px = width * tile
    height_px = height * tile
    # Integer pixel coordinates deliberately put even-sized cell centres on an
    # exact sample.  This is also the convention used by grid/debug overlays.
    px = world_x0 + np.arange(width_px, dtype=np.float64)
    py = world_y0 + np.arange(height_px, dtype=np.float64)
    world_x, world_y = np.meshgrid(px, py)
    warp_x, warp_y = _world_warp(world_x, world_y, config)
    sample_x = world_x + warp_x
    sample_y = world_y + warp_y

    half = tile * 0.5
    qx = sample_x / half
    qy = sample_y / half
    node_x0 = np.floor(qx).astype(np.int64)
    node_y0 = np.floor(qy).astype(np.int64)
    fx = (qx - node_x0).astype(np.float32)
    fy = (qy - node_y0).astype(np.float32)
    node_x1 = node_x0 + 1
    node_y1 = node_y0 + 1

    node_x0 %= 2 * columns
    node_x1 %= 2 * columns
    node_y0 = np.clip(node_y0, 0, 2 * rows)
    node_y1 = np.clip(node_y1, 0, 2 * rows)

    material_ids, lattice = build_corner_lattice(grid)
    wx0, wx1 = 1.0 - fx, fx
    wy0, wy1 = 1.0 - fy, fy
    stack = (
        lattice[:, node_y0, node_x0] * (wy0 * wx0)[None, ...]
        + lattice[:, node_y0, node_x1] * (wy0 * wx1)[None, ...]
        + lattice[:, node_y1, node_x0] * (wy1 * wx0)[None, ...]
        + lattice[:, node_y1, node_x1] * (wy1 * wx1)[None, ...]
    ).astype(np.float32)

    if config.sharpen != 1.0:
        stack = np.power(np.maximum(stack, 0.0), config.sharpen).astype(np.float32)
    stack = _prune_top_k(stack, config.max_materials)
    weights = normalize_weights(
        {int(material): stack[index] for index, material in enumerate(material_ids)}
    )
    normalized = np.stack([weights[int(material)] for material in material_ids], axis=0)
    dominant = material_ids[np.argmax(normalized, axis=0)]
    return CornerWeightResult(
        weights=weights,
        dominant=dominant,
        world_x_px=world_x0,
        world_y_px=world_y0,
        width_px=width_px,
        height_px=height_px,
    )
