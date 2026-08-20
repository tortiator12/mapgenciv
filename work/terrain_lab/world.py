"""OpenCivOne snapshot selection and crop utilities for the terrain lab."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt


DESERT = 0
PLAINS = 1
GRASSLAND = 2
FOREST = 3
HILLS = 4
MOUNTAINS = 5
TUNDRA = 6
ARCTIC = 7
SWAMP = 8
JUNGLE = 9
WATER = 10
RIVER = 11

WORLD_W = 80
WORLD_H = 50


@dataclass(frozen=True)
class Snapshot:
    path: Path
    seed: int
    grid: np.ndarray


@dataclass(frozen=True)
class CropChoice:
    x0: int
    y0: int
    width: int
    height: int
    score: float


def discover_snapshots(root: Path) -> list[Path]:
    paths = sorted((root / "snapshots" / "opencivone_stress" / "maps").glob("oco_seed_*.json"))
    if not paths:
        paths = sorted((root / "snapshots" / "opencivone" / "maps").glob("oco_seed_*.json"))
    if not paths:
        raise FileNotFoundError(f"no OpenCivOne snapshots below {root}")
    return paths


def load_snapshot(path: Path) -> Snapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    grid = np.asarray(payload["terrain"], dtype=np.int16)
    if grid.shape != (WORLD_H, WORLD_W):
        raise ValueError(f"{path.name}: expected 50x80, got {grid.shape}")
    return Snapshot(path=path, seed=int(payload["seed"]), grid=grid)


def dice_snapshots(root: Path, roll_seed: int, count: int) -> list[Snapshot]:
    paths = discover_snapshots(root)
    if count > len(paths):
        raise ValueError(f"requested {count} snapshots from only {len(paths)}")
    rng = random.Random(int(roll_seed))
    return [load_snapshot(path) for path in rng.sample(paths, count)]


def _window(grid: np.ndarray, x0: int, y0: int, width: int, height: int) -> np.ndarray:
    xs = np.arange(x0, x0 + width, dtype=np.int32) % WORLD_W
    return grid[y0 : y0 + height][:, xs]


def choose_crop(grid: np.ndarray, width: int = 12, height: int = 8, halo: int = 2) -> CropChoice:
    """Pick a readable viewport without changing the rolled world itself."""
    best: CropChoice | None = None
    for y0 in range(halo, WORLD_H - height - halo + 1):
        for x0 in range(WORLD_W):
            view = _window(grid, x0, y0, width, height)
            water = int(np.count_nonzero(view == WATER))
            land = view.size - water
            if land < view.size * 0.45 or water < view.size * 0.08:
                continue
            river = int(np.count_nonzero(view == RIVER))
            woods = int(np.count_nonzero((view == FOREST) | (view == JUNGLE)))
            relief = int(np.count_nonzero((view == HILLS) | (view == MOUNTAINS)))
            terrain_types = len(set(int(value) for value in np.unique(view) if value != WATER))
            mouths = 0
            for yy, xx in np.argwhere(view == RIVER):
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = int(xx + dx), int(yy + dy)
                    if 0 <= nx < width and 0 <= ny < height and int(view[ny, nx]) == WATER:
                        mouths += 1
                        break
            water_ratio = water / view.size
            balance = 1.0 - min(abs(water_ratio - 0.28) / 0.28, 1.0)
            centre = view[height // 4 : height * 3 // 4, width // 4 : width * 3 // 4]
            centre_land = float(np.mean(centre != WATER))
            score = (
                river * 1.35
                + mouths * 7.0
                + woods * 0.55
                + relief * 0.42
                + terrain_types * 3.4
                + balance * 13.0
                + centre_land * 6.0
            )
            choice = CropChoice(x0=x0, y0=y0, width=width, height=height, score=score)
            if best is None or choice.score > best.score:
                best = choice
    if best is None:
        return CropChoice(x0=0, y0=max(halo, (WORLD_H - height) // 2), width=width, height=height, score=0.0)
    return best


def extract_with_halo(grid: np.ndarray, crop: CropChoice, halo: int) -> tuple[np.ndarray, int, int]:
    y0 = crop.y0 - halo
    y1 = crop.y0 + crop.height + halo
    if y0 < 0 or y1 > WORLD_H:
        raise ValueError("crop halo falls outside non-wrapping world Y")
    xs = np.arange(crop.x0 - halo, crop.x0 + crop.width + halo, dtype=np.int32) % WORLD_W
    return grid[y0:y1][:, xs].copy(), crop.x0 - halo, y0


def material_underlay(raw_grid: np.ndarray) -> np.ndarray:
    """Extrapolate land materials under coast water; river defaults to grass."""
    material = np.asarray(raw_grid, dtype=np.int16).copy()
    material[material == RIVER] = GRASSLAND
    water = material == WATER
    if water.all():
        material[:] = GRASSLAND
        return material
    if water.any():
        _, nearest = distance_transform_edt(water, return_indices=True)
        nearest_material = material[tuple(nearest)]
        material[water] = nearest_material[water]
    return material


def crop_pixels(image: np.ndarray, halo: int, tile_px: int, width: int, height: int) -> np.ndarray:
    y0 = halo * tile_px
    x0 = halo * tile_px
    return image[y0 : y0 + height * tile_px, x0 : x0 + width * tile_px]

