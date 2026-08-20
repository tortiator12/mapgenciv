"""Reusable V77/V78 unified Project1991 world-window renderer.

This is the first renderer API built from the visually approved V77 stack.
It deliberately does not call the rejected ``render.splatmap`` background.
The Civ grid and map-generator metadata remain authoritative; CoastV31,
V51 ground, V44 relief, Hills NESW and Forest V4.1 are the visual family.
The optional material-edge feather is a crop-independent Nordstern export
gate; leaving it at zero preserves the historically approved V79 pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from work import selected_material_world_v66 as v77
from work.aa_tile_kit_v1.coast_v2 import PixelWindow
from work.aa_tile_kit_v1.coast_v3 import CoastV31Config, TangentGlobalCoast
from work.aa_tile_kit_v1.forest_render_v4 import render_forest_regions_v4
from work.aa_tile_kit_v1.hill_nesw_renderer_v2 import render_hill_nesw_v2
from work.aa_tile_kit_v1.materials import WorldMaterialSampler
from work.terrain_lab.contract import TransitionContext
from work.terrain_lab.ground_corner_lattice_v51 import make_weight_renderer_v51
from work.terrain_lab.relief_component_art_v44 import render_relief_component_art_v44


Window = tuple[int, int, int, int]
SEAMLESS_MATERIAL_SCHEMA = "project1991.unified-window/v79-seamless-materials-v1"
SEAMLESS_MATERIAL_SAMPLING = "toroidal-adaptive-edge-feather-v1"


@dataclass(frozen=True)
class UnifiedWindowV79:
    base: Image.Image
    beauty: Image.Image
    grid: Image.Image
    report: dict


@lru_cache(maxsize=32)
def _cached_material_sampler(
    source_path: str,
    world_period_x: int,
    seamless_edge_feather: int,
) -> WorldMaterialSampler:
    """Cache crop-independent material preparation for multi-chunk exports."""

    with Image.open(source_path) as opened:
        source = opened.convert("RGBA")
    return WorldMaterialSampler(
        source,
        world_period_x=int(world_period_x),
        seamless_edge_feather=int(seamless_edge_feather),
    )


def _cell_x_near_window(x: int, crop_x: int, crop_w: int, world_width: int) -> float:
    centre = crop_x + crop_w * 0.5
    candidates = (x - world_width, x, x + world_width)
    return float(min(candidates, key=lambda value: abs(value - centre)))


def _mouth_intersects_window(
    mouth: dict,
    window: Window,
    world_width: int,
    halo_cells: int = 2,
) -> bool:
    crop_x, crop_y, crop_w, crop_h = window
    for x, y in mouth.get("river_cells", (mouth["river_cell"],)):
        world_x = _cell_x_near_window(int(x), crop_x, crop_w, world_width)
        if (
            crop_x - halo_cells <= world_x < crop_x + crop_w + halo_cells
            and crop_y - halo_cells <= int(y) < crop_y + crop_h + halo_cells
        ):
            return True
    return False


def _select_mouths(
    metadata: dict,
    window: Window,
    world_width: int,
    mouth_cells: Iterable[tuple[int, int]] | None,
) -> list[dict]:
    mouths = list(metadata.get("river_mouths", ()))
    if mouth_cells is not None:
        requested = {tuple(cell) for cell in mouth_cells}
        selected = [mouth for mouth in mouths if tuple(mouth["river_cell"]) in requested]
        missing = requested - {tuple(mouth["river_cell"]) for mouth in selected}
        if missing:
            raise ValueError(f"unknown river mouth cells: {sorted(missing)!r}")
        return selected
    return [
        mouth
        for mouth in mouths
        if _mouth_intersects_window(mouth, window, world_width)
    ]


def _overlap_groups(mouths: list[dict]) -> list[list[dict]]:
    """Group generator systems that share actual recorded river cells."""

    remaining = list(mouths)
    groups: list[list[dict]] = []
    while remaining:
        group = [remaining.pop(0)]
        cells = {tuple(cell) for cell in group[0].get("river_cells", ())}
        changed = True
        while changed:
            changed = False
            keep: list[dict] = []
            for mouth in remaining:
                mouth_cells = {tuple(cell) for cell in mouth.get("river_cells", ())}
                if cells & mouth_cells:
                    group.append(mouth)
                    cells |= mouth_cells
                    changed = True
                else:
                    keep.append(mouth)
            remaining = keep
        groups.append(group)
    return groups


def _recorded_graph(
    mouths: list[dict],
    world_width: int = 80,
) -> dict[tuple[int, int], set[tuple[int, int]]]:
    """Build the exact locked V77 path edges for each generator system.

    ``river_cells`` is a set-like growth log, not an ordered polyline (some
    consecutive entries are not neighbours). The approved V77 painter derives
    its route with ``_system_path``; the merged painter must use those same
    cardinal paths before deduplicating shared edges.
    """

    graph: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for mouth in mouths:
        route = v77._system_path(mouth, world_width=world_width)
        for cell in route:
            graph.setdefault(cell, set())
        for a, b in zip(route, route[1:]):
            graph[a].add(b)
            graph[b].add(a)
    return graph


def _graph_trails(
    graph: dict[tuple[int, int], set[tuple[int, int]]]
) -> list[list[tuple[int, int]]]:
    """Split a recorded graph into maximal non-duplicated trails."""

    def edge(a: tuple[int, int], b: tuple[int, int]):
        return frozenset((a, b))

    visited: set[frozenset[tuple[int, int]]] = set()
    trails: list[list[tuple[int, int]]] = []
    starts = sorted(cell for cell, neighbours in graph.items() if len(neighbours) != 2)
    for start in starts:
        for neighbour in sorted(graph[start]):
            if edge(start, neighbour) in visited:
                continue
            trail = [start, neighbour]
            visited.add(edge(start, neighbour))
            previous, current = start, neighbour
            while len(graph[current]) == 2:
                next_cell = next(cell for cell in graph[current] if cell != previous)
                if edge(current, next_cell) in visited:
                    break
                trail.append(next_cell)
                visited.add(edge(current, next_cell))
                previous, current = current, next_cell
            trails.append(trail)
    # Defensive cycle support: recorded mapgen routes should be acyclic, but a
    # saved map must still render without inventing or dropping an edge.
    for start in sorted(graph):
        for neighbour in sorted(graph[start]):
            if edge(start, neighbour) in visited:
                continue
            trail = [start, neighbour]
            visited.add(edge(start, neighbour))
            previous, current = start, neighbour
            while True:
                candidates = [
                    cell
                    for cell in graph[current]
                    if cell != previous and edge(current, cell) not in visited
                ]
                if not candidates:
                    break
                next_cell = sorted(candidates)[0]
                trail.append(next_cell)
                visited.add(edge(current, next_cell))
                previous, current = current, next_cell
            trails.append(trail)
    return trails


def _paint_overlapping_network(
    image: Image.Image,
    mouths: list[dict],
    *,
    seed: int,
    window: Window,
    tile_px: int,
    world_width: int,
    palette: tuple[tuple[int, int, int, int], ...],
    sand_texture: np.ndarray,
    ocean_texture: np.ndarray,
) -> list[list[tuple[int, int]]]:
    """Paint one shared graph once when generator systems have merged.

    Rendering each mouth independently retraces the shared cells in opposite
    directions and creates parallel blue loops. This painter consumes the
    ordered generator edges, decomposes them into unique trails, and unions
    their masks before any material is composited.
    """

    crop_x, crop_y, crop_w, _ = window
    graph = _recorded_graph(mouths, world_width=world_width)
    trails = _graph_trails(graph)
    mouth_by_cell = {tuple(mouth["river_cell"]): mouth for mouth in mouths}

    local_routes: list[list[tuple[int, int]]] = []
    for trail in trails:
        points: list[tuple[float, float]] = []
        for x, y in trail:
            world_x = _cell_x_near_window(x, crop_x, crop_w, world_width)
            if (x, y) in mouth_by_cell:
                offset_x = offset_y = 0.0
            else:
                offset_x = (((x * 17 + y * 11 + seed) % 9) - 4) * 1.25
                offset_y = (((x * 7 + y * 19 + seed) % 9) - 4) * 1.10
            points.append(
                (
                    (world_x + 0.5 - crop_x) * tile_px + offset_x,
                    (y + 0.5 - crop_y) * tile_px + offset_y,
                )
            )
        route = v77._meander_route(v77._catmull_rom(points), seed=seed)
        local_routes.append(route)

    scale = 4

    def network_mask(width: int, blur: float) -> Image.Image:
        mask_hi = Image.new("L", (image.width * scale, image.height * scale), 0)
        draw = ImageDraw.Draw(mask_hi)
        joint_radius = width * scale * 0.5
        for route in local_routes:
            scaled = [
                (int(round(x * scale)), int(round(y * scale)))
                for x, y in route
            ]
            if len(scaled) >= 2:
                draw.line(scaled, fill=255, width=width * scale, joint="curve")
            for x, y in scaled[1:-1]:
                draw.ellipse(
                    (x - joint_radius, y - joint_radius, x + joint_radius, y + joint_radius),
                    fill=255,
                )
        # Every mouth keeps an exact full-width neck to the authored split.
        for cell, mouth in mouth_by_cell.items():
            x, y = cell
            world_x = _cell_x_near_window(x, crop_x, crop_w, world_width)
            cx = (world_x + 0.5 - crop_x) * tile_px * scale
            cy = (y + 0.5 - crop_y) * tile_px * scale
            dx, dy = v77.EXIT_VECTOR[mouth["exit_port"]]
            ex = cx + dx * v77.DELTA_NECK_OVERLAP_PX * scale
            ey = cy + dy * v77.DELTA_NECK_OVERLAP_PX * scale
            draw.line((cx, cy, ex, ey), fill=255, width=width * scale)
        mask = mask_hi.resize(image.size, Image.Resampling.LANCZOS)
        return mask.filter(ImageFilter.GaussianBlur(blur)) if blur else mask

    bank_rgb = np.asarray(palette[0][:3], dtype=np.float32)
    core_rgb = np.asarray(palette[2][:3], dtype=np.float32)
    highlight_rgb = np.asarray(palette[3][:3], dtype=np.float32)
    river_base = ocean_texture * 0.30 + core_rgb * 0.50 + highlight_rgb * 0.20
    river_glaze = ocean_texture * 0.16 + core_rgb * 0.34 + highlight_rgb * 0.50
    layers = (
        (sand_texture * 0.84 + bank_rgb * 0.16, network_mask(28, 0.38), 1.0),
        (sand_texture * 0.58 + bank_rgb * 0.42, network_mask(24, 0.30), 1.0),
        (river_base, network_mask(20, 0.22), 1.0),
        (river_glaze, network_mask(15, 0.30), 0.56),
    )
    for texture, mask, strength in layers:
        destination = np.asarray(image, dtype=np.float32)
        alpha = np.asarray(mask, dtype=np.float32)[..., None] / 255.0 * strength
        mixed = destination * (1.0 - alpha) + np.clip(texture, 0.0, 255.0) * alpha
        image.paste(Image.fromarray(np.uint8(np.clip(np.round(mixed), 0, 255)), "RGB"))
    return trails


def _render_window_core_v79(
    logical_grid: np.ndarray,
    metadata: dict,
    *,
    seed: int,
    window: Window,
    tile_px: int = 96,
    water_code: int = 10,
    mouth_cells: Iterable[tuple[int, int]] | None = None,
    master_path: Path = v77.MASTER_PATH,
    material_root: Path = v77.MATERIAL_ROOT,
    material_edge_feather_px: int = 0,
) -> UnifiedWindowV79:
    """Render one internal window using the exact V77 visual stack.

    Horizontal world wrap is supported. If ``mouth_cells`` is omitted, every
    river system intersecting the window plus a two-cell art halo is painted.
    """

    logical = np.asarray(logical_grid, dtype=np.int16)
    if logical.ndim != 2:
        raise ValueError("logical_grid must be a 2D terrain array")
    world_height, world_width = logical.shape
    crop_x, crop_y, crop_w, crop_h = (int(value) for value in window)
    tile_px = int(tile_px)
    material_edge_feather_px = int(material_edge_feather_px)
    if crop_w <= 0 or crop_h <= 0 or tile_px <= 0:
        raise ValueError("window and tile size must be positive")
    if material_edge_feather_px < 0:
        raise ValueError("material_edge_feather_px must be non-negative")
    if crop_y < 0 or crop_y + crop_h > world_height:
        raise ValueError("vertical window must stay inside the Civ world")

    pixel_window = PixelWindow(
        crop_x * tile_px,
        crop_y * tile_px,
        crop_w * tile_px,
        crop_h * tile_px,
    )
    coast = TangentGlobalCoast(
        CoastV31Config(tile_px=tile_px, contour_seed=int(seed))
    ).build(logical != int(water_code), window=pixel_window)

    master = Image.open(master_path).convert("RGB")
    art = v77._fit_selected_delta_vertical(
        master.resize((3 * tile_px, 2 * tile_px), Image.Resampling.LANCZOS),
        tile_px,
    )
    alpha = v77._limit_delta_offshore(
        v77._delta_semantic_alpha(art),
        tile_px,
        v77.DELTA_MAX_SEA_FRACTION,
    )
    palette = v77._master_palette(art)
    world_period = world_width * tile_px

    def sample_material(filename: str) -> np.ndarray:
        sampler = _cached_material_sampler(
            str((material_root / filename).resolve()),
            world_period,
            material_edge_feather_px,
        )
        sampled = sampler.sample(
            pixel_window.x,
            pixel_window.y,
            pixel_window.width,
            pixel_window.height,
        )
        return np.asarray(sampled, dtype=np.float32)[..., :3]

    grass = sample_material("grass_lush_01.png")
    ocean = sample_material("ocean_deep_01.png")
    sand = sample_material("coast_sand_01.png")
    authored_bank = np.asarray(palette[0][:3], dtype=np.float32)
    coast_sand = sand * 0.52 + authored_bank * 0.48
    material_samples = {
        0: sample_material("desert_sand_01.png"),
        1: sample_material("plains_dry_01.png"),
        2: grass,
        6: sample_material("tundra_scrub_01.png"),
        7: sample_material("arctic_snow_01.png"),
        8: sample_material("wetland_mud_01.png"),
    }

    visible_x = np.mod(np.arange(crop_x, crop_x + crop_w), world_width)
    visible_grid = logical[crop_y : crop_y + crop_h][:, visible_x]
    context = TransitionContext(
        material_grid=visible_grid,
        tile_px=tile_px,
        transition_px=14,
        world_x0=crop_x,
        world_y0=crop_y,
        world_width=world_width,
        seed=int(seed),
    )
    weights = make_weight_renderer_v51(logical)(context)
    land_material = np.zeros_like(grass, dtype=np.float32)
    for code, weight in weights.items():
        land_material += material_samples.get(int(code), grass) * weight[..., None]

    coverage = coast.land_coverage[..., None]
    image = ocean * (1.0 - coverage) + land_material * coverage
    turquoise = np.array((13.0, 139.0, 159.0), np.float32)
    shallow_material = ocean * 0.30 + turquoise * 0.70
    shallow = coast.shallow[..., None] * (1.0 - coverage)
    image = image * (1.0 - shallow) + shallow_material * shallow
    beach = coast.beach[..., None]
    image = image * (1.0 - beach) + coast_sand * beach
    foam = coast.foam[..., None] * 0.68
    image = image * (1.0 - foam) + np.array(
        (226.0, 238.0, 218.0), np.float32
    ) * foam
    base_ground = Image.fromarray(np.uint8(np.clip(image, 0, 255)), "RGB")

    landscape = base_ground.convert("RGBA")
    mountain_grid = logical.copy()
    mountain_grid[mountain_grid == 4] = 2
    relief_records = render_relief_component_art_v44(
        landscape,
        mountain_grid,
        seed=int(seed),
        window=(crop_x, crop_y, crop_w, crop_h),
        tile_px=tile_px,
        world_width=world_width,
    )
    hill_report = render_hill_nesw_v2(
        landscape,
        logical,
        window=(crop_x, crop_y, crop_w, crop_h),
        tile_px=tile_px,
        world_width=world_width,
        seed=int(seed),
        shoulder_opacity=0.58,
    )
    forest_report = render_forest_regions_v4(
        landscape,
        logical,
        seed=int(seed),
        window=(crop_x, crop_y, crop_w, crop_h),
        tile_px=tile_px,
        world_width=world_width,
    )
    base = landscape.convert("RGB")
    beauty = base.copy()

    selected_mouths = _select_mouths(
        metadata,
        (crop_x, crop_y, crop_w, crop_h),
        world_width,
        mouth_cells,
    )
    painted_systems: list[dict] = []
    # Terminals are independent decorations on the single global coast.
    for mouth in selected_mouths:
        delta, delta_anchor = v77._oriented_delta(
            art, alpha, mouth["exit_port"], tile_px
        )
        mouth_x = _cell_x_near_window(
            int(mouth["river_cell"][0]), crop_x, crop_w, world_width
        )
        mouth_centre = (
            (mouth_x + 0.5 - crop_x) * tile_px,
            (int(mouth["river_cell"][1]) + 0.5 - crop_y) * tile_px,
        )
        left = int(round(mouth_centre[0] - delta_anchor[0]))
        top = int(round(mouth_centre[1] - delta_anchor[1]))
        beauty.paste(delta.convert("RGB"), (left, top), delta.getchannel("A"))

    # Paint every merged river graph once. Independent systems retain the
    # pixel-locked V77 painter; only overlapping generator systems use the
    # unique-edge network painter.
    for group in _overlap_groups(selected_mouths):
        if len(group) == 1:
            mouth = group[0]
            route_cells = v77._paint_system_river(
                beauty,
                mouth,
                crop_x,
                crop_y,
                palette,
                sand,
                ocean,
                tile_px=tile_px,
                seed=int(seed),
                world_width=world_width,
                crop_width=crop_w,
            )
            painted_systems.append(
                {
                    "river_cells": [list(mouth["river_cell"])],
                    "exit_ports": [mouth["exit_port"]],
                    "route_cells": [list(cell) for cell in route_cells],
                    "painter": "locked-v77-single",
                }
            )
        else:
            trails = _paint_overlapping_network(
                beauty,
                group,
                seed=int(seed),
                window=(crop_x, crop_y, crop_w, crop_h),
                tile_px=tile_px,
                world_width=world_width,
                palette=palette,
                sand_texture=sand,
                ocean_texture=ocean,
            )
            painted_systems.append(
                {
                    "river_cells": [list(mouth["river_cell"]) for mouth in group],
                    "exit_ports": [mouth["exit_port"] for mouth in group],
                    "trails": [[list(cell) for cell in trail] for trail in trails],
                    "painter": "recorded-edge-network-v79",
                }
            )

    report = {
        "schema": (
            SEAMLESS_MATERIAL_SCHEMA
            if material_edge_feather_px
            else "project1991.unified-window/v79"
        ),
        "status": "ISOLATED",
        "seed": int(seed),
        "window": [crop_x, crop_y, crop_w, crop_h],
        "tile_px": tile_px,
        "world_size": [world_width, world_height],
        "mouth_count": len(selected_mouths),
        "river_component_count": len(painted_systems),
        "painted_systems": painted_systems,
        "coast": "TangentGlobalCoast CoastV31",
        "ground": "V51 shared corner lattice with world-periodic materials",
        "material_sampling": (
            SEAMLESS_MATERIAL_SAMPLING
            if material_edge_feather_px
            else "legacy-circular-linear"
        ),
        "material_edge_feather_px": material_edge_feather_px,
        "relief_records": list(relief_records),
        "hills_hard_contract_pass": bool(hill_report.hard_contract_pass),
        "forest": forest_report.as_dict(),
    }
    return UnifiedWindowV79(
        base=base,
        beauty=beauty,
        grid=v77._grid(beauty, tile_px),
        report=report,
    )


def render_window_v79(
    logical_grid: np.ndarray,
    metadata: dict,
    *,
    seed: int,
    window: Window,
    tile_px: int = 96,
    water_code: int = 10,
    mouth_cells: Iterable[tuple[int, int]] | None = None,
    master_path: Path = v77.MASTER_PATH,
    material_root: Path = v77.MATERIAL_ROOT,
    render_halo_cells: int = 2,
    material_edge_feather_px: int = 0,
) -> UnifiedWindowV79:
    """Render a crop-stable V77 world window with an internal art halo.

    ``material_edge_feather_px`` is opt-in. A positive value prepares each
    material source as a deterministic toroidal tile before world sampling;
    zero retains the original V79 output byte-for-byte.
    """

    logical = np.asarray(logical_grid, dtype=np.int16)
    if logical.ndim != 2:
        raise ValueError("logical_grid must be a 2D terrain array")
    world_height = logical.shape[0]
    crop_x, crop_y, crop_w, crop_h = (int(value) for value in window)
    halo = max(0, int(render_halo_cells))
    if halo == 0:
        return _render_window_core_v79(
            logical,
            metadata,
            seed=seed,
            window=(crop_x, crop_y, crop_w, crop_h),
            tile_px=tile_px,
            water_code=water_code,
            mouth_cells=mouth_cells,
            master_path=master_path,
            material_root=material_root,
            material_edge_feather_px=material_edge_feather_px,
        )

    expanded_y = max(0, crop_y - halo)
    expanded_bottom = min(world_height, crop_y + crop_h + halo)
    expanded = (
        crop_x - halo,
        expanded_y,
        crop_w + halo * 2,
        expanded_bottom - expanded_y,
    )
    rendered = _render_window_core_v79(
        logical,
        metadata,
        seed=seed,
        window=expanded,
        tile_px=tile_px,
        water_code=water_code,
        mouth_cells=mouth_cells,
        master_path=master_path,
        material_root=material_root,
        material_edge_feather_px=material_edge_feather_px,
    )
    offset_x = (crop_x - expanded[0]) * tile_px
    offset_y = (crop_y - expanded[1]) * tile_px
    box = (
        offset_x,
        offset_y,
        offset_x + crop_w * tile_px,
        offset_y + crop_h * tile_px,
    )
    report = dict(rendered.report)
    report.update(
        {
            "window": [crop_x, crop_y, crop_w, crop_h],
            "internal_render_window": list(expanded),
            "render_halo_cells": halo,
        }
    )
    beauty = rendered.beauty.crop(box)
    return UnifiedWindowV79(
        base=rendered.base.crop(box),
        beauty=beauty,
        grid=v77._grid(beauty, tile_px),
        report=report,
    )
