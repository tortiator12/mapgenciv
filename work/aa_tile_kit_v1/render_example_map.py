"""Render a real OpenCivOne stress crop with the AA tile-kit assets.

The chosen crop crosses the 79 -> 0 world seam and contains coast, forest,
jungle, relief, rivers, and a mouth.  C:\\Fraps is read-only input.
"""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import distance_transform_edt

from work.terrain_lab.algorithms.organic_partition import render_weights
from work.terrain_lab.contract import TransitionContext
from work.terrain_lab.materials import value_noise
from work.terrain_lab.regions import plan_region_dressing
from work.terrain_lab.relief_components_v3 import plan_relief_components_v3
from work.terrain_lab.relief_metatiles import plan_relief_metatiles

from .coast_v2 import PixelWindow
from .coast_v3 import CoastV31Config, TangentGlobalCoast
from .compositor import draw_grid_overlay
from .forest_render_v4 import render_forest_regions_v4
from .materials import WorldMaterialSampler
from .relief_mass_v3 import build_relief_mass_masks
from .river_render_v4 import render_river_components_v4


TILE = 96
WORLD_W = 80
WORLD_H = 50
CROP_X = 74
CROP_Y = 18
CROP_W = 12
CROP_H = 8
HALO = 2

DESERT, PLAINS, GRASS, FOREST, HILLS, MOUNTAINS = range(6)
TUNDRA, ARCTIC, SWAMP, JUNGLE, WATER, RIVER = range(6, 12)
N, E, S, W = 1, 2, 4, 8
DIRECTIONS = ((0, -1, N, "N"), (1, 0, E, "E"), (0, 1, S, "S"), (-1, 0, W, "W"))
OPPOSITE = {N: S, E: W, S: N, W: E}
BIT_NAME = {N: "N", E: "E", S: "S", W: "W"}

ROOT = Path(__file__).resolve().parent
# Only read by this file's own demo entry point, never by the functions
# proof_continuous_hydrology_v12.py imports from here -- not part of the
# live generate_world_package.py path.
SNAPSHOT = Path(os.environ.get("MAPGENCIV_SELFTEST_SNAPSHOT",
    str(ROOT.parents[1] / "civ1" / "snapshots" / "oco_seed_7131.json")))
OUTPUT = ROOT.parents[1] / "outputs" / "aa-tile-kit-v1"

MATERIAL_FILES = {
    DESERT: "desert_sand_01.png",
    PLAINS: "plains_dry_01.png",
    GRASS: "grass_lush_01.png",
    MOUNTAINS: "rocky_ground_01.png",
    TUNDRA: "tundra_scrub_01.png",
    ARCTIC: "arctic_snow_01.png",
    SWAMP: "wetland_mud_01.png",
}

RIVER_FILES = {
    1: "river_n.png", 2: "river_e.png", 3: "river_ne.png", 4: "river_s.png",
    5: "river_ns.png", 6: "river_es.png", 7: "river_nes.png", 8: "river_w.png",
    9: "river_nw.png", 10: "river_ew.png", 11: "river_new.png", 12: "river_sw.png",
    13: "river_nsw.png", 14: "river_esw.png", 15: "river_nesw.png",
}

# Explicit grading controls make visual coast experiments reproducible without
# changing the proven Coast-V3.1 geometry or duplicating the renderer.
OCEAN_GAIN = (0.78, 0.88, 1.36)
OCEAN_LIFT = (0.0, -2.0, 8.0)
SHALLOW_TINT = (16.0, 132.0, 155.0)
SHALLOW_MIX = 0.56
BEACH_OPACITY = 0.86
FOAM_OPACITY = 0.48
COAST_SAND_GAIN = (1.14, 1.05, 0.74)
COAST_SAND_LIFT = (8.0, 4.0, -3.0)


def _load_world(snapshot_path=SNAPSHOT):
    snapshot_path = Path(snapshot_path)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    grid = np.asarray(payload["terrain"], dtype=np.int16)
    if grid.shape != (WORLD_H, WORLD_W):
        raise ValueError(f"unexpected map shape {grid.shape}")
    trace_payload = payload.get("river_traces")
    if trace_payload is None and isinstance(payload.get("presentation"), dict):
        trace_payload = payload["presentation"].get("river_traces")
    authoritative_edges = None
    if trace_payload is not None:
        if trace_payload.get("schema") != "project1991.river-traces/v1":
            raise ValueError("unsupported river trace schema")
        parsed = []
        for item in trace_payload.get("river_edges", ()): 
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError("river edge must contain exactly two cells")
            start = tuple(int(value) for value in item[0])
            end = tuple(int(value) for value in item[1])
            if len(start) != 2 or len(end) != 2:
                raise ValueError("river edge cell must be [x, y]")
            parsed.append((start, end))
        authoritative_edges = tuple(parsed)
    return grid, int(payload["seed"]), authoritative_edges


