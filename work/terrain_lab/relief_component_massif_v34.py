"""Component-wide authored massif layer for five-plus relief cells."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import relief_components_v29 as v29
from . import relief_nesw_v33 as v33
from .world import HILLS, MOUNTAINS


def _unwrap_component(component, world_width: int):
    cells = set(component)
    start = min(cells, key=lambda cell: (cell[1], cell[0]))
    unwrapped = {start: (start[0], start[1])}
    queue = deque((start,))
    while queue:
        x, y = queue.popleft()
        ux, uy = unwrapped[(x, y)]
        for dx, dy, _bit in v33.DIRS:
            neighbour = ((x + dx) % world_width, y + dy)
            if neighbour not in cells or neighbour in unwrapped:
                continue
            unwrapped[neighbour] = (ux + dx, uy + dy)
            queue.append(neighbour)
    return unwrapped


def _massif_sprite(family: str, variant: int, target_width: int):
    # Last-row atlased motifs are intentionally broad component formations.
    slot = 12 + variant % 4
    with Image.open(v33.ASSET_ROOT / f"{family}_nesw_{slot:02x}.png") as handle:
        source = handle.convert("RGBA")
    bbox = source.getchannel("A").getbbox()
    crop = source.crop(bbox) if bbox else source
    scale = target_width / crop.width
    return crop.resize((target_width, max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)


def _hill_cluster_centres(component_unwrapped, count: int):
    """Choose stable, separated owner cells for a broad connected hill chain."""
    points = sorted(component_unwrapped.values(), key=lambda point: (point[1], point[0]))
    chosen = [min(points, key=lambda point: (point[0] + point[1], point[1], point[0]))]
    while len(chosen) < min(count, len(points)):
        candidate = max(
            (point for point in points if point not in chosen),
            key=lambda point: (
                min((point[0] - old[0]) ** 2 + (point[1] - old[1]) ** 2 for old in chosen),
                -point[1],
                -point[0],
            ),
        )
        chosen.append(candidate)
    return tuple(sorted(chosen, key=lambda point: (point[1], point[0])))


def _clip_to_component(sprite: Image.Image, component_unwrapped, left_world: int, top_world: int, tile: int, terrain: int):
    mask = Image.new("L", sprite.size, 0)
    draw = ImageDraw.Draw(mask)
    overhang = round(tile * (0.58 if terrain == MOUNTAINS else 0.30))
    for ux, uy in component_unwrapped.values():
        x0 = ux * tile - left_world
        y0 = uy * tile - top_world - overhang
        x1 = (ux + 1) * tile - left_world
        y1 = (uy + 1) * tile - top_world
        draw.rectangle((x0, y0, x1, y1), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(3.0 if terrain == MOUNTAINS else 5.0))
    rgba = np.asarray(sprite, dtype=np.uint8).copy()
    rgba[..., 3] = np.rint(rgba[..., 3].astype(np.float32) * (np.asarray(mask, dtype=np.float32) / 255.0)).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def render_relief_component_massif_v34(base: Image.Image, full_grid: np.ndarray, *, seed: int, window, tile_px: int = 96, world_width: int | None = None):
    grid = np.asarray(full_grid, dtype=np.int16)
    width = grid.shape[1] if world_width is None else int(world_width)
    x0, y0, cells_w, cells_h = (int(value) for value in window)
    if base.size != (cells_w * tile_px, cells_h * tile_px):
        raise ValueError("base pixel size does not match window")

    # The exact shared-port foot/saddle field grounds every cell first.
    grounded = v33._apply_topology(base, grid, seed, (x0, y0, cells_w, cells_h), tile_px, width)
    base.paste(grounded)
    components = {terrain: v33._components(grid, terrain, width) for terrain in (HILLS, MOUNTAINS)}
    large_cells = {
        terrain: {cell for component in components[terrain] if len(component) >= 5 for cell in component}
        for terrain in (HILLS, MOUNTAINS)
    }

    # Small components keep the exact V29 single/pair/L/2x2 grammar.
    placements = v29.plan_relief_components_v29(grid, seed=seed, world_width=width)
    period = width * tile_px
    for placement in placements:
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

    massifs = []
    for terrain in (HILLS, MOUNTAINS):
        family = "hill" if terrain == HILLS else "mountain"
        for component in components[terrain]:
            if len(component) < 5:
                continue
            unwrapped = _unwrap_component(component, width)
            xs = [point[0] for point in unwrapped.values()]
            ys = [point[1] for point in unwrapped.values()]
            span_x = max(xs) - min(xs) + 1
            span_y = max(ys) - min(ys) + 1
            if terrain == MOUNTAINS:
                centres = (((min(xs) + max(xs) + 1) * 0.5, max(ys) + 0.98),)
                widths = (round(tile_px * min(span_x * 0.90, 3.55)),)
            else:
                # One giant hill reads as a potato.  A five-plus component is
                # instead a low overlapping chain, while the shared NESW foot
                # field underneath makes the separate crowns one landform.
                cluster_count = min(3, max(2, (len(component) + 3) // 4))
                owners = _hill_cluster_centres(unwrapped, cluster_count)
                centres = tuple((ux + 0.5, uy + 0.91) for ux, uy in owners)
                widths = tuple(round(tile_px * 1.72) for _ in centres)
            variants = []
            for index, ((centre_x_cells, bottom_y_cells), target_width) in enumerate(zip(centres, widths)):
                variant = v33._hash(seed, min(xs), min(ys), 3701 + terrain + index * 17) & 3
                sprite = _massif_sprite(family, variant, target_width)
                left_world = round(centre_x_cells * tile_px - sprite.width * 0.5)
                top_world = round(bottom_y_cells * tile_px - sprite.height)
                sprite = _clip_to_component(sprite, unwrapped, left_world, top_world, tile_px, terrain)
                for cycle in range(-2, 3):
                    left = left_world + cycle * period - x0 * tile_px
                    top = top_world - y0 * tile_px
                    if left + sprite.width <= 0 or left >= base.width or top + sprite.height <= 0 or top >= base.height:
                        continue
                    v29._composite_clipped(base, sprite, left, top, terrain)
                variants.append(variant)
            massifs.append({
                "terrain": terrain,
                "size": len(component),
                "span": [span_x, span_y],
                "variant": variants[0],
                "crowns": len(variants),
                "variants": variants,
            })
    return tuple(massifs)


__all__ = ["render_relief_component_massif_v34"]
