"""Authored, exact-cover relief components for the Project1991 renderer.

V29 uses the full Civ terrain grid as authority.  Same-terrain connected
components are deterministically covered with authored 2x2, L, EW/NS pair,
and single motifs.  Every placement owns an explicit set of Civ cells and no
pixel canvas extends beyond that union.  At composition time only the low
contact fringe is colour-matched to the already-rendered live ground.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from .world import HILLS, MOUNTAINS


ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "work" / "aa_tile_kit_v1" / "assets" / "staging_relief_v29"
RELIEF = frozenset((HILLS, MOUNTAINS))


@dataclass(frozen=True, slots=True)
class ReliefPlacementV29:
    placement_id: tuple[int, int, int, str]
    terrain: int
    origin: tuple[int, int]
    cells: tuple[tuple[int, int], ...]
    topology: str
    asset_name: str


def _hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    value = (int(seed) ^ (x * 0x9E3779B1) ^ (y * 0x85EBCA77) ^ (salt * 0xC2B2AE3D)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _components(grid: np.ndarray, terrain: int, world_width: int) -> list[tuple[tuple[int, int], ...]]:
    height, width = grid.shape
    if width != world_width:
        raise ValueError("full authority grid width must equal world_width")
    remaining = {(int(x), int(y)) for y, x in np.argwhere(grid == terrain)}
    result: list[tuple[tuple[int, int], ...]] = []
    while remaining:
        start = min(remaining, key=lambda cell: (cell[1], cell[0]))
        remaining.remove(start)
        queue = deque((start,))
        cells = [start]
        while queue:
            x, y = queue.popleft()
            for nx, ny in (((x - 1) % width, y), ((x + 1) % width, y), (x, y - 1), (x, y + 1)):
                if ny < 0 or ny >= height or (nx, ny) not in remaining:
                    continue
                remaining.remove((nx, ny))
                cells.append((nx, ny))
                queue.append((nx, ny))
        result.append(tuple(sorted(cells, key=lambda cell: (cell[1], cell[0]))))
    return result


def _asset(terrain: int, topology: str, variant: int) -> str:
    family = "mountain" if terrain == MOUNTAINS else "hill"
    if topology == "single":
        return f"{family}_single_{variant % 4 + 1:02d}.png"
    return f"{family}_{topology}_01.png"


def _cover_component(
    cells: tuple[tuple[int, int], ...], terrain: int, seed: int, world_width: int
) -> tuple[ReliefPlacementV29, ...]:
    unclaimed = set(cells)
    placements: list[ReliefPlacementV29] = []

    def add(origin: tuple[int, int], owned: tuple[tuple[int, int], ...], topology: str) -> None:
        x, y = origin
        variant = _hash(seed, x, y, 7101 + terrain) & 3
        placements.append(ReliefPlacementV29(
            placement_id=(terrain, x, y, topology),
            terrain=terrain,
            origin=origin,
            cells=tuple(owned),
            topology=topology,
            asset_name=_asset(terrain, topology, variant),
        ))
        unclaimed.difference_update(owned)

    # Largest exact motifs first.  Candidate order is stable but seed-varied
    # so repeated large components do not decompose on the same phase.
    origins = sorted(cells, key=lambda cell: (_hash(seed, cell[0], cell[1], 7201), cell[1], cell[0]))
    for x, y in origins:
        block = ((x, y), ((x + 1) % world_width, y), (x, y + 1), ((x + 1) % world_width, y + 1))
        if all(cell in unclaimed for cell in block):
            add((x, y), block, "block_2x2")

    # The authored canonical L owns NW+NE+SW.  Other orientations deliberately
    # fall back to pairs/singles rather than rotating painted northwest light.
    for x, y in origins:
        l_cells = ((x, y), ((x + 1) % world_width, y), (x, y + 1))
        if all(cell in unclaimed for cell in l_cells):
            add((x, y), l_cells, "l3_nw_ne_sw")

    pair_origins = sorted(unclaimed, key=lambda cell: (_hash(seed, cell[0], cell[1], 7301), cell[1], cell[0]))
    for x, y in pair_origins:
        if (x, y) not in unclaimed:
            continue
        east = ((x + 1) % world_width, y)
        south = (x, y + 1)
        prefer_ns = bool(_hash(seed, x, y, 7303) & 1)
        candidates = ((south, "pair_ns"), (east, "pair_ew")) if prefer_ns else ((east, "pair_ew"), (south, "pair_ns"))
        for neighbour, topology in candidates:
            if neighbour in unclaimed:
                add((x, y), ((x, y), neighbour), topology)
                break

    for x, y in sorted(unclaimed, key=lambda cell: (cell[1], cell[0])):
        add((x, y), ((x, y),), "single")
    return tuple(placements)


def plan_relief_components_v29(
    full_grid: np.ndarray, *, seed: int, world_width: int | None = None
) -> tuple[ReliefPlacementV29, ...]:
    grid = np.asarray(full_grid, dtype=np.int16)
    if grid.ndim != 2:
        raise ValueError("full_grid must be a 2D authority array")
    width = grid.shape[1] if world_width is None else int(world_width)
    result: list[ReliefPlacementV29] = []
    for terrain in (HILLS, MOUNTAINS):
        for component in _components(grid, terrain, width):
            result.extend(_cover_component(component, terrain, seed, width))
    return tuple(sorted(result, key=lambda item: (max(y for _, y in item.cells), item.origin[0], item.terrain)))


def _contact_weight(sprite: Image.Image, terrain: int = MOUNTAINS) -> np.ndarray:
    rgba = np.asarray(sprite.convert("RGBA"), dtype=np.uint8).copy()
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    if not np.any(alpha > 0.03):
        return np.zeros(alpha.shape, dtype=np.float32)
    bbox = sprite.getchannel("A").point(lambda value: 255 if value >= 8 else 0).getbbox()
    if bbox is None:
        return np.zeros(alpha.shape, dtype=np.float32)
    inside = distance_transform_edt(alpha > 0.03).astype(np.float32)
    edge_depth = 13.0 if terrain == HILLS else 7.0
    edge = 1.0 - np.clip((inside - 1.0) / edge_depth, 0.0, 1.0)
    edge = edge * edge * (3.0 - 2.0 * edge)
    yy = np.arange(sprite.height, dtype=np.float32)[:, None]
    # Green hills are part of the base plate and may dissolve along most of
    # their lower silhouette.  Mountains retain a sharper upper rock face and
    # only merge at the scree/grass foot.
    low_fraction = 0.18 if terrain == HILLS else 0.48
    ramp_fraction = 0.58 if terrain == HILLS else 0.36
    low_start = bbox[1] + (bbox[3] - bbox[1]) * low_fraction
    low = np.clip((yy - low_start) / max(1.0, (bbox[3] - bbox[1]) * ramp_fraction), 0.0, 1.0)
    low = low * low * (3.0 - 2.0 * low)
    rgb = rgba[..., :3].astype(np.float32)
    signed = rgb.astype(np.int16)
    rose = ((np.minimum(signed[..., 0], signed[..., 2]) - signed[..., 1]) > 1).astype(np.float32)
    if terrain == HILLS:
        # A hill is continuous base-plate relief, not a cut-out object.  Its
        # complete antialiased perimeter therefore inherits the exact live
        # world ground below it.  Do not attenuate this RGB replacement by the
        # sprite alpha: partial edge pixels are where chroma contamination is
        # otherwise most visible after compositing.
        return np.maximum(np.maximum(edge * 0.98, low * 0.42), rose * low * 0.98)
    # Chroma cleanup can leave a muted rose/brown contact colour in fully
    # opaque scree.  Replace that colour only in the lower foot zone with the
    # live world ground; do not wash the actual rock faces or upper silhouette.
    return np.maximum(edge * low * 0.78, rose * low * 0.98) * alpha


def _live_ground_contact(
    sprite: Image.Image,
    ground: np.ndarray,
    contact: np.ndarray | None = None,
    *,
    terrain: int = MOUNTAINS,
) -> Image.Image:
    rgba = np.asarray(sprite.convert("RGBA"), dtype=np.uint8).copy()
    if contact is None:
        contact = _contact_weight(sprite, terrain)
    rgb = rgba[..., :3].astype(np.float32)
    rgb = rgb * (1.0 - contact[..., None]) + ground[..., :3].astype(np.float32) * contact[..., None]
    rgba[..., :3] = np.rint(np.clip(rgb, 0.0, 255.0)).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def _composite_clipped(base: Image.Image, sprite: Image.Image, left: int, top: int, terrain: int) -> None:
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(base.width, left + sprite.width), min(base.height, top + sprite.height)
    if x1 <= x0 or y1 <= y0:
        return
    crop_box = (x0 - left, y0 - top, x1 - left, y1 - top)
    local = sprite.crop(crop_box)
    full_contact = _contact_weight(sprite, terrain)
    contact = full_contact[crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
    ground = np.asarray(base.crop((x0, y0, x1, y1)).convert("RGBA"), dtype=np.uint8)
    base.alpha_composite(_live_ground_contact(local, ground, contact, terrain=terrain), (x0, y0))


def render_relief_components_v29(
    base: Image.Image,
    full_grid: np.ndarray,
    *,
    seed: int,
    window: tuple[int, int, int, int],
    tile_px: int = 96,
    world_width: int | None = None,
) -> tuple[ReliefPlacementV29, ...]:
    if tile_px != 96:
        raise ValueError("V29 authored assets are locked to 96 px per Civ cell")
    grid = np.asarray(full_grid, dtype=np.int16)
    width = grid.shape[1] if world_width is None else int(world_width)
    x0, y0, cells_w, cells_h = (int(value) for value in window)
    if base.size != (cells_w * tile_px, cells_h * tile_px):
        raise ValueError("base pixel size does not match cell window")
    placements = plan_relief_components_v29(grid, seed=seed, world_width=width)
    period_px = width * tile_px
    for placement in placements:
        path = ASSET_ROOT / placement.asset_name
        with Image.open(path) as handle:
            sprite = handle.convert("RGBA")
        origin_x, origin_y = placement.origin
        world_left = origin_x * tile_px
        world_top = origin_y * tile_px
        window_left = x0 * tile_px
        window_right = window_left + base.width
        for cycle in range(-2, 3):
            shifted_left = world_left + cycle * period_px
            if shifted_left + sprite.width <= window_left or shifted_left >= window_right:
                continue
            left = shifted_left - window_left
            top = world_top - y0 * tile_px
            _composite_clipped(base, sprite, left, top, placement.terrain)
    return placements


def validate_exact_cover_v29(full_grid: np.ndarray, placements: tuple[ReliefPlacementV29, ...]) -> dict[str, int | bool]:
    grid = np.asarray(full_grid, dtype=np.int16)
    expected = {(x, y) for y, x in np.argwhere(np.isin(grid, tuple(RELIEF)))}
    claimed = [cell for placement in placements for cell in placement.cells]
    wrong = sum(int(grid[y, x] != placement.terrain) for placement in placements for x, y in placement.cells)
    return {
        "expected_cells": len(expected),
        "claimed_cells": len(claimed),
        "unique_claimed_cells": len(set(claimed)),
        "uncovered_cells": len(expected - set(claimed)),
        "duplicate_cells": len(claimed) - len(set(claimed)),
        "wrong_terrain_cells": wrong,
        "valid": not (expected - set(claimed)) and len(claimed) == len(set(claimed)) and wrong == 0,
    }
