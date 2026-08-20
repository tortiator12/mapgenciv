"""River rendering, take 2: one continuous field, no stitched pieces.

The complaint about v1: you can see where curve segments were placed next to
each other, and the mouth is a pasted sprite. Both come from the same root
cause -- v1 assigns each pixel to its single NEAREST source point. At any
confluence (T-junction, cross, river-meets-sea) the nearest point flips
between candidates, and the flip is a visible seam.

Fix: every pixel gets a WEIGHTED BLEND of all nearby source points (Gaussian
kernel on distance), and everything downstream -- position, arclength,
tangent, half-width, "how far into the sea" -- is that same weighted average.
Since it is one field computed the same way everywhere, there is nothing that
can visibly disagree at a boundary; there IS no boundary. The mouth is not a
separate asset: it is the same field, just walked past the coast and re-tinted
towards the sea colour as it goes, with the band widening like a real estuary.
"""
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent
WORLDS = Path(os.environ.get("MAPGENCIV_WORLDS_OUT", str(ROOT / "out" / "worlds")))
HD = Path(os.environ.get("MAPGENCIV_RIVERS_HD", str(ROOT / "assets" / "rivers_hd_1024")))
SOURCE_HD = Path(os.environ.get("MAPGENCIV_RIVER_SOURCES", str(ROOT / "assets" / "river_sources_v19")))
FORMS = json.loads((HD / "forms_1991.json").read_text(encoding="utf-8"))
RIVER_WIDTH_SCALE = 0.95
PORT_VEC = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
EXIT_PORT = {1: "N", 2: "E", 4: "S", 8: "W"}
SOURCE_DIRECTION = {"N": "north", "E": "east", "S": "south", "W": "west"}
SOURCE_ANCHOR = {
    ("mountain", "N"): (0.4894027, 0.49196787),
    ("mountain", "E"): (0.47802198, 0.40825688),
    ("mountain", "S"): (0.47870183, 0.4789916),
    ("mountain", "W"): (0.59550562, 0.50694444),
    ("hill", "N"): (0.50383142, 0.48902196),
    ("hill", "E"): (0.51813472, 0.43230404),
    ("hill", "S"): (0.50682261, 0.47798742),
    ("hill", "W"): (0.558669, 0.54460094),
}


def form_for(ports):
    want = set(ports)
    for f in FORMS.values():
        if set(f["ports"]) == want:
            return f
    return None


# --------------------------------------------------------------- flow field
def _tangents(rp):
    t = np.gradient(rp, axis=0)
    n = np.hypot(t[:, 0], t[:, 1])
    n[n < 1e-6] = 1.0
    return t / n[:, None]


def build_points(cells, x0, y0, T, mouth_extensions=(), source_tile_cells=()):
    """One big list of (pos, tangent, s, half_width, seamix) samples, densely spaced."""
    pos, tan_all, s_all, hw_all, mix_all = [], [], [], [], []
    source_origins = []
    base = 0.0
    for r in cells:
        f = form_for(r["ports"])
        if f is None:
            continue
        ox, oy = (r["x"] - x0) * T, (r["y"] - y0) * T
        mouth_mask = r.get("mouth_exit_mask") or 0
        mouth_target = None
        if mouth_mask:
            mouth_vec = np.array(PORT_VEC[EXIT_PORT[mouth_mask]], float)
            mouth_target = np.array(
                [ox + T / 2 + mouth_vec[0] * T / 2,
                 oy + T / 2 + mouth_vec[1] * T / 2]
            )
        mouth_extension = None
        if mouth_target is not None:
            for candidate in mouth_extensions:
                if np.hypot(
                    candidate["port_x"] - mouth_target[0],
                    candidate["port_y"] - mouth_target[1],
                ) <= 2.0:
                    mouth_extension = candidate
                    break
        source_target = None
        if len(r["ports"]) == 1:
            source_vec = np.array(PORT_VEC[r["ports"]], float)
            source_target = np.array(
                [ox + T / 2 + source_vec[0] * T / 2,
                 oy + T / 2 + source_vec[1] * T / 2]
            )
        for c in f["curves"]:
            pts = np.asarray(c["points"], float) * T + np.array([ox, oy])
            # A small global correction keeps mature bends from looking
            # pot-bellied while preserving every authored centreline.
            hw = np.asarray(c["half_width"], float) * T * RIVER_WIDTH_SCALE
            # resample to even spacing so weighting isn't biased by the
            # original point density
            d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
            total = d[-1] if d[-1] > 0 else 1.0
            n = max(8, int(total / (T * 0.02)))
            u = np.linspace(0, total, n)
            rp = np.stack([np.interp(u, d, pts[:, 0]), np.interp(u, d, pts[:, 1])], axis=1)
            rhw = np.interp(u, d, hw)
            active_mouth = None

            # A composed hill/mountain source owns its complete first tile.
            # Start the procedural river at that tile's port instead; the
            # source asset itself supplies the fine in-tile rivulet.
            if source_target is not None and (r["x"], r["y"]) in source_tile_cells:
                source_origins.append(source_target)
                continue

            # The mouth is not a later overlay.  Extend this SAME authored arm
            # from its existing endpoint, at unchanged end width and sample
            # spacing, through the organic coast and six pixels into water.
            if mouth_extension is not None:
                start_distance = np.hypot(*(rp[0] - mouth_target))
                end_distance = np.hypot(*(rp[-1] - mouth_target))
                if min(start_distance, end_distance) <= T * 0.18:
                    if start_distance < end_distance:
                        rp = rp[::-1]
                        rhw = rhw[::-1]
                    spacing = T * 0.02
                    extra_distance = np.arange(
                        spacing,
                        mouth_extension["end_at"] + spacing * 0.5,
                        spacing,
                    )
                    if len(extra_distance):
                        extra = np.stack([
                            rp[-1, 0] + mouth_extension["vx"] * extra_distance,
                            rp[-1, 1] + mouth_extension["vy"] * extra_distance,
                        ], axis=1)
                        rp = np.concatenate([rp, extra], axis=0)
                        rhw = np.concatenate([
                            rhw,
                            np.full(len(extra_distance), rhw[-1]),
                        ])
                        u = np.concatenate([u, total + extra_distance])
                        total = float(u[-1])
                    active_mouth = mouth_extension

            # Remember the free endpoint of each of the four existing high-res
            # source forms.  Width is assigned later by geodesic distance over
            # the CONNECTED river graph, so growth continues across the first
            # cell boundary instead of being reset or completed there.
            if source_target is not None:
                port_at_start = (
                    np.hypot(*(rp[0] - source_target))
                    <= np.hypot(*(rp[-1] - source_target))
                )
                source_origins.append(rp[-1] if port_at_start else rp[0])

            if active_mouth is None:
                curve_mix = np.zeros(len(rp))
            else:
                along = (
                    (rp[:, 0] - active_mouth["port_x"]) * active_mouth["vx"]
                    + (rp[:, 1] - active_mouth["port_y"]) * active_mouth["vy"]
                )
                colour_start = active_mouth["coast_at"] - T * 0.28
                curve_mix = np.clip(
                    (along - colour_start)
                    / max(active_mouth["coast_at"] - colour_start, 1.0),
                    0.0,
                    1.0,
                )
                curve_mix = curve_mix * curve_mix * (3.0 - 2.0 * curve_mix)
            pos.append(rp)
            tan_all.append(_tangents(rp))
            s_all.append(base + u)
            hw_all.append(rhw)
            mix_all.append(curve_mix)
            base += total + T
    # A halo can legitimately contain only one-cell hill/mountain sources.
    # Their complete RGBA compositions are applied after the procedural
    # field, so every curve above is intentionally skipped.  This is not an
    # invalid river graph; it simply has no procedural samples in this crop.
    if not pos:
        return None

    points = np.concatenate(pos)
    half_widths = np.concatenate(hw_all)

    if source_origins:
        # Build a sparse graph from the densely sampled high-res centrelines.
        # Samples at a cell port/junction occupy the same few pixels and thus
        # join naturally.  Shortest-path distance then follows the river rather
        # than cutting across terrain or a nearby meander.
        tree = cKDTree(points)
        pairs = tree.query_pairs(r=T * 0.042, output_type="ndarray")
        if len(pairs):
            weights = np.hypot(
                points[pairs[:, 0], 0] - points[pairs[:, 1], 0],
                points[pairs[:, 0], 1] - points[pairs[:, 1], 1],
            )
            # Coincident samples are the exact cell/junction connection.  A
            # sparse matrix would interpret numeric zero as "no edge", so give
            # those joins an insignificant positive cost instead.
            weights = np.maximum(weights, 1e-3)
            rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
            cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
            graph = coo_matrix(
                (np.concatenate([weights, weights]), (rows, cols)),
                shape=(len(points), len(points)),
            ).tocsr()
            source_indices = np.unique(tree.query(source_origins, k=1)[1])
            source_distance = dijkstra(
                graph, directed=False, indices=source_indices
            )
            if source_distance.ndim == 2:
                source_distance = np.min(source_distance, axis=0)

            # Two complete cells from spring-port to normal river.  Grow over
            # the whole distance instead of keeping a hairline for one cell
            # and swelling abruptly in the second: after one cell the river
            # has roughly 43% of its authored width, and only reaches 100% at
            # the end of the second cell.
            q = np.clip(source_distance / (2.0 * T), 0.0, 1.0)
            growth = np.interp(
                q,
                [0.0, 0.25, 0.50, 0.75, 1.0],
                [0.045, 0.20, 0.43, 0.70, 1.0],
            )
            half_widths = np.where(
                np.isfinite(source_distance),
                np.maximum(0.65, half_widths * growth),
                half_widths,
            )
    return (points, np.concatenate(tan_all), np.concatenate(s_all),
            half_widths, np.concatenate(mix_all))


