"""Deterministic connected-region dressing for the terrain lab.

This module deliberately plans objects but does not draw them.  The golden-screen
compositor can therefore use the existing asset loading and bottom-centre blitter
while the placement policy stays testable and independent of PIL.

The input grid is expected to include the normal two-cell render halo.  Horizontal
neighbourhood is resolved in absolute world coordinates, so an 80-wide full-world
grid and a crop crossing column 79 -> 0 both form the correct components.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .contract import TransitionContext
from .world import FOREST, HILLS, JUNGLE, MOUNTAINS


Family = Literal["woodland", "relief"]
LocalCell = tuple[int, int]
WorldCell = tuple[int, int]
TileBounds = tuple[int, int, int, int]

TARGET_TERRAINS = frozenset((FOREST, JUNGLE, HILLS, MOUNTAINS))
_WOODLAND = frozenset((FOREST, JUNGLE))
_RELIEF = frozenset((HILLS, MOUNTAINS))

N, E, S, W = 1, 2, 4, 8


@dataclass(frozen=True, slots=True)
class RegionCell:
    """One terrain cell in both local halo and absolute world coordinates."""

    local_x: int
    local_y: int
    world_x: int
    world_y: int
    terrain: int


@dataclass(frozen=True, slots=True)
class TerrainRegion:
    """A four-connected woodland or relief component."""

    family: Family
    key: tuple[str, int, int]
    cells: tuple[RegionCell, ...]
    dominant_terrain: int


@dataclass(frozen=True, slots=True)
class RegionPlacement:
    """Renderer-neutral description of one bottom-centred sprite.

    ``anchor_px`` is the foot point used for y-sorting and compositing.  Sprites
    stay inside their owning Civ cell.  ``component_size`` and
    ``neighbor_mask`` let a renderer opt into a footprint-aware multi-cell
    asset later; they never grant permission to spill across unrelated cells.
    ``asset_key`` matches the keys already used by :mod:`terrain_lab.decor`.
    """

    family: Family
    component_key: tuple[str, int, int]
    asset_key: str
    terrain: int
    owner_local: LocalCell
    owner_world: WorldCell
    anchor_px: tuple[int, int]
    width_px: int
    mirror: bool
    color: float
    priority: int
    component_size: int
    neighbor_mask: int

    @property
    def sort_key(self) -> tuple[int, int, int, int, str]:
        """Stable painter-order key: feet from back to front, then x and id."""

        return (
            self.anchor_px[1],
            self.anchor_px[0],
            self.owner_world[1],
            self.owner_world[0],
            self.asset_key,
        )


def _hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    """Small cross-platform integer hash; never relies on Python's hash seed."""

    value = (int(seed) ^ (x * 0x9E3779B1) ^ (y * 0x85EBCA77) ^ (salt * 0xC2B2AE3D)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _family(terrain: int) -> Family | None:
    if terrain in _WOODLAND:
        return "woodland"
    if terrain in _RELIEF:
        return "relief"
    return None


def _validate_grid(raw_grid: np.ndarray, context: TransitionContext) -> np.ndarray:
    grid = np.asarray(raw_grid)
    if grid.ndim != 2:
        raise ValueError(f"raw_grid must be 2-D, got {grid.shape}")
    if grid.shape != context.material_grid.shape:
        raise ValueError(
            "raw_grid and context.material_grid must describe the same halo: "
            f"{grid.shape} != {context.material_grid.shape}"
        )
    if context.world_width <= 0:
        raise ValueError("context.world_width must be positive")
    if context.tile_px <= 0:
        raise ValueError("context.tile_px must be positive")
    return grid


def _world_cell(context: TransitionContext, x: int, y: int) -> WorldCell:
    return ((context.world_x0 + x) % context.world_width, context.world_y0 + y)


def find_regions(raw_grid: np.ndarray, context: TransitionContext) -> tuple[TerrainRegion, ...]:
    """Return stable four-connected components for woods and relief.

    Forest and jungle share a woodland component; hills and mountains share a
    relief component.  The local grid may contain a full world or only a crop
    plus halo.  A coordinate lookup joins any present world-neighbours, including
    the horizontal wrap pair ``world_width - 1`` and ``0``.
    """

    grid = _validate_grid(raw_grid, context)
    height, width = grid.shape
    nodes: dict[LocalCell, tuple[Family, WorldCell, int]] = {}
    by_world: dict[WorldCell, list[LocalCell]] = {}
    for y in range(height):
        for x in range(width):
            terrain = int(grid[y, x])
            family = _family(terrain)
            if family is None:
                continue
            world = _world_cell(context, x, y)
            nodes[(x, y)] = (family, world, terrain)
            by_world.setdefault(world, []).append((x, y))

    unseen = set(nodes)
    regions: list[TerrainRegion] = []
    while unseen:
        # Local order is only a traversal detail; final keys use world cells.
        start = min(unseen, key=lambda cell: (nodes[cell][1][1], nodes[cell][1][0], cell[1], cell[0]))
        family = nodes[start][0]
        component: list[LocalCell] = []
        queue: deque[LocalCell] = deque((start,))
        unseen.remove(start)
        while queue:
            local = queue.popleft()
            component.append(local)
            wx, wy = nodes[local][1]
            neighbours = (
                ((wx - 1) % context.world_width, wy),
                ((wx + 1) % context.world_width, wy),
                (wx, wy - 1),
                (wx, wy + 1),
            )
            candidates: list[LocalCell] = []
            for world_neighbour in neighbours:
                candidates.extend(by_world.get(world_neighbour, ()))
            for neighbour in sorted(candidates, key=lambda cell: (cell[1], cell[0])):
                # Gameplay authority is the exact Civ terrain code.  Hills and
                # mountains (or forest and jungle) share a drawing family but
                # must never silently merge into one visual component.
                if (
                    neighbour in unseen
                    and nodes[neighbour][0] == family
                    and nodes[neighbour][2] == nodes[start][2]
                ):
                    unseen.remove(neighbour)
                    queue.append(neighbour)

        cells = tuple(
            sorted(
                (
                    RegionCell(
                        local_x=x,
                        local_y=y,
                        world_x=nodes[(x, y)][1][0],
                        world_y=nodes[(x, y)][1][1],
                        terrain=nodes[(x, y)][2],
                    )
                    for x, y in component
                ),
                key=lambda cell: (cell.world_y, cell.world_x, cell.local_y, cell.local_x),
            )
        )
        canonical = min(cells, key=lambda cell: (cell.world_y, cell.world_x))
        counts = Counter(cell.terrain for cell in cells)
        dominant = min(counts, key=lambda terrain: (-counts[terrain], terrain))
        regions.append(
            TerrainRegion(
                family=family,
                key=(family, canonical.world_x, canonical.world_y),
                cells=cells,
                dominant_terrain=int(dominant),
            )
        )

    return tuple(sorted(regions, key=lambda region: (region.key[2], region.key[1], region.family)))


def _region_degree(cell: RegionCell, cells: set[WorldCell], world_width: int) -> int:
    wx, wy = cell.world_x, cell.world_y
    return sum(
        neighbour in cells
        for neighbour in (
            ((wx - 1) % world_width, wy),
            ((wx + 1) % world_width, wy),
            (wx, wy - 1),
            (wx, wy + 1),
        )
    )


def _region_neighbor_mask(cell: RegionCell, cells: set[WorldCell], world_width: int) -> int:
    """Return the exact same-terrain NESW topology around ``cell``."""

    wx, wy = cell.world_x, cell.world_y
    mask = 0
    for neighbour, bit in (
        (((wx) % world_width, wy - 1), N),
        (((wx + 1) % world_width, wy), E),
        (((wx) % world_width, wy + 1), S),
        (((wx - 1) % world_width, wy), W),
    ):
        if neighbour in cells:
            mask |= bit
    return mask


def _candidate_cells(region: TerrainRegion, context: TransitionContext) -> list[tuple[int, RegionCell]]:
    world_cells = {(cell.world_x, cell.world_y) for cell in region.cells}
    salt = 1103 if region.family == "woodland" else 1201
    candidates = []
    for cell in region.cells:
        degree = _region_degree(cell, world_cells, context.world_width)
        noise = _hash(context.seed, cell.world_x, cell.world_y, salt) & 0xFFFF
        # Interior cells form coherent masses; deterministic noise prevents rows.
        score = degree * 100_000 + noise
        candidates.append((score, cell))
    return sorted(candidates, key=lambda item: (-item[0], item[1].world_y, item[1].world_x))


def _select_owners(region: TerrainRegion, context: TransitionContext) -> list[tuple[int, RegionCell]]:
    # Every Civ feature cell remains visually represented.  The previous sparse
    # policy omitted legitimate mountain/forest cells and then compensated with
    # oversized stickers.  Compact per-cell owners are deterministic and may be
    # replaced by exact-footprint metatiles in a later compositor pass.
    return _candidate_cells(region, context)


def _exclusion_clear(
    exclusion: np.ndarray,
    anchor: tuple[int, int],
    tile_px: int,
    width_px: int,
    threshold: float,
) -> bool:
    """Check the foot and its small contact patch, not the full visual crown."""

    x, y = anchor
    radius_x = min(tile_px * 0.24, width_px * 0.13)
    radius_y = tile_px * 0.055
    samples = (
        (x, y),
        (x - radius_x, y),
        (x + radius_x, y),
        (x, y - radius_y),
        (x, y + radius_y),
    )
    height, width = exclusion.shape
    for sample_x, sample_y in samples:
        ix = min(max(int(round(sample_x)), 0), width - 1)
        iy = min(max(int(round(sample_y)), 0), height - 1)
        if float(exclusion[iy, ix]) > threshold:
            return False
    return True


def _placement_for_owner(
    region: TerrainRegion,
    owner: RegionCell,
    score: int,
    context: TransitionContext,
    exclusion: np.ndarray,
    exclusion_threshold: float,
) -> RegionPlacement | None:
    value = _hash(context.seed, owner.world_x, owner.world_y, 1301)
    tile = context.tile_px
    world_cells = {(cell.world_x, cell.world_y) for cell in region.cells}
    neighbor_mask = _region_neighbor_mask(owner, world_cells, context.world_width)
    component_size = len(region.cells)

    if region.family == "woodland":
        conifer = owner.world_y < 13 or (owner.terrain == FOREST and (value & 7) <= 1)
        asset_key = "conifer" if conifer else "broadleaf"
        terrain = owner.terrain if owner.terrain in _WOODLAND else region.dominant_terrain
        # 25--35 px refers to an individual crown.  These authored clusters are
        # kept within their Civ cell; connected cells gain density through
        # neighbouring placements rather than one giant carpet sprite.
        width_tiles = (0.90 if terrain == JUNGLE else 0.86)
        if component_size > 1:
            width_tiles += 0.06
        color = 1.08 if terrain == JUNGLE else 0.94 + ((value >> 25) & 7) * 0.018
    else:
        # Never promote a logical HILLS cell because mountains happen to be
        # nearby.  Single-cell relief uses a genuinely compact asset budget;
        # connected ranges are composed from adjacent compact owners until an
        # exact orientation/footprint metatile is available.
        terrain = owner.terrain
        asset_key = "mountain" if terrain == MOUNTAINS else "hill"
        if terrain == MOUNTAINS:
            width_tiles = 0.86 if component_size == 1 else 0.90
        else:
            width_tiles = 0.80 if component_size == 1 else 0.84
        color = 0.88 if terrain == MOUNTAINS else 0.93

    width_px = max(1, int(round(tile * width_tiles)))
    # Try a deterministic irregular foot first, then safe alternatives within
    # the owning cell.  This lets exclusion masks steer roots away from rivers.
    jitter_x = (((value >> 8) & 0xFF) / 255.0 - 0.5) * 0.20
    jitter_y = (((value >> 16) & 0xFF) / 255.0 - 0.5) * 0.10
    alternatives = (
        (jitter_x, jitter_y),
        (0.0, 0.0),
        (-0.20, -0.04),
        (0.20, -0.04),
        (-0.14, 0.06),
        (0.14, 0.06),
    )
    start = (value >> 24) % len(alternatives)
    for index in range(len(alternatives)):
        offset_x, offset_y = alternatives[(start + index) % len(alternatives)]
        anchor = (
            int(round((owner.local_x + 0.5 + offset_x) * tile)),
            int(round((owner.local_y + 0.80 + offset_y) * tile)),
        )
        if not _exclusion_clear(exclusion, anchor, tile, width_px, exclusion_threshold):
            continue
        return RegionPlacement(
            family=region.family,
            component_key=region.key,
            asset_key=asset_key,
            terrain=int(terrain),
            owner_local=(owner.local_x, owner.local_y),
            owner_world=(owner.world_x, owner.world_y),
            anchor_px=anchor,
            width_px=width_px,
            mirror=bool(value & 1),
            color=round(float(color), 3),
            priority=int(score),
            component_size=component_size,
            neighbor_mask=neighbor_mask,
        )
    return None


def _inside_bounds(cell: LocalCell, bounds: TileBounds | None) -> bool:
    if bounds is None:
        return True
    x0, y0, x1, y1 = bounds
    return x0 <= cell[0] < x1 and y0 <= cell[1] < y1


def plan_region_dressing(
    raw_grid: np.ndarray,
    context: TransitionContext,
    exclusion: np.ndarray | None = None,
    *,
    owner_bounds: TileBounds | None = None,
    exclusion_threshold: float = 0.33,
) -> tuple[RegionPlacement, ...]:
    """Plan compact, cell-authoritative groves and relief for a halo grid.

    Parameters
    ----------
    raw_grid:
        Terrain ids including the compositor's two-cell halo.
    context:
        Matching :class:`TransitionContext`; absolute coordinates drive every
        random-looking choice.
    exclusion:
        Pixel mask where values above ``exclusion_threshold`` reject a sprite's
        foot/contact patch.  ``None`` means no exclusion.
    owner_bounds:
        Optional half-open local tile bounds ``(x0, y0, x1, y1)``.  Leave unset
        while drawing the halo; use ``(2, 2, width-2, height-2)`` when a chunk
        should only *own* placements whose source cell lies in its interior.

    Returns
    -------
    tuple[RegionPlacement, ...]
        Stable painter order, ready for the compositor's existing asset cache.
    """

    grid = _validate_grid(raw_grid, context)
    expected_shape = (context.height_px, context.width_px)
    if exclusion is None:
        exclusion_array = np.zeros(expected_shape, dtype=np.float32)
    else:
        exclusion_array = np.asarray(exclusion)
        if exclusion_array.shape != expected_shape:
            raise ValueError(f"exclusion must have pixel shape {expected_shape}, got {exclusion_array.shape}")
        if not np.isfinite(exclusion_array).all():
            raise ValueError("exclusion contains non-finite values")
    if not 0.0 <= exclusion_threshold <= 1.0:
        raise ValueError("exclusion_threshold must be in [0, 1]")
    if owner_bounds is not None:
        x0, y0, x1, y1 = owner_bounds
        if not (0 <= x0 <= x1 <= grid.shape[1] and 0 <= y0 <= y1 <= grid.shape[0]):
            raise ValueError(f"owner_bounds {owner_bounds} fall outside grid {grid.shape}")

    planned: list[RegionPlacement] = []
    for region in find_regions(grid, context):
        for score, owner in _select_owners(region, context):
            placement = _placement_for_owner(
                region,
                owner,
                score,
                context,
                exclusion_array,
                exclusion_threshold,
            )
            if placement is not None:
                planned.append(placement)

    if owner_bounds is not None:
        planned = [placement for placement in planned if _inside_bounds(placement.owner_local, owner_bounds)]
    return tuple(sorted(planned, key=lambda placement: placement.sort_key))


__all__ = (
    "RegionCell",
    "RegionPlacement",
    "TerrainRegion",
    "find_regions",
    "plan_region_dressing",
)
