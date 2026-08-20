"""Authored component-wide relief art on the proven V33/V29 footprint grammar."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import relief_component_massif_v34 as v34
from . import relief_components_v29 as v29
from . import relief_nesw_v33 as v33
from .world import HILLS, MOUNTAINS


ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "work" / "aa_tile_kit_v1" / "assets" / "staging_relief_component_v42"


def _art_source(terrain: int) -> Image.Image:
    name = "hill_component_3x2.png" if terrain == HILLS else "mountain_component_3x2.png"
    with Image.open(ASSET_ROOT / name) as handle:
        source = handle.convert("RGBA")
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"empty relief source: {name}")
    return source.crop(bbox)


def _scaled_component_art(terrain: int, span_x: int, span_y: int, tile: int) -> Image.Image:
    source = _art_source(terrain)
    # One formation spans the component rather than one owner cell.  A small
    # extra width lets the high three-quarter silhouette project naturally;
    # the authoritative component mask clips its physical foot afterwards.
    width_cells = max(span_x * 0.92, span_y * (1.30 if terrain == MOUNTAINS else 1.22))
    width_cells = min(width_cells, span_x + 0.65)
    target_width = max(tile, round(width_cells * tile))
    scale = target_width / source.width
    return source.resize(
        (target_width, max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )


def _clip_component_art_v42(
    sprite: Image.Image,
    component_unwrapped,
    left_world: int,
    top_world: int,
    tile: int,
    terrain: int,
) -> Image.Image:
    """Feather authored rock inward while keeping its physical support exact.

    The ecological NESW foot underneath may blend a few pixels into the live
    baseplate.  Authored rock itself may project north, but never sideways
    into a non-relief owner column.  Multiplying the blurred mask by the hard
    support gives a soft internal contact without the old outward alpha leak.
    """
    hard = Image.new("L", sprite.size, 0)
    draw = ImageDraw.Draw(hard)
    overhang = round(tile * (0.55 if terrain == MOUNTAINS else 0.28))
    for ux, uy in component_unwrapped.values():
        x0 = ux * tile - left_world
        y0 = uy * tile - top_world - overhang
        # Pillow rectangles include the final coordinate; subtract one so an
        # owner cell never claims the first pixel of its non-relief neighbour.
        x1 = (ux + 1) * tile - left_world - 1
        y1 = (uy + 1) * tile - top_world - 1
        draw.rectangle((x0, y0, x1, y1), fill=255)
    feather = hard.filter(ImageFilter.GaussianBlur(4.0 if terrain == MOUNTAINS else 5.5))
    hard_a = np.asarray(hard, dtype=np.float32) / 255.0
    soft_a = np.asarray(feather, dtype=np.float32) / 255.0
    support = hard_a * np.clip(soft_a * 1.35, 0.0, 1.0)
    rgba = np.asarray(sprite.convert("RGBA"), dtype=np.uint8).copy()
    rgba[..., 3] = np.rint(rgba[..., 3].astype(np.float32) * support).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def render_relief_component_art_v42(
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

    # Keep the exact shared saddle/foot field and the already proven small
    # single/pair/L/2x2 grammar.  V42 replaces only five-plus components.
    grounded = v33._apply_topology(base, grid, seed, (x0, y0, cells_w, cells_h), tile_px, width)
    base.paste(grounded)
    components = {terrain: v33._components(grid, terrain, width) for terrain in (HILLS, MOUNTAINS)}
    large_cells = {
        terrain: {cell for component in components[terrain] if len(component) >= 5 for cell in component}
        for terrain in (HILLS, MOUNTAINS)
    }
    for placement in v29.plan_relief_components_v29(grid, seed=seed, world_width=width):
        if any(cell in large_cells[placement.terrain] for cell in placement.cells):
            continue
        with Image.open(Path(v29.ASSET_ROOT) / placement.asset_name) as handle:
            sprite = handle.convert("RGBA")
        world_left = placement.origin[0] * tile_px
        world_top = placement.origin[1] * tile_px
        for cycle in range(-2, 3):
            left = world_left + cycle * width * tile_px - x0 * tile_px
            top = world_top - y0 * tile_px
            if left + sprite.width <= 0 or left >= base.width or top + sprite.height <= 0 or top >= base.height:
                continue
            v29._composite_clipped(base, sprite, left, top, placement.terrain)

    records = []
    period = width * tile_px
    for terrain in (HILLS, MOUNTAINS):
        for component in components[terrain]:
            if len(component) < 5:
                continue
            unwrapped = v34._unwrap_component(component, width)
            xs = [point[0] for point in unwrapped.values()]
            ys = [point[1] for point in unwrapped.values()]
            span_x = max(xs) - min(xs) + 1
            span_y = max(ys) - min(ys) + 1
            # The first V42 gate deliberately refuses a fake rotated asset.
            # Strongly vertical components retain V34 until a separately
            # authored NW-lit vertical family exists.
            if span_y > span_x + 1:
                sprite = v34._massif_sprite("hill" if terrain == HILLS else "mountain", 0, round(tile_px * min(span_x * 0.92, 3.55)))
                source_kind = "v34_vertical_fallback"
            else:
                sprite = _scaled_component_art(terrain, span_x, span_y, tile_px)
                source_kind = "authored_component_3x2"

            centre_x = (min(xs) + max(xs) + 1) * 0.5
            bottom_y = max(ys) + 1.02
            left_world = round(centre_x * tile_px - sprite.width * 0.5)
            top_world = round(bottom_y * tile_px - sprite.height)
            sprite = _clip_component_art_v42(sprite, unwrapped, left_world, top_world, tile_px, terrain)
            for cycle in range(-2, 3):
                left = left_world + cycle * period - x0 * tile_px
                top = top_world - y0 * tile_px
                if left + sprite.width <= 0 or left >= base.width or top + sprite.height <= 0 or top >= base.height:
                    continue
                v29._composite_clipped(base, sprite, left, top, terrain)
            records.append({
                "terrain": int(terrain),
                "size": len(component),
                "span": [span_x, span_y],
                "source": source_kind,
                "sprite_size": [sprite.width, sprite.height],
            })
    return tuple(records)


__all__ = ["render_relief_component_art_v42"]