def build_mouth_inlets(cells, x0, y0, T):
    """Short centreline reaches carrying real sea colour onto the land side.

    This is the inverse of the rejected estuary extension: it never creates a
    point past the mouth edge.  Each path begins at the river's existing coast
    port and walks upstream inside the technical mouth cell.  The caller uses
    it only as a colour blend over the already-painted river corridor.
    """
    result = []
    reach = T * 0.34
    for record in cells:
        mask = record.get("mouth_exit_mask") or 0
        if not mask:
            continue
        form = form_for(record["ports"])
        if form is None:
            continue
        ox = (record["x"] - x0) * T
        oy = (record["y"] - y0) * T
        vx, vy = PORT_VEC[EXIT_PORT[mask]]
        target = np.array([ox + T / 2 + vx * T / 2,
                           oy + T / 2 + vy * T / 2])
        best_points, best_widths, best_distance = None, None, 1e18
        for curve in form["curves"]:
            points = np.asarray(curve["points"], float) * T + np.array([ox, oy])
            widths = (
                np.asarray(curve["half_width"], float)
                * T
                * RIVER_WIDTH_SCALE
            )
            for end_index, end in ((0, points[0]), (-1, points[-1])):
                distance = np.hypot(*(end - target))
                if distance >= best_distance:
                    continue
                best_distance = distance
                if end_index == 0:
                    best_points, best_widths = points, widths
                else:
                    best_points, best_widths = points[::-1], widths[::-1]
        if best_points is None or best_distance > T * 0.18:
            continue

        arc = np.concatenate([[0.0], np.cumsum(
            np.hypot(*np.diff(best_points, axis=0).T)
        )])
        available = min(reach, float(arc[-1]))
        count = max(8, int(available / (T * 0.015)))
        depth = np.linspace(0.0, available, count)
        path = np.stack([
            np.interp(depth, arc, best_points[:, 0]),
            np.interp(depth, arc, best_points[:, 1]),
        ], axis=1)
        widths = np.interp(depth, arc, best_widths)
        # Preserve the actual connected arm width.  This path is not a delta
        # or inlet overlay; it is the same river continuing to the coastline.
        result.append((path, widths, depth, available, (vx, vy)))
    return result


