"""Sailing ships for the voyage films, from one parametric model.

  NAO     Magellan's Victoria (1519): 26 m on deck, 7.2 m in the beam; a carvel
          hull with tumblehome, a high castle aft (quarterdeck and poop) and a
          forecastle, a flat transom with the stern rudder; foremast and mainmast
          with course and topsail, round tops, a lateen mizzen, the spritsail
          under the bowsprit; the red cross of Santiago on the courses
  BARQUE  Darwin's Beagle after her 1831 refit: 27.5 m, flush deck with a raised
          poop, black sides with a yellow band and gunports, copper below the
          waterline; fore and main square-rigged (course, topsail, topgallant),
          a gaff spanker on the mizzen, jib and staysails

Local frame: bow +x, port +y, the waterline at z = 0.  build(S, spec, name)
returns a Ship whose parts hang on one root empty; pose() places it (heading,
heel, pitch) and sets every sail: 0 furled on its yard, 1 set (bellied by the
wind from astern), with a tattered-and-patched look for the voyage's end.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import geometry as G
import scene as SC

NAO = dict(
    L=26.0, B=7.2, draft=2.5, deck=2.2, rail=1.05, tumble=0.2, transom=0.62, rake=2.6,
    castles=[(0.0, 0.13, 4.3), (0.13, 0.34, 2.2), (0.8, 1.01, 2.3)],        # (s0, s1, height above the main deck)
    masts=[dict(s=0.53, h=22.0, top=15.2, topmast=8.0, yards=[(12.8, 8.0, 'course'), (21.0, 4.6, 'topsail')]),
           dict(s=0.79, h=17.5, top=13.2, topmast=5.5, yards=[(10.8, 6.4, 'course'), (17.0, 3.7, 'topsail')]),
           dict(s=0.2, h=12.5, lateen=True)],
    bowsprit=dict(angle=30.0, length=11.0),
    hull=(0.24, 0.15, 0.085), band=(0.50, 0.13, 0.07), below=(0.05, 0.04, 0.035), sail=(0.86, 0.80, 0.66),
    cross=True, gunports=False, style='nao')

BARQUE = dict(
    L=27.5, B=7.5, draft=3.4, deck=2.4, rail=1.2, tumble=0.1, transom=0.55, rake=1.6,
    castles=[(0.0, 0.2, 1.6)],
    masts=[dict(s=0.52, h=27.0, top=17.5, topmast=10.0, yards=[(15.5, 8.2, 'course'), (22.5, 6.2, 'topsail'), (28.0, 4.2, 'topgallant')]),
           dict(s=0.76, h=24.0, top=15.8, topmast=9.0, yards=[(14.0, 7.4, 'course'), (20.5, 5.6, 'topsail'), (25.5, 3.8, 'topgallant')]),
           dict(s=0.27, h=18.0, gaff=True)],
    bowsprit=dict(angle=16.0, length=13.0, jib=True),
    hull=(0.07, 0.06, 0.055), band=(0.80, 0.62, 0.22), below=(0.62, 0.36, 0.20), sail=(0.90, 0.87, 0.78),
    cross=False, gunports=True, style='barque')


class Ship:
    pass


def smooth(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ================================================================== hull
def stations(spec, ns=56):
    L, B = spec['L'], spec['B']
    s = np.linspace(0.0, 1.0, ns)
    tw = spec['transom']
    fore = np.cos(0.5 * np.pi * np.clip((s - 0.58) / 0.42, 0, 1) ** 1.25) ** 0.62
    aft = tw + (1 - tw) * np.sin(0.5 * np.pi * np.clip(s / 0.3, 0, 1)) ** 0.8
    bmax = 0.5 * B * np.minimum(fore, aft)
    bmax = np.maximum(bmax, 0.04)
    d = spec['draft']
    zk = -d * (1 - 0.75 * smooth(0.86, 1.0, s) ** 1.6 - 0.12 * smooth(0.12, 0.0, s))
    deck = spec['deck'] + 0.35 * smooth(0.5, 0.0, s) + 0.45 * smooth(0.6, 1.0, s)        # the sheer of the main deck
    top = deck + spec['rail']
    for (s0, s1, h) in spec['castles']:
        top = top + h * smooth(s0 - 0.015, s0 + 0.01, s) * smooth(s1 + 0.01, s1 - 0.015, s) if s0 > 0.0 else \
            top + h * smooth(s1 + 0.01, s1 - 0.015, s)
    x = (s - 0.5) * L
    return s, x, bmax, zk, deck, top


def section(bm, zk, zt, k, tumble, zb=0.4):
    """(y, z) on a frame at girth fraction k (0 keel .. 1 rail)."""
    z = zk + (zt - zk) * k ** 1.25
    if z <= zb:
        y = bm * max(1 - ((zb - z) / max(zb - zk, 1e-3)) ** 2.4, 0.0) ** 0.55
    else:
        y = bm * (1 - tumble * ((z - zb) / max(zt - zb, 1e-3)) ** 1.5)
    return y, z


def mat_hull(name, spec):
    """Planking with strakes and butts; the painted band under the rail, and pitch
    (or copper sheathing) below the waterline."""
    m, nb, out = SC.new_material(name)
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    u, v, _ = nb.sep(uv)
    strake, butt = 0.3, 5.1
    k = nb.math('FLOOR', nb.math('DIVIDE', v, strake))
    fv = nb.math('FRACT', nb.math('DIVIDE', v, strake))
    fu = nb.math('FRACT', nb.math('DIVIDE', nb.math('ADD', u, nb.math('MULTIPLY', k, 1.7)), butt))
    seam = nb.math('MAXIMUM', nb.smooth(0.07, 0.0, fv), nb.math('MULTIPLY', nb.smooth(0.012, 0.0, fu), 0.8))
    wn = nb.new('ShaderNodeTexWhiteNoise', noise_dimensions='2D')
    nb.feed(wn.inputs['Vector'], nb.comb(k, nb.math('FLOOR', nb.math('DIVIDE', nb.math('ADD', u, nb.math('MULTIPLY', k, 1.7)), butt)), 0.0))
    tone = nb.math('ADD', 0.85, nb.math('MULTIPLY', wn.outputs['Value'], 0.3))
    col = nb.mix(1.0, spec['hull'] + (1,), nb.comb(tone, tone, tone), blend='MULTIPLY')
    top = nb.attr('sheer_d').outputs['Fac']
    oz = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[2]
    if spec['style'] == 'barque':                      # a yellow band along the gun deck, black above and below
        band = nb.math('MULTIPLY', nb.smooth(0.55, 0.6, top), nb.smooth(1.25, 1.2, top))
    else:
        band = nb.math('MULTIPLY', nb.smooth(0.2, 0.25, top), nb.smooth(0.55, 0.5, top))
    col = nb.mix(band, col, spec['band'] + (1,))
    below = nb.smooth(0.12, -0.02, oz)
    ox_ = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[0]
    if spec['style'] == 'barque':                      # copper sheathing: plates in rows, a little tarnish
        cu_k = nb.math('FLOOR', nb.math('DIVIDE', v, 0.36))
        cu_f = nb.math('FRACT', nb.math('DIVIDE', nb.math('ADD', u, nb.math('MULTIPLY', cu_k, 0.6)), 1.2))
        plate = nb.smooth(0.02, 0.0, nb.math('MINIMUM', cu_f, nb.math('FRACT', nb.math('DIVIDE', v, 0.36))))
        cu = nb.mix(nb.math('MULTIPLY', plate, 0.6), spec['below'] + (1,), (0.28, 0.16, 0.09, 1))
        col = nb.mix(below, col, cu)
    else:
        col = nb.mix(below, col, spec['below'] + (1,))
    foul = nb.value(0.0, 'foul')
    clean_x = nb.value(-1e3, 'clean_x')
    weed = nb.mix(nb.noise(nb.new('ShaderNodeTexCoord').outputs['Object'], 1.2, 3.0, 0.6).outputs['Fac'],
                  (0.16, 0.20, 0.08, 1), (0.30, 0.28, 0.14, 1))
    fouled = nb.math('MULTIPLY', nb.math('MULTIPLY', below, foul), nb.math('GREATER_THAN', ox_, clean_x))
    col = nb.mix(fouled, col, weed)
    col = nb.mix(nb.math('MULTIPLY', seam, 0.7), col, (0.02, 0.015, 0.01, 1))
    metal = nb.math('MULTIPLY', below, 0.7 if spec['style'] == 'barque' else 0.0)
    b = SC.principled(nb, col, rough=nb.math('SUBTRACT', 0.75, nb.math('MULTIPLY', metal, 0.35)), spec=0.35)
    nb.feed(b.inputs['Metallic'], metal)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_sail(name, base, cross=False, patched=False):
    """Sailcloth in panels (bolts sewn together); a red cross of Santiago on the
    courses; patched: patches of other cloth and a stained, weathered tone."""
    m, nb, out = SC.new_material(name)
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    u, v, _ = nb.sep(uv)                                  # u across (0..1), v down (0..1)
    fu = nb.math('FRACT', nb.math('MULTIPLY', u, 14.0))
    seam = nb.smooth(0.06, 0.0, nb.math('MINIMUM', fu, nb.math('SUBTRACT', 1.0, fu)))
    n = nb.noise(nb.comb(u, v, 0.0), 3.0, 3.0, 0.6).outputs['Fac']
    k = nb.math('ADD', 0.88, nb.math('MULTIPLY', n, 0.2))
    col = nb.mix(1.0, base + (1,), nb.comb(k, k, k), blend='MULTIPLY')
    col = nb.mix(nb.math('MULTIPLY', seam, 0.35), col, (0.42, 0.34, 0.24, 1))
    if cross:                                             # a red cross (the cross of Santiago, simplified)
        cu = nb.math('ABSOLUTE', nb.math('SUBTRACT', u, 0.5))
        cv = nb.math('ABSOLUTE', nb.math('SUBTRACT', v, 0.45))
        arm = nb.math('MAXIMUM', nb.math('MULTIPLY', nb.smooth(0.07, 0.06, cu), nb.smooth(0.32, 0.31, cv)),
                      nb.math('MULTIPLY', nb.smooth(0.07, 0.06, cv), nb.smooth(0.3, 0.29, cu)))
        col = nb.mix(arm, col, (0.55, 0.06, 0.04, 1))
    if patched:
        cell = nb.new('ShaderNodeTexWhiteNoise', noise_dimensions='2D')
        nb.feed(cell.inputs['Vector'], nb.comb(nb.math('FLOOR', nb.math('MULTIPLY', u, 7.0)), nb.math('FLOOR', nb.math('MULTIPLY', v, 6.0)), 0.0))
        patch = nb.math('GREATER_THAN', cell.outputs['Value'], 0.72)
        col = nb.mix(nb.math('MULTIPLY', patch, 0.75), col, (0.62, 0.52, 0.38, 1))
        stain = nb.noise(nb.comb(u, v, 0.0), 1.5, 4.0, 0.7).outputs['Fac']
        col = nb.mix(nb.math('MULTIPLY', nb.smooth(0.45, 0.75, stain), 0.45), col, (0.38, 0.32, 0.24, 1))
    b = SC.principled(nb, col, rough=0.9, spec=0.2)
    tr = nb.new('ShaderNodeBsdfTranslucent')
    nb.feed(tr.inputs['Color'], col)
    mix = nb.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = 0.25
    nb.feed(mix.inputs[1], b.outputs[0])
    nb.feed(mix.inputs[2], tr.outputs[0])
    nb.feed(out.inputs['Surface'], mix.outputs[0])
    return m


def build_hull(spec, name, m_hull):
    ns, nk = 56, 12
    s, x, bmax, zk, deck, top = stations(spec, ns)
    L = spec['L']
    V, SD = [], []
    for i in range(ns):
        for j in range(-nk + 1, nk):
            k = abs(j) / (nk - 1)
            y, z = section(bmax[i], zk[i], top[i], k, spec['tumble'])
            xx = x[i]
            if s[i] > 0.92:                                   # the raked stem
                xx += spec['rake'] * smooth(0.92, 1.0, s[i]) * (z - zk[i]) / max(top[i] - zk[i], 1e-3)
            if s[i] < 0.02:                                   # the transom leans aft
                xx -= 0.6 * max(z, 0.0) / max(top[i], 1e-3)
            V.append([xx, math.copysign(y, j) if j else 0.0, z])
            SD.append(top[i] - z)
    V = np.array(V)
    nj = 2 * nk - 1
    Q = [[i * nj + j, i * nj + j + 1, (i + 1) * nj + j + 1, (i + 1) * nj + j] for i in range(ns - 1) for j in range(nj - 1)]
    # the transom: a fan closing the stern
    c = len(V)
    V = np.vstack([V, [[V[:nj, 0].mean(), 0.0, 0.5 * (zk[0] + top[0])]]])
    SD.append(1.0)
    for j in range(nj - 1):
        Q.append([j + 1, j, c, c])
    Q = np.array(Q)
    girth = np.zeros(len(V))
    for i in range(ns):
        row = V[i * nj:(i + 1) * nj]
        g = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(row, axis=0), axis=1))])
        girth[i * nj:(i + 1) * nj] = np.abs(g - g[nk - 1])
    uv = np.stack([V[Q.ravel(), 0], girth[Q.ravel()]], 1)
    sd = np.array(SD)[Q].mean(axis=1)
    me = SC.mesh_from_arrays(name + 'Hull', V, Q, uv=uv, face_attrs={'sheer_d': ('FLOAT', sd)}, mats=[m_hull], smooth=True)
    return me, (s, x, bmax, zk, deck, top)


def half_breadth(st, spec, sx, z):
    s, x, bmax, zk, deck, top = st
    i = int(np.clip(np.searchsorted(x, sx), 1, len(x) - 1))
    bm = float(np.interp(sx, x, bmax))
    zk_ = float(np.interp(sx, x, zk))
    zt = float(np.interp(sx, x, top))
    zb = 0.4
    if z <= zb:
        return bm * max(1 - ((zb - z) / max(zb - zk_, 1e-3)) ** 2.4, 0.0) ** 0.55
    return bm * (1 - spec['tumble'] * ((z - zb) / max(zt - zb, 1e-3)) ** 1.5)


def build_timbers(spec, st, name, mats):
    """Decks, castle bulkheads, wales, channels, rudder, gunports, hatches, capstan."""
    s, x, bmax, zk, deck, top = st
    L = spec['L']
    tb = G.HexBatch(name + 'timber')
    ns = len(s)
    dz = lambda si: float(np.interp(si, s, deck))                           # noqa: E731

    def deck_strip(s0, s1, z_of, mat=1, inset=0.25):
        n = max(2, int((s1 - s0) * 30))
        for q in range(n):
            a, b = s0 + (s1 - s0) * q / n, s0 + (s1 - s0) * (q + 1) / n
            xa, xb = (a - 0.5) * L, (b - 0.5) * L
            za, zb_ = z_of(a), z_of(b)
            ya = max(half_breadth(st, spec, xa, za) - inset, 0.1)
            yb = max(half_breadth(st, spec, xb, zb_) - inset, 0.1)
            bq = np.array([[xa, -ya], [xb, -yb], [xb, yb], [xa, ya]])
            corners = G._hexa(bq, bq, 0.0, 0.0)
            corners[:4, 2] = [za - 0.12, zb_ - 0.12, zb_ - 0.12, za - 0.12]
            corners[4:, 2] = [za, zb_, zb_, za]
            tb.add(corners, mat=mat)
    deck_strip(0.02, 0.985, dz)                                             # the main (weather) deck
    for (s0, s1, h) in spec['castles']:
        s0c, s1c = max(s0, 0.015), min(s1, 0.975)
        deck_strip(s0c, s1c, lambda si, h=h: dz(si) + h)
        for sb in (s0, s1):                                                  # bulkheads at the breaks
            if 0.02 < sb < 0.98:
                xb = (sb - 0.5) * L
                zb_ = dz(sb)
                yy = half_breadth(st, spec, xb, zb_ + h * 0.5) - 0.2
                tb.add(G.box(xb, 0, zb_, 0.15, 2 * yy, h), mat=0)
                tb.add(G.box(xb + (0.1 if sb == s0 else -0.1), 0, zb_, 0.12, 1.0, 1.8), mat=2)   # a door
    for zw in ((0.9, 1.7) if spec['style'] == 'nao' else (1.1,)):           # wales along the sides
        for i in range(2, ns - 3):
            for sg in (-1, 1):
                p0 = [x[i], sg * (half_breadth(st, spec, x[i], zw) + 0.06), zw]
                p1 = [x[i + 1], sg * (half_breadth(st, spec, x[i + 1], zw) + 0.06), zw]
                tb.add(G.beam(p0, p1, 0.22, 0.16), mat=0)
    xr = x[0] - 0.35                                                         # the stern rudder on the sternpost
    tb.add(G.beam([xr - 0.25, 0, zk[0] + 0.2], [xr - 0.45, 0, top[0] - 0.4], 0.28, 1.2, up=(1, 0, 0)), mat=0)
    for i in range(0, ns - 1):                                               # the sheer rail along the top edge
        for sg in (-1, 1):
            p0 = [x[i], sg * (half_breadth(st, spec, x[i], top[i]) + 0.02), top[i] + 0.05]
            p1 = [x[i + 1], sg * (half_breadth(st, spec, x[i + 1], top[i + 1]) + 0.02), top[i + 1] + 0.05]
            tb.add(G.beam(p0, p1, 0.18, 0.2), mat=2)
    if spec['gunports']:
        for i in range(10, ns - 10, 5):
            for sg in (-1, 1):
                zg = dz(s[i]) + 0.45
                yy = half_breadth(st, spec, x[i], zg) + 0.03
                tb.add(G.box(x[i], sg * yy, zg, 0.7, 0.06, 0.55), mat=2)
    for k in range(3):                                                       # hatches, capstan
        xh = (0.38 + 0.08 * k - 0.5) * L
        tb.add(G.box(xh, 0, dz(0.38 + 0.08 * k), 1.6, 1.8, 0.35), mat=0)
    xc = (0.46 - 0.5) * L
    tb.add(G.box(xc, 0, dz(0.46), 0.6, 0.6, 1.0), mat=0)                    # the capstan
    tb.finalize()
    return SC.hex_mesh(name + 'Timber', tb, np.ones(len(tb.t_on), bool), mats)


# ================================================================== rig
def mast_foot(spec, st, m):
    s, x, bmax, zk, deck, top = st
    xm = (m['s'] - 0.5) * spec['L']
    zd = float(np.interp(m['s'], s, deck))
    for (s0, s1, h) in spec['castles']:
        if s0 <= m['s'] <= s1:
            zd += h
    return xm, zd


def build_rig(spec, st, name, mats):
    """Masts, tops, topmasts, yards (square to the ship), bowsprit, shrouds with
    ratlines, stays; returns the mesh and the sail frames (yard centre, half-length,
    height to the foot) for pose()."""
    s, x, bmax, zk, deck, top = st
    L = spec['L']
    rb = G.HexBatch(name + 'rig')
    sails = []
    stem_x, stem_z = x[-1] + spec['rake'], top[-1]
    for mi, m in enumerate(spec['masts']):
        xm, zd = mast_foot(spec, st, m)
        h = m['h']
        r0 = 0.26 if mi == 0 else 0.2
        rb.add(G.beam([xm, 0, zd - 1.5], [xm, 0, zd + (m['top'] + 0.6 if m.get('top') else h)], r0 * 2, r0 * 2), t_on=0.0, mat=0)
        if m.get('top'):
            zt = zd + m['top']
            rb.add(G.box(xm, 0, zt, 2.2 if mi == 0 else 1.8, 2.2 if mi == 0 else 1.8, 0.35), t_on=0.0, mat=0)       # the top
            rb.add(G.beam([xm, 0, zt], [xm, 0, zt + m['topmast'] + 1.0], 0.22, 0.22), t_on=1.0, mat=0)
            for sg in (-1, 1):                                               # shrouds with ratlines
                feet = []
                for dx in (-1.2, -0.6, 0.0, 0.6):
                    xs = xm + dx
                    zr = float(np.interp(xs, x, top)) - 0.2
                    ys = sg * (half_breadth(st, spec, xs, zr) + 0.35)
                    rb.add(G.beam([xm + dx * 0.15, sg * 0.3, zt - 0.2], [xs, ys, zr], 0.045), t_on=0.0, mat=1)
                    feet.append(np.array([xs, ys, zr]))
                head = np.array([xm, sg * 0.3, zt - 0.2])
                for q in np.arange(0.12, 0.92, 0.09):
                    a = feet[0] + (head - feet[0]) * q
                    b = feet[-1] + (head - feet[-1]) * q
                    rb.add(G.beam(a, b, 0.025), t_on=0.0, mat=1)
            # stays: forward to the next mast's top / the bowsprit, back to the deck
            if mi == 0:
                fwd = mast_foot(spec, st, spec['masts'][1])
                rb.add(G.beam([xm, 0, zt], [fwd[0], 0, fwd[1] + 1.0], 0.07), t_on=2.0, mat=1)
                rb.add(G.beam([xm, 0, zt + m['topmast']], [fwd[0], 0, fwd[1] + spec['masts'][1]['top']], 0.04), t_on=2.0, mat=1)
            else:
                rb.add(G.beam([xm, 0, zt], [stem_x + 1.0, 0, stem_z + 0.4], 0.07), t_on=2.0, mat=1)
                rb.add(G.beam([xm, 0, zt + m['topmast']], [stem_x + spec['bowsprit']['length'] * 0.8, 0,
                                                            stem_z + spec['bowsprit']['length'] * 0.4], 0.04), t_on=2.0, mat=1)
        for (hy, a, kind) in m.get('yards', []):
            zy = zd + hy
            rb.add(G.beam([xm + 0.35, -a, zy], [xm + 0.35, a, zy], 0.24, 0.24), t_on=2.0, mat=0)
            rb.add(G.beam([xm, 0, zy + 2.4], [xm + 0.35, -a, zy], 0.03), t_on=2.0, mat=1)     # lifts
            rb.add(G.beam([xm, 0, zy + 2.4], [xm + 0.35, a, zy], 0.03), t_on=2.0, mat=1)
            if kind == 'course':
                h_s = zy - (zd + 1.6)
            else:
                below = [yy for (yy, aa, kk) in m['yards'] if yy < hy]
                h_s = hy - (max(below) if below else 0.0) - 0.5
            sails.append(dict(kind=kind, mast=mi, x=xm + 0.45, z=zy, a=a, h=h_s, foot_a=a * (1.08 if kind == 'course' else 1.35)))
        if m.get('lateen'):
            zb_ = zd + 1.4
            p0 = np.array([xm + 5.0, 0.0, zb_ + 0.6])
            p1 = np.array([xm - 8.5, 0.0, zd + m['h'] + 1.5])
            rb.add(G.beam(p0, p1, 0.2, 0.2), t_on=2.0, mat=0)
            sails.append(dict(kind='lateen', mast=mi, p0=p0, p1=p1, clew=np.array([xm - 7.5, 0.0, zd + 1.3])))
            for sg in (-1, 1):
                for dx in (-0.5, 0.4):
                    xs = xm + dx
                    zr = float(np.interp(xs, x, top)) - 0.2
                    rb.add(G.beam([xm, 0, zd + m['h'] - 1.0], [xs, sg * (half_breadth(st, spec, xs, zr) + 0.3), zr], 0.04), t_on=0.0, mat=1)
        if m.get('gaff'):
            zg = zd + m['h'] - 2.0
            rb.add(G.beam([xm - 0.3, 0, zg], [xm - 8.0, 0, zg + 2.2], 0.18, 0.18), t_on=2.0, mat=0)                 # gaff
            rb.add(G.beam([xm - 0.3, 0, zd + 1.6], [xm - 11.0, 0, zd + 1.3], 0.2, 0.2), t_on=2.0, mat=0)             # boom
            sails.append(dict(kind='spanker', mast=mi, luff=(np.array([xm - 0.3, 0, zd + 1.8]), np.array([xm - 0.3, 0, zg])),
                              leech=(np.array([xm - 10.6, 0, zd + 1.5]), np.array([xm - 7.8, 0, zg + 2.1]))))
            for sg in (-1, 1):
                for dx in (-0.6, 0.0, 0.6):
                    xs = xm + dx
                    zr = float(np.interp(xs, x, top)) - 0.2
                    rb.add(G.beam([xm, 0, zd + m['h'] - 3.0], [xs, sg * (half_breadth(st, spec, xs, zr) + 0.3), zr], 0.04), t_on=0.0, mat=1)
    # the bowsprit, the spritsail (nao) or the jibs (barque)
    bs = spec['bowsprit']
    ang = math.radians(bs['angle'])
    b0 = np.array([stem_x - 3.5, 0.0, stem_z - 0.8])
    b1 = b0 + np.array([math.cos(ang), 0.0, math.sin(ang)]) * (bs['length'] + 3.5)
    rb.add(G.beam(b0, b1, 0.3, 0.3), t_on=1.0, mat=0)
    if spec['style'] == 'nao':
        py = b0 + (b1 - b0) * 0.72
        rb.add(G.beam(py + [0, -3.6, -0.3], py + [0, 3.6, -0.3], 0.16, 0.16), t_on=2.0, mat=0)
        sails.append(dict(kind='sprit', mast=-1, x=py[0] + 0.2, z=py[2] - 0.4, a=3.5, h=3.2, foot_a=3.8))
    else:
        fm = mast_foot(spec, st, spec['masts'][1])
        for q, (dz1, dz2) in enumerate(((0.95, 0.55), (0.7, 0.35))):
            tack = b0 + (b1 - b0) * dz1
            head = np.array([fm[0], 0.0, fm[1] + spec['masts'][1]['top'] + spec['masts'][1]['topmast'] * dz2])
            rb.add(G.beam(tack, head, 0.04), t_on=2.0, mat=1)
            sails.append(dict(kind='jib', mast=-1, tack=tack, head=head, clew=np.array([fm[0] + 1.5, 0.0, fm[1] + 1.4 + 2.5 * q])))
    rb.finalize()
    return rb, sails


# ================================================================== sails
def sail_grid(corners_fn, nu=12, nv=10):
    V, UV = [], []
    for j in range(nv + 1):
        for i in range(nu + 1):
            u, v = i / nu, j / nv
            V.append(corners_fn(u, v))
            UV.append((u, 1 - v))
    V = np.array(V)
    Q, uvl = [], []
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            Q.append([a, a + 1, a + nu + 2, a + nu + 1])
    Q = np.array(Q)
    uv = np.array(UV)[Q.ravel()]
    return V, Q, uv


def sail_geometry(sd, state, billow=0.9, t=0.0):
    """Vertices of one sail for state (0 furled .. 1 set); None when furled."""
    if state < 0.5:
        return None
    kind = sd['kind']
    ph = 0.15 * math.sin(1.7 * t + sd.get('x', 0.0))
    if kind in ('course', 'topsail', 'topgallant', 'sprit'):
        a, fa, h = sd['a'], sd['foot_a'], sd['h']

        def f(u, v):
            y = (-a + 2 * a * u) * (1 - v) + (-fa + 2 * fa * u) * v
            z = sd['z'] - h * v * (1 - 0.06 * math.sin(math.pi * u))
            bx = billow * (1.0 + ph) * math.sin(math.pi * u) ** 0.9 * math.sin(math.pi * min(v * 0.85 + 0.12, 1.0)) ** 0.8 * (h / 8.0)
            return [sd['x'] + bx, y, z]
        return sail_grid(f)
    if kind == 'lateen':
        p0, p1, clew = sd['p0'], sd['p1'], sd['clew']

        def f(u, v):
            head = p0 + (p1 - p0) * u
            p = head + (clew - head) * v * (1 - u * 0.05)
            bil = billow * 1.4 * math.sin(math.pi * u) * math.sin(math.pi * min(v, 1.0)) * (1 + ph)
            return [p[0], p[1] + bil, p[2]]
        return sail_grid(f, 12, 8)
    if kind == 'spanker':
        (l0, l1), (e0, e1) = sd['luff'], sd['leech']

        def f(u, v):
            top = l1 + (e1 - l1) * u
            bot = l0 + (e0 - l0) * u
            p = top + (bot - top) * v
            bil = billow * 1.1 * math.sin(math.pi * u) * math.sin(math.pi * v) * (1 + ph)
            return [p[0], p[1] + bil, p[2]]
        return sail_grid(f, 10, 8)
    if kind == 'jib':
        tack, head, clew = sd['tack'], sd['head'], sd['clew']

        def f(u, v):
            luff = tack + (head - tack) * (1 - v)
            p = luff + (clew - luff) * u * (1 - v * 0.0)
            bil = billow * 0.9 * math.sin(math.pi * u) * math.sin(math.pi * min(v + 0.1, 1.0)) * (1 + ph)
            return [p[0], p[1] + bil, p[2]]
        return sail_grid(f, 8, 8)
    return None


def furled_geometry(sd):
    """A furled sail: a bundle along the yard (square sails) or the spar."""
    fb = G.HexBatch('furl')
    if sd['kind'] in ('course', 'topsail', 'topgallant', 'sprit'):
        fb.add(G.beam([sd['x'] - 0.1, -sd['a'] * 0.92, sd['z'] + 0.05], [sd['x'] - 0.1, sd['a'] * 0.92, sd['z'] + 0.05], 0.42, 0.34), mat=0)
    elif sd['kind'] == 'lateen':
        fb.add(G.beam(sd['p0'] + (sd['p1'] - sd['p0']) * 0.05, sd['p0'] + (sd['p1'] - sd['p0']) * 0.9, 0.4, 0.4), mat=0)
    elif sd['kind'] == 'spanker':
        fb.add(G.beam(sd['luff'][0], sd['luff'][1], 0.45, 0.45), mat=0)
    elif sd['kind'] == 'jib':
        fb.add(G.beam(sd['tack'], sd['tack'] + (sd['head'] - sd['tack']) * 0.25, 0.4, 0.4), mat=0)
    return fb


# ================================================================== build / pose
def build(S, spec, name='Ship', patched=False):
    sh = Ship()
    sh.spec = spec
    sh.name = name
    coll = bpy.context.scene.collection
    sh.root = SC.link(bpy.data.objects.new(name + 'Root', None), coll)
    m_hull = mat_hull(name + 'HullMat', spec)
    m_deck = SC.mat_wood(name + 'Deck', (0.52, 0.42, 0.30), width=0.2)
    m_paint = SC.mat_simple(name + 'Paint', spec['band'], 0.6)
    hull_me, st = build_hull(spec, name, m_hull)
    sh.st = st
    timber_me = build_timbers(spec, st, name, [S.m_wood, m_deck, m_paint])
    sh.rig_batch, sails = build_rig(spec, st, name, [S.m_wood, S.m_rope])
    sh.rig_mats = [S.m_wood, S.m_rope]
    rig_me = SC.hex_mesh(name + 'Rig', sh.rig_batch, sh.rig_batch.select(3.0), sh.rig_mats)
    sh.rig_stage = 3.0
    sh.sail_defs = sails
    sh.parts = []
    for part, me in (('Hull', hull_me), ('Timber', timber_me), ('Rig', rig_me)):
        o = SC.link(bpy.data.objects.new(name + part, me), coll)
        o.parent = sh.root
        o.pass_index = SC.PASS['ship']
        sh.parts.append(o)
    sh.m_sail = [mat_sail(name + 'Sail', spec['sail'], cross=False, patched=False),
                 mat_sail(name + 'SailCross', spec['sail'], cross=spec['cross'], patched=False),
                 mat_sail(name + 'SailPatched', spec['sail'], cross=False, patched=True),
                 mat_sail(name + 'SailCrossPatched', spec['sail'], cross=spec['cross'], patched=True)]
    sh.sails = SC.link(bpy.data.objects.new(name + 'Sails', bpy.data.meshes.new(name + 'Sails')), coll)
    sh.sails.parent = sh.root
    sh.sails.pass_index = SC.PASS['ship']
    sh.flag = SC.link(bpy.data.objects.new(name + 'Flag', bpy.data.meshes.new(name + 'Flag')), coll)
    sh.flag.parent = sh.root
    sh.flag.pass_index = SC.PASS['ship']
    sh.m_flag = mat_flag(name + 'FlagMat', spec['style'])
    xm, zd = mast_foot(spec, st, spec['masts'][0])
    m0 = spec['masts'][0]
    sh.flag_at = (xm, zd + m0['top'] + m0['topmast'] + 1.0)
    sh.key = None
    sh.patched = patched
    sh.m_hull = m_hull
    return sh


def mat_flag(name, style):
    """1519: the Cross of Burgundy (a red ragged saltire on white); 1831: the
    Royal Navy's white ensign simplified to a red cross on white with a canton."""
    m, nb, out = SC.new_material(name)
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    u, v, _ = nb.sep(uv)
    if style == 'nao':
        d1 = nb.math('ABSOLUTE', nb.math('SUBTRACT', u, v))
        d2 = nb.math('ABSOLUTE', nb.math('SUBTRACT', u, nb.math('SUBTRACT', 1.0, v)))
        cross = nb.math('MAXIMUM', nb.smooth(0.1, 0.08, d1), nb.smooth(0.1, 0.08, d2))
    else:
        cu = nb.math('ABSOLUTE', nb.math('SUBTRACT', u, 0.5))
        cv = nb.math('ABSOLUTE', nb.math('SUBTRACT', v, 0.5))
        cross = nb.math('MAXIMUM', nb.smooth(0.08, 0.07, cu), nb.smooth(0.1, 0.09, cv))
    col = nb.mix(cross, (0.92, 0.90, 0.84, 1), (0.62, 0.06, 0.05, 1))
    b = SC.principled(nb, col, rough=0.8, spec=0.2)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    m.use_backface_culling = False
    return m


