"""Build the complete Project1991 river kit from the locked V1 atlas only.

The thirteen V1 panels define the approved roles, proportions, palette and
material language.  Their clean vertical material is normalised once, then
used to reconstruct contract-perfect straights, S-curves, true quarter turns,
rounded junctions and four gently meandering sources.  No V2 or prefab atlas
is read by this builder.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt, label, map_coordinates, median_filter


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "river-tube-atlas-v1-source.png"
SOURCE_RGBA = ROOT / "river-tube-atlas-v1-rgba.png"
OUT = ROOT / "assets_v1_complete"
ATLAS = ROOT / "river-tube-atlas-v1-complete-grid.png"

SOURCE_SHA256 = "895183887eee590a7ef0f270f9e1d68034355c563b354b589d57179120d28818"
SOURCE_RGBA_SHA256 = "7d6185a6b6516bf53cd3fb98758243633a6f4a90af42c88163be4c925fbf1cdc"
TILE = 256
PORT_TOTAL = 100
PORT_VISIBLE = 100
LANDING = 16
PORT_HARD_DEPTH = 4

EXPECTED = (
    "straight_ns",
    "straight_ew",
    "s_curve_ns",
    "s_curve_ew",
    "curve_ne",
    "curve_nw",
    "curve_sw",
    "curve_se",
    "t_esw",
    "t_nes",
    "t_new",
    "t_nsw",
    "cross_nesw",
    "source_n",
    "source_e",
    "source_s",
    "source_w",
)

PORTS = {
    "straight_ns": "NS",
    "straight_ew": "EW",
    "s_curve_ns": "NS",
    "s_curve_ew": "EW",
    "curve_ne": "NE",
    "curve_nw": "NW",
    "curve_sw": "SW",
    "curve_se": "SE",
    "t_esw": "ESW",
    "t_nes": "NES",
    "t_new": "NEW",
    "t_nsw": "NSW",
    "cross_nesw": "NESW",
    "source_n": "N",
    "source_e": "E",
    "source_s": "S",
    "source_w": "W",
}

# Loose boxes around the thirteen separate paintings in V1.  Every crop is
# trimmed to its own alpha component before any sizing or alignment happens.
PANEL_BOXES = {
    "straight_ns": (90, 20, 240, 310),
    "straight_ew": (315, 90, 625, 235),
    "curve_se": (630, 20, 925, 310),
    "curve_sw": (950, 20, 1235, 310),
    "curve_nw_source": (25, 360, 305, 625),
    "curve_ne_source": (330, 360, 605, 625),
    "s_curve_ns": (625, 330, 900, 625),
    "s_curve_ew": (925, 375, 1235, 590),
    "t_esw": (25, 650, 315, 915),
    "t_new": (330, 650, 635, 915),
    "t_nes": (705, 645, 920, 935),
    "t_nsw": (950, 645, 1165, 935),
    "cross_nesw": (15, 925, 325, 1235),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trim(image: Image.Image) -> Image.Image:
    alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[..., 3]
    ys, xs = np.nonzero(alpha > 8)
    if not len(xs):
        raise ValueError("empty V1 panel crop")
    return image.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def _extract(atlas: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    return _trim(atlas.crop(box).convert("RGBA"))


def _resize_premultiplied(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize RGBA without pulling hidden RGB into translucent river edges."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = rgba[..., 3] / 255.0
    premul = rgba[..., :3] * alpha[..., None]

    def resize_plane(plane: np.ndarray) -> np.ndarray:
        source = Image.fromarray(plane.astype(np.float32), mode="F")
        return np.asarray(source.resize(size, Image.Resampling.LANCZOS), dtype=np.float32)

    out_alpha = np.clip(resize_plane(alpha), 0.0, 1.0)
    out_premul = np.stack([resize_plane(premul[..., channel]) for channel in range(3)], axis=2)
    out_rgb = np.zeros_like(out_premul)
    np.divide(
        out_premul,
        out_alpha[..., None],
        out=out_rgb,
        where=out_alpha[..., None] > 1.0e-6,
    )
    out = np.zeros((*out_alpha.shape, 4), dtype=np.uint8)
    out[..., :3] = np.uint8(np.clip(np.round(out_rgb), 0, 255))
    out[..., 3] = np.uint8(np.clip(np.round(out_alpha * 255.0), 0, 255))
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA")


def _normalise_v1_material(image: Image.Image) -> Image.Image:
    """Make one rotationally symmetric 100 px material strip from V1."""
    first = np.asarray(_resize_premultiplied(image, (PORT_TOTAL, TILE)), dtype=np.float32)
    first_alpha = first[..., 3:4] / 255.0
    first_premul = first[..., :3] * first_alpha
    first_alpha = 0.5 * (first_alpha + first_alpha[:, ::-1])
    first_premul = 0.5 * (first_premul + first_premul[:, ::-1])
    first_rgb = np.zeros_like(first_premul)
    np.divide(first_premul, first_alpha, out=first_rgb, where=first_alpha > 1.0e-6)
    first_rgba = np.zeros((TILE, PORT_TOTAL, 4), dtype=np.uint8)
    first_rgba[..., :3] = np.uint8(np.clip(np.round(first_rgb), 0, 255))
    first_rgba[..., 3] = np.uint8(np.clip(np.round(first_alpha[..., 0] * 255.0), 0, 255))

    # The keyed V1 fringe occupies 96 clearly visible samples after the first
    # fit.  Crop that real support and expand it to the contractual 100 px,
    # instead of merely placing a 96 px river inside a 100 px canvas.
    support = np.flatnonzero(first_rgba[TILE // 2, :, 3] > 8)
    if not len(support):
        raise ValueError("V1 material has no visible centre profile")
    visible = Image.fromarray(first_rgba, "RGBA").crop(
        (int(support[0]), 0, int(support[-1]) + 1, TILE)
    )
    local = np.asarray(_resize_premultiplied(visible, (PORT_TOTAL, TILE)), dtype=np.float32)
    alpha = local[..., 3:4] / 255.0
    premul = local[..., :3] * alpha
    alpha = 0.5 * (alpha + alpha[:, ::-1])
    premul = 0.5 * (premul + premul[:, ::-1])
    rgb = np.zeros_like(premul)
    np.divide(premul, alpha, out=rgb, where=alpha > 1.0e-6)

    # The keyed V1 painting contains a few one-to-six-pixel dark/chroma
    # scratches along its banks.  They repeat at every generated seam if left
    # in the material strip.  Replace only strong longitudinal outliers with
    # a robust local median; ordinary water/bank texture remains untouched.
    longitudinal_median = median_filter(rgb, size=(17, 1, 1), mode="reflect")
    outlier = np.max(np.abs(rgb - longitudinal_median), axis=2) > 52.0
    rgb[outlier] = longitudinal_median[outlier]

    # Some keyed scratches span several consecutive rows and can therefore
    # survive a local median.  On the painted shoreline only, compare against
    # the robust whole-strip palette and replace large residual excursions.
    # This does not touch the inner water texture.
    palette_profile = np.median(rgb, axis=0)
    bank_coordinate = np.arange(PORT_TOTAL)
    bank_zone = (bank_coordinate < 14) | (bank_coordinate >= PORT_TOTAL - 14)
    palette_delta = np.max(np.abs(rgb - palette_profile[None, ...]), axis=2)
    keyed_scratch = bank_zone[None, :] & (palette_delta > 78.0)
    rgb[keyed_scratch] = np.broadcast_to(palette_profile[None, ...], rgb.shape)[keyed_scratch]

    # Chroma-key antialiasing also left a handful of salmon/magenta bank
    # pixels whose brightness is plausible but whose hue is not.  Restore the
    # robust warm-orange V1 shoreline palette at those exact samples only.
    pink_key = (
        bank_zone[None, :]
        & (rgb[..., 0] > 180.0)
        & (rgb[..., 0] > rgb[..., 1] + 60.0)
        & (rgb[..., 1] - rgb[..., 2] < 30.0)
    )
    rgb[pink_key] = np.broadcast_to(palette_profile[None, ...], rgb.shape)[pink_key]

    # The two antialias samples themselves were produced next to the chroma
    # key and have no trustworthy colour.  Give them the adjacent clean bank
    # colour while retaining their contractual alpha values.
    rgb[:, :2] = rgb[:, 2:3]
    rgb[:, -2:] = rgb[:, -3:-2]

    # Geometry width is global and independent of longitudinal brush noise.
    # Keep V1 colour variation per row but use one symmetric alpha profile.
    common_alpha = alpha[TILE // 2].copy()
    common_rgb = rgb[TILE // 2].copy()
    valid_common = np.max(common_rgb, axis=1) >= 24.0
    if np.any(valid_common):
        _, nearest_indices = distance_transform_edt(~valid_common, return_indices=True)
        common_rgb = common_rgb[nearest_indices[0]]
    # Keep all 100 contractual samples visibly present and symmetric.  The
    # edge value is a soft antialias copied from its immediate neighbour.
    edge_alpha = max(9.0 / 255.0, min(float(common_alpha[1, 0]), 0.35))
    common_alpha[0, 0] = edge_alpha
    common_alpha[-1, 0] = edge_alpha
    common_rgb[0] = common_rgb[1]
    common_rgb[-1] = common_rgb[-2]
    missing_colour = (np.max(rgb, axis=2) < 24.0) & (common_alpha[None, ..., 0] > 0.0)
    rgb[missing_colour] = np.broadcast_to(common_rgb[None, ...], rgb.shape)[missing_colour]
    alpha = np.repeat(common_alpha[None, ...], TILE, axis=0)
    result = np.zeros((TILE, PORT_TOTAL, 4), dtype=np.uint8)
    result[..., :3] = np.uint8(np.clip(np.round(rgb), 0, 255))
    result[..., 3] = np.uint8(np.clip(np.round(alpha[..., 0] * 255.0), 0, 255))
    result[result[..., 3] == 0, :3] = 0
    return _despill_translucent_edges(_place(Image.fromarray(result, "RGBA"), "NS"))


def _largest_component(image: Image.Image) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    interpolation_black = (rgba[..., 3] <= 16) & (np.max(rgba[..., :3], axis=2) < 4)
    rgba[interpolation_black] = 0
    groups, count = label(rgba[..., 3] > 0)
    if count <= 1:
        rgba[rgba[..., 3] == 0, :3] = 0
        return Image.fromarray(rgba, "RGBA")
    sizes = np.bincount(groups.ravel())
    sizes[0] = 0
    keep = groups == int(np.argmax(sizes))
    rgba[~keep] = 0
    return Image.fromarray(rgba, "RGBA")


def _despill_translucent_edges(image: Image.Image) -> Image.Image:
    """Remove residual chroma-key RGB from antialiased V1 bank pixels."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    alpha = rgba[..., 3]
    opaque = alpha >= 180
    if np.any(opaque):
        _, indices = distance_transform_edt(~opaque, return_indices=True)
        nearest = rgba[indices[0], indices[1], :3]
        partial = (alpha > 0) & (alpha < 230)
        rgba[partial, :3] = nearest[partial]
    rgba[alpha == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def _place(image: Image.Image, ports: str) -> Image.Image:
    """Anchor a fitted V1 panel to its declared open tile sides."""
    if image.width > TILE or image.height > TILE:
        raise ValueError(f"panel does not fit tile: {image.size}")
    if "W" in ports and "E" not in ports:
        x = 0
    elif "E" in ports and "W" not in ports:
        x = TILE - image.width
    else:
        x = (TILE - image.width) // 2
    if "N" in ports and "S" not in ports:
        y = 0
    elif "S" in ports and "N" not in ports:
        y = TILE - image.height
    else:
        y = (TILE - image.height) // 2
    tile = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    tile.alpha_composite(image, (x, y))
    return tile


def _shift_rows_to_center(image: Image.Image, ports: str, influence: int = 72) -> Image.Image:
    """Move only the approach to N/S ports; retain the authored interior."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    centers = np.full(TILE, (TILE - 1) * 0.5, dtype=np.float32)
    for y in range(TILE):
        xs = np.flatnonzero(alpha[y] > 8)
        if len(xs):
            centers[y] = (float(xs[0]) + float(xs[-1])) * 0.5
    top = float(np.median(centers[:12])) if "N" in ports else (TILE - 1) * 0.5
    bottom = float(np.median(centers[-12:])) if "S" in ports else (TILE - 1) * 0.5
    result = np.zeros_like(rgba)
    for y in range(TILE):
        top_weight = max(0.0, 1.0 - y / float(influence)) ** 2
        bottom_weight = max(0.0, 1.0 - (TILE - 1 - y) / float(influence)) ** 2
        shift = int(round(((TILE - 1) * 0.5 - top) * top_weight + ((TILE - 1) * 0.5 - bottom) * bottom_weight))
        if shift >= 0:
            result[y, shift:] = rgba[y, : TILE - shift]
        else:
            result[y, :shift] = rgba[y, -shift:]
    return Image.fromarray(result, "RGBA")


def _shift_cols_to_center(image: Image.Image, ports: str, influence: int = 72) -> Image.Image:
    rotated = image.transpose(Image.Transpose.ROTATE_90)
    mapped = ports.translate(str.maketrans({"E": "N", "W": "S", "N": "W", "S": "E"}))
    shifted = _shift_rows_to_center(rotated, mapped, influence=influence)
    return shifted.transpose(Image.Transpose.ROTATE_270)


def _center_authored_ports(image: Image.Image, ports: str) -> Image.Image:
    return _shift_cols_to_center(_shift_rows_to_center(image, ports), ports)


def _crossfade_rgba(region: np.ndarray, source: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Cross-fade in premultiplied-alpha space."""
    weight = np.clip(weight, 0.0, 1.0)
    dst_alpha = region[..., 3:4] / 255.0
    src_alpha = source[..., 3:4] / 255.0
    out_alpha = dst_alpha * (1.0 - weight) + src_alpha * weight
    out_premul = (
        region[..., :3] * dst_alpha * (1.0 - weight)
        + source[..., :3] * src_alpha * weight
    )
    out = np.zeros_like(region)
    np.divide(out_premul, out_alpha, out=out[..., :3], where=out_alpha > 1.0e-6)
    out[..., 3:4] = out_alpha * 255.0
    return out


def _lock_ports(
    image: Image.Image,
    ports: str,
    canonical_ns: Image.Image,
    canonical_ew: Image.Image,
    *,
    center_ports: bool = True,
) -> Image.Image:
    """Use exact reciprocal edge pixels and a short, soft V1-only landing."""
    if center_ports:
        image = _center_authored_ports(image, ports)
    dst = np.asarray(image.convert("RGBA"), dtype=np.float32).copy()
    ns = np.asarray(canonical_ns.convert("RGBA"), dtype=np.float32)
    ew = np.asarray(canonical_ew.convert("RGBA"), dtype=np.float32)
    mid = TILE // 2
    # Use consecutive V1 texture rows/columns around the seam.  Repeating one
    # profile row made a visible flat band even though the boundary pixels
    # were equal.  These four directional halves form one continuous texture
    # when reciprocal tiles meet.
    ns_north = ns[mid : mid + LANDING]
    ns_south = ns[mid - LANDING + 1 : mid + 1]
    ew_west = ew[:, mid : mid + LANDING]
    ew_east = ew[:, mid - LANDING + 1 : mid + 1]
    u = np.linspace(0.0, 1.0, LANDING, dtype=np.float32)
    fade = 1.0 - (u * u * (3.0 - 2.0 * u))

    if "N" in ports:
        dst[:LANDING] = _crossfade_rgba(dst[:LANDING], ns_north, fade[:, None, None])
    if "S" in ports:
        dst[-LANDING:] = _crossfade_rgba(dst[-LANDING:], ns_south, fade[::-1, None, None])
    if "W" in ports:
        dst[:, :LANDING] = _crossfade_rgba(dst[:, :LANDING], ew_west, fade[None, :, None])
    if "E" in ports:
        dst[:, -LANDING:] = _crossfade_rgba(dst[:, -LANDING:], ew_east, fade[None, ::-1, None])

    # Closed sides are transparent only at the true boundary.  Clearing a
    # wide rectangle would clip bends that legitimately approach that side.
    if "N" not in ports:
        dst[0] = 0.0
    if "S" not in ports:
        dst[-1] = 0.0
    if "W" not in ports:
        dst[:, 0] = 0.0
    if "E" not in ports:
        dst[:, -1] = 0.0

    n_profile = ns[mid].copy()
    e_profile = ew[:, mid].copy()
    if "N" in ports:
        dst[0] = n_profile
    if "S" in ports:
        dst[-1] = n_profile
    if "W" in ports:
        dst[:, 0] = e_profile
    if "E" in ports:
        dst[:, -1] = e_profile
    result = np.uint8(np.clip(np.round(dst), 0, 255))
    result[result[..., 3] == 0, :3] = 0
    return Image.fromarray(result, "RGBA")


def _source_meander(canonical_ns: Image.Image) -> Image.Image:
    """Create a rounded, two-bend spring that widens gradually to the S port."""
    material = np.asarray(canonical_ns.convert("RGBA"), dtype=np.float32)
    support = np.flatnonzero(material[TILE // 2, :, 3] > 8)
    full_width = float(len(support))
    supersample = 4
    coordinates = (
        np.arange(TILE * supersample, dtype=np.float32) + 0.5
    ) / supersample - 0.5
    yy, xx = np.meshgrid(coordinates, coordinates, indexing="ij")
    start = 26.0
    progress = np.clip((yy - start) / (TILE - 1.0 - start), 0.0, 1.0)

    # A supersampled half-ellipse creates a genuinely rounded head instead of
    # the old five-pixel staircase.  The wider spring also begins to grow
    # sooner, so it reads as a winding source rather than a long needle.
    narrow_width = 26.0
    cap_rows = 15.0
    cap_progress = np.clip((yy - start) / cap_rows, 0.0, 1.0)
    cap_width = narrow_width * np.sqrt(
        np.maximum(0.0, 1.0 - (1.0 - cap_progress) ** 2)
    )
    growth = np.clip((progress - 0.12) / 0.88, 0.0, 1.0)
    growth = growth * growth * (3.0 - 2.0 * growth)
    body_width = narrow_width + (full_width - narrow_width) * growth
    width = np.where(cap_progress < 1.0, cap_width, body_width)

    # Squared envelope makes both offset and derivative zero at the port: the
    # source reaches S centred and vertically tangent after its two bends.
    envelope = np.sin(np.pi * progress) ** 2
    centreline = (TILE - 1) * 0.5
    centreline += envelope * (
        15.0 * np.sin(2.35 * np.pi * progress)
        + 4.0 * np.sin(5.0 * np.pi * progress)
    )
    cross_coord = (TILE - 1) * 0.5 + (
        (xx - centreline) * (full_width / np.maximum(width, 0.25))
    )
    longitudinal = TILE * 0.5 + 80.0 * np.sin(np.pi * progress)
    sampled = _sample_material(material, longitudinal, cross_coord)
    sampled[yy < start] = 0.0
    high_res = np.uint8(np.clip(np.round(sampled), 0, 255))
    high_res[high_res[..., 3] == 0, :3] = 0
    downsampled = _resize_premultiplied(
        Image.fromarray(high_res, "RGBA"),
        (TILE, TILE),
    )
    return _largest_component(downsampled)


def _sample_material(material: np.ndarray, longitudinal: np.ndarray, cross_coord: np.ndarray) -> np.ndarray:
    """Bilinearly sample RGBA without introducing dark keyed fringes."""
    alpha = material[..., 3] / 255.0
    premultiplied = material[..., :3] * alpha[..., None]
    sampled_alpha = map_coordinates(
        alpha,
        (longitudinal, cross_coord),
        order=1,
        mode="constant",
        cval=0.0,
    )
    sampled_premultiplied = np.stack(
        [
            map_coordinates(
                premultiplied[..., channel],
                (longitudinal, cross_coord),
                order=1,
                mode="constant",
                cval=0.0,
            )
            for channel in range(3)
        ],
        axis=2,
    )
    result = np.zeros((*sampled_alpha.shape, 4), dtype=np.float32)
    np.divide(
        sampled_premultiplied,
        sampled_alpha[..., None],
        out=result[..., :3],
        where=sampled_alpha[..., None] > 1.0e-6,
    )
    result[..., 3] = sampled_alpha * 255.0
    return result


def _quarter_curve_se(canonical_ns: Image.Image) -> Image.Image:
    """Build one true 90-degree S->E elbow from the locked V1 material.

    Its centreline is a quarter circle around the south-east tile corner.  It
    therefore enters at (127.5, 255), turns exactly 90 degrees and exits at
    (255, 127.5).  Cross-river colour comes only from the two V1 straight
    paintings and changes gradually from the NS to the EW texture.
    """
    material = np.asarray(canonical_ns.convert("RGBA"), dtype=np.float32)
    yy, xx = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    corner = float(TILE - 1)
    radius = (TILE - 1) * 0.5
    leftward = corner - xx
    upward = corner - yy
    radial = np.sqrt(leftward * leftward + upward * upward)
    theta = np.arctan2(upward, leftward)
    progress = np.clip(theta / (0.5 * np.pi), 0.0, 1.0)

    # At both boundary ports cross_coord is the literal edge-array index, so
    # the generated end row/column already equals the canonical V1 profile.
    cross_coord = corner - radial
    longitudinal = TILE * 0.5 + 80.0 * np.sin(np.pi * progress)
    rgba = np.uint8(np.clip(np.round(_sample_material(material, longitudinal, cross_coord)), 0, 255))
    rgba[rgba[..., 3] == 0, :3] = 0
    return _largest_component(Image.fromarray(rgba, "RGBA"))


def _s_curve_ns(canonical_ns: Image.Image) -> Image.Image:
    """Build a centred N->S snake with vertical tangents at both ports."""
    ns = np.asarray(canonical_ns.convert("RGBA"), dtype=np.float32)
    yy, xx = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    progress = yy / float(TILE - 1)
    # Broad fifth-order S polynomial: zero offset and zero derivative at both
    # ports, with a gentle sign change through the tile centre.
    wave = progress**2 * (1.0 - progress) ** 2 * (0.5 - progress)
    peak = float(np.max(np.abs(wave)))
    wave = wave / peak
    centreline = (TILE - 1) * 0.5 + 40.0 * wave
    cross_coord = xx - centreline + (TILE - 1) * 0.5
    longitudinal = TILE * 0.5 + 82.0 * np.sin(np.pi * progress)
    sample = _sample_material(ns, longitudinal, cross_coord)
    rgba = np.uint8(np.clip(np.round(sample), 0, 255))
    rgba[rgba[..., 3] == 0, :3] = 0
    return _largest_component(Image.fromarray(rgba, "RGBA"))


def _junction_esw(canonical_ns: Image.Image) -> Image.Image:
    """Canonical E/S/W T with exact ports and softly rounded confluence."""
    material = np.asarray(canonical_ns.convert("RGBA"), dtype=np.float32)
    yy, xx = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    centre = (TILE - 1) * 0.5
    radius = centre

    distance_h = np.abs(yy - centre)
    distance_v = np.abs(xx - centre)
    outward_h = np.clip(np.abs(xx - centre) / radius, 0.0, 1.0)
    outward_v = np.clip((yy - centre) / radius, 0.0, 1.0)
    rounding = 28.0
    difference = np.abs(distance_h - distance_v)
    blend = np.clip((rounding - difference) / rounding, 0.0, 1.0)
    smooth_distance = np.minimum(distance_h, distance_v) - 0.25 * rounding * blend * blend
    horizontal_weight = np.clip(
        0.5 + 0.5 * (distance_v - distance_h) / rounding,
        0.0,
        1.0,
    )
    below = yy >= centre
    distance = np.where(below, np.maximum(0.0, smooth_distance), distance_h)
    outward = np.where(
        below,
        horizontal_weight * outward_h + (1.0 - horizontal_weight) * outward_v,
        outward_h,
    )
    longitudinal = TILE * 0.5 + 80.0 * (1.0 - outward)
    cross_coord = centre + distance
    rgba = np.uint8(
        np.clip(np.round(_sample_material(material, longitudinal, cross_coord)), 0, 255)
    )
    rgba[rgba[..., 3] == 0, :3] = 0
    return _largest_component(Image.fromarray(rgba, "RGBA"))


def _cross_junction(canonical_ns: Image.Image) -> Image.Image:
    """Four-way junction with a rotationally symmetric rounded union."""
    material = np.asarray(canonical_ns.convert("RGBA"), dtype=np.float32)
    yy, xx = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    centre = (TILE - 1) * 0.5
    radius = centre
    distance_h = np.abs(yy - centre)
    distance_v = np.abs(xx - centre)
    outward_h = np.clip(np.abs(xx - centre) / radius, 0.0, 1.0)
    outward_v = np.clip(np.abs(yy - centre) / radius, 0.0, 1.0)
    rounding = 28.0
    difference = np.abs(distance_h - distance_v)
    blend = np.clip((rounding - difference) / rounding, 0.0, 1.0)
    distance = np.maximum(
        0.0,
        np.minimum(distance_h, distance_v) - 0.25 * rounding * blend * blend,
    )
    horizontal_weight = np.clip(
        0.5 + 0.5 * (distance_v - distance_h) / rounding,
        0.0,
        1.0,
    )
    outward = horizontal_weight * outward_h + (1.0 - horizontal_weight) * outward_v
    longitudinal = TILE * 0.5 + 80.0 * (1.0 - outward)
    cross_coord = centre + distance
    rgba = np.uint8(
        np.clip(np.round(_sample_material(material, longitudinal, cross_coord)), 0, 255)
    )
    rgba[rgba[..., 3] == 0, :3] = 0
    return _largest_component(Image.fromarray(rgba, "RGBA"))


def _lock_common_edge(image: Image.Image, ports: str, profile: np.ndarray) -> Image.Image:
    """Apply the global symmetric port contract to the true edge pixels only."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    if "N" not in ports:
        rgba[0] = 0
    if "S" not in ports:
        rgba[-1] = 0
    if "W" not in ports:
        rgba[:, 0] = 0
    if "E" not in ports:
        rgba[:, -1] = 0
    if "N" in ports:
        rgba[0] = profile
    if "S" in ports:
        rgba[-1] = profile
    if "W" in ports:
        rgba[:, 0] = profile
    if "E" in ports:
        rgba[:, -1] = profile
    rgba[rgba[..., 3] == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def _finish_port_contract(
    image: Image.Image,
    ports: str,
    canonical_ns: Image.Image,
) -> Image.Image:
    """Apply a continuous V1 texture neighbourhood at every declared port."""
    dst = np.asarray(image.convert("RGBA"), dtype=np.float32).copy()
    ns = np.asarray(canonical_ns.convert("RGBA"), dtype=np.float32)
    mid = TILE // 2

    # One direction-neutral local landing C[depth, cross].  Averaging both
    # sides of the V1 material midpoint makes its longitudinal detail
    # reversible; its cross profile is already symmetric.  Every cardinal
    # port consequently receives an exact rotation/reflection of one raster.
    forward = ns[mid : mid + LANDING]
    backward = ns[mid - LANDING + 1 : mid + 1][::-1]
    landing = _crossfade_rgba(
        forward,
        backward,
        np.full((LANDING, 1, 1), 0.5, dtype=np.float32),
    )

    weight = np.ones(LANDING, dtype=np.float32)
    tail = LANDING - PORT_HARD_DEPTH
    # Exactly PORT_HARD_DEPTH pixels are canonical.  The following pixel is
    # already inside the smooth hand-off, so the manifest's hard-depth claim
    # and the saved raster agree one-for-one.
    u = np.linspace(1.0 / tail, 1.0, tail, dtype=np.float32)
    weight[PORT_HARD_DEPTH:] = 1.0 - (u * u * (3.0 - 2.0 * u))
    if "N" in ports:
        dst[:LANDING] = _crossfade_rgba(dst[:LANDING], landing, weight[:, None, None])
    if "S" in ports:
        dst[-LANDING:] = _crossfade_rgba(dst[-LANDING:], landing[::-1], weight[::-1, None, None])
    if "W" in ports:
        west = np.transpose(landing, (1, 0, 2))
        dst[:, :LANDING] = _crossfade_rgba(dst[:, :LANDING], west, weight[None, :, None])
    if "E" in ports:
        east = np.transpose(landing[::-1], (1, 0, 2))
        dst[:, -LANDING:] = _crossfade_rgba(dst[:, -LANDING:], east, weight[None, ::-1, None])
    result = np.uint8(np.clip(np.round(dst), 0, 255))
    result[result[..., 3] == 0, :3] = 0
    common_profile = ns[mid].copy()
    return _lock_common_edge(Image.fromarray(result, "RGBA"), ports, common_profile)


def _edge(image: Image.Image, port: str) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    return {"N": rgba[0], "S": rgba[-1], "W": rgba[:, 0], "E": rgba[:, -1]}[port]


def _water_mask(rgba: np.ndarray) -> np.ndarray:
    rgb = rgba[..., :3].astype(np.int16)
    return (
        (rgba[..., 3] > 8)
        & (rgb[..., 2] > rgb[..., 0] + 16)
        & (rgb[..., 1] > rgb[..., 0] + 4)
    )


def _one_interval(indices: np.ndarray) -> bool:
    return bool(len(indices)) and not np.any(np.diff(indices) != 1)


def _font(size: int) -> ImageFont.ImageFont:
    path = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def _render_atlas(assets: dict[str, Image.Image]) -> None:
    columns, rows = 5, 4
    margin, label_h = 12, 28
    cell_w = TILE + margin
    cell_h = TILE + label_h + margin
    sheet = Image.new("RGB", (columns * cell_w + margin, rows * cell_h + margin), (246, 0, 242))
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(EXPECTED):
        x = margin + (index % columns) * cell_w
        y = margin + (index // columns) * cell_h
        layer = Image.new("RGBA", (TILE, TILE), (246, 0, 242, 255))
        layer.alpha_composite(assets[name])
        sheet.paste(layer.convert("RGB"), (x, y))
        draw.rectangle((x, y, x + TILE - 1, y + TILE - 1), outline=(0, 235, 235), width=2)
        draw.rectangle((x, y + TILE, x + TILE - 1, y + TILE + label_h - 1), fill=(3, 12, 15))
        draw.text((x + 6, y + TILE + 5), name, font=_font(13), fill=(235, 241, 229))
    sheet.save(ATLAS)


def _build_geometry(atlas: Image.Image) -> dict[str, Image.Image]:
    panels = {name: _extract(atlas, box) for name, box in PANEL_BOXES.items()}

    straight_ns = _normalise_v1_material(panels["straight_ns"])
    straight_ew = straight_ns.transpose(Image.Transpose.ROTATE_90)

    curve_se = _quarter_curve_se(straight_ns)
    s_curve_ns = _s_curve_ns(straight_ns)
    t_esw = _junction_esw(straight_ns)
    geometry: dict[str, Image.Image] = {
        "straight_ns": straight_ns,
        "straight_ew": straight_ew,
        "s_curve_ns": s_curve_ns,
        "s_curve_ew": s_curve_ns.transpose(Image.Transpose.ROTATE_90),
        "curve_se": curve_se,
        "curve_ne": curve_se.transpose(Image.Transpose.ROTATE_90),
        "curve_nw": curve_se.transpose(Image.Transpose.ROTATE_180),
        "curve_sw": curve_se.transpose(Image.Transpose.ROTATE_270),
    }

    geometry.update(
        {
            "t_esw": t_esw,
            "t_nes": t_esw.transpose(Image.Transpose.ROTATE_90),
            "t_new": t_esw.transpose(Image.Transpose.ROTATE_180),
            "t_nsw": t_esw.transpose(Image.Transpose.ROTATE_270),
            "cross_nesw": _cross_junction(straight_ns),
        }
    )

    source_s = _source_meander(straight_ns)
    geometry.update(
        {
            "source_s": source_s,
            "source_e": source_s.transpose(Image.Transpose.ROTATE_90),
            "source_n": source_s.transpose(Image.Transpose.ROTATE_180),
            "source_w": source_s.transpose(Image.Transpose.ROTATE_270),
        }
    )
    return {name: _largest_component(image) for name, image in geometry.items()}


def _qa(saved: dict[str, Image.Image], source_hashes: dict[str, str]) -> dict[str, object]:
    failures: list[str] = []
    if source_hashes["source"] != SOURCE_SHA256:
        failures.append(f"source_sha256:{source_hashes['source']}")
    if source_hashes["source_rgba"] != SOURCE_RGBA_SHA256:
        failures.append(f"source_rgba_sha256:{source_hashes['source_rgba']}")

    expected_files = {f"{name}.png" for name in EXPECTED}
    disk_files = {path.name for path in OUT.glob("*.png")}
    if disk_files != expected_files:
        failures.append(f"disk_png_set:{sorted(disk_files)}")

    masks = Counter("".join(sorted(PORTS[name])) for name in EXPECTED)
    expected_masks = Counter(
        {
            "N": 1, "E": 1, "S": 1, "W": 1,
            "EN": 1, "ES": 1, "SW": 1, "NW": 1,
            "NS": 2, "EW": 2,
            "ENS": 1, "ENW": 1, "NSW": 1, "ESW": 1,
            "ENSW": 1,
        }
    )
    if masks != expected_masks:
        failures.append(f"connectivity_multiset:{dict(masks)}")

    canonical_ns = saved["straight_ns"]
    canonical_ew = saved["straight_ew"]
    profiles = {
        "N": _edge(canonical_ns, "N"),
        "S": _edge(canonical_ns, "S"),
        "W": _edge(canonical_ew, "W"),
        "E": _edge(canonical_ew, "E"),
    }
    common_profile = profiles["N"]
    for port in "SEW":
        if not np.array_equal(profiles[port], common_profile):
            failures.append(f"global_profile_mismatch:N:{port}")
    if not np.array_equal(common_profile, common_profile[::-1]):
        failures.append("global_profile_not_symmetric")
    common_visible = np.flatnonzero(common_profile[:, 3] > 8)
    if (
        not _one_interval(common_visible)
        or len(common_visible) != PORT_VISIBLE
        or int(common_visible[0]) != (TILE - PORT_VISIBLE) // 2
        or int(common_visible[-1]) != (TILE + PORT_VISIBLE) // 2 - 1
    ):
        failures.append(f"global_visible_support:{common_visible.tolist()}")
    port_widths: dict[str, dict[str, int]] = {}
    canonical_neighbourhoods = {
        "N": np.asarray(canonical_ns, dtype=np.uint8)[:PORT_HARD_DEPTH],
        "S": np.asarray(canonical_ns, dtype=np.uint8)[-PORT_HARD_DEPTH:],
        "W": np.asarray(canonical_ew, dtype=np.uint8)[:, :PORT_HARD_DEPTH],
        "E": np.asarray(canonical_ew, dtype=np.uint8)[:, -PORT_HARD_DEPTH:],
    }

    for name in EXPECTED:
        image = saved[name]
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        if image.mode != "RGBA" or image.size != (TILE, TILE):
            failures.append(f"format:{name}:{image.mode}:{image.size}")
        if np.any(rgba[rgba[..., 3] == 0, :3]):
            failures.append(f"hidden_rgb:{name}")
        black_visible = (rgba[..., 3] > 0) & (np.max(rgba[..., :3], axis=2) < 24)
        if np.any(black_visible):
            failures.append(f"black_alpha_fringe:{name}:{int(np.count_nonzero(black_visible))}")
        channels = rgba[..., :3].astype(np.int16)
        pink_key = (
            (rgba[..., 3] > 0)
            & (channels[..., 0] > 180)
            & (channels[..., 0] > channels[..., 1] + 60)
            & (channels[..., 1] - channels[..., 2] < 30)
        )
        if np.any(pink_key):
            failures.append(f"chroma_key_fringe:{name}:{int(np.count_nonzero(pink_key))}")
        # Sub-8 alpha is a resampling fringe, not visible geometry.  The same
        # >8 threshold is used for source trimming and port support.
        _, alpha_components = label(rgba[..., 3] > 8)
        if alpha_components != 1:
            failures.append(f"alpha_components:{name}:{alpha_components}")

        water_groups, _ = label(_water_mask(rgba))
        touched_water_groups: list[int] = []
        for port in "NESW":
            edge = _edge(image, port)
            visible = np.flatnonzero(edge[:, 3] > 8)
            if port in PORTS[name]:
                if not np.array_equal(edge, profiles[port]):
                    failures.append(f"port_profile:{name}:{port}")
                neighbourhood = {
                    "N": rgba[:PORT_HARD_DEPTH],
                    "S": rgba[-PORT_HARD_DEPTH:],
                    "W": rgba[:, :PORT_HARD_DEPTH],
                    "E": rgba[:, -PORT_HARD_DEPTH:],
                }[port]
                if not np.array_equal(neighbourhood, canonical_neighbourhoods[port]):
                    failures.append(f"port_neighbourhood:{name}:{port}")
                if not _one_interval(visible):
                    failures.append(f"port_interval:{name}:{port}")
                elif abs((float(visible[0]) + float(visible[-1])) * 0.5 - (TILE - 1) * 0.5) > 0.51:
                    failures.append(f"port_center:{name}:{port}")
                coordinate = {
                    "N": (0, TILE // 2),
                    "S": (TILE - 1, TILE // 2),
                    "W": (TILE // 2, 0),
                    "E": (TILE // 2, TILE - 1),
                }[port]
                group = int(water_groups[coordinate])
                if group == 0:
                    failures.append(f"water_at_port:{name}:{port}")
                touched_water_groups.append(group)
            elif np.any(edge):
                failures.append(f"closed_edge:{name}:{port}")
        if len(set(touched_water_groups)) != 1:
            failures.append(f"water_connectivity:{name}:{touched_water_groups}")

    rotation_contracts = (
        ("straight_ew", "straight_ns", Image.Transpose.ROTATE_90),
        ("s_curve_ew", "s_curve_ns", Image.Transpose.ROTATE_90),
        ("curve_ne", "curve_se", Image.Transpose.ROTATE_90),
        ("curve_nw", "curve_se", Image.Transpose.ROTATE_180),
        ("curve_sw", "curve_se", Image.Transpose.ROTATE_270),
        ("t_nes", "t_esw", Image.Transpose.ROTATE_90),
        ("t_new", "t_esw", Image.Transpose.ROTATE_180),
        ("t_nsw", "t_esw", Image.Transpose.ROTATE_270),
        ("source_e", "source_s", Image.Transpose.ROTATE_90),
        ("source_n", "source_s", Image.Transpose.ROTATE_180),
        ("source_w", "source_s", Image.Transpose.ROTATE_270),
    )
    for target, base, rotation in rotation_contracts:
        expected = np.asarray(saved[base].transpose(rotation), dtype=np.uint8)
        actual = np.asarray(saved[target], dtype=np.uint8)
        if not np.array_equal(actual, expected):
            failures.append(f"rotation_contract:{target}:{base}")
    cross = np.asarray(saved["cross_nesw"], dtype=np.uint8)
    for rotation in (
        Image.Transpose.ROTATE_90,
        Image.Transpose.ROTATE_180,
        Image.Transpose.ROTATE_270,
    ):
        if not np.array_equal(cross, np.asarray(saved["cross_nesw"].transpose(rotation), dtype=np.uint8)):
            failures.append(f"cross_rotation_contract:{rotation}")

    for port, profile in profiles.items():
        visible = np.flatnonzero(profile[:, 3] > 8)
        water = _water_mask(profile[None, ...] if port in "NS" else profile[:, None, :])
        port_widths[port] = {
            "total_px": int(len(visible)),
            "water_px": int(np.count_nonzero(water)),
        }

    if failures:
        raise SystemExit(json.dumps({"passed": False, "failures": failures}, indent=2))
    return {
        "passed": True,
        "asset_count": len(saved),
        "disk_png_set_exact": True,
        "all_visible_alpha_components_single": True,
        "no_dark_or_chroma_key_fringe": True,
        "all_declared_ports_exact": True,
        "one_global_symmetric_port_profile": True,
        "global_visible_port_width_px": PORT_VISIBLE,
        "all_port_neighbourhoods_exact": True,
        "port_hard_depth_px": PORT_HARD_DEPTH,
        "all_rotated_variants_byte_exact": True,
        "all_closed_edges_transparent": True,
        "all_port_water_connected": True,
        "connectivity_multiset_complete": True,
        "port_widths": port_widths,
    }


def build() -> dict[str, object]:
    source_hashes = {"source": _sha256(SOURCE), "source_rgba": _sha256(SOURCE_RGBA)}
    atlas = Image.open(SOURCE_RGBA).convert("RGBA")
    geometry = _build_geometry(atlas)
    if set(geometry) != set(EXPECTED):
        raise SystemExit(f"geometry set mismatch: {sorted(geometry)}")

    OUT.mkdir(parents=True, exist_ok=True)
    canonical_ns = geometry["straight_ns"]
    # Finish one canonical member per rotational family, then derive every
    # orientation by lossless 90-degree transpose.  This simultaneously locks
    # the first four pixels behind every port and prevents tiny orientation
    # drifts from reappearing in curves, T pieces, S pieces, or sources.
    straight_ns = _finish_port_contract(
        geometry["straight_ns"], "NS", canonical_ns
    )
    s_curve_ns = _finish_port_contract(
        geometry["s_curve_ns"], "NS", canonical_ns
    )
    curve_se = _finish_port_contract(
        geometry["curve_se"], "SE", canonical_ns
    )
    t_esw = _finish_port_contract(
        geometry["t_esw"], "ESW", canonical_ns
    )
    cross_nesw = _finish_port_contract(
        geometry["cross_nesw"], "NESW", canonical_ns
    )
    source_s = _finish_port_contract(
        _despill_translucent_edges(geometry["source_s"]), "S", canonical_ns
    )

    finished = {
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
        "cross_nesw": cross_nesw,
        "source_s": source_s,
        "source_e": source_s.transpose(Image.Transpose.ROTATE_90),
        "source_n": source_s.transpose(Image.Transpose.ROTATE_180),
        "source_w": source_s.transpose(Image.Transpose.ROTATE_270),
    }
    for name in EXPECTED:
        finished[name].save(OUT / f"{name}.png")

    saved = {name: Image.open(OUT / f"{name}.png").convert("RGBA") for name in EXPECTED}
    qa = _qa(saved, source_hashes)
    manifest: dict[str, object] = {
        "schema": "project1991.river-style-locked/v1-complete",
        "status": "PASS",
        "tile_px": TILE,
        "asset_count": len(EXPECTED),
        "source": {
            "file": SOURCE.name,
            "sha256": source_hashes["source"],
            "keyed_rgba_file": SOURCE_RGBA.name,
            "keyed_rgba_sha256": source_hashes["source_rgba"],
            "painted_panels_read": 13,
            "painted_panels_used_directly": 1,
            "external_art_sources": [],
        },
        "derivation": {
            "direct_v1_roles": 1,
            "v1_material_true_quarter_turns": ["curve_ne", "curve_nw", "curve_sw", "curve_se"],
            "v1_material_centred_s_curves": ["s_curve_ns", "s_curve_ew"],
            "v1_material_centred_junctions": ["t_esw", "t_nes", "t_new", "t_nsw", "cross_nesw"],
            "global_symmetric_port_profile": True,
            "v1_straight_derived_meandering_sources": ["source_n", "source_e", "source_s", "source_w"],
            "material_strip_width_px": PORT_TOTAL,
            "visible_port_width_px": PORT_VISIBLE,
            "byte_exact_port_neighbourhood_px": PORT_HARD_DEPTH,
        },
        "qa": qa,
        "assets": {
            name: {"file": f"{name}.png", "ports": list(PORTS[name])}
            for name in EXPECTED
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _render_atlas(saved)
    print(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    build()
