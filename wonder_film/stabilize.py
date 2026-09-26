"""Temporal stabilisation of the stylized frames, shot by shot.

A recursive filter: each output frame blends the current frame with the
previous *output*, warped onto it by optical flow (DIS), weighted by how well
the previous input matches the current one after warping.  Shimmer from render
noise, fine texture and the paint filter is averaged away over a few frames,
while real changes (walking figures, time-lapse jumps, the beacon catching)
mismatch strongly and pass through unblended, so nothing ghosts.

Before that, --deflicker shots (the time-lapse) get their overall brightness
smoothed over a few frames: the compressed dusk and dawn change the sky by a
third from one frame to the next, which reads as flashing; a real time-lapse
camera ramps its exposure instead.

  python wonder_film/stabilize.py --inp build/l20/png --meta build/l20 --out build/l20/png_stab --deflicker S2
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np


def luma(img):
    return img @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def brightness_gains(files, shots, deflicker, sigma):
    """Per-frame gain that turns abrupt steps of the log-average luminance into
    ramps (Gaussian in time, within each listed shot)."""
    gains = np.ones(len(files))
    logy = np.zeros(len(files))
    for i, path in enumerate(files):
        if shots[i] in deflicker:
            im = cv2.imread(path)[::4, ::4].astype(np.float32) / 255.0
            logy[i] = float(np.log(luma(to_linear(im)) + 1e-3).mean())     # log-average: as the eye sees it
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    for shot in deflicker:
        idx = np.array([i for i, s in enumerate(shots) if s == shot])
        if len(idx) < 3:
            continue
        sm = np.convolve(np.pad(logy[idx], r, mode='reflect'), k, mode='valid')
        gains[idx] = np.clip(np.exp(sm - logy[idx]), 0.4, 2.5)
    return gains


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inp', required=True, help='stylized frames frame_NNNN.png')
    ap.add_argument('--meta', required=True, help='render dir with meta_NNNN.json (shot names)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--alpha', type=float, default=0.6, help='max weight of the history')
    ap.add_argument('--sigma', type=float, default=0.045, help='mismatch (0..1) at which blending stops')
    ap.add_argument('--deflicker', default='', help='comma-separated shots whose brightness is smoothed (e.g. S2)')
    ap.add_argument('--deflicker-frames', type=float, default=3.5, help='Gaussian width in frames')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(args.inp, 'frame_*.png')))
    shots = []
    for path in files:
        f = int(os.path.basename(path)[6:10])
        with open(os.path.join(args.meta, f'meta_{f:04d}.json')) as fh:
            shots.append(json.load(fh).get('shot', ''))
    deflicker = [s for s in args.deflicker.split(',') if s]
    gains = brightness_gains(files, shots, deflicker, args.deflicker_frames)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    prev_in = prev_out = None
    prev_shot = None
    grid = None
    for i, path in enumerate(files):
        shot = shots[i]
        cur = cv2.imread(path).astype(np.float32) / 255.0
        if gains[i] != 1.0:
            cur = to_srgb(to_linear(cur) * gains[i]).astype(np.float32)
        H, W = cur.shape[:2]
        if grid is None:
            gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
            grid = (gx, gy)
        if prev_in is None or shot != prev_shot:
            out = cur
        else:
            g1 = cv2.resize((luma(cur) * 255).astype(np.uint8), (W // 2, H // 2), interpolation=cv2.INTER_AREA)
            g0 = cv2.resize((luma(prev_in) * 255).astype(np.uint8), (W // 2, H // 2), interpolation=cv2.INTER_AREA)
            flow = dis.calc(g1, g0, None)                       # where each current pixel was a frame ago
            flow = cv2.resize(flow, (W, H), interpolation=cv2.INTER_LINEAR) * 2.0
            mx, my = grid[0] + flow[..., 0], grid[1] + flow[..., 1]
            warped_out = cv2.remap(prev_out, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            warped_in = cv2.remap(prev_in, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            # follow overall brightness changes (dusk, dawn), so the history neither lags nor jumps
            ratio = float(np.clip((luma(cur).mean() + 1e-3) / (luma(warped_in).mean() + 1e-3), 0.5, 2.0))
            warped_out = warped_out * ratio
            warped_in = warped_in * ratio
            err = np.abs(warped_in - cur).mean(axis=2)
            err = cv2.GaussianBlur(err, (0, 0), 1.2)
            w = args.alpha * np.exp(-(err / args.sigma) ** 2)
            out = warped_out * w[..., None] + cur * (1.0 - w[..., None])
        cv2.imwrite(os.path.join(args.out, os.path.basename(path)), np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8))
        prev_in, prev_out, prev_shot = cur, out, shot
    print('stabilised', len(files), 'frames')


if __name__ == '__main__':
    main()
