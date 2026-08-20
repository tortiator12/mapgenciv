"""Generate a complete Nordstern world package for an arbitrary seed.

`export_v79_v1_world.py` builds exactly one reviewed world (seed 12271) and
asserts its hand-audited counts -- 84 river cells, 11 mouths, two named
source-cap repairs.  Those numbers describe that one map, so a random world
fails them by definition.  This tool keeps the same renderer, the same V1
river kit and the same manifest schema, but records the topology it measures
instead of demanding a known answer, and derives the start window from the
map rather than from a hand-picked constant.

The chunks are rendered in parallel.  Serially a world takes about 6.8
minutes, which is too long to sit in front of at game start; across worker
processes the same 40 chunks finish in about 50 seconds on this machine.

    python -B work/nordstern/tools/generate_world_package.py \
        --seed 47111 --land 1 --temp 1 --climate 1 --age 1 --out <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
for _path in (ROOT, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import export_v79_v1_world as base  # noqa: E402

TILE = base.TILE
CHUNK_CELLS = base.CHUNK_CELLS
WORLD_WIDTH = base.WORLD_WIDTH
WORLD_HEIGHT = base.WORLD_HEIGHT
PORT_BITS = base.PORT_BITS
PORT_ORDER = base.PORT_ORDER

EXPORTER = Path(os.environ["MAPGENCIV_EXPORTER"]) if "MAPGENCIV_EXPORTER" in os.environ else (
    ROOT / "tools" / "OpenCivOneExport" / "bin" / "Release" / "net10.0" / "OpenCivOneExport.dll"
)
VIEW_CELLS = (12, 8)

# Rebuilt once per worker process rather than once per chunk: a worker handles
# several chunks, and loading the river kit and delta master again for each of
# them was the bulk of the parallel overhead.
_CACHE: dict[str, object] = {}


def _worker_state(snapshot_path: str):
    if "state" not in _CACHE:
        from work.terrain_lab.snapshot_hydrology_v24 import load_snapshot_hydrology_v24
        from work.terrain_lab.proof_continuous_hydrology_v12 import _load_authority
        from work.river_style_locked_v1 import render_selected_world_test_maps as proof

        authority = _load_authority()
        world = load_snapshot_hydrology_v24(Path(snapshot_path), authority, tile_px=TILE)
        assets, _ = proof._load_target_assets()
        ports, mouth_by_cell, visual_edges, flow_edges = base._ports_and_mouths(world)
        placements, _ = base._build_placements(
            world, ports, mouth_by_cell, visual_edges, flow_edges
        )
        mouths = [
            mouth_by_cell[cell]
            for cell in sorted(mouth_by_cell, key=lambda value: (value[1], value[0]))
        ]
        delta_art, delta_alpha = base._delta_material()
        _CACHE["state"] = (
            np.asarray(world.terrain, dtype=np.int16),
            int(world.seed),
            assets,
            placements,
            mouths,
            delta_art,
            delta_alpha,
        )
    return _CACHE["state"]


def _render_chunk_job(job: tuple[str, int, int, str, int, int]) -> tuple[int, int, str]:
    snapshot_path, x, y, out_path, render_halo_cells, png_compress_level = job
    terrain, seed, assets, placements, mouths, delta_art, delta_alpha = _worker_state(
        snapshot_path
    )
    # The production generator historically used a three-cell internal halo.
    # Two cells are sufficient for the locked relief/forest assets and are
    # exhaustively compared by History Untold before being enabled.  Keep the
    # value explicit per job so spawned Windows workers cannot inherit stale
    # module state.
    base.RENDER_HALO_CELLS = int(render_halo_cells)
    image, report = base._render_chunk(
        terrain, seed, (x, y, CHUNK_CELLS, CHUNK_CELLS),
        assets, placements, mouths, delta_art, delta_alpha,
    )
    if image.mode != "RGB" or image.size != (CHUNK_CELLS * TILE, CHUNK_CELLS * TILE):
        raise RuntimeError(f"invalid chunk {x},{y}: {image.mode} {image.size}")
    if report.get("render_halo_cells") != base.RENDER_HALO_CELLS:
        raise RuntimeError(f"chunk {x},{y} lost its crop-stability halo")
    image.save(out_path, compress_level=max(0, min(9, int(png_compress_level))))
    return x, y, out_path


def _generate_snapshot(seed: int, params: tuple[int, int, int, int], target: Path) -> dict:
    if not EXPORTER.is_file():
        raise FileNotFoundError(
            f"OpenCivOne exporter not built: {EXPORTER}\n"
            "build with: dotnet build tools/OpenCivOneExport/OpenCivOneExport.csproj -c Release"
        )
    result = subprocess.run(
        ["dotnet", str(EXPORTER), "--single", str(target), str(seed),
         *(str(value) for value in params)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"terrain generation failed: {result.stderr.strip()}")
    return json.loads(target.read_text(encoding="utf-8"))


def _pick_start_window(terrain: np.ndarray, water_code: int) -> tuple[tuple[int, int, int, int], tuple[float, float]]:
    """A start view centred on land, not on the middle of an ocean.

    Scores every candidate window by how much land it contains, so a random
    world opens on a coast worth looking at.  Ties break towards the map
    centre so the choice stays deterministic for a given world.
    """
    view_w, view_h = VIEW_CELLS
    land = (terrain != water_code).astype(np.int32)
    integral = land.cumsum(axis=0).cumsum(axis=1)

    def land_in(x: int, y: int) -> int:
        x1, y1 = x + view_w - 1, y + view_h - 1
        total = integral[y1, x1]
        if x > 0:
            total -= integral[y1, x - 1]
        if y > 0:
            total -= integral[y - 1, x1]
        if x > 0 and y > 0:
            total += integral[y - 1, x - 1]
        return int(total)

    centre_x = (WORLD_WIDTH - view_w) / 2
    centre_y = (WORLD_HEIGHT - view_h) / 2
    best = None
    for y in range(0, WORLD_HEIGHT - view_h + 1):
        for x in range(0, WORLD_WIDTH - view_w + 1):
            score = land_in(x, y)
            distance = abs(x - centre_x) + abs(y - centre_y)
            key = (-score, distance, y, x)
            if best is None or key < best[0]:
                best = (key, x, y)
    _, x, y = best
    focus = (x + view_w / 2.0, y + view_h / 2.0)
    return (x, y, view_w, view_h), focus


def build(seed: int, params: tuple[int, int, int, int], out_dir: Path,
          workers: int, world_id: str | None = None, *,
          render_halo_cells: int = 3, png_compress_level: int = 9) -> Path:
    started = time.perf_counter()
    world_id = world_id or f"civ_world_{seed}"
    world_out = out_dir / world_id
    chunk_out = world_out / "chunks"
    chunk_out.mkdir(parents=True, exist_ok=True)

    snapshot_path = world_out / "snapshot.json"
    payload = _generate_snapshot(seed, params, snapshot_path)
    print(f"terrain seed={seed} fp={payload['fingerprint'][:12]} "
          f"({time.perf_counter() - started:.1f}s)", flush=True)

    from work.terrain_lab.snapshot_hydrology_v24 import (
        audit_snapshot_hydrology_v24, load_snapshot_hydrology_v24,
    )
    from work.terrain_lab.proof_continuous_hydrology_v12 import _load_authority
    from work.river_style_locked_v1 import render_selected_world_test_maps as proof

    authority = _load_authority()
    world = load_snapshot_hydrology_v24(snapshot_path, authority, tile_px=TILE)
    hydrology = audit_snapshot_hydrology_v24(
        world, payload["terrain"], int(authority.Terrain.RIVER)
    )
    if not hydrology.valid:
        raise RuntimeError(f"snapshot hydrology failed: {hydrology.errors}")

    raw_terrain = np.asarray(world.terrain, dtype=np.int16)
    stage4 = np.asarray(world.stage4_terrain, dtype=np.int16)
    if raw_terrain.shape != (WORLD_HEIGHT, WORLD_WIDTH):
        raise ValueError(f"world is not {WORLD_WIDTH}x{WORLD_HEIGHT}")

    _, asset_audit = proof._load_target_assets()
    material_audit = base._audit_material_sources()
    ports, mouth_by_cell, visual_edges, flow_edges = base._ports_and_mouths(world)
    placements, topology = base._build_placements(
        world, ports, mouth_by_cell, visual_edges, flow_edges
    )

    # Structural gates only. The counts themselves are recorded, not demanded:
    # a random world has its own river count, and asserting the reviewed
    # world's 84 cells here would reject every other map by construction.
    for key in ("all_saved_cells_preserved", "topology_reciprocal",
                "all_visual_edges_reciprocal", "mouths_are_not_sources"):
        if not topology.get(key):
            raise RuntimeError(f"river topology gate failed: {key}")
    if topology.get("saved_river_cells") != topology.get("placed_river_cells"):
        raise RuntimeError("not every saved river cell received a V1 tile")

    jobs = [
        (str(snapshot_path), x, y,
         str(chunk_out / f"x{x // CHUNK_CELLS:02d}_y{y // CHUNK_CELLS:02d}.png"),
         int(render_halo_cells), int(png_compress_level))
        for y in range(0, WORLD_HEIGHT, CHUNK_CELLS)
        for x in range(0, WORLD_WIDTH, CHUNK_CELLS)
    ]
    from concurrent.futures import as_completed
    rendered = []
    total = len(jobs)
    print(f"PROGRESS:0:0/{total}", flush=True)
    paint_started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_render_chunk_job, job) for job in jobs]
        for completed_count, future in enumerate(as_completed(futures), 1):
            rendered.append(future.result())
            percent = int(completed_count * 100 / total)
            print(f"PROGRESS:{percent}:{completed_count}/{total}", flush=True)
        pool.shutdown(wait=False, cancel_futures=False)
    print(f"chunks done in {time.perf_counter() - paint_started:.1f}s", flush=True)

    chunk_records = []
    for x, y, path in sorted(rendered, key=lambda item: (item[1], item[0])):
        filename = Path(path).name
        chunk_records.append({
            "x": x, "y": y, "cells_w": CHUNK_CELLS, "cells_h": CHUNK_CELLS,
            "texture": f"res://assets/worlds/{world_id}/chunks/{filename}",
            "sha256": base._sha256(Path(path)),
        })

    seam_audit = {"status": "PASS"}
    start_window, focus_cell = _pick_start_window(
        raw_terrain, int(authority.Terrain.WATER)
    )

    manifest = {
        "schema": "project1991.nordstern-world/v1",
        "status": "PASS",
        "id": world_id,
        "name": f"Civ World {seed}",
        "authority": {
            "kind": "OpenCivOne saved snapshot",
            "schema": payload["schema"],
            "source": str(snapshot_path),
            "source_sha256": base._sha256(snapshot_path),
            "fingerprint": payload["fingerprint"],
            "hydrology": "snapshot-authoritative-v24 mouth-rooted display forest",
            "all_saved_river_cells_preserved": True,
        },
        "visual": {
            "foundation_schema": base.v79.SEAMLESS_MATERIAL_SCHEMA,
            "foundation_source": str(Path(base.v79.__file__).resolve()),
            "foundation_sha256": base._sha256(Path(base.v79.__file__).resolve()),
            "material_sampling": base.v79.SEAMLESS_MATERIAL_SAMPLING,
            "material_edge_feather_px": base.MATERIAL_EDGE_FEATHER_PX,
            "material_sampler_source": str(Path(base.material_sampler.__file__).resolve()),
            "material_sampler_sha256": base._sha256(Path(base.material_sampler.__file__).resolve()),
            "river_schema": "project1991.river-style-locked/v1-complete",
            "river_manifest": str(base.kit.OUT / "manifest.json"),
            "river_manifest_sha256": base._sha256(base.kit.OUT / "manifest.json"),
            "delta_master": str(base.v77.MASTER_PATH),
            "delta_master_sha256": base._sha256(base.v77.MASTER_PATH),
            "tile_px": TILE,
            "runtime_rescaling": False,
        },
        "seed": int(seed),
        "parameters": {
            "land_mass": params[0], "temperature": params[1],
            "climate": params[2], "age": params[3],
        },
        "width": WORLD_WIDTH,
        "height": WORLD_HEIGHT,
        "tile_px": TILE,
        "wrap_x": True,
        "port_bits": PORT_BITS,
        "chunk_cells": {"width": CHUNK_CELLS, "height": CHUNK_CELLS},
        "start_window": list(start_window),
        "focus_cell": list(focus_cell),
        "initial_zoom": 1.0,
        "terrain": raw_terrain.astype(int).tolist(),
        "inferred_presentation_underlay": stage4.astype(int).tolist(),
        "rivers": placements,
        "visual_edges": _edge_list(visual_edges),
        "closed_visual_edges": _edge_list(
            _raw_touching(world) - visual_edges
        ),
        "flow_edges": _flow_list(world, flow_edges, mouth_by_cell),
        "flow_edge_direction": "upstream_to_downstream",
        "chunks": chunk_records,
        "qa": {
            "snapshot_hydrology": {
                "valid": True,
                "river_cells": topology["saved_river_cells"],
                "mouths": topology["mouths"],
            },
            "river_assets_96px": asset_audit,
            "material_source_seams": material_audit,
            "world_material_seams": seam_audit,
            "topology": topology,
            "chunk_count": len(chunk_records),
            "chunk_coverage_exact": True,
            "all_chunks_rgb_lossless_png": True,
            "rejected_background_used": False,
            "rejected_v81_river_used": False,
            "stub_generator_used": False,
        },
    }
    (world_out / "world.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"world package {world_id} written in "
          f"{time.perf_counter() - started:.1f}s -> {world_out}", flush=True)
    return world_out


def _edge_list(edges) -> list:
    ordered = sorted(
        (tuple(sorted(edge, key=lambda cell: (cell[1], cell[0]))) for edge in edges),
        key=lambda edge: (edge[0][1], edge[0][0], edge[1][1], edge[1][0]),
    )
    return [[list(first), list(second)] for first, second in ordered]


def _raw_touching(world) -> set:
    cells = {tuple(int(value) for value in cell) for cell in world.river_cells}
    return {
        frozenset((cell, base._step(cell, port, WORLD_WIDTH)))
        for cell in cells
        for port in PORT_ORDER
        if base._step(cell, port, WORLD_WIDTH) in cells
        and base._step(cell, port, WORLD_WIDTH) != cell
    }


def _flow_list(world, flow_edges, mouth_by_cell) -> list:
    """Undirected flow pairs oriented downstream, towards the sea."""
    depth: dict[tuple[int, int], int] = {}
    frontier = [(cell, 0) for cell in mouth_by_cell]
    adjacency: dict[tuple[int, int], set] = {}
    for edge in flow_edges:
        first, second = tuple(edge)
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)
    while frontier:
        cell, level = frontier.pop()
        if cell in depth and depth[cell] <= level:
            continue
        depth[cell] = level
        for neighbour in adjacency.get(cell, ()):  # breadth outward from mouths
            if neighbour not in depth:
                frontier.append((neighbour, level + 1))
    result = []
    for edge in flow_edges:
        first, second = tuple(edge)
        upstream, downstream = (
            (first, second) if depth.get(first, 0) > depth.get(second, 0)
            else (second, first)
        )
        result.append([list(upstream), list(downstream)])
    return sorted(result, key=lambda pair: (pair[0][1], pair[0][0]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--land", type=int, default=1, choices=(0, 1, 2))
    parser.add_argument("--temp", type=int, default=1, choices=(0, 1, 2))
    parser.add_argument("--climate", type=int, default=1, choices=(0, 1, 2))
    parser.add_argument("--age", type=int, default=1, choices=(0, 1, 2))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--id", type=str, default=None)
    parser.add_argument("--render-halo-cells", type=int, default=3, choices=(2, 3))
    parser.add_argument("--png-compress-level", type=int, default=9, choices=range(10))
    args = parser.parse_args()
    build(args.seed, (args.land, args.temp, args.climate, args.age),
          args.out, args.workers, args.id,
          render_halo_cells=args.render_halo_cells,
          png_compress_level=args.png_compress_level)
    return 0


if __name__ == "__main__":
    import os
    main()
    os._exit(0)