def soft_field(pix, P, TAN, S, HW, MIX, sigma):
    """Local Gaussian blend of the centreline samples.

    V2 originally compared every image pixel with every curve sample.  That
    happens to work for a small proof crop but explodes in memory for a real
    10x10-cell world chunk.  A KD tree gives the same local field contract
    while bounding the working set, which also makes the experimental full
    map variant practical to build.
    """
    n = len(pix)
    wsum = np.zeros(n)
    possum = np.zeros((n, 2))
    tansum = np.zeros((n, 2))
    ssum = np.zeros(n)
    hwsum = np.zeros(n)
    mixsum = np.zeros(n)
    dmin = np.full(n, 1e9)
    inv2s2 = 1.0 / (2 * sigma * sigma)
    cutoff = 3.0 * sigma
    tree = cKDTree(P)
    neighbours = min(48, len(P))
    block = 32768
    for lo in range(0, n, block):
        hi = min(n, lo + block)
        dd, ii = tree.query(
            pix[lo:hi], k=neighbours, distance_upper_bound=cutoff, workers=1
        )
        if neighbours == 1:
            dd, ii = dd[:, None], ii[:, None]
        valid = np.isfinite(dd) & (ii < len(P))
        safe = np.where(valid, ii, 0)
        w = np.where(valid, np.exp(-(dd * dd) * inv2s2), 0.0)
        local_w = w.sum(axis=1)
        wsum[lo:hi] = local_w
        dmin[lo:hi] = dd[:, 0]
        possum[lo:hi] = (w[..., None] * P[safe]).sum(axis=1)
        tansum[lo:hi] = (w[..., None] * TAN[safe]).sum(axis=1)
        ssum[lo:hi] = (w * S[safe]).sum(axis=1)
        hwsum[lo:hi] = (w * HW[safe]).sum(axis=1)
        mixsum[lo:hi] = (w * MIX[safe]).sum(axis=1)
    wsafe = np.maximum(wsum, 1e-9)
    pos_f = possum / wsafe[:, None]
    tan_f = tansum / (np.hypot(tansum[:, 0], tansum[:, 1])[:, None] + 1e-9)
    return dict(dist=dmin, pos=pos_f, tan=tan_f, s=ssum / wsafe, hw=hwsum / wsafe,
                mix=mixsum / wsafe, w=wsum)


# --------------------------------------------------------------------- noise
def octave(shape, scale, rng):
    small = rng.normal(size=(max(2, int(shape[0] / scale)), max(2, int(shape[1] / scale))))
    small = ndimage.gaussian_filter(small, 0.6, mode="wrap")
    big = np.asarray(Image.fromarray(small).resize((shape[1], shape[0]), Image.BICUBIC))
    return big / (big.std() + 1e-6)


def fbm(shape, rng, base_scale):
    out = np.zeros(shape)
    amp = 1.0
    tot = 0.0
    for k in range(4):
        out += amp * octave(shape, base_scale / (1.6 ** k), rng)
        tot += amp
        amp *= 0.55
    return out / tot


def _coord_hash(ix, iy, seed):
    """Deterministic random values for integer lattice coordinates."""
    with np.errstate(over="ignore"):
        xbits = (np.asarray(ix, dtype=np.int64).astype(np.uint64)
                 * np.uint64(0x9E3779B185EBCA87))
        ybits = (np.asarray(iy, dtype=np.int64).astype(np.uint64)
                 * np.uint64(0xC2B2AE3D27D4EB4F))
        # The operands are commonly shaped (1,W) and (H,1).  Forming the
        # XOR as a new array permits broadcasting; an in-place XOR cannot
        # expand its left-hand side to the two-dimensional field.
        v = xbits ^ ybits
        v ^= np.uint64(seed + 1) * np.uint64(0x165667B19E3779F9)
        v ^= v >> np.uint64(30)
        v *= np.uint64(0xBF58476D1CE4E5B9)
        v ^= v >> np.uint64(27)
        v *= np.uint64(0x94D049BB133111EB)
        v ^= v >> np.uint64(31)
    return ((v >> np.uint64(11)).astype(np.float64) * (1.0 / (1 << 53))) * 2.0 - 1.0


def coordinate_fbm(shape, world_x0, world_y0, world_period_x, seed, base_scale):
    """Crop-independent value noise anchored in world pixel coordinates."""
    H, W = shape
    gx = np.mod(world_x0 + np.arange(W, dtype=float), world_period_x)
    gy = world_y0 + np.arange(H, dtype=float)
    out = np.zeros((H, W), float)
    amp = 1.0
    total = 0.0
    for octave_i in range(4):
        scale = base_scale / (1.6 ** octave_i)
        nx = max(2, int(round(world_period_x / scale)))
        cell_x = world_period_x / nx
        qx = gx / cell_x
        ix0 = np.floor(qx).astype(np.int64)
        fx = qx - ix0
        ix1 = (ix0 + 1) % nx
        ix0 %= nx

        qy = gy / scale
        iy0 = np.floor(qy).astype(np.int64)
        fy = qy - iy0
        iy1 = iy0 + 1
        sx = fx * fx * (3.0 - 2.0 * fx)
        sy = fy * fy * (3.0 - 2.0 * fy)

        a = _coord_hash(ix0[None, :], iy0[:, None], seed + octave_i * 17)
        b = _coord_hash(ix1[None, :], iy0[:, None], seed + octave_i * 17)
        c = _coord_hash(ix0[None, :], iy1[:, None], seed + octave_i * 17)
        d = _coord_hash(ix1[None, :], iy1[:, None], seed + octave_i * 17)
        top = a * (1.0 - sx[None, :]) + b * sx[None, :]
        bottom = c * (1.0 - sx[None, :]) + d * sx[None, :]
        out += amp * (top * (1.0 - sy[:, None]) + bottom * sy[:, None])
        total += amp
        amp *= 0.55
    # Value-noise octaves have lower variance than the old normal-noise
    # pyramid.  This fixed factor preserves its visible material strength
    # without crop-dependent normalisation (which would reintroduce seams).
    return out / total * 2.4


def coordinate_fbm_points(pixel_x, pixel_y, world_x0, world_y0,
                          world_period_x, seed, base_scale):
    """The same crop-independent noise evaluated only at owned pixels."""
    gx = np.mod(world_x0 + np.asarray(pixel_x, dtype=float), world_period_x)
    gy = world_y0 + np.asarray(pixel_y, dtype=float)
    out = np.zeros(len(gx), float)
    amp = 1.0
    total = 0.0
    for octave_i in range(4):
        scale = base_scale / (1.6 ** octave_i)
        nx = max(2, int(round(world_period_x / scale)))
        cell_x = world_period_x / nx
        qx = gx / cell_x
        ix0 = np.floor(qx).astype(np.int64)
        fx = qx - ix0
        ix1 = (ix0 + 1) % nx
        ix0 %= nx

        qy = gy / scale
        iy0 = np.floor(qy).astype(np.int64)
        fy = qy - iy0
        iy1 = iy0 + 1
        sx = fx * fx * (3.0 - 2.0 * fx)
        sy = fy * fy * (3.0 - 2.0 * fy)

        a = _coord_hash(ix0, iy0, seed + octave_i * 17)
        b = _coord_hash(ix1, iy0, seed + octave_i * 17)
        c = _coord_hash(ix0, iy1, seed + octave_i * 17)
        d = _coord_hash(ix1, iy1, seed + octave_i * 17)
        top = a * (1.0 - sx) + b * sx
        bottom = c * (1.0 - sx) + d * sx
        out += amp * (top * (1.0 - sy) + bottom * sy)
        total += amp
        amp *= 0.55
    return out / total * 2.4


