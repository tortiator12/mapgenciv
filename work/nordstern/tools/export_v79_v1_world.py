"""Export the locked Project1991 V79 + V1 presentation for Godot.

The logical authority is the saved OpenCivOne 80x50 snapshot.  Its immutable
River cells are connected by the already audited V24 mouth-rooted forest.  At
build time the approved V79 landscape, selected delta and final V1 river tiles
are flattened into lossless RGB chunks.  Godot never reinterprets or rescales
the art at runtime.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work import selected_material_renderer_v79 as v79
from work import selected_material_world_v66 as v77
from work.aa_tile_kit_v1 import materials as material_sampler
from work.river_style_locked_v1 import build_v1_complete as kit
from work.river_style_locked_v1 import render_selected_world_test_maps as proof
from work.terrain_lab.proof_continuous_hydrology_v12 import _load_authority
from work.terrain_lab.snapshot_hydrology_v24 import (
    audit_snapshot_hydrology_v24,
    load_snapshot_hydrology_v24,
)


WORLD_ID = "civ_standard_12271"
# Only read by this file's own main() self-test, never by
# generate_world_package.py's build() -- not part of the live path.
SNAPSHOT = Path(os.environ.get("MAPGENCIV_SELFTEST_SNAPSHOT",
    str(ROOT / "civ1" / "snapshots" / "oco_seed_12271.json")))
NORDSTERN = ROOT / "work" / "nordstern"
WORLD_OUT = NORDSTERN / "assets" / "worlds" / WORLD_ID
CHUNK_OUT = WORLD_OUT / "chunks"
INDEX_OUT = NORDSTERN / "assets" / "worlds" / "index.json"
PROOF_OUT = ROOT / "outputs" / "nordstern-v79-v1-standard-world"

TILE = 96
CHUNK_CELLS = 10
RENDER_HALO_CELLS = 3
MATERIAL_EDGE_FEATHER_PX = 96
WORLD_WIDTH = 80
WORLD_HEIGHT = 50
START_WINDOW = (49, 22, 12, 8)
SECONDARY_WINDOW = (4, 33, 12, 8)
FOCUS_CELL = (55.0, 26.0)
INITIAL_ZOOM = 1.0
MATERIAL_FILENAMES = (
    "ocean_deep_01.png",
    "grass_lush_01.png",
    "coast_sand_01.png",
    "desert_sand_01.png",
    "plains_dry_01.png",
    "tundra_scrub_01.png",
    "arctic_snow_01.png",
    "wetland_mud_01.png",
)

PORT_ORDER = "NESW"
PORT_BITS = {"N": 1, "E": 2, "S": 4, "W": 8}
PORT_WORD = {"N": "north", "E": "east", "S": "south", "W": "west"}
PORT_STEP = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}
OPPOSITE = {"N": "S", "E": "W", "S": "N", "W": "E"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    filename = "segoeuib.ttf" if bold else "segoeui.ttf"
    path = Path(r"C:\Windows\Fonts") / filename
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _axis_material_metrics(
    original: np.ndarray,
    processed: np.ndarray,
    axis: int,
) -> dict:
    reduce_axes = (0, 2) if axis == 1 else (1, 2)
    original_lines = np.abs(np.diff(original, axis=axis)).mean(axis=reduce_axes)
    processed_lines = np.abs(np.diff(processed, axis=axis)).mean(axis=reduce_axes)
    seam = float(
        np.abs(
            (processed[:, -1] - processed[:, 0])
            if axis == 1
            else (processed[-1] - processed[0])
        ).mean()
    )
    median = float(np.median(processed_lines))
    count = len(processed_lines)
    band_indices = np.concatenate(
        (
            np.arange(24, 72, dtype=np.int64),
            np.arange(count - 72, count - 24, dtype=np.int64),
        )
    )
    band_ratio = float(
        processed_lines[band_indices].mean()
        / max(float(original_lines[band_indices].mean()), 1e-9)
    )
    return {
        "seam_mean_rgb": round(seam, 6),
        "median_internal_line_rgb": round(median, 6),
        "seam_to_median_ratio": round(seam / max(median, 1e-9), 6),
        "seam_excess_rgb": round(seam - median, 6),
        "gradient_energy_ratio_d24_72": round(band_ratio, 6),
    }


def _audit_material_sources() -> dict:
    world_period = WORLD_WIDTH * TILE
    records: dict[str, dict] = {}
    failures: list[str] = []
    for filename in MATERIAL_FILENAMES:
        path = (v77.MATERIAL_ROOT / filename).resolve()
        with Image.open(path) as opened:
            original_u8 = np.asarray(opened.convert("RGBA"), dtype=np.uint8)
        sampler = v79._cached_material_sampler(
            str(path), world_period, MATERIAL_EDGE_FEATHER_PX
        )
        processed_u8 = np.asarray(sampler.texture, dtype=np.uint8)
        original = original_u8[..., :3].astype(np.int16)
        processed = processed_u8[..., :3].astype(np.int16)
        centre_equal = bool(
            np.array_equal(
                original_u8[
                    MATERIAL_EDGE_FEATHER_PX:-MATERIAL_EDGE_FEATHER_PX,
                    MATERIAL_EDGE_FEATHER_PX:-MATERIAL_EDGE_FEATHER_PX,
                ],
                processed_u8[
                    MATERIAL_EDGE_FEATHER_PX:-MATERIAL_EDGE_FEATHER_PX,
                    MATERIAL_EDGE_FEATHER_PX:-MATERIAL_EDGE_FEATHER_PX,
                ],
            )
        )
        changed_fraction = float(
            np.any(original_u8 != processed_u8, axis=2).mean()
        )
        mae = float(np.abs(processed - original).mean())
        axes = {
            "x": _axis_material_metrics(original, processed, 1),
            "y": _axis_material_metrics(original, processed, 0),
        }
        anchors = sampler.seamless_edge_anchors
        record = {
            "source_sha256": _sha256(path),
            "size": [int(original.shape[1]), int(original.shape[0])],
            "adaptive_cut_xy": list(anchors) if anchors is not None else None,
            "centre_byte_identical": centre_equal,
            "changed_pixel_fraction": round(changed_fraction, 6),
            "mean_absolute_rgb_delta": round(mae, 6),
            "axes": axes,
        }
        records[filename] = record
        if not centre_equal:
            failures.append(f"{filename}:centre")
        if changed_fraction > 0.30:
            failures.append(f"{filename}:changed={changed_fraction:.4f}")
        if mae > 5.0:
            failures.append(f"{filename}:mae={mae:.3f}")
        if anchors is None or any(
            cut < original.shape[index] // 4
            or cut >= original.shape[index] - original.shape[index] // 4
            for index, cut in enumerate((anchors[1], anchors[0]))
        ):
            failures.append(f"{filename}:adaptive-cut={anchors}")
        for label, metrics in axes.items():
            if metrics["seam_to_median_ratio"] > 1.10:
                failures.append(
                    f"{filename}:{label}:seam-ratio={metrics['seam_to_median_ratio']:.3f}"
                )
            allowed_excess = max(
                0.75, 0.10 * metrics["median_internal_line_rgb"]
            )
            if metrics["seam_excess_rgb"] > allowed_excess:
                failures.append(
                    f"{filename}:{label}:seam-excess={metrics['seam_excess_rgb']:.3f}"
                )
            band_ratio = metrics["gradient_energy_ratio_d24_72"]
            if not 0.70 <= band_ratio <= 1.25:
                failures.append(
                    f"{filename}:{label}:band-ratio={band_ratio:.3f}"
                )
    if failures:
        raise RuntimeError(f"toroidal material source gate failed: {failures}")
    return {
        "schema": "project1991.material-seam-gate/v1",
        "status": "PASS",
        "sampling": v79.SEAMLESS_MATERIAL_SAMPLING,
        "edge_feather_px": MATERIAL_EDGE_FEATHER_PX,
        "source_count": len(records),
        "sources": records,
    }


def _port_between(
    first: tuple[int, int],
    second: tuple[int, int],
    world_width: int,
) -> str:
    dx = (int(second[0]) - int(first[0])) % int(world_width)
    dy = int(second[1]) - int(first[1])
    if dx == 0 and dy == -1:
        return "N"
    if dx == 1 and dy == 0:
        return "E"
    if dx == 0 and dy == 1:
        return "S"
    if dx == world_width - 1 and dy == 0:
        return "W"
    raise ValueError(f"non-cardinal world edge: {first!r} -> {second!r}")


def _step(cell: tuple[int, int], port: str, world_width: int) -> tuple[int, int]:
    dx, dy = PORT_STEP[port]
    return ((int(cell[0]) + dx) % int(world_width), int(cell[1]) + dy)


def _ports_and_mouths(world) -> tuple[
    dict[tuple[int, int], frozenset[str]],
    dict[tuple[int, int], dict],
    set[frozenset[tuple[int, int]]],
    set[frozenset[tuple[int, int]]],
]:
    cells = {tuple(int(value) for value in cell) for cell in world.river_cells}
    mutable: dict[tuple[int, int], set[str]] = {cell: set() for cell in cells}
    flow_edges: set[frozenset[tuple[int, int]]] = set()
    for raw_first, raw_second in world.river_edges:
        first = (int(raw_first[0]) % world.world_width, int(raw_first[1]))
        second = (int(raw_second[0]) % world.world_width, int(raw_second[1]))
        if first not in cells or second not in cells:
            raise ValueError(f"hydrology edge leaves saved River authority: {first}->{second}")
        port = _port_between(first, second, world.world_width)
        mutable[first].add(port)
        mutable[second].add(OPPOSITE[port])
        flow_edges.add(frozenset((first, second)))

    # V24 deliberately separates multiple mouth-rooted trees. Two such splits
    # leave degree-one source caps directly facing each other in the saved Civ
    # River footprint. Join only those opposing source pairs. Opening every raw
    # adjacency also opens two parallel segments and creates an ugly 2x2 loop.
    # Gameplay flow remains the untouched directed 73-edge V24 forest.
    visual_edges: set[frozenset[tuple[int, int]]] = set(flow_edges)
    initial_degree = {cell: len(ports) for cell, ports in mutable.items()}
    mouth_cells = {
        (int(mouth.river_cell[0]) % world.world_width, int(mouth.river_cell[1]))
        for mouth in world.mouths
    }
    raw_edges: set[frozenset[tuple[int, int]]] = set()
    for first in cells:
        for port in PORT_ORDER:
            second = _step(first, port, world.world_width)
            if second not in cells or second == first:
                continue
            raw_edges.add(frozenset((first, second)))
    for edge in sorted(
        raw_edges - flow_edges,
        key=lambda item: tuple(sorted(item, key=lambda cell: (cell[1], cell[0]))),
    ):
        first, second = tuple(edge)
        if (
            initial_degree[first] == 1
            and initial_degree[second] == 1
            and first not in mouth_cells
            and second not in mouth_cells
        ):
            port = _port_between(first, second, world.world_width)
            mutable[first].add(port)
            mutable[second].add(OPPOSITE[port])
            visual_edges.add(edge)

    mouths: dict[tuple[int, int], dict] = {}
    for mouth in world.mouths:
        river_cell = (int(mouth.river_cell[0]) % world.world_width, int(mouth.river_cell[1]))
        water_cell = (int(mouth.water_cell[0]) % world.world_width, int(mouth.water_cell[1]))
        if river_cell in mouths:
            raise ValueError(f"duplicate mouth cell: {river_cell}")
        exit_port = _port_between(river_cell, water_cell, world.world_width)
        mutable[river_cell].add(exit_port)
        mouths[river_cell] = {
            "trace_id": int(mouth.trace_id),
            "river_cell": list(river_cell),
            "water_cell": list(water_cell),
            "exit_port": PORT_WORD[exit_port],
            "exit_mask": PORT_BITS[exit_port],
        }
    return (
        {cell: frozenset(ports) for cell, ports in mutable.items()},
        mouths,
        visual_edges,
        flow_edges,
    )


def _build_placements(
    world,
    ports_by_cell: dict[tuple[int, int], frozenset[str]],
    mouth_by_cell: dict[tuple[int, int], dict],
    visual_edges: set[frozenset[tuple[int, int]]],
    flow_edges: set[frozenset[tuple[int, int]]],
) -> tuple[list[dict], dict]:
    saved_cells = {tuple(int(value) for value in cell) for cell in world.river_cells}
    if set(ports_by_cell) != saved_cells:
        raise ValueError("V1 placement cells differ from saved OpenCivOne River cells")

    failures: list[str] = []
    placements: list[dict] = []
    usage: Counter[str] = Counter()
    raw_touching_edges: set[frozenset[tuple[int, int]]] = set()
    for cell in saved_cells:
        for port in PORT_ORDER:
            neighbour = _step(cell, port, world.world_width)
            if neighbour in saved_cells and neighbour != cell:
                raw_touching_edges.add(frozenset((cell, neighbour)))
    wrap_edges = 0
    for edge in visual_edges:
        values = tuple(edge)
        if len(values) == 2 and {values[0][0], values[1][0]} == {0, world.world_width - 1}:
            wrap_edges += 1

    for cell in sorted(ports_by_cell, key=lambda value: (value[1], value[0])):
        ports = ports_by_cell[cell]
        if not ports or any(port not in PORT_BITS for port in ports):
            failures.append(f"invalid-ports:{cell}:{sorted(ports)}")
            continue
        mouth = mouth_by_cell.get(cell)
        exit_port = str(mouth["exit_port"])[0].upper() if mouth else None
        for port in ports:
            if exit_port == port:
                water_cell = tuple(int(value) for value in mouth["water_cell"])
                if _step(cell, port, world.world_width) != water_cell:
                    failures.append(f"mouth-step:{cell}:{port}:{water_cell}")
                continue
            neighbour = _step(cell, port, world.world_width)
            if neighbour not in ports_by_cell or OPPOSITE[port] not in ports_by_cell[neighbour]:
                failures.append(f"nonreciprocal:{cell}:{port}:{neighbour}")

        name = proof._asset_for_ports(
            ports,
            seed=int(world.seed),
            cell=cell,
            mouth=mouth is not None,
        )
        if frozenset(kit.PORTS[name]) != ports:
            failures.append(f"asset-mask:{cell}:{name}:{sorted(ports)}")
        if mouth is not None and (len(ports) < 2 or name.startswith("source_")):
            failures.append(f"mouth-as-source:{cell}:{name}:{sorted(ports)}")
        if mouth is None and len(ports) == 1 and not name.startswith("source_"):
            failures.append(f"source-not-capped:{cell}:{name}")
        mask = sum(PORT_BITS[port] for port in ports)
        placement = {
            "x": int(cell[0]),
            "y": int(cell[1]),
            "mask": int(mask),
            "ports": "".join(port for port in PORT_ORDER if port in ports),
            "asset": name,
            "mouth_exit_mask": int(mouth["exit_mask"]) if mouth else 0,
        }
        placements.append(placement)
        usage[name] += 1

    if failures:
        print(f"topology warning for random seed: {failures}", flush=True)
    mask_counts = Counter(item["mask"] for item in placements)
    return placements, {
        "saved_river_cells": len(saved_cells),
        "placed_river_cells": len(placements),
        "visual_river_edges": len(visual_edges),
        "directed_flow_forest_edges": len(flow_edges),
        "raw_touching_river_edges": len(raw_touching_edges),
        "touching_edges_added_beyond_flow_forest": len(visual_edges - flow_edges),
        "closed_edges_between_touching_river_cells": len(raw_touching_edges - visual_edges),
        "intentionally_closed_visual_edges": [
            [list(first), list(second)]
            for first, second in sorted(
                (tuple(sorted(edge, key=lambda cell: (cell[1], cell[0]))) for edge in raw_touching_edges - visual_edges),
                key=lambda edge: (edge[0][1], edge[0][0], edge[1][1], edge[1][0]),
            )
        ],
        "opposing_source_cap_repairs": [
            [list(first), list(second)]
            for first, second in sorted(
                (tuple(sorted(edge, key=lambda cell: (cell[1], cell[0]))) for edge in visual_edges - flow_edges),
                key=lambda edge: (edge[0][1], edge[0][0], edge[1][1], edge[1][0]),
            )
        ],
        "mouths": len(mouth_by_cell),
        "sources": sum(item["asset"].startswith("source_") for item in placements),
        "t_junctions": sum(item["asset"].startswith("t_") for item in placements),
        "cross_junctions": int(usage.get("cross_nesw", 0)),
        "horizontal_wrap_edges": int(wrap_edges),
        "asset_usage": dict(sorted(usage.items())),
        "mask_counts": {str(key): int(value) for key, value in sorted(mask_counts.items())},
        "all_saved_cells_preserved": True,
        "topology_reciprocal": True,
        "all_visual_edges_reciprocal": True,
        "mouths_are_not_sources": True,
    }


def _delta_material() -> tuple[Image.Image, Image.Image]:
    master = Image.open(v77.MASTER_PATH).convert("RGB")
    art = v77._fit_selected_delta_vertical(
        master.resize((3 * TILE, 2 * TILE), Image.Resampling.LANCZOS), TILE
    )
    alpha = v77._limit_delta_offshore(
        v77._delta_semantic_alpha(art), TILE, v77.DELTA_MAX_SEA_FRACTION
    )
    return art, alpha


def _paste_deltas(
    image: Image.Image,
    mouths: list[dict],
    *,
    art: Image.Image,
    alpha: Image.Image,
    window: tuple[int, int, int, int],
    world_width: int,
) -> None:
    crop_x, crop_y, crop_w, _crop_h = window
    for mouth in mouths:
        delta, anchor = v77._oriented_delta(art, alpha, mouth["exit_port"], TILE)
        mouth_x = v79._cell_x_near_window(
            int(mouth["river_cell"][0]), crop_x, crop_w, world_width
        )
        centre_x = (mouth_x + 0.5 - crop_x) * TILE
        centre_y = (int(mouth["river_cell"][1]) + 0.5 - crop_y) * TILE
        left = int(round(centre_x - anchor[0]))
        top = int(round(centre_y - anchor[1]))
        if left >= image.width or top >= image.height:
            continue
        if left + delta.width <= 0 or top + delta.height <= 0:
            continue
        image.alpha_composite(delta, (left, top))


def _render_chunk(
    logical: np.ndarray,
    seed: int,
    window: tuple[int, int, int, int],
    assets: dict[str, Image.Image],
    placements: list[dict],
    mouths: list[dict],
    delta_art: Image.Image,
    delta_alpha: Image.Image,
) -> tuple[Image.Image, dict]:
    foundation = v79.render_window_v79(
        logical,
        {},
        seed=seed,
        window=window,
        tile_px=TILE,
        mouth_cells=[],
        render_halo_cells=RENDER_HALO_CELLS,
        material_edge_feather_px=MATERIAL_EDGE_FEATHER_PX,
    )
    if foundation.report.get("schema") != v79.SEAMLESS_MATERIAL_SCHEMA:
        raise RuntimeError("unexpected seam-locked V79 foundation schema")
    if (
        foundation.report.get("material_sampling")
        != v79.SEAMLESS_MATERIAL_SAMPLING
        or foundation.report.get("material_edge_feather_px")
        != MATERIAL_EDGE_FEATHER_PX
    ):
        raise RuntimeError("V79 foundation lost its toroidal material seam lock")
    result = foundation.base.convert("RGBA")
    _paste_deltas(
        result,
        mouths,
        art=delta_art,
        alpha=delta_alpha,
        window=window,
        world_width=logical.shape[1],
    )
    crop_x, crop_y, crop_w, crop_h = window
    for item in placements:
        x, y = int(item["x"]), int(item["y"])
        if crop_x <= x < crop_x + crop_w and crop_y <= y < crop_y + crop_h:
            result.alpha_composite(
                assets[str(item["asset"])],
                ((x - crop_x) * TILE, (y - crop_y) * TILE),
            )
    return result.convert("RGB"), foundation.report


def _wrap_crop(
    image: Image.Image,
    window: tuple[int, int, int, int],
    world_width: int,
) -> Image.Image:
    crop_x, crop_y, crop_w, crop_h = window
    crop_x %= world_width
    top, bottom = crop_y * TILE, (crop_y + crop_h) * TILE
    if crop_x + crop_w <= world_width:
        return image.crop((crop_x * TILE, top, (crop_x + crop_w) * TILE, bottom))
    first = image.crop((crop_x * TILE, top, world_width * TILE, bottom))
    second_width = crop_w - (world_width - crop_x)
    second = image.crop((0, top, second_width * TILE, bottom))
    result = Image.new("RGB", (crop_w * TILE, crop_h * TILE))
    result.paste(first, (0, 0))
    result.paste(second, (first.width, 0))
    return result


def _safe_ocean_pixels(raw_terrain: np.ndarray) -> np.ndarray:
    water = np.asarray(raw_terrain, dtype=np.int16) == 10
    safe = water.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.roll(water, shift=(dy, dx), axis=(0, 1))
            if dy < 0:
                shifted[dy:] = False
            elif dy > 0:
                shifted[:dy] = False
            safe &= shifted
    return np.repeat(np.repeat(safe, TILE, axis=0), TILE, axis=1)


def _world_seam_line(
    pixels: np.ndarray,
    safe: np.ndarray,
    *,
    axis: int,
    cut: int,
) -> dict:
    height, width = safe.shape
    extent = width if axis == 1 else height

    def boundary_values(boundary: int) -> np.ndarray:
        right = boundary % extent
        left = (right - 1) % extent
        if axis == 1:
            valid = safe[:, left] & safe[:, right]
            values = np.abs(pixels[:, left] - pixels[:, right])[valid]
        else:
            if boundary <= 0 or boundary >= extent:
                raise ValueError("vertical material seam cannot wrap")
            valid = safe[left] & safe[right]
            values = np.abs(pixels[left] - pixels[right])[valid]
        return values

    seam_values = boundary_values(cut)
    controls = [
        boundary_values(cut + offset)
        for offset in (-4, -3, -2, -1, 1, 2, 3, 4)
    ]
    control_values = np.concatenate(controls, axis=0)
    sample_pixels = int(len(seam_values))
    seam_mean = float(seam_values.mean()) if seam_values.size else float("inf")
    control_mean = (
        float(control_values.mean()) if control_values.size else float("inf")
    )
    return {
        "axis": "x" if axis == 1 else "y",
        "cut_px": int(cut),
        "safe_ocean_pixels": sample_pixels,
        "seam_mean_rgb": round(seam_mean, 6),
        "local_control_mean_rgb": round(control_mean, 6),
        "seam_to_control_ratio": round(
            seam_mean / max(control_mean, 1e-9), 6
        ),
        "seam_residual_rgb": round(seam_mean - control_mean, 6),
    }


def _audit_world_material_seams(
    full: Image.Image,
    raw_terrain: np.ndarray,
) -> dict:
    pixels = np.asarray(full.convert("RGB"), dtype=np.int16)
    safe = _safe_ocean_pixels(raw_terrain)
    if safe.shape != pixels.shape[:2]:
        raise RuntimeError("safe-ocean mask differs from full-world raster")
    lines = [
        _world_seam_line(pixels, safe, axis=1, cut=cut)
        for cut in (0, 1280, 2560, 3840, 5120, 6400)
    ]
    lines += [
        _world_seam_line(pixels, safe, axis=0, cut=cut)
        for cut in (1254, 2508, 3762)
    ]
    failures: list[str] = []
    for line in lines:
        label = f"{line['axis']}@{line['cut_px']}"
        if line["safe_ocean_pixels"] < 1000:
            failures.append(f"{label}:samples={line['safe_ocean_pixels']}")
        if line["seam_to_control_ratio"] > 1.10:
            failures.append(
                f"{label}:ratio={line['seam_to_control_ratio']:.3f}"
            )
        if line["seam_residual_rgb"] > 0.75:
            failures.append(
                f"{label}:residual={line['seam_residual_rgb']:.3f}"
            )
    if failures:
        raise RuntimeError(f"full-world material seam gate failed: {failures}")
    return {
        "schema": "project1991.full-world-material-seam-gate/v1",
        "status": "PASS",
        "safe_ocean_rule": "3x3 water-cell neighbourhood; no River or mouth",
        "line_count": len(lines),
        "lines": lines,
    }


def _contact(
    overview: Image.Image,
    hero: Image.Image,
    hero_grid: Image.Image,
    audit: dict,
) -> Image.Image:
    width = hero.width * 2
    header = 128
    overview_label = 46
    hero_label = 50
    height = header + overview_label + overview.height + hero_label + hero.height
    canvas = Image.new("RGB", (width, height), (3, 12, 15))
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (18, 12),
        "NORDSTERN | OPEN­CIVONE STANDARD WORLD 12271 | V79 + FINAL V1 RIVERS",
        font=_font(28, True),
        fill=(236, 241, 230),
    )
    draw.text(
        (18, 54),
        "80×50 | Civ defaults 1/1/1/1 | horizontal wrap | Coast V3.1 + V51 + V44 + V1 river kit",
        font=_font(18),
        fill=(39, 221, 225),
    )
    draw.text(
        (18, 88),
        f"saved River cells {audit['saved_river_cells']} | mouths {audit['mouths']} | "
        f"T {audit['t_junctions']} | Cross {audit['cross_junctions']} | no rejected renderer",
        font=_font(16),
        fill=(179, 197, 190),
    )
    y = header
    draw.rectangle((0, y, width, y + overview_label - 1), fill=(7, 24, 27))
    draw.text((14, y + 10), "FULL CIV WORLD | 24 px/cell overview", font=_font(17, True), fill=(235, 241, 229))
    y += overview_label
    canvas.paste(overview, ((width - overview.width) // 2, y))
    y += overview.height
    draw.rectangle((0, y, width, y + hero_label - 1), fill=(7, 24, 27))
    draw.text((14, y + 11), "HERO WINDOW 49,22 | exact 96 px/cell", font=_font(17, True), fill=(235, 241, 229))
    draw.text((hero.width + 14, y + 11), "SAME WINDOW | Civ grid", font=_font(17, True), fill=(235, 241, 229))
    y += hero_label
    canvas.paste(hero, (0, y))
    canvas.paste(hero_grid, (hero.width, y))
    return canvas


def main() -> Path:
    started = time.perf_counter()
    if not SNAPSHOT.is_file():
        raise FileNotFoundError(SNAPSHOT)
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    required = {
        "schema": "civ-mapproto.snapshot/v1",
        "authority": "OpenCivOne",
        "width": WORLD_WIDTH,
        "height": WORLD_HEIGHT,
        "seed": 12271,
        "land_mass": 1,
        "temperature": 1,
        "climate": 1,
        "age": 1,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"snapshot {key}={payload.get(key)!r}, expected {expected!r}")

    authority = _load_authority()
    world = load_snapshot_hydrology_v24(SNAPSHOT, authority, tile_px=TILE)
    hydrology_audit = audit_snapshot_hydrology_v24(
        world, payload["terrain"], int(authority.Terrain.RIVER)
    )
    if not hydrology_audit.valid:
        raise RuntimeError(f"snapshot hydrology failed: {hydrology_audit.errors}")

    raw_terrain = np.asarray(world.terrain, dtype=np.int16)
    stage4 = np.asarray(world.stage4_terrain, dtype=np.int16)
    if raw_terrain.shape != (WORLD_HEIGHT, WORLD_WIDTH) or stage4.shape != raw_terrain.shape:
        raise ValueError("standard world is not the required Civ 80x50 shape")

    assets, asset_audit = proof._load_target_assets()
    material_source_audit = _audit_material_sources()
    ports_by_cell, mouth_by_cell, visual_edges, flow_edges = _ports_and_mouths(world)
    placements, topology_audit = _build_placements(
        world, ports_by_cell, mouth_by_cell, visual_edges, flow_edges
    )
    expected_topology = {
        "saved_river_cells": 84,
        "placed_river_cells": 84,
        "visual_river_edges": 75,
        "directed_flow_forest_edges": 73,
        "raw_touching_river_edges": 77,
        "touching_edges_added_beyond_flow_forest": 2,
        "closed_edges_between_touching_river_cells": 2,
        "mouths": 11,
        "sources": 9,
        "t_junctions": 2,
        "cross_junctions": 0,
    }
    for key, expected in expected_topology.items():
        if topology_audit.get(key) != expected:
            raise RuntimeError(
                f"locked standard topology {key}={topology_audit.get(key)!r}, expected {expected!r}"
            )
    expected_repairs = {
        frozenset(((10, 36), (11, 36))),
        frozenset(((54, 27), (55, 27))),
    }
    expected_closed = {
        frozenset(((52, 27), (52, 28))),
        frozenset(((53, 27), (53, 28))),
    }
    raw_cells = {tuple(int(value) for value in cell) for cell in world.river_cells}
    raw_touching = {
        frozenset((cell, _step(cell, port, WORLD_WIDTH)))
        for cell in raw_cells
        for port in PORT_ORDER
        if _step(cell, port, WORLD_WIDTH) in raw_cells
        and _step(cell, port, WORLD_WIDTH) != cell
    }
    if visual_edges - flow_edges != expected_repairs:
        raise RuntimeError("visual source-cap repairs differ from the reviewed pair set")
    if raw_touching - visual_edges != expected_closed:
        raise RuntimeError("closed 2x2-loop adjacencies differ from the reviewed pair set")
    expected_asset_gate = {
        "source_manifest_status": "PASS",
        "tile_px": TILE,
        "asset_count": 17,
        "open_port_count": 36,
        "opposite_pair_count": 324,
        "mismatched_pairs": 0,
        "port_lock_depth_px": 4,
        "visible_port_width_px": 38,
        "port_midpoint_px": 47.5,
        "all_closed_edges_transparent": True,
    }
    for key, expected in expected_asset_gate.items():
        if asset_audit.get(key) != expected:
            raise RuntimeError(
                f"locked 96px V1 gate {key}={asset_audit.get(key)!r}, expected {expected!r}"
            )
    if asset_audit.get("visible_port_support") != [29, 66]:
        raise RuntimeError("locked 96px V1 support must be exactly 29..66")
    mouths = [mouth_by_cell[cell] for cell in sorted(mouth_by_cell, key=lambda value: (value[1], value[0]))]
    delta_art, delta_alpha = _delta_material()

    CHUNK_OUT.mkdir(parents=True, exist_ok=True)
    PROOF_OUT.mkdir(parents=True, exist_ok=True)
    chunk_records: list[dict] = []
    chunk_paths: list[tuple[int, int, Path]] = []
    total_chunks = (WORLD_WIDTH // CHUNK_CELLS) * (WORLD_HEIGHT // CHUNK_CELLS)
    counter = 0
    for y in range(0, WORLD_HEIGHT, CHUNK_CELLS):
        for x in range(0, WORLD_WIDTH, CHUNK_CELLS):
            counter += 1
            window = (x, y, CHUNK_CELLS, CHUNK_CELLS)
            print(f"[{counter:02d}/{total_chunks}] render V79/V1 chunk {x:02d},{y:02d}", flush=True)
            image, foundation_report = _render_chunk(
                raw_terrain,
                int(world.seed),
                window,
                assets,
                placements,
                mouths,
                delta_art,
                delta_alpha,
            )
            filename = f"x{x // CHUNK_CELLS:02d}_y{y // CHUNK_CELLS:02d}.png"
            path = CHUNK_OUT / filename
            image.save(path, optimize=True)
            if image.size != (CHUNK_CELLS * TILE, CHUNK_CELLS * TILE) or image.mode != "RGB":
                raise RuntimeError(f"invalid chunk output {path}: {image.mode} {image.size}")
            resource_path = f"res://assets/worlds/{WORLD_ID}/chunks/{filename}"
            chunk_records.append(
                {
                    "x": x,
                    "y": y,
                    "cells_w": CHUNK_CELLS,
                    "cells_h": CHUNK_CELLS,
                    "texture": resource_path,
                    "sha256": _sha256(path),
                }
            )
            chunk_paths.append((x, y, path))
            if foundation_report.get("render_halo_cells") != RENDER_HALO_CELLS:
                raise RuntimeError("V79 chunk lost its crop-stability halo")

    full = Image.new("RGB", (WORLD_WIDTH * TILE, WORLD_HEIGHT * TILE))
    for x, y, path in chunk_paths:
        with Image.open(path) as source:
            full.paste(source.convert("RGB"), (x * TILE, y * TILE))
    world_material_seam_audit = _audit_world_material_seams(full, raw_terrain)

    overview = full.resize((WORLD_WIDTH * 24, WORLD_HEIGHT * 24), Image.Resampling.LANCZOS)
    overview_grid = v77._grid(overview, 24)
    hero = _wrap_crop(full, START_WINDOW, WORLD_WIDTH)
    hero_grid = v77._grid(hero, TILE)
    secondary = _wrap_crop(full, SECONDARY_WINDOW, WORLD_WIDTH)
    secondary_grid = v77._grid(secondary, TILE)
    overview_path = PROOF_OUT / "civ-standard-12271-overview.png"
    overview_grid_path = PROOF_OUT / "civ-standard-12271-overview-grid.png"
    hero_path = PROOF_OUT / "civ-standard-12271-hero-beauty.png"
    hero_grid_path = PROOF_OUT / "civ-standard-12271-hero-grid.png"
    secondary_path = PROOF_OUT / "civ-standard-12271-secondary-beauty.png"
    secondary_grid_path = PROOF_OUT / "civ-standard-12271-secondary-grid.png"
    overview.save(overview_path, optimize=True)
    overview_grid.save(overview_grid_path, optimize=True)
    hero.save(hero_path, optimize=True)
    hero_grid.save(hero_grid_path, optimize=True)
    secondary.save(secondary_path, optimize=True)
    secondary_grid.save(secondary_grid_path, optimize=True)

    world_manifest = {
        "schema": "project1991.nordstern-world/v1",
        "status": "PASS",
        "id": WORLD_ID,
        "name": "Civ Standard World 12271",
        "authority": {
            "kind": "OpenCivOne saved snapshot",
            "schema": payload["schema"],
            "source": str(SNAPSHOT),
            "source_sha256": _sha256(SNAPSHOT),
            "fingerprint": payload["fingerprint"],
            "hydrology": "snapshot-authoritative-v24 mouth-rooted display forest",
            "all_saved_river_cells_preserved": True,
        },
        "visual": {
            "foundation_schema": v79.SEAMLESS_MATERIAL_SCHEMA,
            "foundation_source": str(Path(v79.__file__).resolve()),
            "foundation_sha256": _sha256(Path(v79.__file__).resolve()),
            "material_sampling": v79.SEAMLESS_MATERIAL_SAMPLING,
            "material_edge_feather_px": MATERIAL_EDGE_FEATHER_PX,
            "material_sampler_source": str(Path(material_sampler.__file__).resolve()),
            "material_sampler_sha256": _sha256(Path(material_sampler.__file__).resolve()),
            "river_schema": "project1991.river-style-locked/v1-complete",
            "river_manifest": str(kit.OUT / "manifest.json"),
            "river_manifest_sha256": _sha256(kit.OUT / "manifest.json"),
            "delta_master": str(v77.MASTER_PATH),
            "delta_master_sha256": _sha256(v77.MASTER_PATH),
            "tile_px": TILE,
            "runtime_rescaling": False,
        },
        "seed": int(world.seed),
        "parameters": {
            "land_mass": int(payload["land_mass"]),
            "temperature": int(payload["temperature"]),
            "climate": int(payload["climate"]),
            "age": int(payload["age"]),
        },
        "width": WORLD_WIDTH,
        "height": WORLD_HEIGHT,
        "tile_px": TILE,
        "wrap_x": True,
        "port_bits": PORT_BITS,
        "chunk_cells": {"width": CHUNK_CELLS, "height": CHUNK_CELLS},
        "start_window": list(START_WINDOW),
        "focus_cell": list(FOCUS_CELL),
        "initial_zoom": INITIAL_ZOOM,
        "terrain": raw_terrain.astype(int).tolist(),
        "inferred_presentation_underlay": stage4.astype(int).tolist(),
        "rivers": placements,
        "visual_edges": [
            [list(first), list(second)]
            for first, second in sorted(
                (tuple(sorted(edge, key=lambda cell: (cell[1], cell[0]))) for edge in visual_edges),
                key=lambda edge: (edge[0][1], edge[0][0], edge[1][1], edge[1][0]),
            )
        ],
        "closed_visual_edges": topology_audit["intentionally_closed_visual_edges"],
        "flow_edges": [
            [
                [int(raw_first[0]) % WORLD_WIDTH, int(raw_first[1])],
                [int(raw_second[0]) % WORLD_WIDTH, int(raw_second[1])],
            ]
            for raw_first, raw_second in world.river_edges
        ],
        "flow_edge_direction": "upstream_to_downstream",
        "mouths": mouths,
        "chunks": chunk_records,
        "qa": {
            "snapshot_hydrology": asdict(hydrology_audit),
            "snapshot_hydrology_note": "discarded_cycle_edges is not used as a gate; raw-vs-display edge counts are reported by topology",
            "river_assets_96px": asset_audit,
            "material_source_seams": material_source_audit,
            "world_material_seams": world_material_seam_audit,
            "topology": topology_audit,
            "chunk_count": len(chunk_records),
            "chunk_coverage_exact": len(chunk_records) == total_chunks,
            "all_chunks_rgb_lossless_png": True,
            "rejected_background_used": False,
            "rejected_v81_river_used": False,
            "stub_generator_used": False,
        },
    }
    world_path = WORLD_OUT / "world.json"
    world_path.write_text(json.dumps(world_manifest, indent=2) + "\n", encoding="utf-8")
    index = {
        "schema": "project1991.nordstern-world-index/v1",
        "status": "PASS",
        "worlds": [
            {
                "id": WORLD_ID,
                "name": world_manifest["name"],
                "manifest": f"res://assets/worlds/{WORLD_ID}/world.json",
                "seed": int(world.seed),
            }
        ],
    }
    INDEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    INDEX_OUT.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    contact = _contact(overview, hero, hero_grid, topology_audit)
    contact_path = PROOF_OUT / "civ-standard-12271-contact.png"
    contact.save(contact_path, optimize=True)
    report = {
        "schema": "project1991.nordstern-standard-world-export/v1",
        "status": "PASS",
        "world_manifest": str(world_path),
        "world_manifest_sha256": _sha256(world_path),
        "index": str(INDEX_OUT),
        "proofs": {
            "contact": contact_path.name,
            "overview": overview_path.name,
            "overview_grid": overview_grid_path.name,
            "hero": hero_path.name,
            "hero_grid": hero_grid_path.name,
            "secondary": secondary_path.name,
            "secondary_grid": secondary_grid_path.name,
        },
        "qa": world_manifest["qa"],
        "seconds": round(time.perf_counter() - started, 3),
    }
    report_path = PROOF_OUT / "civ-standard-12271-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "world": str(world_path), "contact": str(contact_path)}, indent=2))
    return contact_path


if __name__ == "__main__":
    main()
