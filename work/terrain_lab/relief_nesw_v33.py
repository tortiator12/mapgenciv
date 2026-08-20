"""True 16-mask NESW relief grammar with authored peaks and shared saddles.

Every logical hill/mountain cell derives its 4-bit same-terrain mask.  Shared
edge ports are fixed at edge midpoints and receive the same width from both
cells.  A low connected world-space saddle/foothill layer carries topology;
sparse authored motifs carry high-frequency geology and vertical silhouette.
"""

from __future__ import annotations

from collections import deque
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from work.aa_tile_kit_v1 import render_example_map as ground_renderer

from . import relief_components_v29 as v29
from .world import HILLS, MOUNTAINS


ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "work" / "aa_tile_kit_v1" / "assets" / "staging_relief_nesw_v33"
N, E, S, W = 1, 2, 4, 8
DIRS = ((0, -1, N), (1, 0, E), (0, 1, S), (-1, 0, W))


def _hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    value = (seed ^ (x * 0x9E3779B1) ^ (y * 0x85EBCA77) ^ (salt * 0xC2B2AE3D)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def relief_mask(grid: np.ndarray, x: int, y: int, terrain: int, world_width: int) -> int:
    value = 0
    height = grid.shape[0]
    for dx, dy, bit in DIRS:
        ny = y + dy
        if 0 <= ny < height and int(grid[ny, (x + dx) % world_width]) == terrain:
            value |= bit
    return value


def _components(grid: np.ndarray, terrain: int, world_width: int):
    remaining = {(int(x), int(y)) for y, x in np.argwhere(grid == terrain)}
    result = []
    while remaining:
        start = min(remaining, key=lambda cell: (cell[1], cell[0]))
        remaining.remove(start)
        queue = deque((start,))
        cells = [start]
        while queue:
            x, y = queue.popleft()
            for dx, dy, _bit in DIRS:
                cell = ((x + dx) % world_width, y + dy)
                if cell in remaining:
                    remaining.remove(cell)
                    queue.append(cell)
                    cells.append(cell)
        result.append(tuple(sorted(cells, key=lambda cell: (cell[1], cell[0]))))
    return result


def _peak_cells(component, seed: int, terrain: int, world_width: int):
    target = 1 if len(component) == 1 else (2 if len(component) == 2 else max(2, int(math.ceil(len(component) / 2.6))))
    ordered = sorted(component, key=lambda cell: (_hash(seed, cell[0], cell[1], 3300 + terrain), cell[1], cell[0]))
    selected = [ordered[0]]
    while len(selected) < min(target, len(ordered)):
        best = None
        best_key = None
        for cell in ordered:
            if cell in selected:
                continue
            distance = min(abs(cell[1] - other[1]) + min(abs(cell[0] - other[0]), world_width - abs(cell[0] - other[0])) for other in selected)
            key = (distance, _hash(seed, cell[0], cell[1], 3311 + terrain))
            if best_key is None or key > best_key:
                best_key, best = key, cell
        selected.append(best)
    return tuple(selected)


def _hub(seed: int, x: int, y: int, terrain: int, tile: int):
    jx = ((_hash(seed, x, y, 3401 + terrain) / 0xFFFFFFFF) - 0.5) * tile * 0.15
    jy = ((_hash(seed, x, y, 3407 + terrain) / 0xFFFFFFFF) - 0.5) * tile * 0.13
    return (x * tile + tile * 0.5 + jx, y * tile + tile * 0.54 + jy)


def _curve_points(start, end, seed: int, x: int, y: int, bit: int, steps: int = 11):
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    length = max(math.hypot(dx, dy), 1.0)
    nx, ny = -dy / length, dx / length
    bend = (((_hash(seed, x, y, 3500 + bit) / 0xFFFFFFFF) - 0.5) * 10.0)
    control = ((sx + ex) * 0.5 + nx * bend, (sy + ey) * 0.5 + ny * bend)
    points = []
    for q in np.linspace(0.0, 1.0, steps):
        one = 1.0 - q
        points.append((one * one * sx + 2.0 * one * q * control[0] + q * q * ex, one * one * sy + 2.0 * one * q * control[1] + q * q * ey))
    return points


def _topology_masks(grid, terrain: int, seed: int, window, tile: int, world_width: int):
    x0, y0, cells_w, cells_h = window
    scale = 2
    size = (cells_w * tile * scale, cells_h * tile * scale)
    foot = Image.new("L", size, 0)
    ridge = Image.new("L", size, 0)
    foot_draw, ridge_draw = ImageDraw.Draw(foot), ImageDraw.Draw(ridge)
    foot_width = (46 if terrain == MOUNTAINS else 52) * scale
    ridge_width = (23 if terrain == MOUNTAINS else 18) * scale
    margin = tile * 1.2
    period = world_width * tile
    for y in range(grid.shape[0]):
        for x in range(world_width):
            if int(grid[y, x]) != terrain:
                continue
            hub_world = _hub(seed, x, y, terrain, tile)
            mask = relief_mask(grid, x, y, terrain, world_width)
            for cycle in range(-2, 3):
                hx = hub_world[0] + cycle * period - x0 * tile
                hy = hub_world[1] - y0 * tile
                if hx < -margin or hx > cells_w * tile + margin or hy < -margin or hy > cells_h * tile + margin:
                    continue
                hub = (hx * scale, hy * scale)
                radius = foot_width * (0.34 if mask else 0.47)
                foot_draw.ellipse((hub[0] - radius, hub[1] - radius, hub[0] + radius, hub[1] + radius), fill=232)
                ridge_draw.ellipse((hub[0] - ridge_width * 0.43, hub[1] - ridge_width * 0.43, hub[0] + ridge_width * 0.43, hub[1] + ridge_width * 0.43), fill=218)
                for dx, dy, bit in DIRS:
                    if not (mask & bit):
                        continue
                    port_world = (x * tile + (0.5 + 0.5 * dx) * tile, y * tile + (0.5 + 0.5 * dy) * tile)
                    port = ((port_world[0] + cycle * period - x0 * tile) * scale, (port_world[1] - y0 * tile) * scale)
                    points = [(px * scale, py * scale) for px, py in _curve_points((hx, hy), (port[0] / scale, port[1] / scale), seed, x, y, bit)]
                    foot_draw.line(points, fill=232, width=foot_width, joint="curve")
                    ridge_draw.line(points, fill=220, width=ridge_width, joint="curve")
    foot = foot.resize((cells_w * tile, cells_h * tile), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(4.2))
    ridge = ridge.resize((cells_w * tile, cells_h * tile), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(2.3))
    return np.asarray(foot, dtype=np.float32) / 255.0, np.asarray(ridge, dtype=np.float32) / 255.0


def _apply_topology(base: Image.Image, grid: np.ndarray, seed: int, window, tile: int, world_width: int):
    rgba = np.asarray(base.convert("RGBA"), dtype=np.uint8).copy()
    base_rgb = rgba[..., :3].astype(np.float32)
    world_x = window[0] * tile
    world_y = window[1] * tile
    rock = ground_renderer._sample_texture("rocky_ground_01.png", world_x, world_y, base.width, base.height)
    grass = ground_renderer._sample_texture("grass_lush_01.png", world_x, world_y, base.width, base.height)
    for terrain in (HILLS, MOUNTAINS):
        foot, ridge = _topology_masks(grid, terrain, seed, window, tile, world_width)
        if terrain == MOUNTAINS:
            foot_rgb = base_rgb * 0.54 + rock * 0.46
            ridge_rgb = rock * np.asarray((0.93, 0.94, 0.91), dtype=np.float32)
            foot_mix = foot * 0.48
            ridge_mix = ridge * 0.38
        else:
            foot_rgb = base_rgb * 0.66 + grass * np.asarray((0.86, 0.91, 0.74), dtype=np.float32) * 0.34
            ridge_rgb = grass * np.asarray((0.76, 0.82, 0.64), dtype=np.float32)
            foot_mix = foot * 0.36
            ridge_mix = ridge * 0.27
        base_rgb = base_rgb * (1.0 - foot_mix[..., None]) + foot_rgb * foot_mix[..., None]
        base_rgb = base_rgb * (1.0 - ridge_mix[..., None]) + ridge_rgb * ridge_mix[..., None]
    rgba[..., :3] = np.rint(np.clip(base_rgb, 0.0, 255.0)).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def _motif(family: str, mask: int, target_width: int):
    with Image.open(ASSET_ROOT / f"{family}_nesw_{mask:02x}.png") as handle:
        source = handle.convert("RGBA")
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        return source
    crop = source.crop(bbox)
    scale = target_width / crop.width
    return crop.resize((target_width, max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)


def render_relief_nesw_v33(base: Image.Image, full_grid: np.ndarray, *, seed: int, window, tile_px: int = 96, world_width: int | None = None):
    grid = np.asarray(full_grid, dtype=np.int16)
    width = grid.shape[1] if world_width is None else int(world_width)
    x0, y0, cells_w, cells_h = (int(value) for value in window)
    if base.size != (cells_w * tile_px, cells_h * tile_px):
        raise ValueError("base pixel size does not match window")
    painted = _apply_topology(base, grid, seed, (x0, y0, cells_w, cells_h), tile_px, width)
    base.paste(painted)
    period = width * tile_px
    peaks = []
    for terrain in (HILLS, MOUNTAINS):
        family = "hill" if terrain == HILLS else "mountain"
        for component in _components(grid, terrain, width):
            for x, y in _peak_cells(component, seed, terrain, width):
                mask = relief_mask(grid, x, y, terrain, width)
                target_width = (78 + (_hash(seed, x, y, 3601) % 7)) if terrain == HILLS else (84 + (_hash(seed, x, y, 3607) % 9))
                sprite = _motif(family, mask, target_width)
                for cycle in range(-2, 3):
                    cx = x * tile_px + tile_px * 0.5 + cycle * period - x0 * tile_px
                    bottom = y * tile_px + tile_px * 0.92 - y0 * tile_px
                    left = round(cx - sprite.width * 0.5)
                    top = round(bottom - sprite.height)
                    if left + sprite.width <= 0 or left >= base.width or top + sprite.height <= 0 or top >= base.height:
                        continue
                    v29._composite_clipped(base, sprite, left, top, terrain)
                peaks.append((terrain, x, y, mask))
    return tuple(peaks)


__all__ = ["relief_mask", "render_relief_nesw_v33"]
