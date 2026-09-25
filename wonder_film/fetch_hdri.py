"""Download the photographed sky (CC0, Poly Haven) for the bright look and take its sun out.

  python wonder_film/fetch_hdri.py        # -> wonder_film/assets/hdri/  (not in git: ~20 MB)

The sky only replaces the painted-by-numbers cloud deck: our own sun lamp
(placed by the film's clock) keeps lighting the scene and casting the
shadows, so the photographed sun is removed and the sky is clamped; the
world shader adds our sun disc and glow on top.  All Poly Haven assets are
CC0 (https://polyhaven.com/license).
"""
import json
import os
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'assets', 'hdri')
SKIES = {'day': 'kloofendal_48d_partly_cloudy_puresky'}
RES = '4k'
API = 'https://api.polyhaven.com'


def get(url, path=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'mapgenciv-wonder-film'})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    if path is None:
        return json.loads(data)
    with open(path, 'wb') as fh:
        fh.write(data)


def remove_sun(img, radius_deg=6.0, clamp=12.0):
    """Fill the photographed sun (and its bloom) with the sky around it."""
    import cv2
    H, W = img.shape[:2]
    lum = img @ np.array([0.0722, 0.7152, 0.2126], np.float32)          # BGR
    y, x = np.unravel_index(np.argmax(cv2.GaussianBlur(lum, (0, 0), 3)), lum.shape)
    lat = (0.5 - (y + 0.5) / H) * np.pi
    lon = ((x + 0.5) / W - 0.5) * 2 * np.pi
    sun = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    yy, xx = np.mgrid[0:H, 0:W]
    la = (0.5 - (yy + 0.5) / H) * np.pi
    lo = ((xx + 0.5) / W - 0.5) * 2 * np.pi
    d = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1) @ sun
    ang = np.degrees(np.arccos(np.clip(d, -1, 1)))
    # fill the disc around the sun by diffusion from its rim (smooth, no seam),
    # then ease back into the photograph over a wider ring
    mask = ang < radius_deg * 1.25
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = max(ys.min() - 20, 0), min(ys.max() + 21, H), max(xs.min() - 20, 0), min(xs.max() + 21, W)
    patch = img[y0:y1, x0:x1].copy()
    m = mask[y0:y1, x0:x1]
    patch[m] = np.median(img[(ang > radius_deg * 1.25) & (ang < radius_deg * 1.6)], axis=0)
    for _ in range(400):
        blur = cv2.GaussianBlur(patch, (0, 0), 4.0)
        patch[m] = blur[m]
    out = img.copy()
    out[y0:y1, x0:x1] = patch
    w = np.clip((radius_deg * 1.6 - ang) / (radius_deg * 0.35), 0, 1)[..., None]
    out = img * (1 - w) + out * w
    return np.minimum(out, clamp).astype(np.float32), (float(np.degrees(lat)), float(np.degrees(lon)))


def main():
    import cv2
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    for role, asset in SKIES.items():
        files = get(f'{API}/files/{asset}')
        info = get(f'{API}/info/{asset}')
        raw = os.path.join(OUT, f'{asset}_{RES}.hdr')
        if not os.path.exists(raw):
            get(files['hdri'][RES]['hdr']['url'], raw)
        img = cv2.imread(raw, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR).astype(np.float32)
        clean, sun = remove_sun(img)
        path = os.path.join(OUT, f'{asset}_{RES}_nosun.hdr')
        cv2.imwrite(path, clean)
        H = clean.shape[0]
        upper = clean[: H // 2] @ np.array([0.0722, 0.7152, 0.2126], np.float32)
        manifest[role] = dict(asset=asset, file=os.path.basename(path), sun_lat_lon=sun,
                              median_sky=float(np.median(upper)), authors=list(info.get('authors', {}).keys()),
                              license='CC0 1.0 (Poly Haven)', url=f'https://polyhaven.com/a/{asset}')
        print(role, asset, 'sun at', [round(v, 1) for v in sun], 'median sky', round(manifest[role]['median_sky'], 3))
    with open(os.path.join(OUT, 'manifest.json'), 'w') as fh:
        json.dump(manifest, fh, indent=1)


if __name__ == '__main__':
    sys.exit(main())