def _crop_with_halo(grid, crop_x=CROP_X, crop_y=CROP_Y, crop_w=CROP_W, crop_h=CROP_H):
    xs = np.arange(crop_x - HALO, crop_x + crop_w + HALO) % WORLD_W
    return grid[crop_y - HALO:crop_y + crop_h + HALO][:, xs].copy()


def _material_grid(raw):
    material = np.full(raw.shape, -1, dtype=np.int16)
    material[raw == DESERT] = DESERT
    material[raw == PLAINS] = PLAINS
    # Civ I's feature cells sit on a common readable ground family. Mountains
    # are therefore relief stamps over grass, not dark rectangular rock slabs.
    material[
        (raw == GRASS)
        | (raw == FOREST)
        | (raw == HILLS)
        | (raw == MOUNTAINS)
        | (raw == JUNGLE)
    ] = GRASS
    material[raw == TUNDRA] = TUNDRA
    material[raw == ARCTIC] = ARCTIC
    material[raw == SWAMP] = SWAMP
    valid = material >= 0
    if not valid.any():
        raise ValueError("crop has no material-bearing land")
    _, nearest = distance_transform_edt(~valid, return_indices=True)
    material[~valid] = material[tuple(nearest)][~valid]
    return material


def _sample_texture(filename: str, world_x: int, world_y: int, width: int, height: int):
    with Image.open(ROOT / "assets" / "materials" / filename) as source:
        sampler = WorldMaterialSampler(
            source.convert("RGBA"),
            world_period_x=WORLD_W * TILE,
        )
        sample = sampler.sample(world_x, world_y, width, height).convert("RGB")
    return np.asarray(sample, dtype=np.float32)


def _sample_coast_sand(world_x: int, world_y: int, width: int, height: int):
    """One warm grade shared by coast, river banks and delta stamps."""

    sand = _sample_texture("coast_sand_01.png", world_x, world_y, width, height)
    sand = sand * np.asarray(COAST_SAND_GAIN, dtype=np.float32)
    sand += np.asarray(COAST_SAND_LIFT, dtype=np.float32)
    return np.clip(sand, 0.0, 255.0)


