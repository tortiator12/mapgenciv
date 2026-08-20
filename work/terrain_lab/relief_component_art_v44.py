"""Projected authored relief over an exact Civ component foot.

The logical foot remains the V33 NESW topology.  Authored 2.5D art receives a
separate bounded visual support: generous north projection and small lateral
silhouette room, while the actual terrain ownership never changes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import relief_component_art_v43 as v43
from . import relief_component_massif_v34 as v34
from . import relief_components_v29 as v29
from . import relief_nesw_v33 as v33
from .world import HILLS, MOUNTAINS


ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "work" / "aa_tile_kit_v1" / "assets" / "staging_relief_component_v44"


def _asset(terrain: int, kind: str) -> Image.Image:
    family = "hill" if terrain == HILLS else "mountain"
    with Image.open(ASSET_ROOT / f"{family}_{kind}.png") as handle:
        return handle.convert("RGBA")


def _scaled_asset(terrain: int, kind: str, span_x: int, span_y: int, tile: int) -> Image.Image:
    source = _asset(terrain, kind)
    if terrain == HILLS:
        if kind == "horizontal":
            target_width = round(min(span_x * 0.88, 3.60) * tile)
            scale = target_width / source.width
        elif kind == "vertical":
            target_height = round(min(span_y * 0.72 + 0.30, 3.50) * tile)
            scale = target_height / source.height
        elif kind.startswith("l_missing_"):
            target_width = round(min(max(span_x, span_y) * 0.92, 3.10) * tile)
            scale = target_width / source.width
        else:
            target_width = round(min(max(span_x, span_y) * 0.88, 3.20) * tile)
            scale = target_width / source.width
    else:
        if kind == "horizontal":
            target_width = round(min(span_x * 1.04, 4.10) * tile)
            scale = target_width / source.width
        elif kind == "vertical":
            target_height = round(min(span_y * 0.82 + 0.42, 4.10) * tile)
            scale = target_height / source.height
        elif kind.startswith("l_missing_"):
            target_width = round(min(max(span_x, span_y) * 1.08, 3.55) * tile)
            scale = target_width / source.width
        else:
            target_width = round(min(max(span_x, span_y) * 1.03, 3.85) * tile)
            scale = target_width / source.width
    result = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )
    if terrain == HILLS:
        # Preserve the green base family while making the authored NW-lit
        # crests and erosion grooves survive at gameplay zoom.
        result = ImageEnhance.Brightness(result).enhance(0.84)
        result = ImageEnhance.Contrast(result).enhance(1.18)
        result = ImageEnhance.Color(result).enhance(0.78)
        result = ImageEnhance.Sharpness(result).enhance(1.38)
        result = result.filter(ImageFilter.UnsharpMask(radius=1.15, percent=115, threshold=2))
    return result


def _projected_support(sprite, component_unwrapped, left_world: int, top_world: int, tile: int, terrain: int):
    """Clip art to a bounded projected silhouette, independent of ownership.

    The logical V33 layer owns the exact cells.  This mask only controls visual
    height.  A mountain may project north and a little sideways, as requested,
    but it cannot spread by a whole foreign cell or fill a missing L quadrant.
    """
    hard = Image.new("L", sprite.size, 0)
    draw = ImageDraw.Draw(hard)
    if terrain == MOUNTAINS:
        # A tall three-quarter-view ridge needs almost half a cell of lateral
        # silhouette room; its logical foot remains the exact V33 component.
        north, side, south, blur = 0.75, 0.45, 0.10, 4.0
    else:
        north, side, south, blur = 0.38, 0.24, 0.06, 5.0
    north_px = round(tile * north)
    side_px = round(tile * side)
    south_px = round(tile * south)
    for ux, uy in component_unwrapped.values():
        x0 = ux * tile - left_world - side_px
        y0 = uy * tile - top_world - north_px
        x1 = (ux + 1) * tile - left_world - 1 + side_px
        y1 = (uy + 1) * tile - top_world - 1 + south_px
        draw.rounded_rectangle((x0, y0, x1, y1), radius=max(2, round(tile * 0.10)), fill=255)
    feather = hard.filter(ImageFilter.GaussianBlur(blur))
    hard_a = np.asarray(hard, dtype=np.float32) / 255.0
    soft_a = np.asarray(feather, dtype=np.float32) / 255.0
    support = hard_a * np.clip(soft_a * 1.30, 0.0, 1.0)
    rgba = np.asarray(sprite.convert("RGBA"), dtype=np.uint8).copy()
    rgba[..., 3] = np.rint(rgba[..., 3].astype(np.float32) * support).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA"), {
        "north_overhang_px": north_px,
        "side_overhang_px": side_px,
        "south_overhang_px": south_px,
    }


def render_relief_component_art_v44(
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
            kind, metadata = v43.classify_component_v43(unwrapped)
            span_x, span_y = metadata["span"]
            sprite = _scaled_asset(terrain, kind, span_x, span_y, tile_px)
            points = tuple(unwrapped.values())
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            centre_x = (min(xs) + max(xs) + 1) * 0.5
            bottom_y = max(ys) + (1.00 if terrain == MOUNTAINS else 0.98)
            left_world = round(centre_x * tile_px - sprite.width * 0.5)
            top_world = round(bottom_y * tile_px - sprite.height)
            sprite, projection = _projected_support(
                sprite, unwrapped, left_world, top_world, tile_px, terrain
            )
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
                **projection,
                "asset": f"{'hill' if terrain == HILLS else 'mountain'}_{kind}.png",
                "sprite_size": list(sprite.size),
            })
    return tuple(records)


__all__ = ["render_relief_component_art_v44"]
