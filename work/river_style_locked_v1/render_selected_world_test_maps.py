"""Render the final V1 river tiles on the approved Project1991 V77/V79 world.

This proof deliberately uses ``selected_material_renderer_v79`` only for the
visually approved ground/coast/relief/forest foundation.  The rejected
``render.splatmap`` background and the rejected V81 river art are never used.
Logical paths still come from the production map-generator metadata.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from work import selected_material_renderer_v79 as v79
from work import selected_material_world_v66 as v77
from work.river_style_locked_v1 import build_v1_complete as kit


OUTPUT = ROOT / "outputs" / "river-style-locked-v1-selected-world-tests"
TILE = 96
PORT_LOCK_DEPTH = 4

CASES = (
    {
        "slug": "seed-25378-approved-south",
        "title": "Seed 25378 | approved V77/V79 south-coast world",
        "seed": 25378,
        "window": (9, 6, 12, 8),
        "mouth_cells": ((15, 11),),
    },
    {
        "slug": "seed-1991-two-mouths",
        "title": "Seed 1991 | approved V79 two-mouth world",
        "seed": 1991,
        "window": (61, 11, 12, 7),
        "mouth_cells": ((64, 14), (69, 14)),
    },
    {
        "slug": "seed-14327-xwrap",
        "title": "Seed 14327 | approved V79 horizontal-wrap world",
        "seed": 14327,
        "window": (74, 10, 12, 7),
        "mouth_cells": ((0, 13),),
    },
    {
        "slug": "seed-1115-cross-two-mouths",
        "title": "Seed 1115 | V79 cross junction with west/east mouths",
        "seed": 1115,
        "window": (58, 28, 12, 8),
        "mouth_cells": ((60, 33), (66, 32)),
    },
    {
        "slug": "seed-18-t-junction-two-mouths",
        "title": "Seed 18 | V79 T junction with north/east mouths",
        "seed": 18,
        "window": (30, 8, 12, 8),
        "mouth_cells": ((37, 12), (33, 10)),
    },
)

PORT_ORDER = "NESW"
OPPOSITE = {"N": "S", "E": "W", "S": "N", "W": "E"}
PORT_STEP = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    path = Path(r"C:\Windows\Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def _symmetric_port_strip(strip: np.ndarray) -> np.ndarray:
    rgba = strip.astype(np.float64)
    alpha = rgba[..., 3:4] / 255.0
    premul = rgba[..., :3] * alpha
    pair_alpha = (alpha + alpha[:, ::-1]) * 0.5
    pair_premul = (premul + premul[:, ::-1]) * 0.5
    rgb = np.divide(
        pair_premul,
        pair_alpha,
        out=np.zeros_like(pair_premul),
        where=pair_alpha > 0,
    )
    result = np.concatenate((rgb, pair_alpha * 255.0), axis=2)
    result = np.uint8(np.clip(np.rint(result), 0, 255))
    half = result.shape[1] // 2
    result[:, half:] = result[:, :half][:, ::-1]
    result[result[..., 3] == 0, :3] = 0
    return result


def _lock_ports(image: Image.Image, ports: str, strip: np.ndarray) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    depth = int(strip.shape[0])
    if "N" in ports:
        rgba[:depth] = strip
    else:
        rgba[0] = 0
    if "S" in ports:
        rgba[-depth:] = strip[::-1]
    else:
        rgba[-1] = 0
    if "W" in ports:
        rgba[:, :depth] = np.transpose(strip, (1, 0, 2))
    else:
        rgba[:, 0] = 0
    if "E" in ports:
        rgba[:, -depth:] = np.transpose(strip, (1, 0, 2))[:, ::-1]
    else:
        rgba[:, -1] = 0
    rgba[rgba[..., 3] == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def _read_inward_strip(rgba: np.ndarray, port: str) -> np.ndarray:
    depth = PORT_LOCK_DEPTH
    if port == "N":
        return rgba[:depth]
    if port == "S":
        return rgba[-1:-depth - 1:-1]
    if port == "W":
        return np.transpose(rgba[:, :depth], (1, 0, 2))
    return np.transpose(rgba[:, -1:-depth - 1:-1], (1, 0, 2))


def _load_target_assets() -> tuple[dict[str, Image.Image], dict[str, object]]:
    manifest_path = kit.OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS" or not manifest.get("qa", {}).get("passed"):
        raise RuntimeError("final V1 river asset manifest is not PASS")
    source = {
        name: Image.open(kit.OUT / f"{name}.png").convert("RGBA")
        for name in kit.EXPECTED
    }

    def resize(name: str) -> Image.Image:
        return kit._resize_premultiplied(source[name], (TILE, TILE))

    canonical_ns = resize("straight_ns")
    strip = _symmetric_port_strip(
        np.asarray(canonical_ns, dtype=np.uint8)[:PORT_LOCK_DEPTH].copy()
    )
    if not np.array_equal(strip, strip[:, ::-1]):
        raise RuntimeError("96 px canonical port strip is not symmetric")

    straight_ns = _lock_ports(canonical_ns, "NS", strip)
    s_curve_ns = _lock_ports(resize("s_curve_ns"), "NS", strip)
    curve_se = _lock_ports(resize("curve_se"), "SE", strip)
    t_esw = _lock_ports(resize("t_esw"), "ESW", strip)
    cross = _lock_ports(resize("cross_nesw"), "NESW", strip)
    source_s = _lock_ports(resize("source_s"), "S", strip)
    assets = {
        "straight_ns": straight_ns,
        "straight_ew": straight_ns.transpose(Image.Transpose.ROTATE_90),
        "s_curve_ns": s_curve_ns,
        "s_curve_ew": s_curve_ns.transpose(Image.Transpose.ROTATE_90),
        "curve_se": curve_se,
        "curve_ne": curve_se.transpose(Image.Transpose.ROTATE_90),
        "curve_nw": curve_se.transpose(Image.Transpose.ROTATE_180),
        "curve_sw": curve_se.transpose(Image.Transpose.ROTATE_270),
        "t_esw": t_esw,
        "t_nes": t_esw.transpose(Image.Transpose.ROTATE_90),
        "t_new": t_esw.transpose(Image.Transpose.ROTATE_180),
        "t_nsw": t_esw.transpose(Image.Transpose.ROTATE_270),
        "cross_nesw": cross,
        "source_s": source_s,
        "source_e": source_s.transpose(Image.Transpose.ROTATE_90),
        "source_n": source_s.transpose(Image.Transpose.ROTATE_180),
        "source_w": source_s.transpose(Image.Transpose.ROTATE_270),
    }
    if set(assets) != set(kit.EXPECTED):
        raise RuntimeError("96 px cache does not contain the exact final 17-piece set")

    strips: dict[tuple[str, str], np.ndarray] = {}
    failures: list[str] = []
    for name, asset in assets.items():
        rgba = np.asarray(asset, dtype=np.uint8)
        for port, edge in {
            "N": rgba[0],
            "E": rgba[:, -1],
            "S": rgba[-1],
            "W": rgba[:, 0],
        }.items():
            if port in kit.PORTS[name]:
                actual = _read_inward_strip(rgba, port)
                strips[(name, port)] = actual
                if not np.array_equal(actual, strip):
                    failures.append(f"{name}:{port}:inward4")
            elif np.any(edge):
                failures.append(f"{name}:{port}:closed-edge")

    pair_count = 0
    for a_name, a_port in strips:
        for b_name, b_port in strips:
            if OPPOSITE[a_port] != b_port:
                continue
            pair_count += 1
            if not np.array_equal(strips[(a_name, a_port)], strips[(b_name, b_port)]):
                failures.append(f"pair:{a_name}:{a_port}:{b_name}:{b_port}")
    if failures:
        raise RuntimeError(f"96 px river contract failed: {failures}")

    profile = strip[0]
    visible = np.flatnonzero(profile[:, 3] > 8)
    return assets, {
        "source_manifest": str(manifest_path),
        "source_manifest_status": manifest["status"],
        "tile_px": TILE,
        "asset_count": len(assets),
        "open_port_count": len(strips),
        "opposite_pair_count": pair_count,
        "mismatched_pairs": 0,
        "port_lock_depth_px": PORT_LOCK_DEPTH,
        "visible_port_support": [int(visible[0]), int(visible[-1])],
        "visible_port_width_px": int(len(visible)),
        "port_midpoint_px": (float(visible[0]) + float(visible[-1])) * 0.5,
        "all_closed_edges_transparent": True,
    }


def _port_between(a: tuple[int, int], b: tuple[int, int], world_width: int) -> str:
    dx = (int(b[0]) - int(a[0])) % int(world_width)
    dy = int(b[1]) - int(a[1])
    if dx == 1 and dy == 0:
        return "E"
    if dx == world_width - 1 and dy == 0:
        return "W"
    if dx == 0 and dy == 1:
        return "S"
    if dx == 0 and dy == -1:
        return "N"
    raise ValueError(f"non-cardinal recorded edge: {a!r}->{b!r}")


def _ports_by_cell(mouths: list[dict], world_width: int) -> dict[tuple[int, int], frozenset[str]]:
    graph = v79._recorded_graph(mouths, world_width=world_width)
    ports: dict[tuple[int, int], set[str]] = {cell: set() for cell in graph}
    for cell, neighbours in graph.items():
        for neighbour in neighbours:
            ports[cell].add(_port_between(cell, neighbour, world_width))
    for mouth in mouths:
        cell = tuple(int(value) for value in mouth["river_cell"])
        ports.setdefault(cell, set()).add(str(mouth["exit_port"])[0].upper())
    return {cell: frozenset(value) for cell, value in ports.items()}


def _asset_for_ports(
    ports: frozenset[str],
    *,
    seed: int,
    cell: tuple[int, int],
    mouth: bool,
) -> str:
    mapping = {
        frozenset("N"): "source_n",
        frozenset("E"): "source_e",
        frozenset("S"): "source_s",
        frozenset("W"): "source_w",
        frozenset("NE"): "curve_ne",
        frozenset("NW"): "curve_nw",
        frozenset("SE"): "curve_se",
        frozenset("SW"): "curve_sw",
        frozenset("NES"): "t_nes",
        frozenset("NEW"): "t_new",
        frozenset("NSW"): "t_nsw",
        frozenset("ESW"): "t_esw",
        frozenset("NESW"): "cross_nesw",
    }
    if ports == frozenset("NS"):
        return "s_curve_ns" if not mouth and ((cell[0] * 31 + cell[1] * 17 + seed) % 3 == 0) else "straight_ns"
    if ports == frozenset("EW"):
        return "s_curve_ew" if not mouth and ((cell[0] * 31 + cell[1] * 17 + seed) % 3 == 0) else "straight_ew"
    if ports not in mapping:
        raise ValueError(f"unsupported ports {sorted(ports)} at {cell}")
    return mapping[ports]


def _paste_delta(
    image: Image.Image,
    mouth: dict,
    *,
    art: Image.Image,
    alpha: Image.Image,
    window: tuple[int, int, int, int],
    world_width: int,
) -> None:
    crop_x, crop_y, crop_w, _crop_h = window
    delta, anchor = v77._oriented_delta(art, alpha, mouth["exit_port"], TILE)
    mouth_x = v79._cell_x_near_window(
        int(mouth["river_cell"][0]), crop_x, crop_w, world_width
    )
    centre = (
        (mouth_x + 0.5 - crop_x) * TILE,
        (int(mouth["river_cell"][1]) + 0.5 - crop_y) * TILE,
    )
    image.alpha_composite(
        delta,
        (int(round(centre[0] - anchor[0])), int(round(centre[1] - anchor[1]))),
    )


def _validate_topology(
    ports_by_cell: dict[tuple[int, int], frozenset[str]],
    mouth_by_cell: dict[tuple[int, int], dict],
    world_width: int,
) -> None:
    failures: list[str] = []
    for cell, ports in ports_by_cell.items():
        for port in ports:
            if cell in mouth_by_cell and port == str(mouth_by_cell[cell]["exit_port"])[0].upper():
                continue
            dx, dy = PORT_STEP[port]
            neighbour = ((cell[0] + dx) % world_width, cell[1] + dy)
            if neighbour not in ports_by_cell or OPPOSITE[port] not in ports_by_cell[neighbour]:
                failures.append(f"{cell}:{port}->{neighbour}")
    for cell, mouth in mouth_by_cell.items():
        exit_port = str(mouth["exit_port"])[0].upper()
        ports = ports_by_cell.get(cell, frozenset())
        if exit_port not in ports or len(ports) < 2:
            failures.append(f"mouth:{cell}:{exit_port}:{sorted(ports)}")
    if failures:
        raise RuntimeError(f"recorded river topology failed: {failures}")


def _render_case(case: dict, assets: dict[str, Image.Image]) -> tuple[Image.Image, Image.Image, dict]:
    seed = int(case["seed"])
    window = tuple(int(value) for value in case["window"])
    mapgen = v77._load_mapgen()
    grid, metadata = mapgen.generate_with_metadata(seed)
    logical = np.asarray(grid, dtype=np.int16)
    world_width = int(logical.shape[1])

    foundation = v79.render_window_v79(
        logical,
        metadata,
        seed=seed,
        window=window,
        tile_px=TILE,
        mouth_cells=[],
    )
    selected = v79._select_mouths(
        metadata,
        window,
        world_width,
        case["mouth_cells"],
    )
    requested = {tuple(cell) for cell in case["mouth_cells"]}
    selected_cells = {tuple(mouth["river_cell"]) for mouth in selected}
    if selected_cells != requested:
        raise RuntimeError(f"mouth selection mismatch: {selected_cells} != {requested}")

    beauty = foundation.base.convert("RGBA")
    master = Image.open(v77.MASTER_PATH).convert("RGB")
    art = v77._fit_selected_delta_vertical(
        master.resize((3 * TILE, 2 * TILE), Image.Resampling.LANCZOS), TILE
    )
    alpha = v77._limit_delta_offshore(
        v77._delta_semantic_alpha(art), TILE, v77.DELTA_MAX_SEA_FRACTION
    )
    for mouth in selected:
        _paste_delta(
            beauty,
            mouth,
            art=art,
            alpha=alpha,
            window=window,
            world_width=world_width,
        )

    ports_by_cell = _ports_by_cell(selected, world_width)
    mouth_by_cell = {tuple(mouth["river_cell"]): mouth for mouth in selected}
    _validate_topology(ports_by_cell, mouth_by_cell, world_width)
    crop_x, crop_y, crop_w, crop_h = window
    placements: list[dict] = []
    usage = Counter()
    for cell, ports in sorted(ports_by_cell.items(), key=lambda item: (item[0][1], item[0][0])):
        near_x = v79._cell_x_near_window(cell[0], crop_x, crop_w, world_width)
        local_x = int(round((near_x - crop_x) * TILE))
        local_y = int(round((cell[1] - crop_y) * TILE))
        if (
            local_x <= -TILE
            or local_x >= crop_w * TILE
            or local_y <= -TILE
            or local_y >= crop_h * TILE
        ):
            continue
        name = _asset_for_ports(
            ports,
            seed=seed,
            cell=cell,
            mouth=cell in mouth_by_cell,
        )
        if frozenset(kit.PORTS[name]) != ports:
            raise RuntimeError(f"asset/port mismatch at {cell}: {name} {ports}")
        if cell in mouth_by_cell and name.startswith("source_"):
            raise RuntimeError(f"mouth rendered as source at {cell}")
        beauty.alpha_composite(assets[name], (local_x, local_y))
        usage[name] += 1
        placements.append(
            {
                "cell": list(cell),
                "ports": "".join(port for port in PORT_ORDER if port in ports),
                "asset": name,
                "mouth": cell in mouth_by_cell,
            }
        )

    beauty_rgb = beauty.convert("RGB")
    report = {
        "slug": case["slug"],
        "title": case["title"],
        "seed": seed,
        "window": list(window),
        "mouth_cells": [list(cell) for cell in case["mouth_cells"]],
        "mouth_exit_ports": [mouth["exit_port"] for mouth in selected],
        "river_cell_count": len(ports_by_cell),
        "visible_placement_count": len(placements),
        "asset_usage": dict(sorted(usage.items())),
        "placements": placements,
        "topology_reciprocal": True,
        "mouths_are_not_sources": True,
        "base_schema": foundation.report["schema"],
    }
    return beauty_rgb, v77._grid(beauty_rgb, TILE), report


def _contact(rows: list[tuple[str, Image.Image, Image.Image]]) -> Image.Image:
    panel_w = max(beauty.width for _title, beauty, _grid in rows)
    header = 126
    label_h = 48
    width = panel_w * 2
    height = header + sum(label_h + beauty.height for _title, beauty, _grid in rows)
    sheet = Image.new("RGB", (width, height), (3, 12, 15))
    draw = ImageDraw.Draw(sheet)
    draw.text((18, 10), "PROJECT1991 | APPROVED V77/V79 WORLDS + FINAL V1 RIVERS", font=_font(29, True), fill=(235, 241, 229))
    draw.text((18, 53), "Coast V3.1 + V51 Ground + V44 Relief + Hills NESW + Forest V4.1 | 96 px/cell", font=_font(17), fill=(31, 222, 226))
    draw.text((18, 83), "No rejected splatmap background | final 17-piece river overlay | beauty + Civ grid", font=_font(16), fill=(174, 190, 185))
    y = header
    for title, beauty, grid in rows:
        draw.rectangle((0, y, width, y + label_h - 1), fill=(3, 12, 15))
        draw.text((12, y + 10), title, font=_font(17, True), fill=(235, 241, 229))
        y += label_h
        sheet.paste(beauty, (0, y))
        sheet.paste(grid, (panel_w, y))
        y += beauty.height
    return sheet


def main() -> Path:
    assets, asset_audit = _load_target_assets()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    contact_rows: list[tuple[str, Image.Image, Image.Image]] = []
    case_reports: list[dict] = []
    for case in CASES:
        beauty, grid, report = _render_case(case, assets)
        beauty_path = OUTPUT / f"{case['slug']}-beauty.png"
        grid_path = OUTPUT / f"{case['slug']}-grid.png"
        beauty.save(beauty_path)
        grid.save(grid_path)
        report["beauty"] = beauty_path.name
        report["grid"] = grid_path.name
        case_reports.append(report)
        contact_rows.append((str(case["title"]), beauty, grid))

    contact = _contact(contact_rows)
    contact_path = OUTPUT / "selected-world-final-v1-river-test-contact.png"
    contact.save(contact_path)
    summary = {
        "schema": "project1991.v77-v79/final-v1-river-map-tests",
        "status": "PASS",
        "pipeline": {
            "logical_map_generator": str(v77.MAPGEN_PATH),
            "visual_foundation": str(Path(v79.__file__).resolve()),
            "visual_foundation_api": "render_window_v79(...).base",
            "rejected_splatmap_background_used": False,
            "rejected_v81_river_art_used": False,
            "selected_delta_semantics_retained": True,
        },
        "river_assets": asset_audit,
        "cases": case_reports,
        "contact": contact_path.name,
    }
    report_path = OUTPUT / "selected-world-final-v1-river-test-report.json"
    report_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(contact_path)
    return contact_path


if __name__ == "__main__":
    main()
