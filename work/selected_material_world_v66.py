from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MAPGEN_PATH = Path(os.environ.get("MAPGENCIV_AUTHORITY", str(ROOT / "civ1" / "mapgen.py")))
MASTER_PATH = ROOT / "outputs" / "coast-first-outlet-balloon-v56" / "mouth-metatile-3x2-selected-v1.png"
OUTPUT = ROOT / "outputs" / "coast-first-outlet-balloon-v56"
MATERIAL_ROOT = ROOT / "work" / "aa_tile_kit_v1" / "assets" / "materials"
SEED = 25378
TILE = 96
CROP = (12, 8, 7, 6)
MOUTH_CELL = (15, 11)
VERSION = "v73"
VIEW_TAG = ""
DELTA_MAX_SEA_FRACTION = 1.0 / 3.0
DELTA_NECK_OVERLAP_PX = 14.0
EXIT_VECTOR = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}
ROTATE_FROM_SOUTH = {
    "south": 0,
    "east": 90,
    "north": 180,
    "west": 270,
}


def _load_mapgen():
    spec = importlib.util.spec_from_file_location("production_mapgen_v66", MAPGEN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {MAPGEN_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _font(size: int, bold: bool = False):
    names = ("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")
    for name in names:
        path = Path(r"C:\Windows\Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _mirrored_tile(source: Image.Image, size: int = 512) -> np.ndarray:
    source = source.convert("RGB").resize((size // 2, size // 2), Image.Resampling.LANCZOS)
    array = np.asarray(source)
    top = np.concatenate((array, array[:, ::-1]), axis=1)
    tile = np.concatenate((top, top[::-1]), axis=0)
    return tile.astype(np.float32)


def _sample(tile: np.ndarray, world_x: np.ndarray, world_y: np.ndarray) -> np.ndarray:
    height, width = tile.shape[:2]
    return tile[np.mod(world_y, height), np.mod(world_x, width)]


def _master_palette(master: Image.Image) -> tuple[tuple[int, int, int, int], ...]:
    """Measure the authored inlet instead of hand-guessing a second river style."""

    rgb = np.asarray(master.convert("RGB"), dtype=np.int16)
    yy, xx = np.mgrid[0:master.height, 0:master.width]
    centre = master.width * 0.5
    inlet = (yy < master.height * 0.42) & (np.abs(xx - centre) < master.width * 0.12)
    water = inlet & (rgb[..., 2] > rgb[..., 0] + 18) & (rgb[..., 1] > rgb[..., 0] + 8)
    if not np.any(water):
        raise AssertionError("selected master inlet water could not be measured")
    # Colour authority comes from the visibly better funnel arms, not from the
    # darker narrow inlet painted above them.
    fan = (
        (yy > master.height * 0.31)
        & (yy < master.height * 0.64)
        & (np.abs(xx - centre) < master.width * 0.35)
        & (rgb[..., 2] > rgb[..., 0] + 15)
        & (rgb[..., 1] > rgb[..., 0] + 7)
        & (rgb[..., 2] > 65)
    )
    water_pixels = rgb[fan] if np.any(fan) else rgb[water]
    core = tuple(int(v) for v in np.percentile(water_pixels, 50, axis=0)) + (255,)
    highlight = tuple(int(v) for v in np.percentile(water_pixels, 75, axis=0)) + (220,)

    water_image = Image.fromarray(np.uint8(water) * 255, "L")
    near = np.asarray(water_image.filter(ImageFilter.MaxFilter(17)), dtype=np.uint8) > 0
    warm = (
        inlet
        & near
        & (rgb[..., 0] > rgb[..., 1] + 3)
        & (rgb[..., 1] > rgb[..., 2] + 18)
        & (rgb[..., 0] > rgb[..., 2] + 34)
    )
    bank_pixels = rgb[warm]
    bank_rgb = np.percentile(bank_pixels, 48, axis=0) if len(bank_pixels) else np.array((170, 132, 55))
    bank = tuple(int(v) for v in bank_rgb) + (230,)
    dark_edge = tuple(max(0, int(v * factor)) for v, factor in zip(core[:3], (0.72, 0.78, 0.80))) + (255,)
    return bank, dark_edge, core, highlight


def _meander_route(
    points: list[tuple[int, int]],
    *,
    seed: int | None = None,
) -> list[tuple[int, int]]:
    """Add continuous sub-cell bends without moving either terminal anchor."""

    if len(points) < 5:
        return points
    values = np.asarray(points, dtype=np.float64)
    delta = np.diff(values, axis=0, prepend=values[:1])
    distance = np.hypot(delta[:, 0], delta[:, 1])
    station = np.cumsum(distance)
    tangent = np.gradient(values, axis=0)
    tangent_length = np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-6)
    normal = np.stack((-tangent[:, 1], tangent[:, 0]), axis=1) / tangent_length[:, None]
    phase = (SEED if seed is None else int(seed)) * 0.0173
    offset = (
        6.2 * np.sin(station * (2.0 * np.pi / 118.0) + phase)
        + 2.1 * np.sin(station * (2.0 * np.pi / 53.0) - phase * 0.61)
    )
    # Exact anchors: source taper and delta neck never drift off their ports.
    start_fade = np.clip(station / 18.0, 0.0, 1.0)
    end_fade = np.clip((station[-1] - station) / 28.0, 0.0, 1.0)
    fitted = values + normal * (offset * start_fade * end_fade)[:, None]
    fitted[0] = values[0]
    fitted[-1] = values[-1]
    return [(int(round(x)), int(round(y))) for x, y in fitted]


def _delta_semantic_alpha(master: Image.Image) -> Image.Image:
    """Keep authored delta/river semantics, never the master's rectangular coast plate."""

    rgb = np.asarray(master.convert("RGB"), dtype=np.int16)
    yy, xx = np.mgrid[0:master.height, 0:master.width]
    centre = master.width * 0.5
    tile = master.width / 3.0
    coast_y = tile

    blue = (
        (rgb[..., 2] > rgb[..., 0] + 15)
        & (rgb[..., 1] > rgb[..., 0] + 7)
        & (rgb[..., 2] > 65)
    )
    # The envelope is narrow at the exact upstream port and opens only inside
    # the final land half-tile / first sea half-tile.  Ordinary side coastline
    # is excluded, so there can be only one global coast contour.
    fan_t = np.clip((yy - tile * 0.28) / (tile * 1.18), 0.0, 1.0)
    half_width = tile * (0.12 + 0.78 * fan_t)
    envelope = np.abs(xx - centre) <= half_width
    vertical = (yy <= coast_y + tile * 0.50)
    authored_water = blue & envelope & vertical

    water_image = Image.fromarray(np.uint8(authored_water) * 255, "L")
    near_water = np.asarray(water_image.filter(ImageFilter.MaxFilter(19)), dtype=np.uint8) > 0
    warm = (
        (rgb[..., 0] > rgb[..., 1] + 3)
        & (rgb[..., 1] > rgb[..., 2] + 18)
        & (rgb[..., 0] > rgb[..., 2] + 34)
        & (rgb[..., 0] > 105)
    )
    sediment = warm & near_water & envelope & vertical
    semantic = authored_water | sediment

    # Soft peripheral dissolve, but the upstream neck itself stays opaque.
    edge_distance = half_width - np.abs(xx - centre)
    side_feather = np.clip(edge_distance / 12.0, 0.0, 1.0)
    sea_fade = np.clip((coast_y + tile * 0.50 - yy) / 12.0, 0.0, 1.0)
    alpha = semantic.astype(np.float32) * side_feather * sea_fade
    inlet = (yy < 18) & (np.abs(xx - centre) < tile * 0.12) & semantic
    alpha[inlet] = 1.0
    return Image.fromarray(np.uint8(np.round(alpha * 255.0)), "L").filter(
        ImageFilter.GaussianBlur(1.05)
    )


def _limit_delta_offshore(alpha: Image.Image, tile_px: int, fraction: float) -> Image.Image:
    """Keep the fan on land plus at most a fixed fraction of one sea cell."""
    if not 0.0 < fraction <= 0.5:
        raise ValueError("delta offshore fraction must be in (0, 0.5]")
    values = np.asarray(alpha.convert("L"), dtype=np.float32)
    yy = np.arange(values.shape[0], dtype=np.float32)[:, None]
    limit = tile_px * (1.0 + fraction)
    feather = max(6.0, tile_px * 0.10)
    keep = 1.0 - np.clip((yy - (limit - feather)) / feather, 0.0, 1.0)
    return Image.fromarray(np.uint8(np.clip(np.round(values * keep), 0.0, 255.0)), "L")


def _fit_selected_delta_vertical(
    master: Image.Image,
    tile_px: int | None = None,
) -> Image.Image:
    """Anchor the locked master: split at 0.50 land tile, coast at tile edge.

    In the selected painting the first visible branch split is around row 72
    and its authored coast around row 112 after scaling to 3x2 @ 96 px.  A
    piecewise monotone vertical fit moves those two semantic anchors to rows
    48 and 96 without rotating or shearing the delta.
    """

    tile_px = TILE if tile_px is None else int(tile_px)
    source = np.asarray(master.convert("RGB"), dtype=np.float32)
    height, width = source.shape[:2]
    if (width, height) != (3 * tile_px, 2 * tile_px):
        raise ValueError("selected delta vertical fit expects the locked 3x2 size")
    dst_y = np.arange(height, dtype=np.float32)
    src_y = np.interp(
        dst_y,
        np.array((0.0, tile_px * 0.50, float(tile_px), float(height - 1)), np.float32),
        np.array((0.0, tile_px * 0.75, tile_px * (112.0 / 96.0), float(height - 1)), np.float32),
    )
    y0 = np.floor(src_y).astype(np.int32)
    y1 = np.minimum(y0 + 1, height - 1)
    t = (src_y - y0)[:, None, None]
    fitted = source[y0] * (1.0 - t) + source[y1] * t
    return Image.fromarray(np.uint8(np.clip(np.round(fitted), 0, 255)), "RGB")


def _oriented_delta(
    art: Image.Image,
    alpha: Image.Image,
    exit_port: str,
    tile_px: int,
) -> tuple[Image.Image, tuple[int, int]]:
    """Rotate the locked south master around its exact half-tile split.

    A transparent 4x4-cell carrier keeps the split at one immutable centre for
    all four cardinal exits.  The south result is pixel-identical to the old
    placement; only its transparent canvas is larger.  No landscape pixel is
    generated here.
    """

    if exit_port not in ROTATE_FROM_SOUTH:
        raise ValueError(f"unsupported Civ river exit port: {exit_port!r}")
    rgba = art.convert("RGBA")
    rgba.putalpha(alpha.convert("L"))
    canvas = Image.new("RGBA", (4 * tile_px, 4 * tile_px), (0, 0, 0, 0))
    # South master: split=(1.5T,.5T). Placing at (.5T,1.5T) moves it to
    # the carrier centre=(2T,2T), which is the logical river-cell centre.
    canvas.alpha_composite(rgba, (tile_px // 2, 3 * tile_px // 2))
    angle = ROTATE_FROM_SOUTH[exit_port]
    if angle:
        canvas = canvas.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
    return canvas, (2 * tile_px, 2 * tile_px)


def _edge_feather(width: int, height: int, feather: int = 14) -> Image.Image:
    yy, xx = np.mgrid[0:height, 0:width]
    distance = np.minimum.reduce((xx, width - 1 - xx, yy, height - 1 - yy)).astype(np.float32)
    alpha = np.clip(distance / float(feather), 0.0, 1.0)
    alpha = alpha * alpha * (3.0 - 2.0 * alpha)
    inlet = (np.abs(xx - width * 0.5) <= width * 0.07) & (yy <= feather + 4)
    alpha[inlet] = 1.0
    return Image.fromarray(np.uint8(np.round(alpha * 255.0)), "L")


def _terrain_tint(code: int) -> np.ndarray:
    # Civ terrain remains authoritative; these are restrained colour families,
    # not new terrain classification.
    return {
        0: np.array((1.18, 0.92, 0.48), np.float32),  # desert
        1: np.array((1.04, 0.96, 0.73), np.float32),  # plains
        2: np.array((1.00, 1.00, 1.00), np.float32),  # grass
        3: np.array((0.76, 0.86, 0.70), np.float32),  # forest ground
        4: np.array((0.92, 0.98, 0.86), np.float32),  # green hills
        5: np.array((0.83, 0.88, 0.80), np.float32),  # mountain ground
        6: np.array((0.95, 0.96, 0.82), np.float32),  # tundra
        7: np.array((1.16, 1.16, 1.11), np.float32),  # arctic
        8: np.array((0.73, 0.87, 0.67), np.float32),  # swamp
        9: np.array((0.67, 0.83, 0.58), np.float32),  # jungle ground
        11: np.array((1.00, 1.00, 1.00), np.float32), # river owns land below
    }.get(int(code), np.ones(3, np.float32))


def _grid(image: Image.Image, tile_px: int | None = None) -> Image.Image:
    tile_px = TILE if tile_px is None else int(tile_px)
    result = image.copy()
    draw = ImageDraw.Draw(result, "RGBA")
    for x in range(0, result.width + 1, tile_px):
        draw.line((x, 0, x, result.height), fill=(20, 235, 225, 200), width=2)
    for y in range(0, result.height + 1, tile_px):
        draw.line((0, y, result.width, y), fill=(20, 235, 225, 200), width=2)
    return result


def _system_path(mouth: dict, world_width: int = 80) -> list[tuple[int, int]]:
    cells = {tuple(cell) for cell in mouth["river_cells"]}
    start = tuple(mouth["river_cell"])
    queue = [start]
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    for cell in queue:
        x, y = cell
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            neighbour = ((x + dx) % int(world_width), y + dy)
            if neighbour in cells and neighbour not in parent:
                parent[neighbour] = cell
                queue.append(neighbour)
    endpoint = max(parent, key=lambda cell: (len(_backtrack(parent, cell)), -cell[1], -cell[0]))
    path = _backtrack(parent, endpoint)
    # _backtrack already returns farthest inland River cell -> mouth.
    return path


def _backtrack(parent, cell):
    path = []
    current = cell
    while current is not None:
        path.append(current)
        current = parent[current]
    return path


def _catmull_rom(points: list[tuple[float, float]], samples_per_segment: int = 22):
    if len(points) < 2:
        return points
    padded = [points[0], *points, points[-1]]
    result: list[tuple[int, int]] = []
    for index in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[index - 1:index + 3]
        for sample in range(samples_per_segment):
            t = sample / samples_per_segment
            t2, t3 = t * t, t * t * t
            x = 0.5 * (
                2.0 * p1[0]
                + (-p0[0] + p2[0]) * t
                + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                2.0 * p1[1]
                + (-p0[1] + p2[1]) * t
                + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
            )
            result.append((int(round(x)), int(round(y))))
    result.append((int(round(points[-1][0])), int(round(points[-1][1]))))
    return result


def _paint_system_river(
    image: Image.Image,
    mouth: dict,
    crop_x: int,
    crop_y: int,
    palette: tuple[tuple[int, int, int, int], ...],
    sand_texture: np.ndarray,
    ocean_texture: np.ndarray,
    *,
    tile_px: int | None = None,
    seed: int | None = None,
    world_width: int = 80,
    crop_width: int | None = None,
):
    tile_px = TILE if tile_px is None else int(tile_px)
    seed = SEED if seed is None else int(seed)
    route_cells = _system_path(mouth, world_width=world_width)
    world_points: list[tuple[float, float]] = []

    crop_width = image.width // tile_px if crop_width is None else int(crop_width)
    crop_centre_x = crop_x + crop_width * 0.5

    def unwrap_x(x: int) -> float:
        candidates = (x - world_width, x, x + world_width)
        return float(min(candidates, key=lambda value: abs(value - crop_centre_x)))

    # The highland source is metadata, not inferred from the finished bitmap.
    source_cells = [tuple(cell) for cell in mouth.get("source_cells", ())]
    if source_cells:
        source = source_cells[0]
        world_points.append(((unwrap_x(source[0]) + 0.5) * tile_px, (source[1] + 0.5) * tile_px))
    for index, (x, y) in enumerate(route_cells):
        # Small deterministic sub-cell offsets break the cardinal centre rhythm
        # while preserving the authoritative cell sequence and mouth port.
        if index == len(route_cells) - 1:
            offset_x = offset_y = 0.0
        else:
            offset_x = (((x * 17 + y * 11 + seed) % 9) - 4) * 1.25
            offset_y = (((x * 7 + y * 19 + seed) % 9) - 4) * 1.10
        world_points.append(((unwrap_x(x) + 0.5) * tile_px + offset_x, (y + 0.5) * tile_px + offset_y))

    local_points = [
        (x - crop_x * tile_px, y - crop_y * tile_px)
        for x, y in world_points
    ]
    route = _meander_route(_catmull_rom(local_points), seed=seed)
    bank, dark_edge, core, highlight = palette

    def line_mask(width: int, blur: float = 0.0) -> Image.Image:
        """Render one continuous river body with slow component-wide width drift.

        The old constant-width line was technically clean but read like a
        manufactured pipe.  Width now varies at world scale, while the source
        taper and the final delta neck are locked to their exact contracts.
        Dense round joins prevent the saw-tooth edge produced by per-segment
        hard width changes.
        """

        scale = 4
        mask_hi = Image.new("L", (image.width * scale, image.height * scale), 0)
        draw_mask = ImageDraw.Draw(mask_hi)
        taper_samples = min(18, max(1, len(route) - 1))
        mask_route = list(route)
        # The painted fan has its first visible branch a few pixels below the
        # mathematical split anchor.  A short straight overlap keeps the
        # normal river at full width until the authored arms actually divide.
        # It remains well inside the final land half-tile.
        if mask_route:
            neck_overlap_px = DELTA_NECK_OVERLAP_PX
            dx, dy = EXIT_VECTOR[mouth["exit_port"]]
            mask_route.append(
                (
                    mask_route[-1][0] + dx * neck_overlap_px,
                    mask_route[-1][1] + dy * neck_overlap_px,
                )
            )
        scaled_route = [
            (int(round(point[0] * scale)), int(round(point[1] * scale)))
            for point in mask_route
        ]
        values = np.asarray(mask_route, dtype=np.float64)
        if len(values) < 2:
            return mask_hi.resize(image.size, Image.Resampling.LANCZOS)
        distances = np.hypot(
            np.diff(values[:, 0], prepend=values[0, 0]),
            np.diff(values[:, 1], prepend=values[0, 1]),
        )
        station = np.cumsum(distances)
        total = max(float(station[-1]), 1.0)
        phase = seed * 0.0137 + width * 0.071
        slow = (
            0.055 * np.sin(station * (2.0 * np.pi / 181.0) + phase)
            + 0.025 * np.sin(station * (2.0 * np.pi / 79.0) - phase * 0.43)
        )
        # Both terminal contracts are exact: the spring begins as a fine
        # runnel and the final 32 px reach the authored delta at nominal width.
        source_taper = np.clip(station / 24.0, 0.0, 1.0)
        source_factor = 0.22 + 0.78 * source_taper
        neck_lock = np.clip((total - station) / 32.0, 0.0, 1.0)
        width_factor = (1.0 + slow * neck_lock) * source_factor
        width_factor[-1] = 1.0

        widths_hi = np.maximum(
            2,
            np.round(width * scale * width_factor).astype(np.int32),
        )
        for index in range(len(scaled_route) - 1):
            segment_width = int(round((widths_hi[index] + widths_hi[index + 1]) * 0.5))
            draw_mask.line(
                (scaled_route[index], scaled_route[index + 1]),
                fill=255,
                width=max(2, segment_width),
            )
            # Interior round joins keep the curve smooth.  The terminal point
            # deliberately has no round cap: it must meet the authored delta
            # as a flat, full-width pipe-to-funnel neck at the half-tile mark.
            if index + 1 < len(scaled_route) - 1:
                px, py = scaled_route[index + 1]
                radius = widths_hi[index + 1] * 0.5
                draw_mask.ellipse(
                    (px - radius, py - radius, px + radius, py + radius),
                    fill=255,
                )
        mask = mask_hi.resize(image.size, Image.Resampling.LANCZOS)
        return mask.filter(ImageFilter.GaussianBlur(blur)) if blur else mask

    bank_rgb = np.asarray(bank[:3], dtype=np.float32)
    core_rgb = np.asarray(core[:3], dtype=np.float32)
    highlight_rgb = np.asarray(highlight[:3], dtype=np.float32)

    def opacity_mask(mask: Image.Image, strength: float) -> Image.Image:
        alpha = np.asarray(mask, dtype=np.float32) * float(strength)
        return Image.fromarray(np.uint8(np.clip(np.round(alpha), 0, 255)), "L")

    river_base = ocean_texture * 0.30 + core_rgb * 0.50 + highlight_rgb * 0.20
    river_glaze = ocean_texture * 0.16 + core_rgb * 0.34 + highlight_rgb * 0.50
    textured_layers = (
        # No dark parallel outline: the same warm coast sand meets the water
        # directly, as in the selected delta painting.  A two-pixel damp-sand
        # transition and a translucent turquoise glaze provide depth without
        # reintroducing a road-like centre line.
        (sand_texture * 0.84 + bank_rgb * 0.16, line_mask(28, 0.38)),
        (sand_texture * 0.58 + bank_rgb * 0.42, line_mask(24, 0.30)),
        (river_base, line_mask(20, 0.22)),
        (river_glaze, opacity_mask(line_mask(15, 0.30), 0.56)),
    )

    def composite_texture(texture: np.ndarray, mask: Image.Image) -> None:
        destination = np.asarray(image, dtype=np.float32)
        alpha = np.asarray(mask, dtype=np.float32)[..., None] / 255.0
        mixed = destination * (1.0 - alpha) + np.clip(texture, 0.0, 255.0) * alpha
        image.paste(Image.fromarray(np.uint8(np.clip(np.round(mixed), 0, 255)), "RGB"))

    for texture, mask in textured_layers:
        composite_texture(texture, mask)

    return route_cells


def main() -> Path:
    sys.path.insert(0, str(ROOT))
    from work.aa_tile_kit_v1.materials import WorldMaterialSampler
    from work.aa_tile_kit_v1.coast_v2 import PixelWindow
    from work.aa_tile_kit_v1.coast_v3 import CoastV31Config, TangentGlobalCoast
    from work.terrain_lab.contract import TransitionContext
    from work.terrain_lab.ground_corner_lattice_v51 import make_weight_renderer_v51
    from work.terrain_lab.relief_component_art_v44 import render_relief_component_art_v44
    from work.aa_tile_kit_v1.forest_render_v4 import render_forest_regions_v4
    from work.aa_tile_kit_v1.hill_nesw_renderer_v2 import render_hill_nesw_v2

    mapgen = _load_mapgen()
    grid, metadata = mapgen.generate_with_metadata(SEED)
    logical = np.asarray(grid, dtype=np.int16)
    land = logical != int(mapgen.Terrain.WATER)

    crop_x, crop_y, crop_w, crop_h = CROP
    window = PixelWindow(crop_x * TILE, crop_y * TILE, crop_w * TILE, crop_h * TILE)
    coast = TangentGlobalCoast(
        CoastV31Config(tile_px=TILE, contour_seed=SEED)
    ).build(land, window=window)

    master = Image.open(MASTER_PATH).convert("RGB")
    art = _fit_selected_delta_vertical(
        master.resize((3 * TILE, 2 * TILE), Image.Resampling.LANCZOS)
    )
    alpha = _limit_delta_offshore(
        _delta_semantic_alpha(art), TILE, DELTA_MAX_SEA_FRACTION
    )
    palette = _master_palette(art)
    world_period = int(mapgen.MAP_W) * TILE

    def sample_material(filename: str) -> np.ndarray:
        source = Image.open(MATERIAL_ROOT / filename).convert("RGBA")
        sampled = WorldMaterialSampler(
            source,
            world_period_x=world_period,
        ).sample(window.x, window.y, window.width, window.height)
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

    # Civ-III-style corner grammar: materials meet through shared four-corner
    # weights rather than hard rectangular cell fills.  Forest/Hill/Mountain
    # cells retain the common grass underlay and receive their objects later.
    visible_x = np.mod(np.arange(crop_x, crop_x + crop_w), mapgen.MAP_W)
    visible_grid = logical[crop_y : crop_y + crop_h][:, visible_x]
    context = TransitionContext(
        material_grid=visible_grid,
        tile_px=TILE,
        transition_px=14,
        world_x0=crop_x,
        world_y0=crop_y,
        world_width=mapgen.MAP_W,
        seed=SEED,
    )
    weights = make_weight_renderer_v51(logical)(context)
    land_material = np.zeros_like(grass, dtype=np.float32)
    for code, weight in weights.items():
        source = material_samples.get(int(code), grass)
        land_material += source * weight[..., None]

    coverage = coast.land_coverage[..., None]
    image = ocean * (1.0 - coverage) + land_material * coverage
    turquoise = np.array((13.0, 139.0, 159.0), np.float32)
    shallow_material = ocean * 0.30 + turquoise * 0.70
    shallow = coast.shallow[..., None] * (1.0 - coverage)
    image = image * (1.0 - shallow) + shallow_material * shallow
    beach = coast.beach[..., None]
    image = image * (1.0 - beach) + coast_sand * beach
    foam = coast.foam[..., None] * 0.68
    image = image * (1.0 - foam) + np.array((226.0, 238.0, 218.0), np.float32) * foam
    base = Image.fromarray(np.uint8(np.clip(image, 0, 255)), "RGB")

    # Locked landscape art: Civ cell ownership stays exact, while V44 relief
    # may project north as 2.5D silhouette and V4.1 woodland uses immutable
    # per-cell feet plus component-wide understory.  Rivers are painted after
    # these layers so no projected sprite can hide their rule-critical path.
    landscape = base.convert("RGBA")
    mountain_grid = logical.copy()
    mountain_grid[mountain_grid == 4] = 2
    relief_records = render_relief_component_art_v44(
        landscape,
        mountain_grid,
        seed=SEED,
        window=CROP,
        tile_px=TILE,
        world_width=mapgen.MAP_W,
    )
    hill_report = render_hill_nesw_v2(
        landscape,
        logical,
        window=CROP,
        tile_px=TILE,
        world_width=mapgen.MAP_W,
        seed=SEED,
        shoulder_opacity=0.58,
    )
    forest_report = render_forest_regions_v4(
        landscape,
        logical,
        seed=SEED,
        window=CROP,
        tile_px=TILE,
        world_width=mapgen.MAP_W,
    )
    base = landscape.convert("RGB")

    mouth = next(item for item in metadata["river_mouths"] if item["river_cell"] == MOUTH_CELL)
    delta, delta_anchor = _oriented_delta(art, alpha, mouth["exit_port"], TILE)
    mouth_centre = (
        (mouth["river_cell"][0] + 0.5 - crop_x) * TILE,
        (mouth["river_cell"][1] + 0.5 - crop_y) * TILE,
    )
    left = int(round(mouth_centre[0] - delta_anchor[0]))
    top = int(round(mouth_centre[1] - delta_anchor[1]))
    beauty = base.copy()
    # The selected semantic delta goes down first.  Then the measured normal
    # river brush is painted through to the exact half-tile split anchor.  This
    # guarantees one continuous full-width neck instead of a narrow pasted cap.
    if beauty.mode == "RGBA":
        beauty.alpha_composite(delta, (left, top))
    else:
        beauty.paste(delta.convert("RGB"), (left, top), delta.getchannel("A"))
    route_cells = _paint_system_river(
        beauty,
        mouth,
        crop_x,
        crop_y,
        palette,
        sand,
        ocean,
    )

    suffix = f"-{VIEW_TAG}" if VIEW_TAG else ""
    slug = f"selected-material-{VERSION}-seed{SEED}-x{MOUTH_CELL[0]}-y{MOUTH_CELL[1]}{suffix}"
    base_path = OUTPUT / f"{slug}-base.png"
    beauty_path = OUTPUT / f"{slug}-beauty.png"
    grid_path = OUTPUT / f"{slug}-grid.png"
    base.save(base_path)
    beauty.save(beauty_path)
    _grid(beauty).save(grid_path)

    header = 92
    sheet = Image.new("RGB", (beauty.width * 2, header + beauty.height), (4, 13, 16))
    draw = ImageDraw.Draw(sheet)
    draw.text((14, 8), f"PROJECT1991 | {VERSION.upper()} UNIFIED WORLD VIEW | 96 PX/CELL", font=_font(25, True), fill=(238, 242, 232))
    draw.text((14, 45), "new-map crop | delta-matched water | wet/dry sand | V44 + Hills NESW + Forest V4.1", font=_font(15), fill=(58, 226, 215))
    draw.text((10, 70), "BEAUTY", font=_font(13, True), fill=(234, 236, 227))
    draw.text((beauty.width + 10, 70), f"GRID / {crop_w}x{crop_h} LOGICAL CELLS", font=_font(13, True), fill=(234, 236, 227))
    sheet.paste(beauty, (0, header))
    sheet.paste(_grid(beauty), (beauty.width, header))
    contact = OUTPUT / f"{slug}-contact.png"
    sheet.save(contact)

    report = {
        "schema": f"project1991.selected-material-world/{VERSION}",
        "seed": SEED,
        "crop": list(CROP),
        "tile_px": TILE,
        "production_mapgen": str(MAPGEN_PATH),
        "master": str(MASTER_PATH),
        "master_usage": "delta water/sediment semantics only; no rectangular coast plate",
        "terminal_anchors": {
            "full_width_river_to_land_tile": 0.50,
            "delta_split_at_land_tile": 0.50,
            "coast_at_land_tile": 1.00,
            "max_offshore_sea_tile": DELTA_MAX_SEA_FRACTION,
            "full_width_neck_overlap_px": DELTA_NECK_OVERLAP_PX,
        },
        "mouth": mouth,
        "painted_route_cells": route_cells,
        "coast": "single TangentGlobalCoast CoastV31 contour; global sand/turquoise/foam",
        "ground": "V51 Civ-III-style shared corner lattice; world-periodic material samplers",
        "relief": {
            "renderer": "locked projected Relief V44 mountains + contextual Hill NESW V2",
            "large_component_records": list(relief_records),
            "hills": {
                "logical_cells": hill_report.hill_cells_in_window,
                "painted_cells": hill_report.painted_hill_cells,
                "mask_usage": hill_report.mask_usage,
                "centre_alpha_failures": hill_report.centre_alpha_failures,
                "peak_cells": hill_report.peak_cells,
                "shoulder_cells": hill_report.shoulder_cells,
                "hard_contract_pass": hill_report.hard_contract_pass,
            },
        },
        "forest": forest_report.as_dict(),
        "scope": "one newly generated 7x6 crop; no 100-map run",
        "contact": str(contact),
    }
    (OUTPUT / f"{slug}-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(contact)
    return contact


if __name__ == "__main__":
    main()
