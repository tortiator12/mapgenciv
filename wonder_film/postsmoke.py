"""Smoke and dust drawn after the render (no bpy).

At the films' six samples per pixel Cycles renders a semi-transparent,
self-lit billboard as a cloud of dark specks (sampling noise that only
converges at ~64 samples).  So a film may instead hand its puffs to the
stylizer through the frame's meta data: world position, size, density, age,
seed and kind, plus the light that falls on them.  draw() projects every puff
with the frame's camera, occludes it by the depth pass (smoke behind a mast
stays behind it) and blends soft, evolving sprites far to near into the
scene-linear image, before the aerial haze and the paint.

Puff record: [x, y, z, size, density, glow, seed, age_fraction, kind]
kind 0 = smoke (grey), 1 = dust (warm ochre).
"""
import math

import cv2
import numpy as np

COLORS = {0: ((0.62, 0.60, 0.57), (0.80, 0.78, 0.74)), 1: ((0.52, 0.42, 0.30), (0.70, 0.58, 0.42))}
_NOISE = {}


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def noise_field(n=256, seed=7):
    """Tileable smooth noise in [0, 1]: a few octaves of wrapped, blurred white noise."""
    if n not in _NOISE:
        rng = np.random.default_rng(seed)
        acc = np.zeros((n, n), np.float32)
        amp = 1.0
        for sig in (18.0, 9.0, 4.5):
            w = rng.normal(0, 1, (n, n)).astype(np.float32)
            big = np.tile(w, (3, 3))
            big = cv2.GaussianBlur(big, (0, 0), sig)
            acc += amp * big[n:2 * n, n:2 * n] / big.std()
            amp *= 0.45
        acc = (acc - acc.min()) / (acc.max() - acc.min())
        _NOISE[n] = acc
    return _NOISE[n]


def project(meta, P, W, H):
    M = np.array(meta['cam_matrix'], float)
    R, t = M[:3, :3], M[:3, 3]
    loc = R.T @ (np.asarray(P, float) - t)
    depth = -loc[2]
    f = meta['lens'] / meta['sensor'] * W
    if depth <= 0.05:
        return None
    return W / 2 + loc[0] / depth * f, H / 2 - loc[1] / depth * f, depth, f


def draw(rgb, Z, meta):
    """Composite meta['smoke'] into rgb (scene-linear, H x W x 3) in place; returns rgb."""
    puffs = meta.get('smoke') or []
    if not puffs:
        return rgb
    H, W = Z.shape
    light = np.array(meta.get('smoke_light', (1.0, 1.0, 1.0)), np.float32)
    N = noise_field()
    n = N.shape[0]
    items = []
    for p in puffs:
        pr = project(meta, p[:3], W, H)
        if pr is not None:
            items.append((pr, p))
    items.sort(key=lambda it: -it[0][2])                      # far to near
    Zs = np.where(np.isfinite(Z), Z, 1e9).astype(np.float32)
    for (sx, sy, depth, f), (x, y, z, size, dens, glow, seed, age, kind) in items:
        r = 0.5 * size / depth * f
        if r < 0.7 or dens < 0.01:
            continue
        x0, x1 = int(max(sx - r - 1, 0)), int(min(sx + r + 2, W))
        y0, y1 = int(max(sy - r - 1, 0)), int(min(sy + r + 2, H))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        du = (xx + 0.5 - sx) / (2 * r)                        # -0.5 .. 0.5 across the sprite
        dv = (sy - (yy + 0.5)) / (2 * r)
        rr = 2.0 * np.sqrt(du * du + dv * dv)
        fall = smoothstep(1.0, 0.05, rr)
        # noise coordinates: 1.3 cells across the puff, turned per puff, drifting with age
        spin = seed * 6.283
        cs, sn = math.cos(spin), math.sin(spin)
        u = (du * cs - dv * sn) * 1.3 * 64.0 + seed * 97.0 + age * 23.0
        v = (du * sn + dv * cs) * 1.3 * 64.0 + seed * 53.0 + age * 11.0
        nz = cv2.remap(N, np.mod(u, n).astype(np.float32), np.mod(v, n).astype(np.float32), cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_WRAP)
        body = smoothstep(0.18, 0.72, nz + 0.3 * fall)
        a = np.clip(np.power(fall, 0.7) * body * dens, 0.0, 1.0)
        vis = smoothstep(depth - 0.6, depth + 0.6, Zs[y0:y1, x0:x1])
        a = a * vis
        if a.max() < 1e-3:
            continue
        lo, hi = (np.array(c, np.float32) for c in COLORS.get(int(kind), COLORS[0]))
        col = lo[None, None, :] + (hi - lo)[None, None, :] * (nz * 0.6)[..., None]
        shade = (0.72 + 0.4 * (dv + 0.5))[..., None]
        col = col * light[None, None, :] * shade
        if glow > 0:
            col = col + glow * 6.0 * np.array([1.0, 0.45, 0.14], np.float32)[None, None, :] * (1.0 - (dv + 0.5))[..., None]
        sub = rgb[y0:y1, x0:x1]
        rgb[y0:y1, x0:x1] = sub * (1 - a[..., None]) + col * a[..., None]
    return rgb
