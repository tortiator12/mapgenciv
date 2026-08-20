"""Topology-authored large relief components with fixed NW light and exact Civ feet."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from . import relief_component_art_v42 as v42
from . import relief_component_massif_v34 as v34
from . import relief_components_v29 as v29
from . import relief_nesw_v33 as v33
from .world import HILLS, MOUNTAINS


ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "work" / "aa_tile_kit_v1" / "assets" / "staging_relief_component_v43"


def _quadrant_counts(points: tuple[tuple[int, int], ...]):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mid_x = (min(xs) + max(xs) + 1) * 0.5
    mid_y = (min(ys) + max(ys) + 1) * 0.5
    counts = {"nw": 0, "ne": 0, "sw": 0, "se": 0}
    for x, y in points:
        side = ("n" if y + 0.5 < mid_y else "s") + ("w" if x + 0.5 < mid_x else "e")
        counts[side] += 1
    return counts


def classify_component_v43(component_unwrapped) -> tuple[str, dict]:
    points = tuple(component_unwrapped.values())
    point_set = set(points)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    span_x = max(xs) - min(xs) + 1
    span_y = max(ys) - min(ys) + 1
    density = len(points) / float(span_x * span_y)
    max_degree = max(
        sum((x + dx, y + dy) in point_set for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)))
        for x, y in points
    )
    if span_x >= span_y + 2 or (span_x >= span_y + 1 and density >= 0.74):
        kind = "horizontal"
    elif span_y >= span_x + 2 or (span_y >= span_x + 1 and density >= 0.74):
        kind = "vertical"
    else:
        counts = _quadrant_counts(points)
        missing = min(counts, key=lambda key: (counts[key], key))
        values = sorted(counts.values())
        kind = f"l_missing_{missing}" if max_degree <= 2 and density <= 0.72 and values[0] + 1 <= values[-1] else "mass"
    return kind, {"span": [span_x, span_y], "density": round(density, 6), "max_degree": max_degree}


def _asset(terrain: int, kind: str) -> Image.Image:
    family = "hill" if terrain == HILLS else "mountain"
    with Image.open(ASSET_ROOT / f"{family}_{kind}.png") as handle:
        return handle.convert("RGBA")


def _scaled_asset(terrain: int, kind: str, span_x: int, span_y: int, tile: int) -> Image.Image:
    source = _asset(terrain, kind)
    if kind == "horizontal":
        target_width = round(min(span_x * 1.05, 4.10) * tile)
        scale = target_width / source.width
    elif kind == "vertical":
        target_height = round(min(span_y * 0.78 + 0.40, 3.50) * tile)
        scale = target_height / source.height
    elif kind.startswith("l_missing_"):
        target_width = round(min(max(span_x, span_y) * 1.06, 3.40) * tile)
        scale = target_width / source.width
    else:
        target_width = round(min(max(span_x, span_y) * 1.00, 3.70) * tile)
        scale = target_width / source.width
    return source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )


def render_relief_component_art_v43(
    base: Image.Image,
    full_grid: np.ndarray,
    *,
    seed: int,
    window,
    tile_px: int = 96,
    world_width: int | None = None,
):
    grid = np.asarray(full_grid, dtype=np.int16)
    width = grid.shape[1] if world_width is None else int(world_width)
    x0, y0, cells_w, cells_h = (int(value) for value in window)
    if base.size != (cells_w * tile_px, cells_h * tile_px):
        raise ValueError("base pixel size does not match window")

    grounded = v33._apply_topology(base, grid, seed, (x0, y0, cells_w, cells_h), tile_px, width)
    base.paste(grounded)
    components = {terrain: v33._components(grid, terrain, width) for terrain in (HILLS, MOUNTAINS)}
    large_cells = {
        terrain: {cell for component in components[terrain] if len(component) >= 5 for cell in component}
        for terrain in (HILLS, MOUNTAINS)
    }

    period = width * tile_px
    for placement in v29.plan_relief_components_v29(grid, seed=seed, world_width=width):
        if any(cell in large_cells[placement.terrain] for cell in placement.cells):
            continue
        with Image.open(Path(v29.ASSET_ROOT) / placement.asset_name) as handle:
            sprite = handle.convert("RGBA")
        world_left = placement.origin[0] * tile_px
        world_top = placement.origin[1] * tile_px
        for cycle in range(-2, 3):
            left = world_left + cycle * period - x0 * tile_px
            top = world_top - y0 * tile_px
            if left + sprite.width <= 0 or left >= base.width or top + sprite.height <= 0 or top >= base.height:
                continue
            v29._composite_clipped(base, sprite, left, top, placement.terrain)

    records = []
    for terrain in (HILLS, MOUNTAINS):
        for component in components[terrain]:
            if len(component) < 5:
                continue
            unwrapped = v34._unwrap_component(component, width)
            kind, metadata = classify_component_v43(unwrapped)
            span_x, span_y = metadata["span"]
            sprite = _scaled_asset(terrain, kind, span_x, span_y, tile_px)
            points = tuple(unwrapped.values())
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            centre_x = (min(xs) + max(xs) + 1) * 0.5
            bottom_y = max(ys) + (1.00 if terrain == MOUNTAINS else 0.97)
            left_world = round(centre_x * tile_px - sprite.width * 0.5)
            top_world = round(bottom_y * tile_px - sprite.height)
            sprite = v42._clip_component_art_v42(sprite, unwrapped, left_world, top_world, tile_px, terrain)
            for cycle in range(-2, 3):
                left = left_world + cycle * period - x0 * tile_px
                top = top_world - y0 * tile_px
                if left + sprite.width <= 0 or left >= base.width or top + sprite.height <= 0 or top >= base.height:
                    continue
                v29._composite_clipped(base, sprite, left, top, terrain)
            records.append({
                "terrain": int(terrain),
                "size": len(component),
                "kind": kind,
                **metadata,
                "asset": f"{'hill' if terrain == HILLS else 'mountain'}_{kind}.png",
                "sprite_size": list(sprite.size),
            })
    return tuple(records)


__all__ = ["classify_component_v43", "render_relief_component_art_v43"]