def _render_ground(
    raw,
    seed,
    full_grid,
    mouth_ports,
    *,
    crop_x=CROP_X,
    crop_y=CROP_Y,
    weight_renderer=render_weights,
):
    material_grid = _material_grid(raw)
    context = TransitionContext(
        material_grid=material_grid,
        tile_px=TILE,
        # Contour placement carries the organic movement; the blend itself is
        # deliberately sharper so isolated tundra/desert cells read as ground
        # rather than rectangular fog patches.
        transition_px=15,
        world_x0=crop_x - HALO,
        world_y0=crop_y - HALO,
        world_width=WORLD_W,
        seed=seed,
    )
    weights = weight_renderer(context)
    world_x = context.world_x0 * TILE
    world_y = context.world_y0 * TILE
    width, height = context.width_px, context.height_px
    textures = {
        int(material): _sample_texture(
            MATERIAL_FILES[int(material)], world_x, world_y, width, height
        )
        for material in weights
    }
    if PLAINS in textures:
        plains = textures[PLAINS]
        luma = (
            plains[..., 0:1] * 0.2126
            + plains[..., 1:2] * 0.7152
            + plains[..., 2:3] * 0.0722
        )
        textures[PLAINS] = plains * 0.82 + luma * 0.18
    if DESERT in textures:
        desert = textures[DESERT]
        luma = (
            desert[..., 0:1] * 0.2126
            + desert[..., 1:2] * 0.7152
            + desert[..., 2:3] * 0.0722
        )
        textures[DESERT] = desert * 0.88 + luma * 0.12
    if TUNDRA in textures and GRASS in textures:
        tundra = textures[TUNDRA]
        mean = tundra.mean(axis=(0, 1), keepdims=True)
        tundra = mean + (tundra - mean) * 0.68
        textures[TUNDRA] = tundra * 0.64 + textures[GRASS] * 0.36
    if ARCTIC in textures and GRASS in textures:
        textures[ARCTIC] = textures[ARCTIC] * 0.84 + textures[GRASS] * 0.16
    if SWAMP in textures and GRASS in textures:
        textures[SWAMP] = textures[SWAMP] * 0.72 + textures[GRASS] * 0.28
    if MOUNTAINS in textures:
        rock = textures[MOUNTAINS]
        mean = rock.mean(axis=(0, 1), keepdims=True)
        rock = mean + (rock - mean) * 0.70
        if GRASS in textures:
            rock = rock * 0.78 + textures[GRASS] * 0.22
        textures[MOUNTAINS] = rock

    land = np.zeros((height, width, 3), dtype=np.float32)
    for material, weight in weights.items():
        land += textures[int(material)] * weight[..., None]
    macro = 0.94 + value_noise(context, TILE * 4.7, 701)[..., None] * 0.10
    land *= macro

    # Components of three or more exact relief cells receive one continuous
    # underpainting before their authored peak silhouettes are composited.
    # This turns a chain into a geological mass and removes the repeated
    # "one sticker per tile" read without changing a single Civ cell owner.
    relief = build_relief_mass_masks(full_grid, context)
    rock = _sample_texture("rocky_ground_01.png", world_x, world_y, width, height)
    if GRASS in textures:
        hill_soil = rock * 0.46 + textures[GRASS] * 0.54
    else:
        hill_soil = rock
    mountain_alpha = np.clip(
        relief.mountain_mass * 0.18 + relief.mountain_ridge * 0.34,
        0.0,
        0.58,
    )
    hill_alpha = np.clip(
        relief.hill_mass * 0.10 + relief.hill_ridge * 0.16,
        0.0,
        0.30,
    )
    land = land * (1.0 - hill_alpha[..., None]) + hill_soil * hill_alpha[..., None]
    land = land * (1.0 - mountain_alpha[..., None]) + rock * mountain_alpha[..., None]

    coast = TangentGlobalCoast(
        CoastV31Config(contour_seed=seed)
    ).build(
        full_grid != WATER,
        window=PixelWindow(world_x, world_y, width, height),
        mouth_ports=mouth_ports,
    )
    signed = coast.signed_distance
    land_cov = coast.land_coverage
    ocean = _sample_texture("ocean_deep_01.png", world_x, world_y, width, height)
    # Lock the approved material dramaturgy: cobalt deep water transitions to
    # a clearly readable cyan shelf before the restrained sand/foam line.
    # The previous petrol blend was technically present but visually vanished
    # at target zoom.
    ocean = ocean * np.asarray(OCEAN_GAIN, dtype=np.float32) + np.asarray(
        OCEAN_LIFT, dtype=np.float32
    )
    ocean = np.clip(ocean, 0.0, 255.0)
    shallow_tint = np.asarray(SHALLOW_TINT, dtype=np.float32)
    deep = 1.0 - coast.shallow
    shallow = ocean * (1.0 - SHALLOW_MIX) + shallow_tint[None, None, :] * SHALLOW_MIX
    sea = shallow * (1.0 - deep[..., None]) + ocean * deep[..., None]

    sand = _sample_coast_sand(world_x, world_y, width, height)
    beach = coast.beach * BEACH_OPACITY
    ground = land * (1.0 - beach[..., None]) + sand * beach[..., None]
    image = sea * (1.0 - land_cov[..., None]) + ground * land_cov[..., None]

    foam = coast.foam
    # Vary opacity along the global contour so the surf is painted, not a tube.
    yy, xx = np.indices(signed.shape, dtype=np.float32)
    breakup = np.clip(
        0.46
        + 0.28 * np.sin((xx + world_x) * 0.071 + (yy + world_y) * 0.039)
        + 0.18 * np.sin((xx + world_x) * 0.031 - (yy + world_y) * 0.083),
        0.08,
        0.86,
    )
    foam *= breakup * FOAM_OPACITY
    foam_color = np.asarray((188, 211, 202), dtype=np.float32)
    image = image * (1.0 - foam[..., None]) + foam_color * foam[..., None]
    return Image.fromarray(np.clip(image, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def _sea_bits(grid, x, y):
    mask = 0
    for dx, dy, bit, _ in DIRECTIONS:
        ny = y + dy
        nx = (x + dx) % WORLD_W
        if 0 <= ny < WORLD_H and int(grid[ny, nx]) == WATER:
            mask |= bit
    return mask


def _river_topology(grid, authoritative_edges=None):
    cells = {(int(x), int(y)) for y, x in np.argwhere(grid == RIVER)}
    if authoritative_edges is not None:
        edges = set()
        for start, end in authoritative_edges:
            start = (int(start[0]) % WORLD_W, int(start[1]))
            end = (int(end[0]) % WORLD_W, int(end[1]))
            if start not in cells or end not in cells:
                raise ValueError("authoritative river edge leaves RIVER terrain")
            dx = min((start[0] - end[0]) % WORLD_W, (end[0] - start[0]) % WORLD_W)
            dy = abs(start[1] - end[1])
            if dx + dy != 1:
                raise ValueError("authoritative river edges must be cardinal")
            edges.add((start, end))
            edges.add((end, start))
        return cells, edges
    distance = {}
    queue = deque()
    for cell in sorted(cells, key=lambda p: (p[1], p[0])):
        if _sea_bits(grid, *cell):
            distance[cell] = 0
            queue.append(cell)
    while queue:
        x, y = queue.popleft()
        for dx, dy, _, _ in DIRECTIONS:
            nxt = ((x + dx) % WORLD_W, y + dy)
            if 0 <= nxt[1] < WORLD_H and nxt in cells and nxt not in distance:
                distance[nxt] = distance[(x, y)] + 1
                queue.append(nxt)

    edges, seen = set(), set()
    queue = deque(sorted((cell for cell in cells if distance.get(cell) == 0), key=lambda p: (p[1], p[0])))
    seen.update(queue)

    def walk():
        while queue:
            current = queue.popleft()
            x, y = current
            for dx, dy, _, _ in DIRECTIONS:
                nxt = ((x + dx) % WORLD_W, y + dy)
                if 0 <= nxt[1] < WORLD_H and nxt in cells and nxt not in seen:
                    seen.add(nxt)
                    edges.add((current, nxt))
                    edges.add((nxt, current))
                    queue.append(nxt)

    walk()
    for cell in sorted(cells, key=lambda p: (p[1], p[0])):
        if cell not in seen:
            seen.add(cell)
            queue.append(cell)
            walk()
    return cells, edges


def _river_mask(cells, edges, x, y):
    mask = 0
    for dx, dy, bit, _ in DIRECTIONS:
        neighbor = ((x + dx) % WORLD_W, y + dy)
        if neighbor in cells and ((x, y), neighbor) in edges:
            mask |= bit
    return mask


def _pick_mouth(river_mask, sea_mask):
    for bit in (N, E, S, W):
        if sea_mask & bit and river_mask & OPPOSITE[bit]:
            return bit
    for bit in (N, E, S, W):
        if sea_mask & bit:
            return bit
    return 0


def _mouth_port_grid(full_grid, cells, edges):
    ports = np.zeros(full_grid.shape, dtype=np.uint8)
    for x, y in cells:
        river_mask = _river_mask(cells, edges, x, y)
        ports[y, x] = _pick_mouth(river_mask, _sea_bits(full_grid, x, y))
    return ports


def _place_rivers(
    image,
    full_grid,
    raw_halo,
    seed,
    *,
    crop_x=CROP_X,
    crop_y=CROP_Y,
):
    cells, edges = _river_topology(full_grid)
    river_assets = {}
    mouth_assets = {}
    for mask, filename in RIVER_FILES.items():
        stem = Path(filename).stem
        river_assets[mask] = (
            Image.open(ROOT / "assets" / "rivers" / filename).convert("RGBA"),
            Image.open(ROOT / "assets" / "rivers" / f"{stem}_b.png").convert("RGBA"),
        )
    for name in ("n", "e", "s", "w"):
        mouth_assets[name.upper()] = Image.open(ROOT / "assets" / "mouths" / f"mouth_{name}.png").convert("RGBA")

    x_unwrapped0 = crop_x - HALO
    y0 = crop_y - HALO
    mouths = []
    for local_y in range(raw_halo.shape[0]):
        world_y = y0 + local_y
        for local_x in range(raw_halo.shape[1]):
            world_x = (x_unwrapped0 + local_x) % WORLD_W
            if int(raw_halo[local_y, local_x]) != RIVER:
                continue
            mask = _river_mask(cells, edges, world_x, world_y)
            mouth = _pick_mouth(mask, _sea_bits(full_grid, world_x, world_y))
            visual_mask = mask | mouth
            if visual_mask == 0:
                visual_mask = N
            variant = _stable_hash(seed, world_x, world_y, 2101) & 1
            image.alpha_composite(
                river_assets[visual_mask][variant],
                (local_x * TILE, local_y * TILE),
            )
            if mouth:
                dx, dy, _, name = next(item for item in DIRECTIONS if item[2] == mouth)
                sea_lx, sea_ly = local_x + dx, local_y + dy
                if 0 <= sea_lx < raw_halo.shape[1] and 0 <= sea_ly < raw_halo.shape[0]:
                    mouths.append((sea_lx, sea_ly, name))
    for local_x, local_y, name in mouths:
        image.alpha_composite(mouth_assets[name], (local_x * TILE, local_y * TILE))


def _place_rivers_component_v4(
    image,
    full_grid,
    seed,
    *,
    crop_x=CROP_X,
    crop_y=CROP_Y,
    crop_w=CROP_W,
    crop_h=CROP_H,
    authoritative_edges=None,
):
    """Paint one world-planned river network without per-cell phase resets."""
    cells, directed_edges = _river_topology(full_grid, authoritative_edges)
    unique_edges = {
        tuple(sorted((start, end), key=lambda cell: (cell[1], cell[0])))
        for start, end in directed_edges
    }
    mouths = {}
    for x, y in cells:
        mask = _river_mask(cells, directed_edges, x, y)
        bit = _pick_mouth(mask, _sea_bits(full_grid, x, y))
        if bit:
            mouths[(x, y)] = BIT_NAME[bit]
    return render_river_components_v4(
        image,
        full_grid,
        tuple(sorted(unique_edges)),
        mouths,
        seed=seed,
        window=(crop_x - HALO, crop_y - HALO, crop_w + HALO * 2, crop_h + HALO * 2),
        tile_px=TILE,
        world_width=WORLD_W,
        mouth_asset_root=ROOT / "assets" / "mouths",
    )


def _components(raw, terrain_codes):
    wanted = np.isin(raw, list(terrain_codes))
    seen = np.zeros(raw.shape, dtype=bool)
    result = []
    for y, x in np.argwhere(wanted):
        y, x = int(y), int(x)
        if seen[y, x]:
            continue
        queue = [(x, y)]
        seen[y, x] = True
        component = []
        while queue:
            cx, cy = queue.pop()
            component.append((cx, cy))
            for dx, dy, _, _ in DIRECTIONS:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < raw.shape[1] and 0 <= ny < raw.shape[0] and wanted[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((nx, ny))
        result.append(component)
    return result


def _scaled_sprite(filename: str, target_width: int):
    with Image.open(ROOT / "assets" / "sprites" / filename) as source:
        rgba = source.convert("RGBA")
    bbox = rgba.getchannel("A").point(lambda a: 255 if a >= 8 else 0).getbbox()
    if bbox is None:
        raise ValueError(f"empty sprite {filename}")
    rgba = rgba.crop(bbox)
    height = max(1, round(rgba.height * target_width / rgba.width))
    rgba = rgba.resize((target_width, height), Image.Resampling.LANCZOS)
    if filename.startswith("hill_"):
        rgba = _prepare_hill_sprite(rgba)
    return rgba


def _prepare_hill_sprite(sprite: Image.Image) -> Image.Image:
    """Give painted hills a green baseplate fade without flattening the rock.

    The authored silhouette and NW lighting remain untouched in the core.  A
    luminance-matched olive colour cools only the inner contact fringe.  The
    outer fringe becomes transparent so the live world baseplate supplies the
    actual local green; this avoids a painted green halo around every hill.
    """

    rgba = np.asarray(sprite.convert("RGBA"), dtype=np.uint8).copy()
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    inside = distance_transform_edt(alpha > (18.0 / 255.0)).astype(np.float32)
    edge_feather = np.clip(inside / 4.4, 0.0, 1.0)
    edge_feather = edge_feather * edge_feather * (3.0 - 2.0 * edge_feather)

    rgb = rgba[..., :3].astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    grass = np.asarray((76.0, 88.0, 45.0), dtype=np.float32)
    grass_luma = float(grass[0] * 0.2126 + grass[1] * 0.7152 + grass[2] * 0.0722)
    green_material = grass[None, None, :] * np.clip(luma / grass_luma, 0.68, 1.34)[..., None]
    foot = 1.0 - np.clip((inside - 3.0) / max(5.0, sprite.width * 0.075), 0.0, 1.0)
    foot = foot * foot * (3.0 - 2.0 * foot)
    foot_mix = np.clip(foot * 0.44 * edge_feather, 0.0, 0.44)
    rgb = rgb * (1.0 - foot_mix[..., None]) + green_material * foot_mix[..., None]
    # Remove the overall ochre cast without turning the exposed crown grey.
    rgb *= np.asarray((0.96, 1.0, 0.94), dtype=np.float32)

    rgba[..., :3] = np.rint(np.clip(rgb, 0.0, 255.0)).astype(np.uint8)
    rgba[..., 3] = np.rint(np.clip(alpha * edge_feather, 0.0, 1.0) * 255.0).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def _alpha_anchor(canvas, sprite, anchor_x, anchor_y):
    left = round(anchor_x - sprite.width / 2)
    top = round(anchor_y - sprite.height)
    right, bottom = left + sprite.width, top + sprite.height
    clip = (max(0, left), max(0, top), min(canvas.width, right), min(canvas.height, bottom))
    if clip[0] >= clip[2] or clip[1] >= clip[3]:
        return
    source_box = (clip[0] - left, clip[1] - top, clip[2] - left, clip[3] - top)
    canvas.alpha_composite(sprite.crop(source_box), (clip[0], clip[1]))


def _contact_shadow(width: int):
    """Return one restrained, neutral ground shadow for the whole asset family."""

    height = max(18, round(width * 0.22))
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow, "RGBA")
    pad_x = max(5, round(width * 0.10))
    pad_y = max(3, round(height * 0.22))
    draw.ellipse(
        (pad_x, pad_y, width - pad_x, height - pad_y),
        fill=(12, 22, 16, 64),
    )
    return shadow.filter(ImageFilter.GaussianBlur(max(3.0, width * 0.035)))


def _stable_hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    value = (int(seed) ^ (x * 0x9E3779B1) ^ (y * 0x85EBCA77) ^ (salt * 0xC2B2AE3D)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _unwrap_relief_cells(cells):
    """Return the shortest horizontally contiguous representation of cells."""
    cells = tuple(cells)
    best = None
    for base_x, _ in cells:
        mapped = {
            cell: base_x + ((cell[0] - base_x + WORLD_W // 2) % WORLD_W) - WORLD_W // 2
            for cell in cells
        }
        values = tuple(mapped.values())
        candidate = (max(values) - min(values), min(values), mapped)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    return best[2]


def _small_mountain_specials(full_grid, seed):
    """Map exact 2--4-cell topologies to authored, non-rotated V3 assets."""
    plans = plan_relief_components_v3(
        full_grid,
        seed=int(seed),
        world_width=WORLD_W,
    )
    specials = []
    consumed = set()
    for plan in plans:
        if plan.terrain != MOUNTAINS or not 2 <= plan.size <= 4:
            continue
        unwrapped = _unwrap_relief_cells(plan.cells)
        min_x = min(unwrapped.values())
        min_y = min(cell[1] for cell in plan.cells)
        shape = {
            (unwrapped[cell] - min_x, cell[1] - min_y)
            for cell in plan.cells
        }
        filename = None
        target_width = 0
        span_x = span_y = 0
        if shape == {(0, 0), (1, 0)}:
            filename, target_width, span_x, span_y = "mountain_pair_ew_v3.png", 176, 2, 1
        elif shape == {(0, 0), (1, 0), (2, 0)}:
            filename, target_width, span_x, span_y = "mountain_line3_ew_v3.png", 269, 3, 1
        elif shape == {(0, 0), (1, 0), (0, 1)}:
            # This authored L has an explicitly empty south-east cell.  Other
            # orientations intentionally fall back to exact smaller pieces;
            # rotating painted NW light would be a visible art error.
            filename, target_width, span_x, span_y = "mountain_L3_v3.png", 180, 2, 2
        elif shape == {(0, 0), (1, 0), (0, 1), (1, 1)}:
            filename, target_width, span_x, span_y = "mountain_block2x2_v3.png", 180, 2, 2
        if filename is None:
            continue
        specials.append((tuple(plan.cells), min_x, min_y, span_x, span_y, filename, target_width))
        consumed.update(plan.cells)
    return tuple(specials), frozenset(consumed)


def _place_landscape_stamps(
    image,
    full_grid,
    seed,
    *,
    crop_x=CROP_X,
    crop_y=CROP_Y,
    crop_w=CROP_W,
    crop_h=CROP_H,
    include_hills=True,
    include_mountains=True,
):
    context = TransitionContext(
        material_grid=full_grid.copy(),
        tile_px=TILE,
        transition_px=15,
        world_x0=0,
        world_y0=0,
        world_width=WORLD_W,
        seed=seed,
    )
    planned = plan_region_dressing(full_grid, context)
    metatiles = plan_relief_metatiles(planned, world_width=WORLD_W)
    relief_by_member = {
        member.owner_world: metatile
        for metatile in metatiles
        for member in metatile.members
    }
    x0 = crop_x - HALO
    y0 = crop_y - HALO
    halo_w = crop_w + HALO * 2
    halo_h = crop_h + HALO * 2
    placements = []
    mountain_specials, special_cells = (
        _small_mountain_specials(full_grid, seed)
        if include_mountains
        else ((), frozenset())
    )
    for cells, min_x, min_y, span_x, span_y, filename, width in mountain_specials:
        local_cells = [
            ((world_x - x0) % WORLD_W, world_y - y0)
            for world_x, world_y in cells
        ]
        if not any(0 <= x < halo_w and 0 <= y < halo_h for x, y in local_cells):
            continue
        local_min_x = (min_x - x0) % WORLD_W
        local_min_y = min_y - y0
        placements.append((
            (local_min_y + span_y - 0.16) * TILE,
            (local_min_x + span_x * 0.5) * TILE,
            filename,
            width,
        ))
    for placement in planned:
        world_x, world_y = placement.owner_world
        # Forest/Jungle V4 owns woodland presentation as world-stable
        # individual populations. Legacy one-cluster stamps would duplicate
        # them and reintroduce the visible wallpaper this pass replaces.
        if placement.family == "woodland":
            continue
        if placement.asset_key == "mountain" and not include_mountains:
            continue
        if placement.asset_key != "mountain" and placement.family == "relief" and not include_hills:
            continue
        if placement.owner_world in special_cells:
            continue
        local_x = (world_x - x0) % WORLD_W
        local_y = world_y - y0
        metatile = relief_by_member.get(placement.owner_world)
        if metatile is not None and metatile.orientation != "single":
            if placement.owner_world != metatile.start.owner_world:
                continue
            orientation = metatile.orientation
            if metatile.asset_key == "mountain" and orientation == "EW":
                pair_asset, pair_width = "mountain_pair_ew_v3.png", 176
            elif metatile.asset_key == "mountain":
                pair_asset, pair_width = "mountain_pair_ns_01.png", 82
            elif orientation == "NS":
                # We do not rotate the painted EW hill pair: doing so would
                # rotate its light.  Until an approved NS metatile is promoted,
                # two compact green singles are the honest topology-preserving
                # fallback and remain clearly inside their owner cells.
                for index, member in enumerate(metatile.members):
                    member_x, member_y = member.owner_world
                    member_lx = (member_x - x0) % WORLD_W
                    member_ly = member_y - y0
                    if 0 <= member_lx < halo_w and 0 <= member_ly < halo_h:
                        placements.append((
                            (member_ly + 0.84) * TILE,
                            (member_lx + 0.5) * TILE,
                            "hill_single_03.png" if index % 2 == 0 else "hill_single_01.png",
                            round(TILE * 0.80),
                        ))
                continue
            else:
                pair_asset, pair_width = "hill_pair_ew_01.png", round(TILE * 1.71)
            if 0 <= local_x < halo_w and 0 <= local_y < halo_h:
                if orientation == "EW":
                    pair_anchor_x = (local_x + 1.0) * TILE
                    pair_anchor_y = (local_y + 0.84) * TILE
                else:
                    pair_anchor_x = (local_x + 0.5) * TILE
                    pair_anchor_y = (local_y + 1.84) * TILE
                placements.append((
                    pair_anchor_y,
                    pair_anchor_x,
                    pair_asset,
                    pair_width,
                ))
            continue
        if not (0 <= local_x < halo_w and 0 <= local_y < halo_h):
            continue
        value = _stable_hash(seed, world_x, world_y, 1701)
        if placement.terrain == JUNGLE:
            variants = ("jungle_dense_01.png", "jungle_dense_02.png")
        elif placement.family == "woodland":
            if placement.asset_key == "conifer":
                variants = (
                    "forest_conifer_01.png", "forest_conifer_02.png", "forest_conifer_03.png",
                )
            else:
                # The crescent mixed grove is intentionally rare; it works best
                # at a region edge rather than as the repeating centre stamp.
                variants = (
                    "forest_temperate_01.png", "forest_temperate_02.png",
                    "forest_temperate_03.png", "forest_temperate_01.png",
                    "forest_temperate_02.png", "forest_temperate_03.png",
                    "forest_temperate_04.png",
                )
        elif placement.asset_key == "mountain":
            # Every logical mountain cell receives a compact, grass-faded
            # footprint.  Long ridges are reserved for a later exact-footprint
            # metatile pass and are never selected for a single owner cell.
            variants = (
                "mountain_single_03.png", "mountain_single_04.png",
            )
        else:
            variants = (
                "hill_single_03.png", "hill_single_03.png", "hill_single_01.png",
            )
        filename = variants[value % len(variants)]
        offset_x = placement.anchor_px[0] - (world_x + 0.5) * TILE
        anchor_x = (local_x + 0.5) * TILE + offset_x
        anchor_y = placement.anchor_px[1] - y0 * TILE
        placements.append((anchor_y, anchor_x, filename, placement.width_px))

    # Swamps and tundra are ground biomes in Civ I, not guaranteed object
    # regions. Add only sparse, world-stable accents so they never become a
    # repeated one-stamp-per-cell carpet.
    accents = (
        (SWAMP, ("wetland_reeds_01.png",), 126, 3, 1801),
        (TUNDRA, (
            "forest_conifer_01.png", "forest_conifer_02.png", "forest_conifer_03.png",
        ), 116, 8, 1901),
    )
    for terrain, variants, width, divisor, salt in accents:
        for world_y, world_x in np.argwhere(full_grid == terrain):
            world_x, world_y = int(world_x), int(world_y)
            value = _stable_hash(seed, world_x, world_y, salt)
            if value % divisor:
                continue
            local_x = (world_x - x0) % WORLD_W
            local_y = world_y - y0
            if not (0 <= local_x < halo_w and 0 <= local_y < halo_h):
                continue
            jitter_x = ((value >> 8) & 255) / 255.0 - 0.5
            filename = variants[(value >> 16) % len(variants)]
            placements.append((
                (local_y + 0.86) * TILE,
                (local_x + 0.5 + jitter_x * 0.24) * TILE,
                filename,
                width,
            ))

    sprite_cache = {}
    shadow_cache = {}
    for anchor_y, anchor_x, filename, width in sorted(placements):
        key = filename, width
        if key not in sprite_cache:
            sprite_cache[key] = _scaled_sprite(filename, width)
        if width not in shadow_cache:
            shadow_cache[width] = _contact_shadow(width)
        _alpha_anchor(image, shadow_cache[width], anchor_x + 4, anchor_y + 4)
        _alpha_anchor(image, sprite_cache[key], anchor_x, anchor_y)


def render_snapshot(
    snapshot_path,
    *,
    crop_x,
    crop_y,
    crop_w=CROP_W,
    crop_h=CROP_H,
    output_stem=None,
):
    if crop_y < HALO or crop_y + crop_h + HALO > WORLD_H:
        raise ValueError("crop plus halo must stay inside non-wrapping world Y")
    full_grid, seed, authoritative_edges = _load_world(snapshot_path)
    raw = _crop_with_halo(full_grid, crop_x, crop_y, crop_w, crop_h)
    cells, edges = _river_topology(full_grid, authoritative_edges)
    mouth_ports = _mouth_port_grid(full_grid, cells, edges)
    image = _render_ground(
        raw,
        seed,
        full_grid,
        mouth_ports,
        crop_x=crop_x,
        crop_y=crop_y,
    )
    # Under-canopy mass and individual trees are painted before relief. A
    # future common object queue will merge their y-sort; this ordering keeps
    # rock silhouettes readable while already removing cluster wallpaper.
    render_forest_regions_v4(
        image,
        full_grid,
        seed=seed,
        window=(
            crop_x - HALO,
            crop_y - HALO,
            crop_w + HALO * 2,
            crop_h + HALO * 2,
        ),
        tile_px=TILE,
        world_width=WORLD_W,
    )
    _place_landscape_stamps(
        image,
        full_grid,
        seed,
        crop_x=crop_x,
        crop_y=crop_y,
        crop_w=crop_w,
        crop_h=crop_h,
    )
    # Rivers are the dominant grammar layer and remain readable through dense
    # forest/relief regions. Mouth stamps are drawn last inside this pass.
    _place_rivers_component_v4(
        image,
        full_grid,
        seed,
        crop_x=crop_x,
        crop_y=crop_y,
        crop_w=crop_w,
        crop_h=crop_h,
        authoritative_edges=authoritative_edges,
    )

    left = HALO * TILE
    top = HALO * TILE
    beauty = image.crop((left, top, left + crop_w * TILE, top + crop_h * TILE))
    gridded = draw_grid_overlay(
        beauty,
        tile_size=(TILE, TILE),
        world_offset_px=(crop_x * TILE, crop_y * TILE),
        dark=(5, 24, 24, 84),
        light=(195, 216, 204, 10),
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stem = output_stem or f"opencivone-seed-{seed}-aa-map-v2"
    no_grid_path = OUTPUT / f"{stem}-nogrid.png"
    grid_path = OUTPUT / f"{stem}.png"
    beauty.convert("RGB").save(no_grid_path, quality=95)
    gridded.convert("RGB").save(grid_path, quality=95)
    print(no_grid_path)
    print(grid_path)
    return no_grid_path, grid_path


def render():
    return render_snapshot(
        SNAPSHOT,
        crop_x=CROP_X,
        crop_y=CROP_Y,
        output_stem="opencivone-seed-7131-aa-map-v2",
    )


if __name__ == "__main__":
    render()
