# mapgenciv

Standalone extraction of the Civilization I map-generation pipeline used by
History Untold (a Godot/C# Civ1 remake). Generates a
complete, authentic 80x50 Civ1 world (terrain, rivers, hi-res art chunks)
from a seed, ready for a 2D game engine to load.

This is a curated extraction, not a raw dump: the original working tree
spans three separate project trees totalling ~500 MB, most of it dead-end
experimental iterations. This repo contains exactly the ~50 Python files,
~26 data assets and the C# exporter that a real, verified generation run
actually touches (confirmed by instrumenting a live run's file opens and
imports, not by guessing from imports alone).

## Pipeline

```
seed --> [1] OpenCivOneExport (C#)  --> terrain snapshot JSON
      --> [2] generate_world_package.py (Python)  --> art chunks (PNG) + manifest
      --> [3] river_v2 (Python)  --> continuous river rendering pass
```

**[1] Terrain.** `tools/OpenCivOneExport` runs the actual Civ1 map algorithm
via `third_party/OpenCivOne` (Rajko Horvat's MIT-licensed reconstruction of
the original DOS `MapInitAndIntro.cs:F7_0000_0012_GenerateMap()`), and
captures the resulting terrain grid as JSON. `civ1/mapgen.py` is a from-
scratch Python port of the same algorithm, used as an independent
cross-check ("authority") by the hydrology code in step 2 -- both exist
because the terrain has to be right before anything downstream can be.

**[2] Art.** `work/nordstern/tools/generate_world_package.py` reads that
JSON and paints it: continents, coastlines, forests, hills/mountains,
rivers (`work/terrain_lab`, `work/aa_tile_kit_v1`,
`work/river_style_locked_v1`), rendered in parallel chunks.

**[3] Rivers, take 2.** `river_v2/` is a second, independent river renderer
(one continuous weighted field instead of stitched curve segments, no
visible seams at confluences). History Untold uses this output instead of
step 2's river art.

## Requirements

- Python 3.11+ with `numpy`, `Pillow`, `scipy` (`pip install -r requirements.txt`)
- .NET 10 SDK (for `tools/OpenCivOneExport`)

### A note on third_party/OpenCivOne

This is **not** a plain checkout of upstream OpenCivOne -- it is upstream
pinned at commit `2f95a055a8d65957cbe54c24c132acc1ebd6acea` (2026-07-24)
plus a small, documented set of patches that replace its desktop-only
`Window` dependency with a headless `IClassicGameHost` boundary (see
`third_party/OpenCivOne/INTEGRATION_NOTES.md` for the exact patch list).
Building against a fresh clone of upstream `master` will **not** compile as-is;
upstream has since diverged (e.g. `TextBoxDialogues.cs`/`Tools.cs` now
reference the real Avalonia `EditBox`/`MessageBox` windows directly). This
snapshot is committed in full for that reason, rather than as a submodule.

## Build & run

```bash
pip install -r requirements.txt
dotnet build tools/OpenCivOneExport -c Release

python work/nordstern/tools/generate_world_package.py \
    --seed 47111 --land 1 --temp 1 --climate 1 --age 1 \
    --out out/civ_world_47111 --workers 1
```

`--workers 1` is the verified-safe path (confirmed end-to-end on Windows).
Higher worker counts use a `ProcessPoolExecutor` and render ~10x faster when
they work, but weren't fully re-verified after this extraction -- if a
parallel run stalls, fall back to `--workers 1` and please open an issue
with what you saw.

Then, optionally, the second river-rendering pass:

```bash
python river_v2/build_river_v2_variant.py \
    --world out/civ_world_47111/civ_world_47111/world.json \
    --out out/civ_world_47111_river_v2
```

## Configuration

Every path that used to be hardcoded to a specific machine is now an
environment variable with a working default (see each script for the exact
name): `MAPGENCIV_EXPORTER`, `MAPGENCIV_AUTHORITY`, `MAPGENCIV_IC_ROOT`,
`MAPGENCIV_WORLDS_OUT`, `MAPGENCIV_RIVERS_HD`, `MAPGENCIV_RIVER_SOURCES`,
`MAPGENCIV_DEBUG_OUT`, `MAPGENCIV_SELFTEST_SNAPSHOT`.

## License

MIT (see `LICENSE`). `third_party/OpenCivOne` is a separate MIT-licensed
work by Rajko Horvat -- see `third_party/OpenCivOne/LICENSE`.
