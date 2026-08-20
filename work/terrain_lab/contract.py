"""Shared contract for the three terrain-transition proposals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TransitionContext:
    """A crop plus halo in absolute OpenCivOne world coordinates."""

    material_grid: np.ndarray
    tile_px: int
    transition_px: int
    world_x0: int
    world_y0: int
    world_width: int
    seed: int

    @property
    def height_px(self) -> int:
        return int(self.material_grid.shape[0] * self.tile_px)

    @property
    def width_px(self) -> int:
        return int(self.material_grid.shape[1] * self.tile_px)


def smoothstep01(value: np.ndarray | float) -> np.ndarray:
    value = np.clip(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def normalize_weights(weights: dict[int, np.ndarray]) -> dict[int, np.ndarray]:
    """Normalize in place to a partition of unity at every output pixel."""
    if not weights:
        raise ValueError("transition renderer returned no material weights")
    first = next(iter(weights.values()))
    total = np.zeros_like(first, dtype=np.float32)
    for value in weights.values():
        if value.shape != first.shape:
            raise ValueError("all transition weights must share one pixel shape")
        np.maximum(value, 0.0, out=value)
        total += value
    total = np.maximum(total, 1e-7)
    for terrain in list(weights):
        weights[terrain] = (weights[terrain] / total).astype(np.float32, copy=False)
    return weights


def assert_weight_contract(weights: dict[int, np.ndarray], context: TransitionContext) -> None:
    expected = (context.height_px, context.width_px)
    for terrain, value in weights.items():
        if value.shape != expected:
            raise AssertionError(f"terrain {terrain}: {value.shape} != {expected}")
        if not np.isfinite(value).all():
            raise AssertionError(f"terrain {terrain}: non-finite weight")
        if float(value.min()) < -1e-6 or float(value.max()) > 1.000001:
            raise AssertionError(f"terrain {terrain}: outside [0,1]")
    total = np.zeros(expected, dtype=np.float32)
    for value in weights.values():
        total += value
    if not np.allclose(total, 1.0, atol=2e-5):
        raise AssertionError(f"weight sum range {float(total.min())}..{float(total.max())}")