# ------------------------------------------------------------------- ground
def _fill_from(img, hole, source, jitter_seed):
    """Inpaint `hole` sampling only from pixels where `source` is True."""
    H, W, _ = img.shape
    exclude = hole | ~source
    if exclude.all():                      # no valid donor at all -- degrade to img
        return img.copy()
    idx = ndimage.distance_transform_edt(exclude, return_indices=True)[1]
    bx, by = idx[1].astype(float), idx[0].astype(float)
    ys, xs = np.mgrid[0:H, 0:W]
    dx, dy = bx - xs, by - ys
    sx = np.clip((bx + dx * 1.9).round().astype(int), 0, W - 1)
    sy = np.clip((by + dy * 1.9).round().astype(int), 0, H - 1)
    bad = exclude[sy, sx]
    sx, sy = np.where(bad, bx.astype(int), sx), np.where(bad, by.astype(int), sy)
    jx = (fbm((H, W), np.random.default_rng(jitter_seed), 30) * 7).astype(int)
    jy = (fbm((H, W), np.random.default_rng(jitter_seed + 1), 30) * 7).astype(int)
    sx2 = np.clip(sx + jx, 0, W - 1)
    sy2 = np.clip(sy + jy, 0, H - 1)
    bad2 = exclude[sy2, sx2]
    sx2, sy2 = np.where(bad2, sx, sx2), np.where(bad2, sy, sy2)
    return img[sy2, sx2]


def rebuild_ground(img, hole, sea):
    """Fill the erased river/bank pixels.

    A hole pixel can end up ambiguous near the coast (a stray water pocket
    that a topology heuristic could misjudge either way). Rather than commit
    to one classification and risk a wrong-coloured patch, blend the land
    fill and the sea fill by the LOCAL sea probability -- a misclassification
    then degrades to a soft, plausible colour instead of a visible blob.
    """
    land_fill = _fill_from(img, hole, ~sea, jitter_seed=5)
    sea_fill = _fill_from(img, hole, sea, jitter_seed=7)
    f = ndimage.gaussian_filter(sea.astype(float), 6.0)[..., None]
    filled = land_fill * (1 - f) + sea_fill * f
    return np.where(hole[..., None], filled, img)


# ------------------------------------------------------------------- render
def window_pixels(d, world_id, x0, y0, w, h):
    T = d["tile_px"]
    CW, CH = d["chunk_cells"]["width"], d["chunk_cells"]["height"]
    wd = WORLDS / world_id
    out = np.zeros((h * T, w * T, 3), float)
    for cy in range(h):
        for cx in range(w):
            gx, gy = x0 + cx, y0 + cy
            p = wd / "chunks" / f"x{gx // CW:02d}_y{gy // CH:02d}.png"
            if not p.exists():
                continue
            ch = np.asarray(Image.open(p).convert("RGB")).astype(float)
            lx, ly = (gx % CW) * T, (gy % CH) * T
            out[cy * T:(cy + 1) * T, cx * T:(cx + 1) * T] = ch[ly:ly + T, lx:lx + T]
    return out


def window_river_cells(d, x0, y0, w, h):
    """River records intersecting a crop, including horizontal wrap copies."""
    world_width = int(d["width"])
    result = []
    for record in d["rivers"]:
        ry = int(record["y"])
        if not (y0 <= ry < y0 + h):
            continue
        for shift in (-world_width, 0, world_width):
            rx = int(record["x"]) + shift
            if x0 <= rx < x0 + w:
                copy = dict(record)
                copy["x"] = rx
                result.append(copy)
    return result


def cell_water_coverage(d, x0, y0, w, h):
    """Blocky fallback used by standalone proofs without CoastV31 coverage."""
    T = int(d["tile_px"])
    terrain = d["terrain"]
    world_width = int(d["width"])
    cells = np.zeros((h, w), float)
    for cy in range(h):
        gy = y0 + cy
        if not (0 <= gy < len(terrain)):
            continue
        for cx in range(w):
            gx = (x0 + cx) % world_width
            cells[cy, cx] = terrain[gy][gx] == 10
    return np.kron(cells, np.ones((T, T), float))


def composite_relief_sources(canvas, source_tiles, x0, y0, T):
    """Place one complete V19 hill/mountain source composition per first cell.

    These authored RGBA assets contain the relief and its fine outlet as one
    image.  Each is centred and clipped to the logical source cell; therefore
    the river leaves at the exact edge while no foreign ground can cover a
    neighbour.  This is the final source-layer operation.
    """
    result = np.asarray(canvas, dtype=float).copy()
    for record, kind in source_tiles:
        port = record["ports"]
        direction = SOURCE_DIRECTION[port]
        path = SOURCE_HD / f"{kind}_source_{direction}_v19.png"
        if not path.is_file():
            continue
        with Image.open(path) as opened:
            sprite = opened.convert("RGBA")
        # Scale the complete source composition to the tile: its registry
        # anchor sits on the spring near the relief centre and its fine outlet
        # must just reach the selected N/E/S/W edge before clipping.
        target = round(T * 1.10)
        scale = target / max(sprite.size)
        sprite = sprite.resize(
            (max(1, round(sprite.width * scale)),
             max(1, round(sprite.height * scale))),
            Image.Resampling.LANCZOS,
        )
        cell_left = int(record["x"] - x0) * T
        cell_top = int(record["y"] - y0) * T

        rgba = np.asarray(sprite, dtype=float)
        # Locate the ACTUAL blue terminal in this direction-specific PNG.
        # Anchoring only the spring fissure leaves different gaps because the
        # four authored outlets do not all end at the same relative extent.
        blue = (
            (rgba[..., 3] > 80.0)
            & (rgba[..., 2] > rgba[..., 0] * 1.22)
            & (rgba[..., 2] > rgba[..., 1] * 1.06)
            & (rgba[..., 2] > 50.0)
        )
        blue_y, blue_x = np.nonzero(blue)
        if not len(blue_x):
            continue
        if port == "N":
            edge = blue_y.min()
            terminal = blue_y <= edge + 2
        elif port == "E":
            edge = blue_x.max()
            terminal = blue_x >= edge - 2
        elif port == "S":
            edge = blue_y.max()
            terminal = blue_y >= edge - 2
        else:
            edge = blue_x.min()
            terminal = blue_x <= edge + 2
        terminal_x = float(np.median(blue_x[terminal]))
        terminal_y = float(np.median(blue_y[terminal]))

        # Put that real terminal three pixels beyond the exact technical port.
        # The computed river begins at the port, giving a genuine overlap in
        # every direction instead of a separate straight repair stroke.
        vx, vy = PORT_VEC[port]
        port_x = cell_left + T * 0.5 + vx * T * 0.5
        port_y = cell_top + T * 0.5 + vy * T * 0.5
        overlap = max(3, round(T * 0.035))
        left = round(port_x + vx * overlap - terminal_x)
        top = round(port_y + vy * overlap - terminal_y)

        # Keep the relief inside its logical tile, but let the authored fine
        # outlet overlap the computed river by a few pixels on the selected
        # exit side.  The PNG is transparent there except for the rivulet, so
        # this closes the last anti-aliased hairline without duplicating land
        # in the neighbouring cell.
        overlap = max(4, round(T * 0.07))
        x0_limit = cell_left - (overlap if port == "W" else 0)
        y0_limit = cell_top - (overlap if port == "N" else 0)
        x1_limit = cell_left + T + (overlap if port == "E" else 0)
        y1_limit = cell_top + T + (overlap if port == "S" else 0)
        x0d = max(x0_limit, left, 0)
        y0d = max(y0_limit, top, 0)
        x1d = min(x1_limit, left + sprite.width, result.shape[1])
        y1d = min(y1_limit, top + sprite.height, result.shape[0])
        if x1d <= x0d or y1d <= y0d:
            continue
        sx0, sy0 = x0d - left, y0d - top
        sx1, sy1 = sx0 + x1d - x0d, sy0 + y1d - y0d
        patch = rgba[sy0:sy1, sx0:sx1]
        alpha = patch[..., 3:4] / 255.0
        result[y0d:y1d, x0d:x1d] = (
            result[y0d:y1d, x0d:x1d] * (1.0 - alpha)
            + patch[..., :3] * alpha
        )
    return result


