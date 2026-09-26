"""Clothed figures for close shots, sculpted as signed-distance fields.

The lighthouse people are skinned stick figures: fine at a distance, too
crude in a room.  Here a figure is a handful of smooth-blended primitives in
the clothes of the 16th century, in a given pose, turned into a mesh by
marching cubes (sculpt.py) and cached:

  scholar(pose)    a canon of Frauenburg: a long robe falling in folds to the
                   floor, a fur collar, wide sleeves, hair cut to the jaw
  craftsman(pose)  a carpenter: shirt, leather apron, hose, a cap

Human scale (m), facing +y, feet at z = 0.  pose is a dict of a few joint
targets; figures are posed in a handful of phases and swapped per frame.
Regions (robe, fur, skin, hair, apron, shirt, hose, cap, wood) are written
per face so one material can colour them.
"""
import hashlib
import math
import os

import numpy as np

import sculpt as SD

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build', 'cache')
H = 0.012                              # voxel (m)
R_ROBE, R_FUR, R_SKIN, R_HAIR, R_APRON, R_SHIRT, R_HOSE, R_CAP, R_WOOD = range(9)


def _folds(cx, cy, n, amp, z_top):
    def disp(P, d):
        ang = np.arctan2(P[:, 1] - cy, P[:, 0] - cx)
        k = np.clip((z_top - P[:, 2]) / z_top, 0, 1)
        return d - amp * k * (0.6 + 0.4 * np.cos(n * ang + 2.0 * P[:, 2])) * np.cos(n * ang)
    return disp


def _limb(p, a, b, ra, rb, k=0.02, tag=0):
    p.append(SD.Prim('cone', k=k, a=a, b=b, ra=ra, rb=rb, tag=tag))


def _ell(p, c, r, k=0.02, R=None, tag=0, op='add', disp=None):
    g = dict(c=c, r=r)
    if R is not None:
        g['R'] = R
    p.append(SD.Prim('ell', op=op, k=k, disp=disp, tag=tag, **g))


def head_hair(p, neck_top, look=(0.0, 1.0, 0.0), cap=False, bob=True):
    hx, hy, hz = neck_top
    f = np.asarray(look, float)
    f /= np.linalg.norm(f)
    hc = np.array([hx, hy, hz + 0.1]) + f * 0.012
    _ell(p, hc, (0.075, 0.09, 0.105), k=0.02, R=SD.rot_from_axes(f), tag=R_SKIN)          # head
    _ell(p, hc + f * 0.085 + [0, 0, -0.02], (0.012, 0.02, 0.022), k=0.012, R=SD.rot_from_axes(f), tag=R_SKIN)   # nose
    if cap:
        _ell(p, hc + [0, 0, 0.06], (0.09, 0.1, 0.05), k=0.015, tag=R_CAP)
    if bob:                                                          # hair to the jaw, cut straight
        _ell(p, hc - f * 0.02 + [0, 0, 0.005], (0.09, 0.1, 0.1), k=0.01, R=SD.rot_from_axes(f), tag=R_HAIR)
        _ell(p, hc - f * 0.04 + [0, 0, -0.06], (0.085, 0.07, 0.07), k=0.02, R=SD.rot_from_axes(f), tag=R_HAIR)
    return hc


def scholar(pose):
    """A canon in a long robe.  pose: hand_r, hand_l (targets), look (head direction), stoop (m)."""
    p = []
    stoop = pose.get('stoop', 0.0)
    sh_z = 1.45
    chest = np.array([0.0, stoop * 0.6, 1.3])
    neck = np.array([0.0, stoop, 1.52])
    # the robe: a flared bell from the shoulders to the floor, folds deepening downwards
    _limb(p, (0.0, stoop * 0.4, 1.42), (0.0, -0.02, 0.02), 0.19, 0.36, k=0.05, tag=R_ROBE)
    p[-1].disp = _folds(0.0, 0.0, 9, 0.02, 1.4)
    _ell(p, chest, (0.19, 0.13, 0.2), k=0.06, tag=R_ROBE)
    _ell(p, neck + [0, 0, -0.08], (0.21, 0.15, 0.06), k=0.03, tag=R_FUR)                  # fur collar
    _limb(p, neck + [0, 0, -0.04], neck + [0, 0, 0.05], 0.05, 0.045, k=0.02, tag=R_SKIN)
    head_hair(p, neck + [0, 0, 0.04], look=pose.get('look', (0.0, 1.0, -0.2)))
    for s, key in ((1, 'hand_r'), (-1, 'hand_l')):
        sh = np.array([s * 0.2, stoop * 0.8, sh_z])
        hand = np.array(pose.get(key, (s * 0.22, 0.1, 0.95)), float)
        mid = sh + (hand - sh) * 0.5 + np.array([s * 0.08, -0.05, -0.06])
        _limb(p, sh, mid, 0.07, 0.075, k=0.03, tag=R_ROBE)                             # wide sleeve
        _limb(p, mid, hand - (hand - mid) * 0.12, 0.075, 0.085, k=0.02, tag=R_ROBE)
        _ell(p, hand, (0.035, 0.05, 0.022), k=0.012, tag=R_SKIN)
    return p


