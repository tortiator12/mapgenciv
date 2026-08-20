"""Build an optional V2 river visual beside the reviewed V1 world chunks.

The technical river topology remains in ``world.json``.  V79 renders its
river-free ``base`` from ``inferred_presentation_underlay`` and V2 paints the
visible river exactly once on top.  Existing ``chunks/`` files and the main
world manifest are never modified.

Run with Windows Python because the reviewed V79 renderer and its material
paths are Windows-native::

    python -B tools/build_river_v2_variant.py \
        --world data/worlds/civ_world_19146/world.json --workers 4

The result is ``chunks_river_v2/`` plus ``river-v2.json`` next to the normal
world package.  Godot treats that manifest as an explicitly experimental,
fingerprint-locked visual alternative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import chain
from pathlib import Path

import numpy as np
from PIL import Image

from river_paint_v2 import paint_rivers


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = ROOT / "data" / "worlds" / "civ_world_19146" / "world.json"
# The "ic" root historically lived in a separate checkout; this repo unifies
# it with everything else under one root, so that's the new default.
DEFAULT_IC_ROOT = Path(os.environ.get("MAPGENCIV_IC_ROOT", str(ROOT)))
VARIANT_SCHEMA = "project1991.river-visual-variant/v1"
RENDERER_SCHEMA = "project1991.continuous-river/v2-experimental"
HALO_CELLS = 2

_CACHE: dict[str, object] = {}


def save_png_atomic(image: Image.Image, target: Path, compress_level: int) -> None:
    """Publish a chunk only after the PNG encoder has closed it completely.

    The live game may consume an announced chunk while the remaining workers
    continue.  A normal ``Image.save(target)`` briefly exposes a truncated
    file; a same-directory replace gives Windows and POSIX one atomic commit.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(
        f".{target.stem}.{os.getpid()}.{time.time_ns()}.building.png"
    )
    try:
        image.save(
            temporary, format="PNG",
            compress_level=max(0, min(9, int(compress_level))),
        )
        # Close + flush the complete payload before the atomic name becomes
        # visible to the running game.  The final manifest is still the only
        # durable full-package authority.
        # Windows' FlushFileBuffers rejects a read-only CRT descriptor.  Open
        # the already encoded file read/write without changing a byte.
        with temporary.open("r+b", buffering=0) as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.is_file():
            temporary.unlink()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_renderer(ic_root: Path):
    key = str(ic_root.resolve())
    cached = _CACHE.get("renderer")
    if cached is not None and _CACHE.get("renderer_root") == key:
        return cached
    if str(ic_root) not in sys.path:
        sys.path.insert(0, str(ic_root))
    from work import selected_material_renderer_v79 as v79
    from work.aa_tile_kit_v1.coast_v2 import PixelWindow
    from work.aa_tile_kit_v1.coast_v3 import CoastV31Config, TangentGlobalCoast

    value = (v79, PixelWindow, CoastV31Config, TangentGlobalCoast)
    _CACHE["renderer"] = value
    _CACHE["renderer_root"] = key
    return value


def load_world(world_path: Path) -> dict:
    key = str(world_path.resolve())
    if _CACHE.get("world_path") != key:
        _CACHE["world"] = json.loads(world_path.read_text(encoding="utf-8"))
        _CACHE["world_path"] = key
    return _CACHE["world"]  # type: ignore[return-value]


