"""Civ-style 0..F contextual renderer for the staged green hill family."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from work.terrain_lab.world import HILLS


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSET_ROOT = ROOT / "assets" / "staging_hills_nesw_v2"
N, E, S, W = 1, 2, 4, 8


@dataclass(frozen=True, slots=True)
class HillNeswRenderReport:
    hill_cells_in_window: int
    painted_hill_cells: int
    mask_usage: dict[int, int]
    centre_alpha_failures: int
    peak_cells: int
    shoulder_cells: int

    @property
    def hard_contract_pass(self) -> bool:
        return self.hill_cells_in_window == self.painted_hill_cells and self.centre_alpha_failures == 0


def hill_mask(full_grid: np.ndarray, x: int, y: int, *, world_width: int = 80) -> int:
    grid = np.asarray(full_grid)
    height = grid.shape[0]
    result = 0
    if y > 0 and int(grid[y - 1, x % world_width]) == HILLS:
        result |= N
    if int(grid[y, (x + 1) % world_width]) == HILLS:
        result |= E
    if y + 1 < height and int(grid[y + 1, x % world_width]) == HILLS:
        result |= S
    if int(grid[y, (x - 1) % world_width]) == HILLS:
        result |= W
    return result


def _hash(seed: int, x: int, y: int) -> int:
    value = (int(seed) ^ (x * 0x9E3779B1) ^ (y * 0x85EBCA77)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _visual_roles(full_grid: np.ndarray, *, seed: int, world_width: int) -> dict[tuple[int, int], str]:
    grid = np.asarray(full_grid)
    cells = {(int(x), int(y)) for y, x in np.argwhere(grid == HILLS)}
    roles: dict[tuple[int, int], str] = {}
    while cells:
        start = min(cells, key=lambda cell: (cell[1], cell[0]))
        component = set()
        queue = [start]
        cells.remove(start)
        while queue:
            cell = queue.pop()
            component.add(cell)
            x, y = cell
            for neighbour in (((x + 1) % world_width, y), ((x - 1) % world_width, y), (x, y - 1), (x, y + 1)):
                if neighbour in cells:
                    cells.remove(neighbour)
                    queue.append(neighbour)
        if len(component) <= 2:
            for cell in component:
                roles[cell] = "peak"
            continue
        peak_target = max(1, (len(component) + 4) // 5)
        selected: list[tuple[int, int]] = []
        ordered = sorted(component, key=lambda cell: (_hash(seed, cell[0], cell[1]), cell[1], cell[0]))
        for cell in ordered:
            if len(selected) >= peak_target:
                break
            x, y = cell
            if any(
                (abs(y - sy) + min((x - sx) % world_width, (sx - x) % world_width)) <= 1
                for sx, sy in selected
            ):
                continue
            selected.append(cell)
        for cell in ordered:
            if len(selected) >= peak_target:
                break
            if cell not in selected:
                selected.append(cell)
        peak_set = set(selected)
        for cell in component:
            roles[cell] = "peak" if cell in peak_set else "shoulder"
    return roles


def render_hill_nesw_v2(
    image: Image.Image,
    full_grid: np.ndarray,
    *,
    window: tuple[int, int, int, int],
    tile_px: int = 96,
    world_width: int = 80,
    seed: int = 0,
    shoulder_opacity: float = 0.50,
    asset_root: Path = DEFAULT_ASSET_ROOT,
) -> HillNeswRenderReport:
    x0, y0, width, height = (int(value) for value in window)
    if image.size != (width * tile_px, height * tile_px):
        raise ValueError("hill canvas does not match the cell window")
    grid = np.asarray(full_grid)
    cache: dict[int, Image.Image] = {}
    usage: Counter[int] = Counter()
    painted = 0
    failures = 0
    logical = 0
    peak_cells = 0
    shoulder_cells = 0
    roles = _visual_roles(grid, seed=int(seed), world_width=world_width)
    for local_y in range(height):
        world_y = y0 + local_y
        if not 0 <= world_y < grid.shape[0]:
            continue
        for local_x in range(width):
            world_x = (x0 + local_x) % world_width
            if int(grid[world_y, world_x]) != HILLS:
                continue
            logical += 1
            mask = hill_mask(grid, world_x, world_y, world_width=world_width)
            role = roles[(world_x, world_y)]
            key = (role, mask)
            if key not in cache:
                prefix = "hill_nesw" if role == "peak" else "hill_shoulder_nesw"
                with Image.open(Path(asset_root) / f"{prefix}_{mask:x}.png") as opened:
                    loaded = opened.convert("RGBA").resize(
                        (tile_px, tile_px), Image.Resampling.LANCZOS
                    )
                if role == "shoulder":
                    if not 0.0 <= shoulder_opacity <= 1.0:
                        raise ValueError("shoulder_opacity must be in [0, 1]")
                    rgba = np.asarray(loaded, dtype=np.uint8).copy()
                    rgba[..., 3] = np.rint(rgba[..., 3].astype(np.float32) * shoulder_opacity).astype(np.uint8)
                    loaded = Image.fromarray(rgba, "RGBA")
                cache[key] = loaded
            sprite = cache[key]
            if sprite.getpixel((tile_px // 2, tile_px // 2))[3] < 24:
                failures += 1
            image.alpha_composite(sprite, (local_x * tile_px, local_y * tile_px))
            usage[mask] += 1
            if role == "peak":
                peak_cells += 1
            else:
                shoulder_cells += 1
            painted += 1
    return HillNeswRenderReport(
        logical,
        painted,
        dict(sorted(usage.items())),
        failures,
        peak_cells,
        shoulder_cells,
    )


__all__ = ["HillNeswRenderReport", "hill_mask", "render_hill_nesw_v2"]
