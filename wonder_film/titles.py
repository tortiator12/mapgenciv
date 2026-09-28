"""Title overlays: opening caption and the 'wonder completed' card.

Rendered with PIL (Cinzel + Cormorant Garamond, SIL OFL) on top of the
stylized frames, plus the fade in / fade to black.
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as TL  # noqa: E402

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'fonts')
GOLD = (214, 178, 112)
IVORY = (242, 234, 216)

QUOTE = ['“Sostratus of Cnidus, son of Dexiphanes, to the Saviour Gods,',
         'on behalf of those who sail the seas.”']
ATTRIB = '—  DEDICATION OF THE PHAROS, AS TOLD BY LUCIAN'

_fonts = {}


def font(name, size):
    key = (name, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    return _fonts[key]


def spaced_width(text, fnt, spacing):
    return sum(fnt.getlength(c) for c in text) + spacing * (len(text) - 1)


def draw_spaced(draw, xy, text, fnt, fill, spacing, anchor_center=True):
    w = spaced_width(text, fnt, spacing)
    x, y = xy
    if anchor_center:
        x -= w / 2
    for c in text:
        draw.text((x, y), c, font=fnt, fill=fill, anchor='ls')
        x += fnt.getlength(c) + spacing


def ramp(t, t0, t1):
    return TL.ease((t - t0) / (t1 - t0))


def _layer(W, H):
    return Image.new('RGBA', (W, H), (0, 0, 0, 0))


def _composite(img, layer, shadow=True, s=1.0):
    """img float RGB [0,1] (H,W,3); layer RGBA PIL."""
    arr = np.asarray(layer).astype(np.float32) / 255.0
    if shadow:
        a = arr[..., 3]
        sh = cv2.GaussianBlur(a, (0, 0), 3.0 * s) * 0.75
        img = img * (1 - sh[..., None])
    a = arr[..., 3:4]
    return img * (1 - a) + arr[..., :3] * a


def opening_caption(img, t):
    H, W = img.shape[:2]
    s = H / 720.0
    k = ramp(t, 1.0, 1.7) * (1 - ramp(t, 4.1, 4.8))
    if k <= 0.001:
        return img
    L = _layer(W, H)
    d = ImageDraw.Draw(L)
    x0, y0 = 64 * s, 612 * s
    rise = (1 - ramp(t, 1.0, 1.9)) * 6 * s
    a = int(255 * k)
    d.line([(x0, y0 - 34 * s + rise), (x0 + 56 * s, y0 - 34 * s + rise)], fill=GOLD + (a,), width=max(1, int(2 * s)))
    f1 = font('Cinzel-SemiBold.ttf', int(24 * s))
    x = x0
    for c in 'PHAROS  ·  ALEXANDRIA':
        d.text((x, y0 + rise), c, font=f1, fill=IVORY + (a,), anchor='ls')
        x += f1.getlength(c) + 4 * s
    f2 = font('CormorantGaramond-MediumItalic.ttf', int(25 * s))
    d.text((x0, y0 + 32 * s + rise), 'Ptolemaic Egypt, c. 280 BC', font=f2, fill=IVORY + (int(a * 0.8),), anchor='ls')
    return _composite(img, L, s=s)


def end_card(img, t):
    H, W = img.shape[:2]
    s = H / 720.0
    t0 = TL.T_TITLE
    if t < t0:
        return img
    # darkening band under the text
    band = ramp(t, t0, t0 + 0.9)
    yy = np.arange(H, dtype=np.float32)[:, None] / H
    shade = np.clip((yy - 0.56) / 0.3, 0, 1) ** 1.3 * 0.78 * band
    img = img * (1 - shade[..., None]) + np.array([0.02, 0.018, 0.03], np.float32) * shade[..., None]

    L = _layer(W, H)
    d = ImageDraw.Draw(L)
    cx = W / 2
    # "WONDER COMPLETED"
    k1 = ramp(t, t0 + 0.1, t0 + 0.8)
    draw_spaced(d, (cx, 492 * s), 'WONDER  COMPLETED', font('Cinzel-SemiBold.ttf', int(17 * s)),
                GOLD + (int(255 * k1),), 7 * s)
    # ornament rules + lozenge
    k2 = ramp(t, t0 + 0.3, t0 + 1.2)
    half = 300 * s * k2
    yo = 512 * s
    if k2 > 0:
        for sgn in (-1, 1):
            d.line([(cx + sgn * 14 * s, yo), (cx + sgn * (14 * s + half), yo)], fill=GOLD + (int(220 * k2),),
                   width=max(1, int(1.5 * s)))
        r = 5 * s
        d.polygon([(cx, yo - r), (cx + r, yo), (cx, yo + r), (cx - r, yo)], fill=GOLD + (int(255 * k2),))
    # name of the wonder
    k3 = ramp(t, t0 + 0.35, t0 + 1.15)
    rise = (1 - k3) * 10 * s
    draw_spaced(d, (cx, 566 * s + rise), 'THE GREAT LIGHTHOUSE', font('Cinzel-SemiBold.ttf', int(48 * s)),
                IVORY + (int(255 * k3),), 3 * s)
    # the inscription
    k4 = ramp(t, t0 + 1.2, t0 + 2.1)
    fq = font('CormorantGaramond-MediumItalic.ttf', int(25 * s))
    for i, line in enumerate(QUOTE):
        d.text((cx, 612 * s + i * 29 * s), line, font=fq, fill=IVORY + (int(235 * k4),), anchor='ms')
    k5 = ramp(t, t0 + 1.9, t0 + 2.6)
    draw_spaced(d, (cx, 690 * s), ATTRIB, font('Cinzel-Regular.ttf', int(12 * s)), GOLD + (int(200 * k5),), 3 * s)
    return _composite(img, L, s=s)


def apply(img, t):
    img = opening_caption(img, t)
    img = end_card(img, t)
    k = ramp(t, *TL.T_FADE_IN) * (1 - ramp(t, *TL.T_FADE))
    return img * k