def manifest_from_snapshot(snapshot_path: Path, ic_root: Path) -> dict:
    """Build the exact V2 render contract before the legacy manifest exists.

    A new world used to wait for all 40 legacy chunks and ``world.json``
    before River V2 could even begin.  Both renderers are pure views of the
    same immutable OpenCivOne snapshot, so derive only the fields V2 needs
    directly from that snapshot.  The completed public manifests are still
    validated against each other by Godot before the game starts.
    """
    key = f"snapshot:{snapshot_path.resolve()}"
    cached = _CACHE.get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    tools_root = ic_root / "work" / "nordstern" / "tools"
    for path in (ic_root, tools_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from work.terrain_lab.snapshot_hydrology_v24 import load_snapshot_hydrology_v24
    from work.terrain_lab.proof_continuous_hydrology_v12 import _load_authority
    import export_v79_v1_world as legacy

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    authority = _load_authority()
    world = load_snapshot_hydrology_v24(snapshot_path, authority, tile_px=legacy.TILE)
    ports, mouth_by_cell, visual_edges, flow_edges = legacy._ports_and_mouths(world)
    placements, topology = legacy._build_placements(
        world, ports, mouth_by_cell, visual_edges, flow_edges
    )
    if not topology.get("all_saved_cells_preserved") or not topology.get("topology_reciprocal"):
        raise RuntimeError("snapshot river topology failed before parallel V2 render")

    terrain = np.asarray(world.terrain, dtype=np.int16)
    underlay = np.asarray(world.stage4_terrain, dtype=np.int16)
    height, width = terrain.shape
    chunk_cells = int(legacy.CHUNK_CELLS)
    chunks = [
        {
            "x": x, "y": y,
            "cells_w": min(chunk_cells, width - x),
            "cells_h": min(chunk_cells, height - y),
            "texture": f"chunks/x{x // chunk_cells:02d}_y{y // chunk_cells:02d}.png",
        }
        for y in range(0, height, chunk_cells)
        for x in range(0, width, chunk_cells)
    ]
    manifest = {
        "schema": "project1991.nordstern-world/v1",
        "status": "BUILDING",
        "id": snapshot_path.parent.name,
        "authority": {"fingerprint": payload["fingerprint"]},
        "seed": int(payload["seed"]),
        "width": int(width),
        "height": int(height),
        "tile_px": int(legacy.TILE),
        "terrain": terrain.astype(int).tolist(),
        "inferred_presentation_underlay": underlay.astype(int).tolist(),
        "rivers": placements,
        "visual": {"material_edge_feather_px": int(legacy.MATERIAL_EDGE_FEATHER_PX)},
        "chunks": chunks,
    }
    _CACHE[key] = manifest
    return manifest


def expanded_window(
    x: int, y: int, wide: int, high: int, world_height: int
) -> tuple[int, int, int, int]:
    x0 = x - HALO_CELLS
    y0 = max(0, y - HALO_CELLS)
    bottom = min(world_height, y + high + HALO_CELLS)
    return x0, y0, wide + HALO_CELLS * 2, bottom - y0


def render_clean_water_base(v79, PixelWindow, coast, window, world_width,
                            tile, material_edge_feather_px,
                            captured_samples: dict[str, np.ndarray] | None = None):
    """Rebuild V79's decoration-free water side without a second renderer.

    The former guard called the complete V79 stack again with every land cell
    changed to grass.  That stack then spent most of its time proving there
    were no mountains, hills or forests to draw.  V79's pre-decoration water
    result is only three cached material samples plus the already available
    CoastV31 fields, so reproduce those exact operations directly.  The
    result is byte-identical to ``water_guard.base`` but avoids an entire
    relief/forest/weight-render pass for every chunk.
    """
    wx, wy, ww, wh = window
    pixel_window = PixelWindow(wx * tile, wy * tile, ww * tile, wh * tile)
    world_period = int(world_width) * int(tile)
    material_root = v79.v77.MATERIAL_ROOT

    def sample(filename: str) -> np.ndarray:
        if captured_samples is not None and filename in captured_samples:
            return np.asarray(captured_samples[filename], dtype=np.float32)[..., :3]
        sampler = v79._cached_material_sampler(
            str((material_root / filename).resolve()),
            world_period,
            int(material_edge_feather_px),
        )
        return np.asarray(sampler.sample(
            pixel_window.x, pixel_window.y,
            pixel_window.width, pixel_window.height,
        ), dtype=np.float32)[..., :3]

    palette_key = f"coast_palette:{int(tile)}"
    palette = _CACHE.get(palette_key)
    if palette is None:
        with Image.open(v79.v77.MASTER_PATH) as opened:
            master = opened.convert("RGB")
        art = v79.v77._fit_selected_delta_vertical(
            master.resize((3 * tile, 2 * tile), Image.Resampling.LANCZOS), tile
        )
        palette = v79.v77._master_palette(art)
        _CACHE[palette_key] = palette

    grass = sample("grass_lush_01.png")
    ocean = sample("ocean_deep_01.png")
    sand = sample("coast_sand_01.png")
    authored_bank = np.asarray(palette[0][:3], dtype=np.float32)
    coast_sand = sand * 0.52 + authored_bank * 0.48
    coverage = np.asarray(coast.land_coverage, dtype=np.float32)[..., None]
    image = ocean * (1.0 - coverage) + grass * coverage
    turquoise = np.array((13.0, 139.0, 159.0), np.float32)
    shallow_material = ocean * 0.30 + turquoise * 0.70
    shallow = np.asarray(coast.shallow, dtype=np.float32)[..., None] * (1.0 - coverage)
    image = image * (1.0 - shallow) + shallow_material * shallow
    beach = np.asarray(coast.beach, dtype=np.float32)[..., None]
    image = image * (1.0 - beach) + coast_sand * beach
    foam = np.asarray(coast.foam, dtype=np.float32)[..., None] * 0.68
    image = image * (1.0 - foam) + np.array(
        (226.0, 238.0, 218.0), np.float32
    ) * foam
    return np.asarray(np.uint8(np.clip(image, 0, 255)), dtype=float)


def render_chunk(job: tuple[str, str, int, int, int, int, str, int, int, bool, int]):
    (world_arg, ic_arg, x, y, wide, high, out_arg,
     river_seed, png_level, legacy_water_guard, foundation_internal_halo) = job
    chunk_started = time.perf_counter()
    world_path, ic_root, out_path = Path(world_arg), Path(ic_arg), Path(out_arg)
    manifest = load_world(world_path)
    v79, PixelWindow, CoastV31Config, TangentGlobalCoast = load_renderer(ic_root)

    tile = int(manifest["tile_px"])
    world_height = int(manifest["height"])
    underlay = np.asarray(
        manifest.get("inferred_presentation_underlay", manifest["terrain"]),
        dtype=np.int16,
    )
    # Complete authored spring tiles own their relief.  Keep the technical
    # world terrain untouched, but suppress V79's ordinary hill/mountain prop
    # underneath those four V2 source compositions so two reliefs cannot sit
    # on top of each other.  Grassland is the neutral material bed used by
    # both authored assets at their feathered perimeter.
    foundation_underlay = underlay.copy()
    world_width = int(manifest["width"])
    for river in manifest.get("rivers", ()):
        if len(str(river.get("ports", ""))) != 1:
            continue
        source_x = int(river["x"]) % world_width
        source_y = int(river["y"])
        if int(underlay[source_y, source_x]) in (4, 5):
            foundation_underlay[source_y, source_x] = 2
    window = expanded_window(x, y, wide, high, world_height)
    wx, wy, ww, wh = window

    # V79 already computes the authoritative CoastV31 field while composing
    # its foundation.  Capture that immutable result instead of rebuilding
    # the same 1344x1344 distance/coverage fields a second time below.  The
    # land/water mask is identical after source-relief suppression, so this
    # is not an approximation.
    captured_coast: dict[str, object] = {}
    captured_samples: dict[str, np.ndarray] = {}
    original_coast_build = TangentGlobalCoast.build
    original_sampler_factory = v79._cached_material_sampler

    def capture_coast(instance, *build_args, **build_kwargs):
        value = original_coast_build(instance, *build_args, **build_kwargs)
        captured_coast["value"] = value
        return value

    class CaptureSampler:
        def __init__(self, sampler, filename: str):
            self._sampler = sampler
            self._filename = filename

        def sample(self, *sample_args, **sample_kwargs):
            value = self._sampler.sample(*sample_args, **sample_kwargs)
            captured_samples[self._filename] = value
            return value

    def capture_sampler(source_path, world_period_x, seamless_edge_feather):
        sampler = original_sampler_factory(
            source_path, world_period_x, seamless_edge_feather
        )
        filename = Path(source_path).name
        if filename in {"grass_lush_01.png", "ocean_deep_01.png", "coast_sand_01.png"}:
            return CaptureSampler(sampler, filename)
        return sampler

    stage_started = time.perf_counter()
    TangentGlobalCoast.build = capture_coast
    v79._cached_material_sampler = capture_sampler
    try:
        foundation = v79.render_window_v79(
            foundation_underlay,
            {},
            seed=int(manifest["seed"]),
            window=window,
            tile_px=tile,
            mouth_cells=[],
            render_halo_cells=foundation_internal_halo,
            material_edge_feather_px=int(manifest["visual"]["material_edge_feather_px"]),
        )
    finally:
        v79._cached_material_sampler = original_sampler_factory
        TangentGlobalCoast.build = original_coast_build
    if foundation.report.get("schema") != v79.SEAMLESS_MATERIAL_SCHEMA:
        raise RuntimeError(f"chunk {x},{y}: V79 seam-locked base contract lost")
    foundation_ms = (time.perf_counter() - stage_started) * 1000.0

    stage_started = time.perf_counter()
    coast = captured_coast.get("value")
    if coast is None:
        raise RuntimeError(f"chunk {x},{y}: V79 did not expose its CoastV31 field")
    water_coverage = 1.0 - np.asarray(coast.land_coverage, dtype=float)
    coast_signed_distance = np.asarray(coast.signed_distance, dtype=float)
    coast_ms = (time.perf_counter() - stage_started) * 1000.0

    # V79 places large hill/mountain/forest decorations after composing its
    # organic coast.  A large relief sprite can therefore protrude into a
    # small neighbouring lake even though world.json says those pixels are
    # water.  Render a decoration-free copy of the exact same coast/material
    # foundation and let it own only the water side of the signed shoreline.
    # Land keeps every normal decoration; water can never be covered by one.
    stage_started = time.perf_counter()
    if legacy_water_guard:
        water_guard_underlay = np.where(underlay == 10, 10, 2).astype(np.int16)
        water_guard = v79.render_window_v79(
            water_guard_underlay,
            {},
            seed=int(manifest["seed"]),
            window=window,
            tile_px=tile,
            mouth_cells=[],
            render_halo_cells=foundation_internal_halo,
            material_edge_feather_px=int(manifest["visual"]["material_edge_feather_px"]),
        )
        clean_water_base = np.asarray(water_guard.base, dtype=float)
    else:
        clean_water_base = render_clean_water_base(
            v79, PixelWindow, coast, window, world_width, tile,
            int(manifest["visual"]["material_edge_feather_px"]), captured_samples,
        )
    water_guard_ms = (time.perf_counter() - stage_started) * 1000.0
    decorated_base = np.asarray(foundation.base, dtype=float)
    water_owner = np.clip((1.0 - coast_signed_distance) / 2.0, 0.0, 1.0)
    water_owner = water_owner * water_owner * (3.0 - 2.0 * water_owner)
    guarded_foundation = (
        decorated_base * (1.0 - water_owner[..., None])
        + clean_water_base * water_owner[..., None]
    )
    stage_started = time.perf_counter()
    painted = paint_rivers(
        manifest,
        guarded_foundation,
        wx,
        wy,
        seed=river_seed,
        water_coverage=water_coverage,
        coast_signed_distance=coast_signed_distance,
    )
    river_ms = (time.perf_counter() - stage_started) * 1000.0

    left = (x - wx) * tile
    top = (y - wy) * tile
    image = Image.fromarray(painted, "RGB").crop(
        (left, top, left + wide * tile, top + high * tile)
    )
    stage_started = time.perf_counter()
    # Pillow's optimize=True performs an expensive exhaustive encoder pass.
    # A selectable ordinary zlib level preserves pixels exactly and lets the
    # profiler expose the honest speed/size trade-off.
    save_png_atomic(image, out_path, png_level)
    encode_ms = (time.perf_counter() - stage_started) * 1000.0
    output_sha = sha256(out_path)
    return x, y, wide, high, str(out_path), {
        "foundation_ms": foundation_ms,
        "coast_ms": coast_ms,
        "water_guard_ms": water_guard_ms,
        "river_ms": river_ms,
        "png_encode_ms": encode_ms,
        "total_ms": (time.perf_counter() - chunk_started) * 1000.0,
        "png_bytes": out_path.stat().st_size,
        "sha256": output_sha,
    }


def chunk_jobs(manifest: dict, world_path: Path, ic_root: Path, out_dir: Path,
               river_seed: int, selected: set[tuple[int, int]] | None,
               png_compress_level: int, legacy_water_guard: bool,
               foundation_internal_halo: int):
    jobs = []
    for record in manifest["chunks"]:
        x, y = int(record["x"]), int(record["y"])
        if selected is not None and (x, y) not in selected:
            continue
        wide, high = int(record["cells_w"]), int(record["cells_h"])
        name = Path(record["texture"]).name
        jobs.append((
            str(world_path), str(ic_root), x, y, wide, high,
            str(out_dir / name), river_seed, png_compress_level,
            legacy_water_guard, foundation_internal_halo,
        ))
    return jobs


def bundle_adjacent_jobs(jobs: list[tuple], columns: int) -> list[tuple[tuple, ...]]:
    """Share the expensive halo between horizontal neighbour chunks."""
    columns = max(1, int(columns))
    bundles: list[tuple[tuple, ...]] = []
    current: list[tuple] = []
    for job in jobs:
        if current:
            previous = current[-1]
            contiguous = (
                job[3] == previous[3]
                and job[2] == previous[2] + previous[4]
                and job[5] == previous[5]
            )
            if len(current) >= columns or not contiguous:
                bundles.append(tuple(current))
                current = []
        current.append(job)
    if current:
        bundles.append(tuple(current))
    return bundles


def render_job_bundle(bundle: tuple[tuple, ...]):
    if len(bundle) == 1:
        result = render_chunk(bundle[0])
        return result, 1

    first = bundle[0]
    last = bundle[-1]
    world_arg, ic_arg = first[0], first[1]
    x, y = int(first[2]), int(first[3])
    wide = int(last[2]) + int(last[4]) - x
    high = int(first[5])
    first_out = Path(first[6])
    temporary = first_out.parent / f".river_bundle_{x}_{y}_{wide}.png"
    combined = (
        world_arg, ic_arg, x, y, wide, high, str(temporary),
        first[7], 0, first[9], first[10],
    )
    started = time.perf_counter()
    result = render_chunk(combined)
    final_encode_started = time.perf_counter()
    png_bytes = 0
    try:
        with Image.open(temporary) as opened:
            image = opened.convert("RGB")
        tile = image.width // wide
        for original in bundle:
            offset = (int(original[2]) - x) * tile
            target = Path(original[6])
            crop = image.crop((
                offset, 0, offset + int(original[4]) * tile,
                int(original[5]) * tile,
            ))
            save_png_atomic(crop, target, int(original[8]))
            png_bytes += target.stat().st_size
    finally:
        if temporary.is_file():
            temporary.unlink()
    profile = dict(result[5])
    profile["png_encode_ms"] += (time.perf_counter() - final_encode_started) * 1000.0
    profile["total_ms"] = (time.perf_counter() - started) * 1000.0
    profile["png_bytes"] = png_bytes
    profile["chunk_records"] = [
        {
            "x": int(original[2]), "y": int(original[3]),
            "cells_w": int(original[4]), "cells_h": int(original[5]),
            "path": str(original[6]), "sha256": sha256(Path(original[6])),
        }
        for original in bundle
    ]
    paths = ",".join(str(original[6]) for original in bundle)
    return (x, y, wide, high, paths, profile), len(bundle)


def write_variant_manifest(world_path: Path, manifest: dict, out_dir: Path,
                           river_seed: int, png_compress_level: int,
                           foundation_internal_halo: int) -> Path | None:
    chunks = []
    tile = int(manifest["tile_px"])
    for record in manifest["chunks"]:
        path = out_dir / Path(record["texture"]).name
        if not path.is_file():
            return None
        with Image.open(path) as image:
            expected = (int(record["cells_w"]) * tile, int(record["cells_h"]) * tile)
            if image.mode != "RGB" or image.size != expected:
                raise RuntimeError(f"invalid V2 chunk {path.name}: {image.mode} {image.size}")
        chunks.append({
            "x": int(record["x"]),
            "y": int(record["y"]),
            "cells_w": int(record["cells_w"]),
            "cells_h": int(record["cells_h"]),
            "texture": f"{out_dir.name}/{path.name}",
            "sha256": sha256(path),
        })

    source = Path(__file__).with_name("river_paint_v2.py")
    payload = {
        "schema": VARIANT_SCHEMA,
        "status": "EXPERIMENTAL",
        "id": "river-v2",
        "world_id": manifest["id"],
        "authority_fingerprint": manifest["authority"]["fingerprint"],
        "width": int(manifest["width"]),
        "height": int(manifest["height"]),
        "tile_px": tile,
        "renderer": {
            "schema": RENDERER_SCHEMA,
            "source": str(source.resolve()),
            "source_sha256": sha256(source),
            "river_seed": river_seed,
            "png_compress_level": png_compress_level,
            "foundation": "V79 base from inferred_presentation_underlay",
            "foundation_internal_halo": int(foundation_internal_halo),
            "river_outer_halo": HALO_CELLS,
            "water_guard": "direct byte-identical V79 ground reconstruction",
            "visible_river_owner_count": 1,
        },
        "chunks": chunks,
        "qa": {
            "chunk_count": len(chunks),
            "chunk_coverage_exact": len(chunks) == len(manifest["chunks"]),
            "old_chunks_modified": False,
            "old_river_inpainted": False,
        },
    }
    target = world_path.with_name("river-v2.json")
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def parse_chunk(value: str) -> tuple[int, int]:
    try:
        first, second = value.split(",", 1)
        return int(first), int(second)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("chunk must be CELL_X,CELL_Y (for example 10,20)") from exc


def prioritise_jobs(jobs: list[tuple], start_cell: tuple[int, int] | None,
                    world_width: int) -> list[tuple]:
    """Put chunks around the real player start into the first worker wave.

    Only submission order changes.  Rendering, pixels and final manifest stay
    byte-identical.  Horizontal distance wraps like gameplay does.
    """
    if start_cell is None:
        return jobs
    sx, sy = start_cell

    def score(job: tuple) -> tuple[float, int, int]:
        x, y, wide, high = map(int, (job[2], job[3], job[4], job[5]))
        cx, cy = x + wide * .5, y + high * .5
        dx = abs(cx - (sx + .5))
        dx = min(dx, max(0.0, world_width - dx))
        dy = abs(cy - (sy + .5))
        contains = x <= sx < x + wide and y <= sy < y + high
        return (0.0 if contains else dx * dx + dy * dy, y, x)

    return sorted(jobs, key=score)


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--world", type=Path,
                        help="completed legacy world.json (normal/rebuild path)")
    source.add_argument("--snapshot", type=Path,
                        help="authoritative snapshot.json (parallel new-world path)")
    parser.add_argument("--ic-root", type=Path, default=DEFAULT_IC_ROOT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--river-seed", type=int, default=11)
    parser.add_argument("--png-compress-level", type=int, default=3,
                        help="Pillow PNG zlib level 0..9; pixels are identical")
    parser.add_argument("--legacy-water-guard", action="store_true",
                        help="QA only: use the former full second V79 render")
    parser.add_argument("--foundation-internal-halo", type=int, default=0,
                        help="QA: extra V79 halo beyond the explicit two-cell river halo")
    parser.add_argument("--bundle-columns", type=int, default=2,
                        help="share one outer halo across adjacent horizontal chunks")
    parser.add_argument("--chunk", type=parse_chunk, action="append",
                        help="render only a chunk origin; repeatable")
    parser.add_argument("--priority-cell", type=parse_chunk,
                        help="real player start cell; nearby chunks enter the first worker wave")
    parser.add_argument("--preview", action="store_true",
                        help="write selected images to river_v2_previews without touching the switchable set")
    parser.add_argument("--preview-tag", default="",
                        help="optional subfolder name that preserves this preview iteration")
    args = parser.parse_args()

    world_path = (args.world or DEFAULT_WORLD).resolve()
    snapshot_path = args.snapshot.resolve() if args.snapshot else None
    render_source_path = world_path
    if snapshot_path is not None:
        world_path = snapshot_path
        manifest = manifest_from_snapshot(snapshot_path, args.ic_root.resolve())
        # Spawned Windows workers do not inherit the parent's Python cache.
        # Give them a small, explicit immutable render contract beside the
        # snapshot; it is not a public PASS manifest and is removed on
        # successful completion.
        render_source_path = snapshot_path.with_name("river-v2-building.json")
        render_source_path.write_text(
            json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
        )
    else:
        manifest = json.loads(world_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "project1991.nordstern-world/v1":
        raise RuntimeError("not a Nordstern V1 world package")
    out_dir = world_path.parent / (
        "river_v2_previews" if args.preview else "chunks_river_v2"
    )
    if args.preview and args.preview_tag:
        safe_tag = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in args.preview_tag
        ).strip("_")
        if not safe_tag:
            raise RuntimeError("preview tag contains no usable characters")
        out_dir /= safe_tag
    selected = set(args.chunk) if args.chunk else None
    jobs = chunk_jobs(
        manifest, render_source_path, args.ic_root.resolve(), out_dir,
        int(args.river_seed), selected,
        max(0, min(9, int(args.png_compress_level))),
        bool(args.legacy_water_guard),
        max(0, min(HALO_CELLS, int(args.foundation_internal_halo))),
    )
    jobs = prioritise_jobs(jobs, args.priority_cell, int(manifest["width"]))
    if not jobs:
        raise RuntimeError("no matching chunks selected")
    bundles = bundle_adjacent_jobs(jobs, max(1, int(args.bundle_columns)))

    started = time.perf_counter()
    completed = []
    print(f"river-v2: rendering {len(jobs)} chunk(s), old chunks remain untouched", flush=True)
    with ProcessPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        futures = [pool.submit(render_job_bundle, bundle) for bundle in bundles]
        completed_chunks = 0
        # Priority is a publication contract, not merely a submit hint.  All
        # workers may calculate concurrently, but the chunk containing the
        # true start is awaited and announced first; a faster ocean neighbour
        # must never make the UI claim that the start region is ready.
        publication_order = chain(futures[:1], as_completed(futures[1:]))
        for future in publication_order:
            result, bundle_size = future.result()
            completed.append(result)
            completed_chunks += bundle_size
            records = result[5].get("chunk_records") or [{
                "x": int(result[0]), "y": int(result[1]),
                "cells_w": int(result[2]), "cells_h": int(result[3]),
                "path": str(result[4]), "sha256": str(result[5]["sha256"]),
            }]
            for record in records:
                print("CHUNK_READY:" + json.dumps({
                    "renderer": "river-v2",
                    "authority_fingerprint": manifest["authority"]["fingerprint"],
                    **record,
                }, separators=(",", ":")), flush=True)
            print(
                f"[{completed_chunks:02d}/{len(jobs):02d}] chunk {result[0]},{result[1]}",
                flush=True,
            )

    variant = None if args.preview else write_variant_manifest(
        world_path, manifest, out_dir, int(args.river_seed),
        max(0, min(9, int(args.png_compress_level))),
        max(0, min(HALO_CELLS, int(args.foundation_internal_halo))),
    )
    if snapshot_path is not None and render_source_path.is_file():
        render_source_path.unlink()
    elapsed = time.perf_counter() - started
    stage_names = (
        "foundation_ms", "coast_ms", "water_guard_ms",
        "river_ms", "png_encode_ms", "total_ms",
    )
    timings = [result[5] for result in completed]
    profile = {
        "schema": "history-untold.river-v2-profile/v1",
        "chunks": len(completed),
        "render_jobs": len(completed),
        "output_chunks": len(jobs),
        "bundle_columns": max(1, int(args.bundle_columns)),
        "workers": max(1, int(args.workers)),
        "png_compress_level": max(0, min(9, int(args.png_compress_level))),
        "water_guard": (
            "legacy-full-v79" if args.legacy_water_guard
            else "direct-byte-identical-ground"
        ),
        "foundation_internal_halo": max(
            0, min(HALO_CELLS, int(args.foundation_internal_halo))
        ),
        "wall_seconds": round(elapsed, 3),
        "png_bytes": sum(int(item["png_bytes"]) for item in timings),
        "stages": {
            name: {
                "mean": round(statistics.fmean(float(item[name]) for item in timings), 2),
                "max": round(max(float(item[name]) for item in timings), 2),
            }
            for name in stage_names
        },
    }
    profile_path = out_dir / "generation-profile.json"
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print("PROFILE:river-v2:" + json.dumps(profile, separators=(",", ":")), flush=True)
    if variant is None:
        print(f"river-v2: partial set written to {out_dir} ({elapsed:.1f}s)", flush=True)
    else:
        print(f"river-v2: switchable variant {variant} ({elapsed:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