def paint_rivers(
    d,
    ground_image,
    x0,
    y0,
    seed=11,
    water_coverage=None,
    coast_signed_distance=None,
):
    """Paint V2 exactly once on a river-free high-resolution foundation.

    ``ground_image`` is deliberately an input instead of being reconstructed
    from the old beauty chunks.  The map keeps its technical river topology,
    while this function becomes the sole owner of visible river pixels.
    ``water_coverage`` and ``coast_signed_distance`` are CoastV31 fields for
    the same crop.  The signed distance is what lets a mouth meet the organic
    coast itself instead of the unrelated edge of its logical terrain cell.
    """
    ground = np.asarray(ground_image.convert("RGB") if isinstance(ground_image, Image.Image)
                        else ground_image, dtype=float)
    H, W, channels = ground.shape
    T = int(d["tile_px"])
    if channels != 3 or H % T or W % T:
        raise ValueError(f"ground must be an RGB whole-cell crop, got {ground.shape}")
    h, w = H // T, W // T
    cells = window_river_cells(d, x0, y0, w, h)
    if not cells:
        return np.clip(ground, 0, 255).astype(np.uint8)

    underlay = d.get("inferred_presentation_underlay", d["terrain"])
    world_width = int(d["width"])
    source_tiles = []
    for record in cells:
        if len(record["ports"]) != 1:
            continue
        code = int(underlay[int(record["y"])][int(record["x"]) % world_width])
        if code == 4:
            source_tiles.append((record, "hill"))
        elif code == 5:
            source_tiles.append((record, "mountain"))
    source_tile_cells = {(record["x"], record["y"]) for record, _ in source_tiles}

    incell = np.zeros((H, W), bool)
    for record in cells:
        lx = int(record["x"] - x0) * T
        ly = int(record["y"] - y0) * T
        incell[ly:ly + T, lx:lx + T] = True

    if water_coverage is None:
        water_coverage = cell_water_coverage(d, x0, y0, w, h)
    water_coverage = np.asarray(water_coverage, dtype=float)
    if water_coverage.shape != (H, W):
        raise ValueError(
            f"water coverage {water_coverage.shape} does not match ground {(H, W)}"
        )
    water_coverage = np.clip(water_coverage, 0.0, 1.0)
    if coast_signed_distance is not None:
        coast_signed_distance = np.asarray(coast_signed_distance, dtype=float)
        if coast_signed_distance.shape != (H, W):
            raise ValueError(
                "coast signed distance "
                f"{coast_signed_distance.shape} does not match ground {(H, W)}"
            )

    ys, xs = np.mgrid[0:H, 0:W]
    pix = np.stack([xs.ravel(), ys.ravel()], axis=1).astype(float)

    # Resolve the organic coast before building the field.  A mouth is an
    # extension of the SAME authored curve, at its unchanged terminal width;
    # it is deliberately not a second shape composited over the river later.
    mouth_geometries = []
    for path, widths, depth, reach, (mouth_vx, mouth_vy) in build_mouth_inlets(
        cells, x0, y0, T
    ):
        # Use the authored endpoint direction whenever it still agrees with
        # the technical exit.  This preserves bends immediately before a
        # lake/sea instead of snapping them to a cardinal straight line.
        tangent_index = min(6, len(path) - 1)
        actual = path[0] - path[tangent_index]
        actual_norm = float(np.hypot(actual[0], actual[1]))
        if actual_norm > 1e-6:
            actual /= actual_norm
            if actual[0] * mouth_vx + actual[1] * mouth_vy > 0.55:
                mouth_vx, mouth_vy = float(actual[0]), float(actual[1])

        port_x, port_y = float(path[0, 0]), float(path[0, 1])
        samples = np.linspace(-T * 0.48, T * 0.88, int(T * 1.36) + 1)
        sample_x = np.clip(
            np.rint(port_x + mouth_vx * samples).astype(int), 0, W - 1
        )
        sample_y = np.clip(
            np.rint(port_y + mouth_vy * samples).astype(int), 0, H - 1
        )
        if coast_signed_distance is not None:
            profile = coast_signed_distance[sample_y, sample_x]
        else:
            profile = 0.5 - water_coverage[sample_y, sample_x]
        crossings = np.flatnonzero((profile[:-1] > 0.0) & (profile[1:] <= 0.0))
        if not len(crossings):
            continue
        ci = int(crossings[-1])
        p0, p1 = float(profile[ci]), float(profile[ci + 1])
        fraction = p0 / max(p0 - p1, 1e-6)
        coast_at = float(
            samples[ci] + (samples[ci + 1] - samples[ci]) * fraction
        )

        # A slanted shoreline crosses the left bank, centre and right bank at
        # different along-distances.  Extending only six pixels past the
        # centre leaves a triangular piece of coast blocking one river bank.
        # Find the last crossing over the COMPLETE authored width instead.
        coast_across = [coast_at]
        for across_offset in np.linspace(
            -float(widths[0]) * 0.95, float(widths[0]) * 0.95, 9
        ):
            offset_x = -mouth_vy * across_offset
            offset_y = mouth_vx * across_offset
            offset_sample_x = np.clip(
                np.rint(port_x + offset_x + mouth_vx * samples).astype(int),
                0,
                W - 1,
            )
            offset_sample_y = np.clip(
                np.rint(port_y + offset_y + mouth_vy * samples).astype(int),
                0,
                H - 1,
            )
            if coast_signed_distance is not None:
                offset_profile = coast_signed_distance[
                    offset_sample_y, offset_sample_x
                ]
            else:
                offset_profile = 0.5 - water_coverage[
                    offset_sample_y, offset_sample_x
                ]
            offset_crossings = np.flatnonzero(
                (offset_profile[:-1] > 0.0) & (offset_profile[1:] <= 0.0)
            )
            if not len(offset_crossings):
                continue
            oi = int(offset_crossings[-1])
            op0, op1 = float(offset_profile[oi]), float(offset_profile[oi + 1])
            ofraction = op0 / max(op0 - op1, 1e-6)
            coast_across.append(float(
                samples[oi]
                + (samples[oi + 1] - samples[oi]) * ofraction
            ))
        coast_far_at = max(coast_across)
        mouth_geometries.append({
            "port_x": port_x,
            "port_y": port_y,
            "vx": float(mouth_vx),
            "vy": float(mouth_vy),
            "coast_at": coast_at,
            "coast_far_at": coast_far_at,
            # Six pixels of genuine full-width continuation are enough to
            # enter the receiving water without drawing a channel into it.
            "end_at": coast_far_at + 6.0,
            "river_half": float(max(widths[0], 1.0)),
        })

    field_points = build_points(
        cells, x0, y0, T,
        mouth_extensions=mouth_geometries,
        source_tile_cells=source_tile_cells,
    )
    if field_points is None:
        # Keep the river-free V79 foundation untouched and place only the
        # authored fine source tile(s).  Calling soft_field with no samples
        # would be meaningless and previously aborted the complete world.
        return np.clip(
            composite_relief_sources(ground, source_tiles, x0, y0, T),
            0,
            255,
        ).astype(np.uint8)
    P, TAN, S, HW, MIX = field_points
    # Only technical river cells and the short, explicit mouth continuation
    # can ever receive non-zero alpha below.  The former implementation ran
    # a 48-neighbour KD query for every pixel of the 14x14-cell halo anyway —
    # often 1.8 million queries to change one 96x96 cell.  Build the exact
    # eventual ownership mask first and perform the identical field maths on
    # those pixels only.  Outside this mask the final canvas is provably the
    # untouched foundation.
    active_mask = incell.ravel().copy()
    for mouth in mouth_geometries:
        dx = pix[:, 0] - mouth["port_x"]
        dy = pix[:, 1] - mouth["port_y"]
        along = dx * mouth["vx"] + dy * mouth["vy"]
        across = np.abs(-dx * mouth["vy"] + dy * mouth["vx"])
        active_mask |= (
            (across <= mouth["river_half"] * 1.8)
            & (along >= mouth["coast_at"] - T * 0.34)
            & (along <= mouth["end_at"] + 4.0)
        )
    active_idx = np.flatnonzero(active_mask)
    active_pix = pix[active_idx]
    fld = soft_field(active_pix, P, TAN, S, HW, MIX, sigma=T * 0.085)
    tx, ty = fld["tan"][:, 0], fld["tan"][:, 1]

    vec = active_pix - fld["pos"]
    # the TRUE nearest distance, not distance-to-the-blended-average-position:
    # inside a tight meander loop, pos_f averages points from opposite banks
    # and collapses toward the loop's centre, which would falsely paint the
    # enclosed island as riverbed. dmin has no such blind spot.
    dist = fld["dist"]
    side = np.sign(vec[:, 0] * (-ty) + vec[:, 1] * tx)
    hw = np.maximum(fld["hw"], 1.0)
    ratio = dist / hw                          # UNCLIPPED -- must decay far away
    t = np.clip(ratio, 0, 1) * side             # clipped only for the cross-section shade
    mix = np.clip(fld["mix"], 0, 1)

    # The Gaussian field also blends neighbouring inland samples into pixels
    # at a mouth bank.  Without this correction the centre becomes sea first
    # and leaves a pointed/vertical cap.  Drive the material transition by
    # distance ALONG the mouth for its complete visible cross-section.
    for mouth in mouth_geometries:
        dx = active_pix[:, 0] - mouth["port_x"]
        dy = active_pix[:, 1] - mouth["port_y"]
        along = dx * mouth["vx"] + dy * mouth["vy"]
        across = np.abs(-dx * mouth["vy"] + dy * mouth["vx"])
        colour_start = mouth["coast_at"] - T * 0.22
        mouth_mix = np.clip(
            (along - colour_start)
            / max(mouth["coast_at"] - colour_start, 1.0),
            0.0,
            1.0,
        )
        mouth_mix = mouth_mix * mouth_mix * (3.0 - 2.0 * mouth_mix)
        # The old corridor had no downstream limit.  With two opposing
        # inflows into one lake it continued through the complete lake and
        # recoloured the other river wherever the infinite strips crossed,
        # leaving two flat, hard-edged blue polygons.  Own only this mouth's
        # real short reach and feather both the side and the terminal edge.
        side_fade = 1.0 - np.clip(
            (across - mouth["river_half"])
            / max(mouth["river_half"] * 0.25, 1.0),
            0.0,
            1.0,
        )
        end_fade = np.clip((mouth["end_at"] + 4.0 - along) / 4.0, 0.0, 1.0)
        end_fade = end_fade * end_fade * (3.0 - 2.0 * end_fade)
        mouth_mix *= side_fade * end_fade
        mix = np.maximum(mix, mouth_mix)

    world_x0, world_y0 = x0 * T, y0 * T
    world_period_x = int(d["width"]) * T
    fibre = coordinate_fbm_points(
        active_pix[:, 0], active_pix[:, 1], world_x0, world_y0,
        world_period_x, seed + 1, 7,
    )
    chop = coordinate_fbm_points(
        active_pix[:, 0], active_pix[:, 1], world_x0, world_y0,
        world_period_x, seed + 2, 2.3,
    )
    sparkle = coordinate_fbm_points(
        active_pix[:, 0], active_pix[:, 1], world_x0, world_y0,
        world_period_x, seed + 3, 1.1,
    )

    calm = (1 - mix) ** 1.5          # 1 inland -> 0 at the mouth: everything settles down

    at = np.abs(t)
    shade = np.cos(np.clip(at, 0, 1) * np.pi / 2)          # 1 centre -> 0 edge, smooth
    deep = np.array([13, 55, 92.])
    shallow = np.array([88, 160, 178.])
    riverbed = deep[None, :] * shade[:, None] + shallow[None, :] * (1 - shade[:, None])
    grain = (fibre * 0.55 + chop * 0.30 + sparkle * 0.20) * 15.0
    riverbed = riverbed + (grain * calm)[:, None] * (0.5 + 0.5 * shade[:, None])
    riverbed = riverbed + (side * 10.0 * calm)[:, None]     # the bright bank edge fades too

    ground_flat = ground.reshape(-1, 3)
    ground_active = ground_flat[active_idx]
    # Carry real local water material upstream through the complete mouth
    # width.  The donor sits behind the pale shore band; sampling that band
    # itself would recreate the blue cap which made the river look stopped.
    water_source = (
        coast_signed_distance <= -12.0
        if coast_signed_distance is not None
        else water_coverage >= 0.96
    )
    nearest_water = None
    if water_source.any():
        nearest_water = ndimage.distance_transform_edt(
            ~water_source, return_indices=True
        )[1]
        sea_col = ground[nearest_water[0], nearest_water[1]].reshape(-1, 3)[active_idx]
    else:
        sea_col = ground_active

    # Inside each mouth use a translated strip of the actual receiving-water
    # texture.  Unlike nearest-pixel propagation this retains variation across
    # the whole river width and cannot look like a flat turquoise rectangle.
    mouth_sea_col = sea_col.copy()
    for mouth in mouth_geometries:
        dx = active_pix[:, 0] - mouth["port_x"]
        dy = active_pix[:, 1] - mouth["port_y"]
        along = dx * mouth["vx"] + dy * mouth["vy"]
        signed_across = -dx * mouth["vy"] + dy * mouth["vx"]
        across = np.abs(signed_across)
        donor_along = np.maximum(
            mouth["coast_at"] + 4.0,
            mouth["coast_at"] + 12.0 + (along - mouth["coast_at"]) * 0.28,
        )
        donor_x = (
            mouth["port_x"] + mouth["vx"] * donor_along
            - mouth["vy"] * signed_across
        )
        donor_y = (
            mouth["port_y"] + mouth["vy"] * donor_along
            + mouth["vx"] * signed_across
        )
        if nearest_water is not None:
            # On a diagonal coast, translating a full-width strip by the
            # centreline distance can still land its outer bank on beach or
            # land.  Resolve every donor coordinate to a guaranteed deep-water
            # pixel before copying it; a fully opaque mouth can then never
            # contain a sand-coloured remnant.
            donor_ix = np.clip(np.rint(donor_x).astype(int), 0, W - 1)
            donor_iy = np.clip(np.rint(donor_y).astype(int), 0, H - 1)
            sea_y = nearest_water[0, donor_iy, donor_ix]
            sea_x = nearest_water[1, donor_iy, donor_ix]
            local_sea = ground[sea_y, sea_x]
        else:
            local_sea = np.stack([
                ndimage.map_coordinates(
                    ground[..., channel], [donor_y, donor_x],
                    order=1, mode="nearest",
                )
                for channel in range(3)
            ], axis=1)
        active = (
            (across <= mouth["river_half"] * 1.35)
            & (along >= mouth["coast_at"] - T * 0.24)
            & (along <= mouth["end_at"] + 4.0)
        )
        mouth_sea_col[active] = local_sea[active]
    final_col = riverbed * (1 - mix[:, None]) + mouth_sea_col * mix[:, None]

    # Offshore, the colour produced by that same field becomes exactly the
    # untouched lake/sea texture.  There is therefore no cap to hide and no
    # second alpha shape: the river simply becomes indistinguishable from the
    # receiving water after five pixels.
    mouth_to_ground = np.zeros(len(active_idx), float)
    mouth_allow = np.zeros(len(active_idx), float)
    mouth_alpha_floor = np.zeros(len(active_idx), float)
    mouth_coast_protect = np.zeros(len(active_idx), float)
    for mouth in mouth_geometries:
        dx = active_pix[:, 0] - mouth["port_x"]
        dy = active_pix[:, 1] - mouth["port_y"]
        along = dx * mouth["vx"] + dy * mouth["vy"]
        across = np.abs(-dx * mouth["vy"] + dy * mouth["vx"])
        broad_corridor = across <= mouth["river_half"] * 1.8
        owns = (
            broad_corridor
            & (along >= mouth["coast_at"] - T * 0.34)
            & (along <= mouth["end_at"] + 4.0)
        )
        mouth_allow[owns] = 1.0
        # The authored half-width is the river itself, not the centre of an
        # antialiasing band.  Keep that complete width opaque at the crossing
        # and put the feather only OUTSIDE it.  The previous symmetric feather
        # started at 90% width, letting a pale coast wedge shine through the
        # last ten percent of one bank on diagonal shores.
        # Follow the actual curved field here.  Measuring opacity against the
        # straight helper corridor left one outer half of a curved inlet below
        # full opacity, so the diagonal foam/coast line remained visible
        # through the river.  The true field ratio covers exactly the painted
        # river width and does not widen or fan the mouth.
        edge_alpha = 1.0 - np.clip((ratio - 1.10) / 0.08, 0.0, 1.0)
        floor_start = np.clip(
            (along - (mouth["coast_at"] - T * 0.34)) / (T * 0.12),
            0.0,
            1.0,
        )
        floor_start = floor_start * floor_start * (3.0 - 2.0 * floor_start)
        mouth_alpha_floor = np.maximum(
            mouth_alpha_floor, np.where(owns, edge_alpha * floor_start, 0.0)
        )
        if coast_signed_distance is not None:
            # Absolute ownership at the crossing itself.  This narrow band is
            # the only place where even a tiny remainder of CoastV31's foam
            # would read as a white line through the river.  It follows the
            # actual curved river ratio, not the cardinal helper corridor.
            shore_strength = 1.0 - np.clip(
                (np.abs(coast_signed_distance.ravel()[active_idx]) - 6.0) / 6.0,
                0.0,
                1.0,
            )
            mouth_coast_protect = np.maximum(
                mouth_coast_protect,
                np.where(owns, shore_strength * edge_alpha, 0.0),
            )
            # Follow the REAL local shore across the width.  This makes the
            # continuation reach water at both banks even when the coast is
            # diagonal.  Do NOT blend the foundation back at distance zero:
            # its antialiased beach/foam stroke lives exactly there and would
            # draw the white coastline straight across an otherwise opaque
            # river.  Cover that shore band completely for two water pixels,
            # then become the untouched water texture over the next four.
            water_depth_fade = np.clip(
                (-coast_signed_distance.ravel()[active_idx] - 2.0) / 4.0, 0.0, 1.0
            )
            # A tiny inland lake may never contain a pixel twelve units from
            # every shore.  Always finish the hand-off a few pixels after the
            # farthest bank crossing as well, or two opposing mouths can meet
            # as a flat translated-water strip across the lake.
            along_fade = np.clip(
                (along - mouth["coast_far_at"] - 2.0) / 4.0, 0.0, 1.0
            )
            water_side = np.clip(
                (-coast_signed_distance.ravel()[active_idx] - 1.0) / 2.0,
                0.0,
                1.0,
            )
            water_side = water_side * water_side * (3.0 - 2.0 * water_side)
            along_fade *= water_side
            to_ground = np.maximum(water_depth_fade, along_fade)
        else:
            to_ground = np.clip(
                (along - mouth["coast_at"]) / 5.0, 0.0, 1.0
            )
        to_ground = to_ground * to_ground * (3.0 - 2.0 * to_ground)
        mouth_to_ground = np.maximum(
            mouth_to_ground, np.where(broad_corridor, to_ground, 0.0)
        )
    # Never copy coast/foam material back into the protected river crossing.
    # Fade the protection outside the coast band so its own boundary cannot
    # become a replacement polygon edge.
    mouth_to_ground *= 1.0 - mouth_coast_protect
    final_col = (
        final_col * (1.0 - mouth_to_ground[:, None])
        + ground_active * mouth_to_ground[:, None]
    )

    # soft-alpha compositing everywhere: no boolean threshold anywhere in the
    # image means there is no polygon edge that can show up as a seam. The
    # transition band width scales up with the funnel so a wide mouth still
    # gets a gentle shore, not a knife edge.
    # Material may change at the mouth; geometry may not.  A constant feather
    # keeps the visible width identical instead of subtly fanning it wider.
    bw = np.full_like(mix, 0.10)
    alpha = 1.0 - np.clip((ratio - (1.0 - bw)) / (2 * bw), 0, 1)
    alpha = alpha ** 1.4
    alpha = np.maximum(alpha, mouth_alpha_floor)

    # Inland V2 owns its technical cells.  The one continuous mouth curve is
    # additionally allowed through the organic coast at full river width.
    paintable = incell.ravel()[active_idx].astype(float)
    if coast_signed_distance is not None:
        land_allow = np.clip(
            (coast_signed_distance.ravel()[active_idx] + 1.0) / 2.5,
            0.0,
            1.0,
        )
        land_allow = land_allow * land_allow * (3.0 - 2.0 * land_allow)
        paintable *= land_allow
    paintable = np.maximum(paintable, mouth_allow)
    alpha = alpha * paintable
    # River is the final layer and owns one hundred percent of its visible
    # width where it crosses the shoreline.  No white coast pixel can survive.
    alpha = np.maximum(alpha, mouth_coast_protect)

    # Prepare every background/bank effect FIRST.  The river composite below
    # is intentionally the final write in this renderer: no coast, sand, foam,
    # tint, or restored foundation pixel is ever drawn over it afterwards.
    canvas = ground_flat.copy()
    active_canvas = ground_active.copy()

    # wet-sand tint right at the waterline, fading out as the mouth widens
    # (a real shoreline has no ring once it's open sea) and as an inland
    # smoothstep so it never becomes a hard line either
    # tighter than before -- this ring was bleeding well past the actual
    # waterline, especially where two banks sit close together (tight bends)
    bank_pos = np.clip(1.0 - np.abs(ratio - 1.0) / (bw * 0.55), 0, 1) ** 2
    # The bank belongs to the same single coverage field; it cannot become a
    # second, wider ghost river underneath the water band.
    bank_allow = paintable
    wetsand = np.array([182, 172, 122.])
    # Once a mouth has become the untouched water texture, its bank must also
    # be the untouched water texture.  Otherwise the otherwise invisible end
    # of the extended field survives as a hairline in the sea.
    tint = bank_pos * calm * 0.30 * bank_allow * (1.0 - mouth_to_ground)
    active_canvas = (
        active_canvas * (1 - tint[:, None])
        + wetsand[None, :] * tint[:, None]
    )

    # FINAL LAYER.  Inside the authored mouth width `mouth_alpha_floor` makes
    # alpha exactly 1.0, so the already-rendered coastline cannot shine
    # through.  Nothing may be composited after this statement.
    active_canvas = (
        active_canvas * (1 - alpha[:, None]) + final_col * alpha[:, None]
    )
    canvas[active_idx] = active_canvas
    canvas = composite_relief_sources(
        canvas.reshape(H, W, 3), source_tiles, x0, y0, T
    )
    return np.clip(canvas, 0, 255).astype(np.uint8)


def render(world_id, mx, my, half=3, seed=11):
    """Legacy proof wrapper; production variants pass a clean V79 base."""
    d = json.load(open(WORLDS / world_id / "world.json", encoding="utf-8"))
    T = d["tile_px"]
    x0, y0 = mx - half, my - half
    w = h = 2 * half + 1
    img = window_pixels(d, world_id, x0, y0, w, h)
    new = paint_rivers(d, img, x0, y0, seed=seed)
    return img, new, T


if __name__ == "__main__":
    orig, new, T = render("civ_world_19146", 13, 23, half=3)
    OUT = Path(os.environ.get("MAPGENCIV_DEBUG_OUT", str(ROOT / "out" / "debug")))
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(orig.astype(np.uint8)).save(OUT / "tmp2_orig.png")
    Image.fromarray(new).save(OUT / "tmp2_new.png")
    print("ok", new.shape)
