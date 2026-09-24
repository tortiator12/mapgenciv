"""Download the CC0 photo textures used by the bright look (Poly Haven).

  python wonder_film/fetch_textures.py            # 1k JPGs into wonder_film/assets/textures/

All assets are CC0 (public domain, https://polyhaven.com/license), so they may
ship with the game.  The manifest records each texture's real-world size, so
the materials map them at the correct scale, and the mean colour of the
diffuse map, so a texture only adds detail while the palette keeps the colour.
"""
import json
import os
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'assets', 'textures')
RES = '1k'
ROLES = {
    'hull': 'weathered_brown_planks',    # ship and lighter hulls
    'deck': 'old_planks_02',             # decks
    'stone': 'worn_rock_natural_01',     # dressed limestone faces
    'sand': 'sand_01',                   # the island's ground
    'linen': 'rough_linen',              # sail cloth
    'timber': 'rough_wood',              # scaffold poles, cranes, carts
}
MAPS = {'diff': 'Diffuse', 'nor_gl': 'nor_gl', 'rough': 'Rough', 'disp': 'Displacement'}
API = 'https://api.polyhaven.com'


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'mapgenciv-wonder-film'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url, path):
    req = urllib.request.Request(url, headers={'User-Agent': 'mapgenciv-wonder-film'})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as fh:
        fh.write(r.read())


def mean_rgb(path):
    import cv2
    im = cv2.imread(path)[..., ::-1].astype(np.float32) / 255.0
    lin = np.where(im <= 0.04045, im / 12.92, ((im + 0.055) / 1.055) ** 2.4)   # sRGB -> linear
    return [float(v) for v in lin.reshape(-1, 3).mean(axis=0)]


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    for role, asset in ROLES.items():
        info = get_json(f'{API}/info/{asset}')
        files = get_json(f'{API}/files/{asset}')
        d = os.path.join(OUT, asset)
        os.makedirs(d, exist_ok=True)
        entry = dict(asset=asset, name=info.get('name', asset), authors=list(info.get('authors', {}).keys()),
                     size_m=[v / 1000.0 for v in info.get('dimensions', [2000, 2000])],
                     license='CC0 1.0 (Poly Haven)', url=f'https://polyhaven.com/a/{asset}', maps={})
        for key, api_key in MAPS.items():
            url = files[api_key][RES]['jpg']['url']
            path = os.path.join(d, os.path.basename(url))
            if not os.path.exists(path):
                download(url, path)
            entry['maps'][key] = os.path.relpath(path, OUT)
        entry['mean_rgb'] = mean_rgb(os.path.join(OUT, entry['maps']['diff']))
        manifest[role] = entry
        print(role, asset, entry['size_m'], [round(v, 3) for v in entry['mean_rgb']], flush=True)
    with open(os.path.join(OUT, 'manifest.json'), 'w') as fh:
        json.dump(manifest, fh, indent=1)
    print('wrote', os.path.join(OUT, 'manifest.json'))


if __name__ == '__main__':
    sys.exit(main())
