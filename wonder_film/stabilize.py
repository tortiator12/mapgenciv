"""Temporal stabilisation of the stylized frames, shot by shot.

A recursive filter: each output frame blends the current frame with the
previous *output*, warped onto it by optical flow (DIS), weighted by how well
the previous input matches the current one after warping.  Shimmer from render
noise, fine texture and the paint filter is averaged away over a few frames,
while real changes (walking figures, time-lapse jumps, the beacon catching)
mismatch strongly and pass through unblended, so nothing ghosts.

  python wonder_film/stabilize.py --inp build/l20/png --meta build/l20 --out build/l20/png_stab
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np


def luma(img):
    return img @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inp', required=True, help='stylized frames frame_NNNN.png')
    ap.add_argument('--meta', required=True, help='render dir with meta_NNNN.json (shot names)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--alpha', type=float, default=0.6, help='max weight of the history')
    ap.add_argument('--sigma', type=float, default=0.045, help='mismatch (0..1) at which blending stops')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(args.inp, 'frame_*.png')))
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    prev_in = prev_out = None
    prev_shot = None
    grid = None
    for path in files:
        f = int(os.path.basename(path)[6:10])
        with open(os.path.join(args.meta, f'meta_{f:04d}.json')) as fh:
            shot = json.load(fh).get('shot', '')
        cur = cv2.imread(path).astype(np.float32) / 255.0
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
            err = np.abs(warped_in - cur).mean(axis=2)
            err = cv2.GaussianBlur(err, (0, 0), 1.2)
            w = args.alpha * np.exp(-(err / args.sigma) ** 2)
            out = warped_out * w[..., None] + cur * (1.0 - w[..., None])
        cv2.imwrite(os.path.join(args.out, os.path.basename(path)), np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8))
        prev_in, prev_out, prev_shot = cur, out, shot
    print('stabilised', len(files), 'frames')


if __name__ == '__main__':
    main()
