"""Continuous component underpainting for Project1991 relief.

Authored peaks remain the high-frequency silhouette layer.  This module adds
the missing landscape-scale layer beneath them: large exact-terrain Civ
components receive one organic rock/soil mass and, for five-plus cells, a
world-stable ridge spine.  Every pixel mask is clipped to the same component's
cell union (with only a narrow presentation fade at exposed borders).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from work.terrain_lab.algorithms.organic_partition import render_weights
from work.terrain_lab.contract import TransitionContext
from work.terrain_lab.relief_components_v3 import plan_relief_components_v3
from work.terrain_lab.world import HILLS, MOUNTAINS


@dataclass(frozen=True, slots=True)
class ReliefMassMasks:
    mountain_mass: np.ndarray
    mountain_ridge: np.ndarray
    hill_mass: np.ndarray
    hill_ridge: np.ndarray


def _local_x(world_x: int, context: TransitionContext) -> int | None:
    width = int(context.material_grid.shape[1])
    distance = (int(world_x) - int(context.world_x0)) % int(context.world_width)
    return distance if distance < width else None


def _component_weight(
    logical_mask: np.ndarray,
    context: TransitionContext,
    *,
    transition_px: int,
) -> np.ndarray:
    if not np.any(logical_mask):
        return np.zeros((context.height_px, context.width_px), dtype=np.float32)
    binary = TransitionContext(
        material_grid=logical_mask.astype(np.int16),
        tile_px=context.tile_px,
        transition_px=transition_px,
        world_x0=context.world_x0,
        world_y0=context.world_y0,
        world_width=context.world_width,
        seed=context.seed ^ 0x51991,
    )
    weights = render_weights(binary)
    return weights.get(1, np.zeros((context.height_px, context.width_px), dtype=np.float32))


def _ridge_mask(
    plans,
    terrain: int,
    context: TransitionContext,
    component_weight: np.ndarray,
) -> np.ndarray:
    canvas = Image.new("L", (context.width_px, context.height_px), 0)
    draw = ImageDraw.Draw(canvas)
    placement_by_cell = {
        placement.cell: placement
        for plan in plans
        if plan.terrain == terrain and plan.size >= 5
        for placement in plan.placements
    }
    for plan in plans:
        if plan.terrain != terrain or plan.size < 5:
            continue
        for segment in plan.segments:
            start_x = _local_x(segment.start[0], context)
            end_x = _local_x(segment.end[0], context)
            start_y = segment.start[1] - int(context.world_y0)
            end_y = segment.end[1] - int(context.world_y0)
            if start_x is None or end_x is None:
                continue
            if not (
                -1 <= start_y <= context.material_grid.shape[0]
                and -1 <= end_y <= context.material_grid.shape[0]
            ):
                continue
            # The component planner already guarantees cardinal adjacency.
            # In a complete-world buffer, unwrap the one possible 79->0 edge
            # to its short local representation.
            if abs(end_x - start_x) > context.world_width // 2:
                if end_x < start_x:
                    end_x += context.world_width
                else:
                    start_x += context.world_width
            start_placement = placement_by_cell[segment.start]
            end_placement = placement_by_cell[segment.end]
            p0 = (
                (start_x + start_placement.anchor_uv[0]) * context.tile_px,
                (start_y + start_placement.anchor_uv[1]) * context.tile_px,
            )
            p1 = (
                (end_x + end_placement.anchor_uv[0]) * context.tile_px,
                (end_y + end_placement.anchor_uv[1]) * context.tile_px,
            )
            base = 0.40 if terrain == MOUNTAINS else 0.32
            width = max(6, round(context.tile_px * base * segment.width_scale))
            value = 225 if segment.kind == "spine" else 172
            draw.line((p0, p1), fill=value, width=width, joint="curve")
            radius = max(3, width // 2)
            draw.ellipse((p0[0] - radius, p0[1] - radius, p0[0] + radius, p0[1] + radius), fill=value)
            draw.ellipse((p1[0] - radius, p1[1] - radius, p1[0] + radius, p1[1] + radius), fill=value)

    blurred = canvas.filter(ImageFilter.GaussianBlur(max(2.0, context.tile_px * 0.10)))
    ridge = np.asarray(blurred, dtype=np.float32) / 255.0
    return np.minimum(ridge, component_weight).astype(np.float32, copy=False)


def build_relief_mass_masks(
    full_world: np.ndarray,
    context: TransitionContext,
    *,
    minimum_component_size: int = 3,
    transition_px: int | None = None,
) -> ReliefMassMasks:
    """Return continuous masks for large same-terrain relief components."""
    world = np.asarray(full_world)
    if world.ndim != 2 or world.shape[1] != int(context.world_width):
        raise ValueError("full_world must contain the complete horizontal Civ world")
    if minimum_component_size < 2:
        raise ValueError("minimum_component_size must be at least two")

    plans = plan_relief_components_v3(
        world,
        seed=int(context.seed),
        world_width=int(context.world_width),
    )
    eligible = {
        terrain: {
            cell
            for plan in plans
            if plan.terrain == terrain and plan.size >= minimum_component_size
            for cell in plan.cells
        }
        for terrain in (HILLS, MOUNTAINS)
    }
    logical: dict[int, np.ndarray] = {}
    for terrain in (HILLS, MOUNTAINS):
        mask = np.zeros(context.material_grid.shape, dtype=bool)
        for local_y in range(mask.shape[0]):
            world_y = int(context.world_y0) + local_y
            if not 0 <= world_y < world.shape[0]:
                continue
            for local_x in range(mask.shape[1]):
                world_x = (int(context.world_x0) + local_x) % int(context.world_width)
                mask[local_y, local_x] = (world_x, world_y) in eligible[terrain]
        logical[terrain] = mask

    edge = int(transition_px if transition_px is not None else max(5, round(context.tile_px * 0.11)))
    mountain_mass = _component_weight(logical[MOUNTAINS], context, transition_px=edge)
    hill_mass = _component_weight(logical[HILLS], context, transition_px=edge)
    return ReliefMassMasks(
        mountain_mass=mountain_mass,
        mountain_ridge=_ridge_mask(plans, MOUNTAINS, context, mountain_mass),
        hill_mass=hill_mass,
        hill_ridge=_ridge_mask(plans, HILLS, context, hill_mass),
    )

