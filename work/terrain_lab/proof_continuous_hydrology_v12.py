"""Two-world handoff proof for isolated Continuous Hydrology V12."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from work.aa_tile_kit_v1 import render_example_map as renderer
from work.aa_tile_kit_v1.compositor import draw_grid_overlay
from work.terrain_lab.continuous_hydrology_v12 import (
    generate_continuous_hydrology_v12,
    validate_continuous_hydrology_v12,
)
from work.terrain_lab.continuous_river_render_v11 import PixelWindowV11, composite_continuous_rivers_v11
from work.terrain_lab.continuous_river_render_v12 import (
    PixelWindowV12,
    composite_continuous_rivers_v12,
    render_continuous_river_layer_v12,
    validate_continuous_render_v12,
)


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = Path(os.environ.get("MAPGENCIV_AUTHORITY",
    str(ROOT / "civ1" / "mapgen.py")))
OUTPUT = ROOT / "outputs" / "continuous-hydrology-v12"
SNAPSHOTS = OUTPUT / "snapshots"
TILE, CROP_W, CROP_H = 96, 12, 10
CASES = (
    (14584, "corridor-basin", 20, 25),
    (4818, "highland-estuary", 58, 7),
)


def _load_authority():
    spec = importlib.util.spec_from_file_location("continuous_hydrology_v12_proof_authority", AUTHORITY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load authority {AUTHORITY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(_jsonable(payload), separators=(",", ":")), encoding="utf-8")


def _pair(left: Image.Image, right: Image.Image, destination: Path, *, label: str, seed: int, crop_x: int, crop_y: int):
    header = 76
    canvas = Image.new("RGB", (left.width + right.width, max(left.height, right.height) + header), (4, 13, 16))
    canvas.paste(left.convert("RGB"), (0, header))
    canvas.paste(right.convert("RGB"), (left.width, header))
    draw = ImageDraw.Draw(canvas)
    draw.text((14, 7), f"V11 CORRIDOR-FIRST | {label}", font=ImageFont.load_default(size=18), fill=(231, 181, 88))
    draw.text((left.width + 14, 7), f"V12 ELASTIC + TERRAIN MATERIAL | {label}", font=ImageFont.load_default(size=18), fill=(65, 226, 208))
    draw.text(
        (14, 39),
        f"same exact Civ Stage 4 | seed {seed} | crop {crop_x},{crop_y} | isolated derivative; no Main integration",
        font=ImageFont.load_default(size=13),
        fill=(191, 211, 202),
    )
    canvas.save(destination)
    return destination


def _contact(paths: list[Path], destination: Path, label: str) -> Path:
    images = []
    try:
        for path in paths:
            with Image.open(path) as source:
                images.append(source.convert("RGB"))
        header = 46
        canvas = Image.new("RGB", (max(image.width for image in images), sum(image.height + header for image in images)), (4, 12, 15))
        draw = ImageDraw.Draw(canvas)
        y = 0
        for image, case in zip(images, CASES):
            seed, name, crop_x, crop_y = case
            draw.text(
                (12, y + 8),
                f"{label} | {name} | seed {seed} | crop {crop_x},{crop_y}",
                font=ImageFont.load_default(size=17),
                fill=(211, 230, 222),
            )
            canvas.paste(image, (0, y + header))
            y += image.height + header
        canvas.save(destination)
    finally:
        for image in images:
            image.close()
    return destination


def _exact_checks(world, crop_x: int, crop_y: int):
    full = np.asarray(
        render_continuous_river_layer_v12(
            world, PixelWindowV12(crop_x * TILE, crop_y * TILE, 6 * TILE, 5 * TILE)
        )
    )
    crop = np.asarray(
        render_continuous_river_layer_v12(
            world, PixelWindowV12((crop_x + 1) * TILE, (crop_y + 1) * TILE, 3 * TILE, 2 * TILE)
        )
    )
    wrapped = np.asarray(
        render_continuous_river_layer_v12(
            world,
            PixelWindowV12((crop_x + world.world_width) * TILE, crop_y * TILE, 3 * TILE, 2 * TILE),
        )
    )
    unwrapped = np.asarray(
        render_continuous_river_layer_v12(
            world, PixelWindowV12(crop_x * TILE, crop_y * TILE, 3 * TILE, 2 * TILE)
        )
    )
    return bool(np.array_equal(crop, full[TILE : 3 * TILE, TILE : 4 * TILE])), bool(
        np.array_equal(wrapped, unwrapped)
    )


def render():
    authority = _load_authority()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    renderer.OUTPUT = OUTPUT
    beauty_pairs: list[Path] = []
    grid_pairs: list[Path] = []
    reports = []
    for seed, name, crop_x, crop_y in CASES:
        world = generate_continuous_hydrology_v12(authority, seed)
        source = world.source_v11
        if world.stage4_terrain != source.stage4_terrain:
            raise AssertionError("V12 and V11 do not share exact Stage 4")
        hydro_audit = validate_continuous_hydrology_v12(world, authority)
        render_audit = validate_continuous_render_v12(world)

        stage4_snapshot = SNAPSHOTS / f"seed-{seed}-stage4-authority.json"
        _write_json(stage4_snapshot, {"seed": seed, "terrain": [list(row) for row in world.stage4_terrain]})
        derivative_snapshot = SNAPSHOTS / f"seed-{seed}-modern-v12-derivative.json"
        _write_json(
            derivative_snapshot,
            {
                "seed": seed,
                "terrain": [list(row) for row in world.terrain],
                "river_traces": world.snapshot_extension(),
            },
        )
        stem = f"seed-{seed}-crop-x{crop_x}-y{crop_y}-stage4-base"
        base_path, _base_grid = renderer.render_snapshot(
            stage4_snapshot,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_w=CROP_W,
            crop_h=CROP_H,
            output_stem=stem,
        )
        with Image.open(base_path) as image:
            base = image.convert("RGBA")

        v11_window = PixelWindowV11(crop_x * TILE, crop_y * TILE, CROP_W * TILE, CROP_H * TILE)
        v12_window = PixelWindowV12(crop_x * TILE, crop_y * TILE, CROP_W * TILE, CROP_H * TILE)
        v11_beauty = composite_continuous_rivers_v11(base, source, v11_window).convert("RGB")
        v12_beauty = composite_continuous_rivers_v12(base, world, v12_window).convert("RGB")
        v11_grid = draw_grid_overlay(
            v11_beauty,
            tile_size=(TILE, TILE),
            world_offset_px=(crop_x * TILE, crop_y * TILE),
            dark=(5, 24, 24, 84),
            light=(195, 216, 204, 10),
        ).convert("RGB")
        v12_grid = draw_grid_overlay(
            v12_beauty,
            tile_size=(TILE, TILE),
            world_offset_px=(crop_x * TILE, crop_y * TILE),
            dark=(5, 24, 24, 84),
            light=(195, 216, 204, 10),
        ).convert("RGB")
        v11_beauty.save(OUTPUT / f"seed-{seed}-v11-beauty.png")
        v12_beauty.save(OUTPUT / f"seed-{seed}-v12-beauty.png")
        v11_grid.save(OUTPUT / f"seed-{seed}-v11-grid.png")
        v12_grid.save(OUTPUT / f"seed-{seed}-v12-grid.png")
        beauty_pairs.append(
            _pair(
                v11_beauty,
                v12_beauty,
                OUTPUT / f"seed-{seed}-v11-vs-v12-beauty.png",
                label="BEAUTY",
                seed=seed,
                crop_x=crop_x,
                crop_y=crop_y,
            )
        )
        grid_pairs.append(
            _pair(
                v11_grid,
                v12_grid,
                OUTPUT / f"seed-{seed}-v11-vs-v12-grid.png",
                label="GRID AUDIT",
                seed=seed,
                crop_x=crop_x,
                crop_y=crop_y,
            )
        )
        crop_exact, wrap_exact = _exact_checks(world, crop_x, crop_y)
        rising = [
            trace.trace_id
            for trace in world.traces
            if trace.samples[-1].potential >= trace.samples[0].potential
        ]
        reports.append(
            {
                "seed": seed,
                "case": name,
                "crop": [crop_x, crop_y, CROP_W, CROP_H],
                "derivative_label": world.derivative_label,
                "stage4_equal_v11": True,
                "hydrology_audit": hydro_audit.__dict__,
                "render_audit": render_audit.__dict__,
                "branches_preserved": {
                    "primary": sum(trace.kind == "primary" for trace in world.traces),
                    "tributary": sum(trace.kind == "tributary" for trace in world.traces),
                    "mouth": len(world.mouths),
                },
                "overall_rising_trace_ids": rising,
                "crop_exact": crop_exact,
                "wrap_exact": wrap_exact,
                "snapshot_sha256": hashlib.sha256(derivative_snapshot.read_bytes()).hexdigest(),
            }
        )
    _contact(beauty_pairs, OUTPUT / "contact-sheet-v11-vs-v12-beauty.png", "BEAUTY")
    _contact(grid_pairs, OUTPUT / "contact-sheet-v11-vs-v12-grid.png", "GRID AUDIT")
    _write_json(
        OUTPUT / "proof-report.json",
        {
            "schema": "project1991.continuous-hydrology-proof/v12",
            "scope": "isolated-new-world-two-seed-gate-no-main-integration",
            "verdict": {
                "architecture_graph": "GO",
                "shipping_visual_northstar": "NO-GO",
                "reason": (
                    "V12 removes Fine-A* angle rhythm and preserves exact corridor authority, but the 2D overlay still "
                    "reads as a flat vector channel with mechanical Y joins and a soft light-cone estuary. The next "
                    "visual pivot must consume the V12 corridor as a Godot ground displacement/riverbed material mask."
                ),
            },
            "reports": reports,
        },
    )
    return reports


if __name__ == "__main__":
    print(json.dumps(_jsonable(render()), indent=2))