def craftsman(pose):
    """A carpenter at the bench.  pose: hand_r, hand_l, lean (m forward), step (m)."""
    p = []
    lean = pose.get('lean', 0.0)
    step = pose.get('step', 0.18)
    hip = np.array([0.0, lean * 0.3, 0.92])
    chest = np.array([0.0, lean, 1.3])
    neck = np.array([0.0, lean * 1.2, 1.5])
    _ell(p, hip, (0.16, 0.11, 0.1), k=0.04, tag=R_HOSE)
    _ell(p, chest, (0.18, 0.12, 0.2), k=0.06, tag=R_SHIRT)
    _limb(p, hip, chest, 0.14, 0.15, k=0.05, tag=R_SHIRT)
    for s, fy in ((1, step), (-1, -step * 0.4)):                        # legs in hose, shoes
        knee = np.array([s * 0.1, fy * 0.5 + 0.03, 0.5])
        ank = np.array([s * 0.11, fy, 0.08])
        _limb(p, hip + [s * 0.08, 0, -0.02], knee, 0.085, 0.055, k=0.03, tag=R_HOSE)
        _limb(p, knee, ank, 0.055, 0.04, k=0.02, tag=R_HOSE)
        _ell(p, ank + [0, 0.06, -0.04], (0.045, 0.12, 0.04), k=0.02, tag=R_APRON)
    _ell(p, chest + [0, 0.12, -0.25], (0.17, 0.03, 0.42), k=0.03, tag=R_APRON)           # the leather apron
    _limb(p, neck + [0, 0, -0.04], neck + [0, 0, 0.05], 0.05, 0.045, k=0.02, tag=R_SKIN)
    head_hair(p, neck + [0, 0, 0.04], look=pose.get('look', (0.0, 1.0, -0.4)), cap=True, bob=False)
    for s, key in ((1, 'hand_r'), (-1, 'hand_l')):
        sh = np.array([s * 0.2, lean * 1.1, 1.45])
        hand = np.array(pose.get(key, (s * 0.2, 0.3, 0.95)), float)
        el = sh + (hand - sh) * 0.5 + np.array([s * 0.12, -0.06, -0.12])
        _limb(p, sh, el, 0.055, 0.045, k=0.03, tag=R_SHIRT)
        _limb(p, el, hand, 0.045, 0.035, k=0.02, tag=R_SKIN)
        _ell(p, hand, (0.035, 0.05, 0.022), k=0.012, tag=R_SKIN)
    return p


def _key(kind, pose):
    src = open(os.path.abspath(__file__), 'rb').read() + open(SD.__file__, 'rb').read() + repr((kind, sorted(pose.items()))).encode()
    return hashlib.sha1(src).hexdigest()[:14]


def figure(kind, pose):
    """-> (V, F, region per face), cached."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'fig_{kind}_{_key(kind, pose)}.npz')
    if os.path.exists(path):
        d = np.load(path)
        return d['V'], d['F'], d['R']
    prims = scholar(pose) if kind == 'scholar' else craftsman(pose)
    lo = np.array([-0.55, -0.55, -0.03])
    hi = np.array([0.55, 0.65, 1.9])
    vol, org = SD.sample(prims, lo, hi, H)
    V, F = SD.surface(vol, org, H)
    V = SD.taubin(V, F, iters=3)
    # region per face: the primitive nearest to the face centre (by its own distance)
    C = V[F].mean(axis=1)
    best = np.full(len(C), 1e9)
    reg = np.zeros(len(C), np.int32)
    for pr in prims:
        if pr.op != 'add':
            continue
        d = pr.dist(C)
        m = d < best - 1e-4
        best[m] = d[m]
        reg[m] = pr.tag
    np.savez_compressed(path, V=V.astype(np.float32), F=F.astype(np.int32), R=reg)
    return V, F, reg


def mat_figure(name='Figure', robe=(0.10, 0.05, 0.04)):
    import scene as SC
    m, nb, out = SC.new_material(name)
    reg = nb.attr('region').outputs['Fac']
    oi = nb.new('ShaderNodeObjectInfo')
    cloth = oi.outputs['Color']
    cols = {R_ROBE: None, R_FUR: (0.16, 0.11, 0.07), R_SKIN: (0.50, 0.33, 0.24), R_HAIR: (0.06, 0.04, 0.03),
            R_APRON: (0.22, 0.14, 0.08), R_SHIRT: (0.70, 0.66, 0.58), R_HOSE: (0.18, 0.16, 0.14), R_CAP: (0.28, 0.20, 0.12),
            R_WOOD: (0.35, 0.24, 0.14)}
    col = cloth
    for k, c in cols.items():
        if c is None:
            continue
        f = nb.math('COMPARE', reg, float(k), 0.5)
        col = nb.mix(f, col, c + (1,))
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    n = nb.noise(pos, 30.0, 3.0, 0.6).outputs['Fac']
    b = SC.principled(nb, col, rough=nb.math('ADD', 0.75, nb.math('MULTIPLY', n, 0.2)), spec=0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def figure_mesh(name, kind, pose, mat):
    import scene as SC
    V, F, R = figure(kind, pose)
    F4 = np.concatenate([F, F[:, 2:3]], 1)
    return SC.mesh_from_arrays(name, V, F4, face_attrs={'region': ('FLOAT', R.astype(np.float32))}, mats=[mat], smooth=True)
