"""Graphic-novel stylization of the rendered frames.

Input  (per frame, from render.py): beauty EXR (scene-linear colour, depth,
object id), ink-line PNG, meta JSON.
Output: display-ready PNG frames.

The look: dark, moody time-lapse with atmospheric haze; painterly flattened
colour (Kuwahara), soft cel banding, spot blacks and a halftone screen in the
shadows, inked contours, warm glow + god rays from fire, split-tone grade,
vignette and grain.
"""
import argparse
import glob
import json
import math
import os
import sys

import cv2
import numpy as np
import OpenEXR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as TL  # noqa: E402
import titles  # noqa: E402

INK = np.array([0.035, 0.03, 0.045], np.float32)        # blue-black ink (display space)
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def read_exr(path):
    with OpenEXR.File(path, separate_channels=True) as f:
        return {k: np.array(v.pixels) for k, v in f.channels().items()}


def load(d, f):
    ch = read_exr(os.path.join(d, f'beauty_{f:04d}.exr'))
    rgb = np.stack([ch['ViewLayer.Combined.R'], ch['ViewLayer.Combined.G'],
                    ch['ViewLayer.Combined.B']], -1).astype(np.float32)
    Z = ch['ViewLayer.Depth.Z'].astype(np.float32)
    ID = np.rint(ch['ViewLayer.IndexOB.X']).astype(np.int32)
    clouds = ch.get('ViewLayer.clouds.X', np.zeros(Z.shape, np.float32)).astype(np.float32)
    lp = os.path.join(d, f'lines_{f:04d}.png')
    L = cv2.imread(lp, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0 if os.path.exists(lp) else np.zeros(Z.shape, np.float32)
    with open(os.path.join(d, f'meta_{f:04d}.json')) as fh:
        meta = json.load(fh)
    meta['_clouds'] = clouds
    return rgb, Z, ID, L, meta


def frame_key(rgb):
    lum = rgb @ LUMA
    lo, hi = np.percentile(lum, [3, 97])
    lum = np.clip(lum, max(lo, 1e-5), max(hi, 1e-4))
    return float(np.exp(np.mean(np.log(lum))))


LOOKS = {
    # exposure targets (log-average display key) for day and night
    'ink': dict(day=0.095, night=0.04, sigma=0.35),
    'paint': dict(day=0.16, night=0.07, sigma=0.3),
    'clean': dict(day=0.16, night=0.07, sigma=0.3),   # paint grade without the paint filter
}


def exposure_target(day, look='ink'):
    L = LOOKS[look]
    return L['day'] * day + L['night'] * (1 - day)


def exposure_curve(keys, days, fps=TL.FPS, look='ink', shots=None):
    """Smoothed auto-exposure (log domain) with a darker target at night.
    With `shots`, smoothing never crosses a cut."""
    keys = np.asarray(keys, float)
    days = np.asarray(days, float)
    target = exposure_target(days, look)
    ev = np.log(target) - np.log(np.maximum(keys, 1e-6))
    sig = LOOKS[look]['sigma'] * fps
    r = int(3 * sig)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    shots = np.zeros(len(ev), int) if shots is None else np.asarray(shots)
    evs = np.zeros_like(ev)
    for s in np.unique(shots):
        idx = np.where(shots == s)[0]
        evs[idx] = np.convolve(np.pad(ev[idx], r, mode='edge'), k, mode='valid')
    return np.exp(evs)


def aces(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0)


def to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def kuwahara(img, r):
    """Classic 4-quadrant Kuwahara: flattens texture into painterly patches."""
    lum = img @ LUMA
    k = r + 1
    means, varis = [], []
    mean_c = cv2.blur(img, (k, k), borderType=cv2.BORDER_REFLECT)
    mean_l = cv2.blur(lum, (k, k), borderType=cv2.BORDER_REFLECT)
    mean_l2 = cv2.blur(lum * lum, (k, k), borderType=cv2.BORDER_REFLECT)
    var = mean_l2 - mean_l * mean_l
    # box of size k centred at c covers [c-r/2, c+r/2]; quadrant windows are the
    # boxes shifted by +-r/2 in x and y
    h = r // 2 + (r % 2)
    shifts = [(-h, -h), (h, -h), (-h, h), (h, h)]
    for dx, dy in shifts:
        M = np.float32([[1, 0, -dx], [0, 1, -dy]])
        means.append(cv2.warpAffine(mean_c, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT))
        varis.append(cv2.warpAffine(var, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT))
    varis = np.stack(varis, 0)
    idx = np.argmin(varis, axis=0)
    means = np.stack(means, 0)
    out = np.take_along_axis(means, idx[None, ..., None], axis=0)[0]
    return out


_halftone_cache = {}


def halftone_dist(h, w, cell, angle_deg):
    key = (h, w, cell, angle_deg)
    if key not in _halftone_cache:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        a = math.radians(angle_deg)
        u = (xx * math.cos(a) + yy * math.sin(a)) / cell
        v = (-xx * math.sin(a) + yy * math.cos(a)) / cell
        du = u - np.floor(u) - 0.5
        dv = v - np.floor(v) - 0.5
        _halftone_cache[key] = np.sqrt(du * du + dv * dv) * cell
    return _halftone_cache[key]


_paper = {}


def paper(h, w):
    if (h, w) not in _paper:
        rng = np.random.default_rng(4)
        n = rng.normal(0, 1, (h // 4 + 1, w // 4 + 1)).astype(np.float32)
        n = cv2.resize(cv2.GaussianBlur(n, (0, 0), 1.2), (w, h), interpolation=cv2.INTER_CUBIC)
        fib = rng.normal(0, 1, (h, w)).astype(np.float32)
        fib = cv2.GaussianBlur(fib, (0, 0), sigmaX=6, sigmaY=0.6)
        p = 1.0 + 0.018 * n / (n.std() + 1e-6) + 0.01 * fib / (fib.std() + 1e-6)
        _paper[(h, w)] = p.astype(np.float32)
    return _paper[(h, w)]


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def radial_blur(img, cx, cy, n=28, step=0.022, decay=0.94):
    h, w = img.shape[:2]
    acc = np.zeros_like(img)
    wsum = 0.0
    wgt = 1.0
    for i in range(n):
        s = 1.0 - i * step
        M = np.float32([[s, 0, cx * (1 - s)], [0, s, cy * (1 - s)]])
        # sample towards the light: scale the image up around the centre
        Minv = cv2.invertAffineTransform(M)
        acc += cv2.warpAffine(img, Minv, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT) * wgt
        wsum += wgt
        wgt *= decay
    return acc / wsum


_star_cat = None


def star_catalogue(n=9000, seed=3):
    global _star_cat
    if _star_cat is None:
        rng = np.random.default_rng(seed)
        v = rng.normal(size=(n, 3))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        b = np.clip(0.08 + 0.22 * rng.pareto(2.4, n), 0, 4.0)
        tw = rng.uniform(0, 2 * np.pi, n)
        _star_cat = (v, b.astype(np.float32), tw)
    return _star_cat


def star_layer(H, W, meta, frame):
    """Stars projected through the frame's camera; the sky turns about the
    celestial pole with the time-lapse clock (star motion at night)."""
    v, b, tw = star_catalogue()
    lat = TL.LATITUDE
    axis = np.array([0.0, math.cos(lat), math.sin(lat)])
    th = -math.radians(15.0 * meta['hour'])
    c, s_ = math.cos(th), math.sin(th)
    v = v * c + np.cross(axis, v) * s_ + np.outer(v @ axis, axis) * (1 - c)
    M = np.array(meta['cam_matrix'], float)
    R = M[:3, :3]
    vc = v @ R
    ok = (vc[:, 2] < -1e-3) & (v[:, 2] > 0.0)
    vc, bb, tt = vc[ok], b[ok], tw[ok]
    f = meta['lens'] / meta['sensor'] * W
    px = W / 2 + f * vc[:, 0] / -vc[:, 2]
    py = H / 2 - f * vc[:, 1] / -vc[:, 2]
    ins = (px >= 0) & (px < W - 1) & (py >= 0) & (py < H - 1)
    px, py, bb, tt = px[ins], py[ins], bb[ins], tt[ins]
    bb = bb * (0.8 + 0.2 * np.sin(tt + frame * 0.9))
    img = np.zeros((H, W), np.float32)
    x0 = np.floor(px).astype(int)
    y0 = np.floor(py).astype(int)
    fx = px - x0
    fy = py - y0
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(img, (y0 + dy, x0 + dx), bb * w)
    return cv2.GaussianBlur(img, (0, 0), 0.55 * H / 720.0) * (H / 720.0) ** 0


def stylize(rgb, Z, ID, L, meta, exposure, frame, params=None):
    H, W = Z.shape
    s = H / 720.0
    day = meta['day']
    night = 1.0 - day
    t = meta['t']

    # --- atmospheric haze (scene-linear), towards the horizon sky colour
    sky = ~np.isfinite(Z) | (Z > 1e8)
    Zc = np.where(sky, 0, Z)
    fog_col = np.array(meta['horizon'], np.float32) * 0.9 + np.array(meta['zenith'], np.float32) * 0.1
    fog = (1.0 - np.exp(-np.maximum(Zc - 180.0, 0.0) / 2400.0)) * (~sky)
    fog = np.clip(fog, 0, 0.92)[..., None].astype(np.float32)
    lin = rgb * (1 - fog) + fog_col[None, None, :] * fog

    # --- exposure + glow (in linear light)
    lin = lin * exposure
    star_k = TL.smoothstep(-7.0, -15.0, meta['sun_el'])
    stars = None
    if star_k > 0:
        st = star_layer(H, W, meta, frame) * sky * np.clip(1.0 - meta['_clouds'] * 1.4, 0, 1)
        stars = 1.0 - np.exp(-st * star_k * exposure * 2.2)
    bright = np.maximum(lin - 0.9, 0.0)
    bright = np.minimum(bright, 30.0)
    glow = np.zeros_like(lin)
    for sig, k in ((2.5, 0.35), (8.0, 0.25), (24.0, 0.18)):
        glow += cv2.GaussianBlur(bright, (0, 0), sig * s) * k
    fire_k = meta.get('fire', 0.0)
    if fire_k > 0.01 and 0 < meta['fire_screen'][0] < 1 and 0 < meta['fire_screen'][1] < 1:
        fx = meta['fire_screen'][0] * W
        fy = (1 - meta['fire_screen'][1]) * H
        fire_mask = np.hypot(*np.meshgrid(np.arange(W) - fx, np.arange(H) - fy)) < 16 * s
        src = bright * fire_mask[..., None]
        rays = radial_blur(src, fx, fy, n=30, step=0.02, decay=0.955)
        glow += rays * (1.6 * fire_k) * np.array([1.0, 0.62, 0.3], np.float32)
        # big soft halo around the beacon
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.hypot(xx - fx, yy - fy) / (22 * s)
        halo = 0.9 / (1.0 + 2.2 * r * r) + np.exp(-r * 0.35) * 0.08
        glow += (halo * fire_k)[..., None] * np.array([1.0, 0.55, 0.22], np.float32)
    # glow is composited after the paint passes so it stays smooth
    glow_disp = 1.0 - np.exp(-glow * 1.35)

    # --- tone map to display
    disp = to_srgb(aces(lin))

    # --- painterly flattening + soft cel banding
    kw = kuwahara(disp, max(2, int(round(2 * s))))
    disp = disp * 0.35 + kw * 0.65
    lum = disp @ LUMA
    n_bands = 6.0
    q = lum * n_bands
    f = q - np.floor(q)
    band = (np.floor(q) + smoothstep(0.35, 0.65, f)) / n_bands
    lum2 = lum * 0.55 + band * 0.45
    disp = disp * (lum2 / np.maximum(lum, 1e-4))[..., None]

    # --- spot blacks and halftone screen in the shadows
    lum = disp @ LUMA
    spot = smoothstep(0.075, 0.025, lum) * (0.75 + 0.2 * night)
    disp = disp * (1 - spot[..., None]) + INK * spot[..., None]
    dark = smoothstep(0.42, 0.10, lum) * (~sky)
    cell = 4.2 * s
    dist = halftone_dist(H, W, cell, 30.0)
    rad = cell * 0.5 * np.sqrt(dark) * 0.95
    dots = smoothstep(rad + 0.6, rad - 0.6, dist) * (dark > 0.02)
    disp = disp * (1 - 0.2 * dots[..., None]) + INK * 0.2 * dots[..., None]

    # --- ink lines (fade into the haze)
    ink_a = np.clip(L * (1.0 - fog[..., 0] * 0.85), 0, 1) * 0.92
    disp = disp * (1 - ink_a[..., None]) + INK * ink_a[..., None]

    # --- grade: split tone, saturation, contrast
    lum = disp @ LUMA
    sh = (1 - lum) ** 2
    hi = lum ** 2
    disp = disp + sh[..., None] * np.array([-0.012, 0.004, 0.022], np.float32) * (1 + night)
    disp = disp + hi[..., None] * np.array([0.03, 0.012, -0.02], np.float32)
    sat = 0.82 - 0.12 * night
    gray = (disp @ LUMA)[..., None]
    disp = gray + (disp - gray) * sat
    disp = np.clip(disp, 0, 1)
    disp = disp * disp * (3 - 2 * disp) * 0.5 + disp * 0.5     # S-curve

    # --- light: glow, halo and god rays (screen blend over the inked image)
    disp = 1.0 - (1.0 - disp) * (1.0 - np.clip(glow_disp, 0, 1))
    # --- stars go on after the painterly passes (Kuwahara would erase them)
    if stars is not None:
        disp = disp + stars[..., None] * np.array([0.9, 0.93, 1.0], np.float32)
    # --- vignette, paper, grain
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / math.sqrt(2)
    vig = 1.0 - 0.42 * rr ** 2.2
    disp = disp * vig[..., None]
    disp = disp * paper(H, W)[..., None]
    rng = np.random.default_rng(frame * 7 + 1)
    g = rng.normal(0, 1, (H, W)).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 0.6 * s)
    disp = disp + g[..., None] * 0.018
    return np.clip(disp, 0, 1)


def unsharp(img, sigma, amount):
    return img + (img - cv2.GaussianBlur(img, (0, 0), sigma)) * amount


def stylize_paint(rgb, Z, ID, meta, exposure, frame, paint=True):
    """Bright, warm, painterly look of the Civ1 wonder films: aerial haze,
    filmic tone curve, soft Kuwahara paint with the detail sharpened back in,
    bloom and beacon glow, gentle warm grade.  No inks, no halftone."""
    H, W = Z.shape
    s = H / 720.0
    day = meta['day']
    night = 1.0 - day

    sky = ~np.isfinite(Z) | (Z > 1e8)
    Zc = np.where(sky, 0, Z)
    fog_col = np.array(meta['horizon'], np.float32) * 0.85 + np.array(meta['zenith'], np.float32) * 0.15
    fog = (1.0 - np.exp(-np.maximum(Zc - 300.0, 0.0) / 6000.0)) * (~sky)
    fog = np.clip(fog, 0, 0.6)[..., None].astype(np.float32)
    lin = rgb * (1 - fog) + fog_col[None, None, :] * fog
    lin = lin * exposure

    star_k = TL.smoothstep(-7.0, -15.0, meta['sun_el']) * meta.get('stars', 1.0)
    stars = None
    if star_k > 0:
        st = star_layer(H, W, meta, frame) * sky * np.clip(1.0 - meta['_clouds'] * 1.4, 0, 1)
        stars = 1.0 - np.exp(-st * star_k * exposure * 2.2)

    bright = np.minimum(np.maximum(lin - 1.0, 0.0), 30.0)
    glow = np.zeros_like(lin)
    for sig, k in ((3.0, 0.22), (10.0, 0.16), (30.0, 0.12)):
        glow += cv2.GaussianBlur(bright, (0, 0), sig * s) * k
    fire_k = meta.get('fire', 0.0)
    if fire_k > 0.01 and 0 < meta['fire_screen'][0] < 1 and 0 < meta['fire_screen'][1] < 1 \
            and meta['fire_screen'][2] > 0:
        fx = meta['fire_screen'][0] * W
        fy = (1 - meta['fire_screen'][1]) * H
        dist = meta['fire_screen'][2]
        size = np.clip(300.0 / max(dist, 1.0), 0.25, 3.0)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.hypot(xx - fx, yy - fy) / (18 * s * size)
        halo = 0.8 / (1.0 + 2.5 * r * r) + np.exp(-r * 0.3) * 0.06 * (0.4 + night)
        glow += (halo * fire_k)[..., None] * np.array([1.0, 0.55, 0.22], np.float32)
        fire_mask = np.hypot(xx - fx, yy - fy) < 14 * s * size
        rays = radial_blur(bright * fire_mask[..., None], fx, fy, n=24, step=0.02, decay=0.95)
        glow += rays * (1.2 * fire_k * (0.3 + 0.7 * night)) * np.array([1.0, 0.62, 0.3], np.float32)
    glow_disp = 1.0 - np.exp(-glow * 1.2)

    disp = to_srgb(aces(lin * 0.9))
    if paint:
        kw = kuwahara(disp, max(2, int(round(2 * s))))
        disp = disp * 0.45 + kw * 0.55
        disp = np.clip(unsharp(disp, 1.4 * s, 0.45), 0, 1)

    lum = disp @ LUMA
    sh = (1 - lum) ** 2
    hi = lum ** 2
    disp = disp + sh[..., None] * np.array([-0.006, 0.0, 0.016], np.float32) * (1 + night)
    disp = disp + hi[..., None] * np.array([0.03, 0.014, -0.018], np.float32)
    sat = 1.18 - 0.14 * night
    gray = (disp @ LUMA)[..., None]
    disp = np.clip(gray + (disp - gray) * sat, 0, 1)
    disp = disp * disp * (3 - 2 * disp) * 0.35 + disp * 0.65

    disp = 1.0 - (1.0 - disp) * (1.0 - np.clip(glow_disp, 0, 1))
    if stars is not None:
        disp = disp + stars[..., None] * np.array([0.9, 0.93, 1.0], np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / math.sqrt(2)
    disp = disp * (1.0 - 0.22 * rr ** 2.4)[..., None]
    rng = np.random.default_rng(frame * 7 + 1)
    g = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.6 * s)
    disp = disp + g[..., None] * 0.01
    return np.clip(disp, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inp', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--frames', default=None)
    ap.add_argument('--no-titles', action='store_true')
    ap.add_argument('--look', default='ink', choices=['ink', 'paint', 'clean'])
    ap.add_argument('--fade-in', type=float, default=0.0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    metas = sorted(glob.glob(os.path.join(args.inp, 'meta_*.json')))
    frames = [int(os.path.basename(m)[5:9]) for m in metas]
    # pass 1: exposure keys (cached)
    cache = os.path.join(args.inp, 'keys.json')
    keys = json.load(open(cache)) if os.path.exists(cache) else {}
    missing = [f for f in frames if str(f) not in keys]
    for f in missing:
        keys[str(f)] = frame_key(load(args.inp, f)[0])
    if missing:   # only write when something changed (parallel runs share the cache)
        tmp = cache + f'.{os.getpid()}'
        json.dump(keys, open(tmp, 'w'))
        os.replace(tmp, cache)
    metas_all = [json.load(open(os.path.join(args.inp, f'meta_{f:04d}.json'))) for f in frames]
    days = [m['day'] for m in metas_all]
    shots = [m.get('shot', '') for m in metas_all]
    if len(frames) > 30:
        expo = exposure_curve([keys[str(f)] for f in frames], days, look=args.look,
                              shots=[sorted(set(shots)).index(s) for s in shots])
    else:   # sparse previews: no temporal smoothing
        expo = [exposure_target(dd, args.look) / keys[str(f)] for f, dd in zip(frames, days)]
    todo = frames if args.frames is None else [f for f in frames if str(f) in args.frames.split(',')]
    for f in todo:
        rgb, Z, ID, L, meta = load(args.inp, f)
        if args.look in ('paint', 'clean'):
            img = stylize_paint(rgb, Z, ID, meta, expo[frames.index(f)], f, paint=args.look == 'paint')
        else:
            img = stylize(rgb, Z, ID, L, meta, expo[frames.index(f)], f)
        if args.fade_in > 0:
            img = img * min(1.0, meta['t'] / args.fade_in)
        if not args.no_titles:
            img = titles.apply(img, f / TL.FPS)
        cv2.imwrite(os.path.join(args.out, f'frame_{f:04d}.png'),
                    (img[..., ::-1] * 255 + 0.5).astype(np.uint8))
        print('styled', f, flush=True)


if __name__ == '__main__':
    main()