def pose(sh, pos, heading, t, sails=None, heel=0.0, pitch=0.0, billow=0.9, patched=None, flag=True, masts=True,
         rig=3.0, foul=0.0, clean_x=-1e3, flag_up=1.0):
    """sails: dict kind -> state (0 furled, 1 set), or a single number for all.
    rig: 0 lower masts and shrouds, 1 + topmasts and bowsprit, 2 + yards and stays
    (sails only from 2).  foul: weed on the bottom forward of clean_x (scraping).
    flag_up: 0 on deck .. 1 at the masthead (hoisting)."""
    if rig != sh.rig_stage:
        SC.set_dynamic_mesh(sh.parts[2], sh.name + 'Rig', sh.rig_batch, sh.rig_batch.select(rig), sh.rig_mats)
        sh.rig_stage = rig
    nt = sh.m_hull.node_tree.nodes
    nt['foul'].outputs[0].default_value = foul
    nt['clean_x'].outputs[0].default_value = clean_x
    sh.root.matrix_world = (Matrix.Translation(pos) @ Matrix.Rotation(heading, 4, 'Z')
                            @ Matrix.Rotation(heel, 4, 'X') @ Matrix.Rotation(pitch, 4, 'Y'))
    for o in sh.parts:
        o.hide_render = False
    sh.parts[2].hide_render = not masts
    patched = sh.patched if patched is None else patched
    if sails is None:
        sails = 1.0
    parts_V, parts_Q, parts_uv, parts_m = [], [], [], []
    off = 0
    fb = G.HexBatch('furled')
    for sd in sh.sail_defs:
        stt = sails if isinstance(sails, (int, float)) else sails.get(sd['kind'], sails.get('all', 0.0))
        if not masts or rig < 2.0:
            continue
        geo = sail_geometry(sd, stt, billow, t)
        if geo is None:
            fb.extend(furled_geometry(sd))
            continue
        V, Q, uv = geo
        parts_V.append(V)
        parts_Q.append(Q + off)
        parts_uv.append(uv)
        cross = sd['kind'] == 'course'
        parts_m.append(np.full(len(Q), (1 if cross else 0) + (2 if patched else 0), np.int32))
        off += len(V)
    old = sh.sails.data
    if parts_V:
        me = SC.mesh_from_arrays(sh.name + 'Sails', np.vstack(parts_V), np.vstack(parts_Q), uv=np.vstack(parts_uv),
                                 mats=sh.m_sail, mat_idx=np.concatenate(parts_m), smooth=True)
    else:
        me = bpy.data.meshes.new(sh.name + 'Sails')
    if len(fb):
        fb.finalize()
        fm = SC.hex_mesh('Furled', fb, np.ones(len(fb.t_on), bool), [sh.m_sail[0]])
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.from_mesh(fm)
        bm.to_mesh(me)
        bm.free()
        if len(me.materials) == 0:
            me.materials.append(sh.m_sail[0])
        bpy.data.meshes.remove(fm)
    sh.sails.data = me
    sh.sails.hide_render = not masts
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    # the flag at the main masthead, streaming forward with the wind from astern
    fx, fz = sh.flag_at
    fz = fz - (1.0 - flag_up) * (fz - float(np.interp((sh.flag_at[0] / sh.spec['L']) + 0.5, sh.st[0], sh.st[4])) - 3.0)
    V, Q, uv = sail_grid(lambda u, v: [fx + 0.1 + 2.4 * u, 0.12 * math.sin(6.0 * u - 5.0 * t) * u, fz - 1.5 * v], 8, 4)
    oldf = sh.flag.data
    sh.flag.data = SC.mesh_from_arrays(sh.name + 'Flag', V, Q, uv=uv, mats=[sh.m_flag], smooth=True)
    sh.flag.hide_render = not (flag and masts)
    if oldf is not None and oldf.users == 0:
        bpy.data.meshes.remove(oldf)


def hide(sh):
    for o in sh.parts + [sh.sails, sh.flag]:
        o.hide_render = True
