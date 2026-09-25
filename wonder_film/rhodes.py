"""Rhodes, 292-280 BC: the harbour, the mole and the building site of the Colossus.

The world of wunderfilm_03_colossus (film_colossus20.py).  It borrows the
sky, sun, sea, cloud shadows and materials of scene.py (the bright look of
the lighthouse film) and adds its own ground, quays, city and the work:

  pedestal   white marble, built course by course
  statue     helios.py: bronze plates on an iron frame, weighted with stone
  mound      Philon of Byzantium: the figure was cast part by part inside a
             growing mound of earth, then uncovered by taking it away.  Here
             a fixed cone (55 deg, timber cribs) filled in 1-m layers, a
             spiral ramp cut into it; unbuilt from the top down at the end.

Coordinates: metres, +x east, +y north, sea level z = 0.  The statue stands
at the origin on the head of the western mole and looks west, out to sea;
the harbour lies to the east, the city on the rising ground south and east.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import geometry as G
import helios as HL
import life
import scene as SC
import timeline as TL

GROUND = 2.6                         # top of quays, moles and the statue platform
PLAT = 48.0                          # statue platform: half size (m), chamfered corners
CHAMFER = 12.0
MOLE_X = (-14.0, 14.0)               # the Colossus mole runs south to the shore
SHORE_S = -262.0                     # harbour front (quay) y
SHORE_E = 430.0                      # east quay x
NMOLE_Y = (59.0, 81.0)               # northern mole, from the east shore to its tower
NMOLE_HEAD = (110.0, 70.0, 11.0)
STATUE_YAW = math.pi / 2             # model faces +y; turned to look west

# pedestal: stepped base, die, cornice (half widths, course heights)
PED_STEPS = [(11.0, 0.6), (10.4, 0.6), (9.8, 0.6)]
PED_DIE = (8.8, 7, 0.8)
PED_CORNICE = [(9.25, 0.5), (9.55, 0.5)]
PT = GROUND + sum(h for _, h in PED_STEPS) + PED_DIE[1] * PED_DIE[2] + sum(h for _, h in PED_CORNICE)   # 11.0

# construction clock tc (abstract units, mapped to film time by each shot)
TC_PED = (0.0, 1.0)
TC_STATUE = (1.0, 9.0)               # bronze from the feet (0 m) to the top of the head (31 m)
TC_CROWN = (9.0, 9.4)
TC_SCAF_DOWN = (9.4, 9.9)
TC_REVEAL = (10.0, 12.0)             # the mound is taken away, top first
LEAD = 4.8                           # the iron frame stands this far above the finished bronze
FILL_LEAD = 1.3
M_GAP = 4.0                          # bronze stands this far above the top of the mound (trestles bridge it)
LAYER = 1.0                          # earth is heaped in layers of 1 m
M_MAX = GROUND + 32 * LAYER          # 34.6: the mound stops at the chest; the head is done from a scaffold
R_BASE = 38.0                        # mound: foot radius, flank slope (cot 55 deg)
COT = 0.70
RAMP_W, RAMP_G = 4.2, 0.14           # ramp width, gradient (1 : 7)
RAMP_TH0 = -math.pi / 2              # the ramp starts at the ground, south (towards the mole)
CRIB_DZ = 1.6                        # timber cribs in the flank every 1.6 m
SCAF_C, SCAF_R = (-0.5, 2.0), 7.2    # the scaffold round head and raised arm (world xy, radius)


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


# ================================================================== ground
def _coast_s(X):
    """South shore: the straight quay inside the harbour, a beach to the west."""
    west = np.clip((MOLE_X[0] - X) / 90.0, 0, 1)
    return SHORE_S - 30.0 * west ** 1.5 + 14.0 * west * G.fbm(X / 140.0, 0.3, 3, seed=51)


def _coast_e(Y):
    north = np.clip((Y - NMOLE_Y[1]) / 80.0, 0, 1)
    return SHORE_E + 40.0 * north ** 1.4 + 16.0 * north * G.fbm(0.7, Y / 150.0, 3, seed=52)


def built_mask(X, Y):
    """Platform, moles: flat built ground at GROUND."""
    ax, ay = np.abs(X), np.abs(Y)
    plat = (ax <= PLAT) & (ay <= PLAT) & (ax + ay <= 2 * PLAT - CHAMFER)
    mole = (X >= MOLE_X[0]) & (X <= MOLE_X[1]) & (Y <= -PLAT + 1) & (Y >= SHORE_S - 5)
    hx, hy, hr = NMOLE_HEAD
    nmole = ((X >= hx) & (X <= SHORE_E + 5) & (Y >= NMOLE_Y[0]) & (Y <= NMOLE_Y[1])) | (np.hypot(X - hx, Y - hy) <= hr)
    return plat | mole | nmole


def land_height(X, Y):
    """Natural ground and sea floor (without the built quays)."""
    ds = _coast_s(X) - Y
    de = X - _coast_e(Y)
    d = np.maximum(ds, de)                                   # > 0 inland
    quay = (X > MOLE_X[1] - 1) & (Y > SHORE_S - 60) & (X < SHORE_E + 60) & (Y < NMOLE_Y[0] + 1)
    rise = np.maximum(d - 42.0, 0.0)
    h = GROUND + 0.018 * rise + np.minimum(rise / 150.0, 1.0) * 5.0 * (G.fbm(X / 380.0, Y / 380.0, 4, seed=61) + 0.3)
    # the acropolis (Monte Smith) south-west of the town, the island's hills far to the south
    h += 96.0 * np.exp(-(((X + 620.0) / 300.0) ** 2 + ((Y + 900.0) / 380.0) ** 2))
    h += 190.0 * np.clip((-Y - 3200.0) / 1800.0, 0, 1) ** 1.5 * (0.75 + 0.5 * G.fbm(X / 900.0, Y / 900.0, 3, seed=66))
    beach = GROUND + 0.09 * np.minimum(d, 0.0) * 1.0
    sea = -7.0 + 4.0 * np.exp(np.minimum(d, 0.0) / 25.0)
    h_nat = np.where(d >= 0.0, np.where(quay, np.maximum(h, GROUND), h), np.maximum(beach, sea))
    h_nat = np.where(quay & (d < 0.0), -6.0, h_nat)          # dredged harbour: deep water at the quays
    return h_nat


def rhodes_height(X, Y):
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    h = land_height(X, Y)
    b = built_mask(X, Y)
    return np.where(b, np.maximum(h, GROUND + 0.03 * G.fbm(X / 7.0, Y / 7.0, 2, seed=8)), h)


def ground_z(x, y):
    return float(rhodes_height(np.array([x]), np.array([y]))[0])


def _graded(lo, hi, f_lo, f_hi, h, growth=1.12):
    """Coordinates: step h inside [f_lo, f_hi], growing geometrically outside."""
    mid = list(np.arange(f_lo, f_hi + 1e-6, h))
    left, x, s = [], f_lo, h
    while x > lo:
        s *= growth
        x -= s
        left.append(max(x, lo))
    right, x, s = [], f_hi, h
    while x < hi:
        s *= growth
        x += s
        right.append(min(x, hi))
    return np.array(left[::-1] + mid + right)


def mat_ground():
    """Dry Rhodian ground: sand and rock by slope, dust on the worked platform,
    green scrub (maquis) on the hills, wet stone at the waterline."""
    P = SC.P
    m, nb, out = SC.new_material('RhodesGround')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    nz = nb.sep(geo.outputs['Normal'])[2]
    x_, y_, z = nb.sep(pos)
    n1 = nb.noise(pos, 0.08, 3.0, 0.6).outputs['Fac']
    n2 = nb.noise(pos, 0.9, 3.0, 0.6).outputs['Fac']
    rock = nb.mix(n2, P['rock'][0] + (1,), P['rock'][1] + (1,))
    sand = nb.mix(n1, P['sand'][0] + (1,), P['sand'][1] + (1,))
    flat = nb.smooth(0.78, 0.93, nz)
    col = nb.mix(nb.math('MULTIPLY', flat, nb.smooth(0.42, 0.72, nb.math('ADD', n1, 0.1))), rock, sand)
    rr = nb.vmath('LENGTH', nb.comb(x_, y_, 0.0))
    yard = nb.math('MULTIPLY', nb.smooth(62.0, 44.0, rr), flat)
    dust = nb.mix(nb.noise(pos, 0.25, 4.0, 0.6).outputs['Fac'], P['dust'][0] + (1,), P['dust'][1] + (1,))
    col = nb.mix(yard, col, dust)
    hills = nb.smooth(12.0, 40.0, z)                              # maquis, pines and olive groves on the hills
    town = nb.smooth(1500.0, 1100.0, nb.vmath('LENGTH', nb.comb(nb.math('SUBTRACT', x_, 200.0), nb.math('ADD', y_, 200.0), 0.0)))
    cover = nb.math('ADD', 0.5, nb.math('MULTIPLY', hills, 0.3))
    cover = nb.math('SUBTRACT', cover, nb.math('MULTIPLY', town, 0.25))
    sn = nb.noise(pos, 0.12, 4.0, 0.62).outputs['Fac']
    scrub = nb.smooth(0.0, 0.08, nb.math('SUBTRACT', nb.math('ADD', sn, nb.math('MULTIPLY', n2, 0.15)), nb.math('SUBTRACT', 1.0, cover)))
    scrub = nb.math('MULTIPLY', scrub, nb.math('SUBTRACT', 1.0, yard))
    green = nb.mix(nb.noise(pos, 0.03, 3.0, 0.6).outputs['Fac'], (0.10, 0.14, 0.05, 1), (0.22, 0.25, 0.10, 1))
    col = nb.mix(nb.math('MULTIPLY', scrub, 0.85), col, green)
    wet = nb.smooth(1.6, 0.2, z)
    col = nb.mix(nb.math('MULTIPLY', wet, 0.75), col, P['wet'] + (1,))
    relief = nb.noise(pos, 1.6, 3.0, 0.6).outputs['Fac']
    if SC.use_textures():
        t1 = SC.tex_sample(nb, 'sand', pos, detail=0.7)
        sandy = nb.math('MULTIPLY', flat, nb.math('SUBTRACT', 1.0, wet))
        col = SC.mul_col(nb, col, nb.mix(sandy, (1.0, 1.0, 1.0, 1.0), t1[0]))
        relief = nb.math('ADD', nb.math('MULTIPLY', relief, 0.4), nb.math('MULTIPLY', t1[3], 0.9))
    b = SC.principled(nb, col, rough=nb.math('SUBTRACT', 0.95, nb.math('MULTIPLY', wet, 0.5)), spec=0.3)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.6
    nb.feed(bump.inputs['Height'], relief)
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_ground(coll):
    xs = _graded(-4500.0, 5000.0, -130.0, 470.0, 1.5)
    ys = _graded(-5500.0, 3000.0, -330.0, 130.0, 1.5)
    X, Y = np.meshgrid(xs, ys)
    Z = rhodes_height(X, Y)
    V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    nx = len(xs)
    idx = np.arange(len(ys) * nx).reshape(len(ys), nx)
    Q = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
    me = SC.mesh_from_arrays('RhodesGround', V, Q, mats=[mat_ground()], smooth=True)
    o = SC.link(bpy.data.objects.new('RhodesGround', me), coll)
    o.pass_index = SC.PASS['terrain']
    return o


# ================================================================== quays and moles
def _arc(cx, cy, r, a0, a1, n):
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(a0, a1, n)]


def quay_lines():
    """Faced edges of the built ground; water on the right of each segment."""
    p, c = PLAT, CHAMFER
    plat = [(MOLE_X[1], SHORE_S), (MOLE_X[1], -p), (p - c, -p), (p, -p + c), (p, p - c), (p - c, p),
            (-p + c, p), (-p, p - c), (-p, -p + c), (-p + c, -p), (MOLE_X[0], -p), (MOLE_X[0], SHORE_S - 30)]
    hx, hy, hr = NMOLE_HEAD
    nm = ([(SHORE_E + 30, NMOLE_Y[1]), (hx + 1.0, NMOLE_Y[1])] + _arc(hx, hy, hr, math.radians(95), math.radians(265), 14)
          + [(hx + 1.0, NMOLE_Y[0]), (SHORE_E, NMOLE_Y[0])])
    harbour = [(SHORE_E, NMOLE_Y[0]), (SHORE_E, SHORE_S), (MOLE_X[1], SHORE_S)]
    return [plat, nm, harbour]


def build_quay_walls(coll, mat):
    """Ashlar facing of all built edges: five courses from below the water to
    the quay top, header and stretcher blocks, a projecting coping."""
    qb = G.HexBatch('quays')
    rng = np.random.default_rng(31)
    courses = [(-1.9, 0.8), (-1.1, 0.8), (-0.3, 0.8), (0.5, 0.8), (1.3, 0.85)]
    for line in quay_lines():
        for a, b in zip(line[:-1], line[1:]):
            a, b = np.array(a, float), np.array(b, float)
            L = float(np.linalg.norm(b - a))
            if L < 0.5:
                continue
            d = (b - a) / L
            n = np.array([d[1], -d[0]])                    # outward (water side)
            rot = math.atan2(d[1], d[0])
            for ci, (z0, h) in enumerate(courses + [(GROUND - 0.45, 0.5)]):
                coping = ci == len(courses)
                s = -rng.uniform(0.0, 1.6) if ci % 2 else 0.0
                while s < L:
                    bl = rng.uniform(1.4, 2.4) if not coping else rng.uniform(1.8, 2.6)
                    s1 = min(s + bl, L)
                    if s1 - max(s, 0.0) > 0.3:
                        m = a + d * (max(s, 0.0) + s1) * 0.5
                        depth = 1.1 if not coping else 1.3
                        c = m - n * (depth * 0.5 - (0.12 if coping else 0.0))
                        qb.add(G.box(c[0], c[1], z0, s1 - max(s, 0.0) - 0.03, depth, h - 0.03, rot), mat=0)
                    s = s1
    qb.finalize()
    me = SC.hex_mesh('QuayWalls', qb, np.ones(len(qb.t_on), bool), [mat])
    o = SC.link(bpy.data.objects.new('QuayWalls', me), coll)
    o.pass_index = SC.PASS['masonry']
    return o


def build_paving(coll, mat):
    """Quays, moles and the statue platform paved with large slabs in rows."""
    pb = G.HexBatch('paving')
    rng = np.random.default_rng(37)
    step_y = 1.25
    for y in np.arange(SHORE_S - 5.0, NMOLE_Y[1] + 1.0, step_y):
        in_nmole = NMOLE_Y[0] - 12.0 < y < NMOLE_Y[1] + 1.0
        x = -PLAT - 1.0 + rng.uniform(0, 1.6)
        x_end = SHORE_E + 30.0 if in_nmole else PLAT + 1.0
        if in_nmole and y > PLAT + 1.0:
            x = NMOLE_HEAD[0] - NMOLE_HEAD[2] - 1.0 + rng.uniform(0, 1.6)
        while x < x_end:
            w = rng.uniform(1.4, 2.4)
            xs = np.array([x + 0.1, x + w - 0.1, x + 0.1, x + w - 0.1])
            ys = np.array([y + 0.1, y + 0.1, y + step_y - 0.1, y + step_y - 0.1])
            if built_mask(xs, ys).all():
                pb.add(G.box(x + w / 2, y + step_y / 2, GROUND - 0.12, w - 0.04, step_y - 0.04,
                             0.15 + rng.uniform(-0.01, 0.015)), mat=0, tone=rng.random())
            x += w
    pb.finalize()
    me = SC.hex_mesh('Paving', pb, np.ones(len(pb.t_on), bool), [mat])
    o = SC.link(bpy.data.objects.new('Paving', me), coll)
    o.pass_index = SC.PASS['masonry']
    return o


def build_breakwater(coll):
    """Rubble mound against the seaward faces of the platform and the mole."""
    from scipy.spatial import ConvexHull
    rng = np.random.default_rng(29)
    V, F = [], []
    pts = []
    for line in quay_lines()[:1]:
        for a, b in zip(line[:-1], line[1:]):
            a, b = np.array(a, float), np.array(b, float)
            L = float(np.linalg.norm(b - a))
            d = (b - a) / L
            n = np.array([d[1], -d[0]])
            if n[0] > -0.3 and n[1] < 0.3:                     # faces the harbour: a quay, no rubble
                continue
            for s in np.arange(1.0, L, 2.3):
                for row in range(2):
                    pts.append(a + d * (s + rng.uniform(-0.8, 0.8)) + n * (1.6 + 2.6 * row + rng.uniform(0, 1.2)))
    for (x, y) in pts:
        r = rng.uniform(1.0, 2.2)
        q = rng.normal(size=(14, 3))
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        q *= rng.uniform(0.75, 1.0, (14, 1)) * [r * rng.uniform(1.0, 1.4), r, r * rng.uniform(0.55, 0.8)]
        hull = ConvexHull(q)
        zc = rng.uniform(-0.6, 0.4)
        base = len(V)
        V.extend([[x + p_[0], y + p_[1], zc + p_[2]] for p_ in q])
        for simp in hull.simplices:
            i0, i1, i2 = simp
            nrm = np.cross(q[i1] - q[i0], q[i2] - q[i0])
            if np.dot(nrm, q[i0]) < 0:
                i1, i2 = i2, i1
            F.append([base + i0, base + i1, base + i2])
    me = SC.mesh_from_arrays('Breakwater', np.array(V), np.array(F), mats=[SC.mat_rock()])
    o = SC.link(bpy.data.objects.new('Breakwater', me), coll)
    o.pass_index = SC.PASS['terrain']
    return o


# ================================================================== the city
def mat_roof():
    m, nb, out = SC.new_material('RoofTiles')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    tone = nb.attr('tone').outputs['Fac']
    base = nb.mix(tone, (0.46, 0.20, 0.11, 1), (0.62, 0.33, 0.18, 1))
    n = nb.noise(pos, 0.6, 3.0, 0.6).outputs['Fac']
    col = SC.mul_col(nb, base, nb.comb(nb.math('ADD', 0.8, nb.math('MULTIPLY', n, 0.4)),
                                       nb.math('ADD', 0.8, nb.math('MULTIPLY', n, 0.4)),
                                       nb.math('ADD', 0.8, nb.math('MULTIPLY', n, 0.4))))
    b = SC.principled(nb, col, 0.8, 0.0, 0.35)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_houses():
    """Lime-washed, ochre and pink-plastered walls (tone per house); windows
    and doors lit at night like the lighthouse film's city."""
    m, nb, out = SC.new_material('Houses')
    tone = nb.attr('tone').outputs['Fac']
    base = nb.ramp(tone, [(0.0, (0.86, 0.83, 0.76)), (0.45, (0.80, 0.76, 0.66)), (0.62, (0.74, 0.60, 0.42)),
                          (0.8, (0.78, 0.63, 0.53)), (1.0, (0.66, 0.55, 0.42))])
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    u, v, _ = nb.sep(uv)
    cu = nb.math('FLOOR', nb.math('DIVIDE', u, 3.2))
    cv = nb.math('FLOOR', nb.math('DIVIDE', v, 3.4))
    fu = nb.math('FRACT', nb.math('DIVIDE', u, 3.2))
    fv = nb.math('FRACT', nb.math('DIVIDE', v, 3.4))
    win = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.smooth(0.3, 0.36, fu), nb.smooth(0.7, 0.64, fu)),
                  nb.math('MULTIPLY', nb.smooth(0.3, 0.36, fv), nb.smooth(0.72, 0.66, fv)))
    wn = nb.new('ShaderNodeTexWhiteNoise', noise_dimensions='3D')
    nb.feed(wn.inputs['Vector'], nb.comb(cu, cv, nb.math('MULTIPLY', tone, 97.0)))
    lit = nb.math('GREATER_THAN', wn.outputs['Value'], 0.8)
    geo = nb.new('ShaderNodeNewGeometry')
    nz = nb.math('ABSOLUTE', nb.sep(geo.outputs['Normal'])[2])
    vert = nb.math('LESS_THAN', nz, 0.3)
    k = nb.value(0.0, 'city_lights')
    wl = nb.math('MULTIPLY', win, lit)
    far = nb.smooth(0.8, 3.0, SC.pixel_footprint(nb))
    wl = nb.mix(far, wl, 0.06, dtype='FLOAT')
    grime = nb.noise(geo.outputs['Position'], 0.4, 3.0, 0.6).outputs['Fac']
    col = SC.mul_col(nb, base, nb.comb(nb.math('ADD', 0.82, nb.math('MULTIPLY', grime, 0.3)),
                                       nb.math('ADD', 0.82, nb.math('MULTIPLY', grime, 0.3)),
                                       nb.math('ADD', 0.82, nb.math('MULTIPLY', grime, 0.28))))
    # dark doorways and small windows by day
    col = nb.mix(nb.math('MULTIPLY', nb.math('MULTIPLY', win, vert), nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, far), 0.55)),
                 col, (0.12, 0.10, 0.08, 1))
    e = nb.math('MULTIPLY', wl, nb.math('MULTIPLY', vert, k))
    b = SC.principled(nb, col, 0.9, 0.0, 0.3, (1.0, 0.55, 0.22, 1), e)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


INSULA = (50.0, 32.0)                # Hippodamian grid: block pitch (x, y), streets included
STREET = (6.0, 5.0)


def on_land(x, y, margin):
    ds = float(_coast_s(np.array([x]))[0]) - y
    de = x - float(_coast_e(np.array([y]))[0])
    return max(ds, de) > margin


def build_city(coll, m_city, m_roof, m_marble):
    """Houses on the grid of Hippodamus (courtyard houses, flat and tiled
    roofs), merged blocks further away, a temple of Helios on the acropolis,
    a stoa on the harbour front, ship sheds on the east quay, towers."""
    cb = G.HexBatch('rhodes_city')
    rng = np.random.default_rng(41)
    hc = np.array([200.0, -200.0])
    for gx in np.arange(-2600.0, 3200.0, INSULA[0]):
        for gy in np.arange(-3600.0, 1200.0, INSULA[1]):
            cx, cy = gx + INSULA[0] / 2, gy + INSULA[1] / 2
            dist = float(np.hypot(cx - hc[0], cy - hc[1]))
            if dist > 1500 or not on_land(cx, cy, 48.0):
                continue
            if abs(cx + 620) < 170 and abs(cy + 900) < 200:          # the acropolis sanctuary is open ground
                continue
            if rng.random() < 0.08 + 0.35 * clamp((dist - 700) / 800):   # gardens, open squares, fields
                continue
            w, d = INSULA[0] - STREET[0], INSULA[1] - STREET[1]
            if dist < 800:
                for i in range(4):
                    for j in range(2):
                        hw, hd = w / 4, d / 2
                        x = gx + STREET[0] / 2 + hw * (i + 0.5)
                        y = gy + STREET[1] / 2 + hd * (j + 0.5)
                        z = ground_z(x, y)
                        h = rng.uniform(4.5, 8.5) * (1.35 if rng.random() < 0.1 else 1.0)
                        cb.add(G.box(x, y, z - 2.0, hw - 0.4, hd - 0.4, h + 2.0), mat=0, tone=rng.random())
                        if rng.random() < 0.72:
                            rot = 0.0 if rng.random() < 0.5 else math.pi / 2
                            a, b = (hw - 0.2, hd - 0.2) if rot == 0.0 else (hd - 0.2, hw - 0.2)
                            cb.add(G.tent(x, y, z + h, a, b, 1.6, rot), mat=1, tone=rng.random())
                        elif rng.random() < 0.5:
                            cb.add(G.box(x + rng.uniform(-1, 1), y, z + h, hw * 0.45, hd * 0.5, 2.6), mat=0, tone=rng.random())
            else:
                z = ground_z(cx, cy)
                h = rng.uniform(5.0, 8.0)
                cb.add(G.box(cx, cy, z - 3.0, w, d, h + 3.0), mat=0, tone=rng.random())
                if rng.random() < 0.75:
                    cb.add(G.tent(cx, cy, z + h, w * 0.98, d * 0.98, 2.0, 0.0), mat=1, tone=rng.random())
    # temple of Helios on the acropolis: stylobate, colonnade, cella, pediment roof
    tx, ty = -620.0, -900.0
    tz = ground_z(tx, ty)
    cb.add(G.box(tx, ty, tz - 3.0, 26.0, 50.0, 4.4), mat=2, tone=0.5)
    for k in range(6):
        for side in (-1, 1):
            cb.add(G.box(tx + (k - 2.5) * 4.3, ty + side * 22.0, tz + 1.4, 1.5, 1.5, 9.0), mat=2)
    for k in range(1, 11):
        for side in (-1, 1):
            cb.add(G.box(tx + side * 10.8, ty + (k - 5.5) * 4.3, tz + 1.4, 1.5, 1.5, 9.0), mat=2)
    cb.add(G.box(tx, ty, tz + 1.4, 15.0, 32.0, 9.0), mat=2, tone=0.4)
    cb.add(G.box(tx, ty, tz + 10.4, 24.0, 47.0, 1.8), mat=2, tone=0.5)
    cb.add(G.tent(tx, ty, tz + 12.2, 47.5, 24.5, 3.6, math.pi / 2), mat=1, tone=0.4)
    # stoa on the harbour front, facing the water
    for k in range(38):
        x = 60.0 + k * 4.0
        cb.add(G.box(x, SHORE_S - 14.0, GROUND, 0.9, 0.9, 6.5), mat=2)
    cb.add(G.box(60.0 + 37 * 2.0, SHORE_S - 22.0, GROUND, 38 * 4.0 + 2, 14.0, 7.2), mat=0, tone=0.8)
    cb.add(G.box(60.0 + 37 * 2.0, SHORE_S - 16.0, GROUND + 6.5, 38 * 4.0 + 3, 12.5, 0.9), mat=2, tone=0.6)
    cb.add(G.tent(60.0 + 37 * 2.0, SHORE_S - 20.0, GROUND + 7.4, 38 * 4.0 + 3, 17.0, 2.4, 0.0), mat=1, tone=0.6)
    # ship sheds (neosoikoi) on the east quay: long roofs sloping to the water
    for k in range(9):
        y = -150.0 + k * 7.2
        cb.add(G.box(SHORE_E + 22.0, y, GROUND, 40.0, 0.8, 5.5), mat=0, tone=0.7)
        cb.add(G.tent(SHORE_E + 22.0, y + 3.6, GROUND + 5.5, 40.0, 7.0, 1.6, 0.0), mat=1, tone=rng.random())
    cb.add(G.box(SHORE_E + 22.0, -150.0 + 9 * 7.2, GROUND, 40.0, 0.8, 5.5), mat=0, tone=0.7)
    # towers: at the root of the Colossus mole, on the northern mole head, the harbour corners
    for (x, y, r, h) in ((NMOLE_HEAD[0], NMOLE_HEAD[1], 7.0, 17.0), (0.0, SHORE_S - 10.0, 6.0, 15.0),
                         (SHORE_E + 10.0, NMOLE_Y[0] - 8.0, 6.0, 14.0)):
        n = 12
        for k in range(int(h / 1.0)):
            for i in range(n):
                a0 = 2 * math.pi * (i + 0.5 * (k % 2)) / n
                bx, by = x + r * math.cos(a0), y + r * math.sin(a0)
                cb.add(G.box(bx, by, GROUND + k * 1.0, 2 * math.pi * r / n - 0.05, 1.2, 0.97, a0 + math.pi / 2), mat=0,
                       tone=rng.random())
        cb.add(G.box(x, y, GROUND, r * 1.6, r * 1.6, h), mat=0, tone=0.5)
    cb.finalize()
    me = SC.hex_mesh('RhodesCity', cb, np.ones(len(cb.t_on), bool), [m_city, m_roof, m_marble])
    o = SC.link(bpy.data.objects.new('RhodesCity', me), coll)
    o.pass_index = SC.PASS['city']
    return o


def build_trees(coll):
    """Cypresses, Aleppo pines and olive trees: sparse in the town's gardens,
    in groves on the hills and the acropolis."""
    from scipy.spatial import ConvexHull
    rng = np.random.default_rng(43)
    m_leaf = SC.mat_simple('Foliage', (0.07, 0.12, 0.045), 0.85)
    m_olive = SC.mat_simple('OliveFoliage', (0.20, 0.25, 0.14), 0.85)
    m_pine = SC.mat_simple('PineFoliage', (0.11, 0.16, 0.06), 0.85)
    N = 160000
    X = rng.uniform(-2600, 3200, N)
    Y = rng.uniform(-3600, 1000, N)
    ds = _coast_s(X) - Y
    de = X - _coast_e(Y)
    land = np.maximum(ds, de) > 55.0
    town = np.hypot(X - 200, Y + 200) < 1100
    grove = 0.5 + 0.5 * G.fbm(X / 260.0, Y / 260.0, 3, seed=71)
    p = np.where(town, 0.05, 0.35 + 0.5 * grove)
    p = np.where(np.hypot((X + 620) / 300, (Y + 900) / 380) < 1.0, 0.8, p)
    keep = land & (rng.random(N) < p * 0.25) & (np.hypot(X, Y) > 120)
    X, Y = X[keep][:9000], Y[keep][:9000]
    Z = rhodes_height(X, Y)
    V, F, M = [], [], []

    def add(verts, faces, mat):
        b = len(V)
        V.extend(verts)
        F.extend([[b + i for i in f] for f in faces])
        M.extend([mat] * len(faces))
    ring = np.linspace(0, 2 * math.pi, 7, endpoint=False)
    for x, y, z in zip(X, Y, Z):
        kind = rng.random()
        if kind < 0.35:                                       # cypress
            h, r = rng.uniform(9, 16), rng.uniform(1.0, 1.6)
            lo = [(x + r * math.cos(a), y + r * math.sin(a), z + 1.2) for a in ring]
            mid = [(x + r * 1.05 * math.cos(a), y + r * 1.05 * math.sin(a), z + h * 0.45) for a in ring]
            add(lo + mid + [(x, y, z + h)], [[i, (i + 1) % 7, 7 + (i + 1) % 7, 7 + i] for i in range(7)]
                + [[7 + i, 7 + (i + 1) % 7, 14, 14] for i in range(7)], 0)
            continue
        pine = kind < 0.6
        r = rng.uniform(2.5, 4.5) if pine else rng.uniform(2.0, 3.6)
        hc = rng.uniform(7, 11) if pine else rng.uniform(2.2, 3.2)
        flat = 0.45 if pine else 0.75
        c = np.array([x, y, z + hc])
        q = rng.normal(size=(12, 3))
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        pts = c + q * [r, r * rng.uniform(0.8, 1.1), r * flat]
        hull = ConvexHull(pts)
        fs = []
        for sm in hull.simplices:
            a, b, cc = sm
            if np.dot(np.cross(pts[b] - pts[a], pts[cc] - pts[a]), pts[a] - c) < 0:
                b, cc = cc, b
            fs.append([a, b, cc, cc])
        add([tuple(p_) for p_ in pts], fs, 2 if pine else 1)
        if pine:                                              # a bare trunk under the umbrella
            tr = [(x + 0.25 * math.cos(a), y + 0.25 * math.sin(a), z - 0.3) for a in ring[::2]]
            tt = [(x + 0.2 * math.cos(a) + 0.6, y + 0.2 * math.sin(a), z + hc - r * flat * 0.6) for a in ring[::2]]
            add(tr + tt, [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)], 3)
    me = SC.mesh_from_arrays('Trees', np.array(V), np.array(F), mats=[m_leaf, m_olive, m_pine, SC.mat_simple('Bark', (0.2, 0.15, 0.1), 0.9)],
                             mat_idx=np.array(M))
    o = SC.link(bpy.data.objects.new('Trees', me), coll)
    o.pass_index = SC.PASS['terrain']
    return o


# ================================================================== pedestal
def build_pedestal():
    """White marble: three steps, the die in seven courses, a two-course
    cornice.  Blocks are laid round each course in turn (t_on in tc); the
    corner blocks alternate between the sides course by course (bond)."""
    pb = G.HexBatch('pedestal')
    courses = [(a, h, 2.1) for a, h in PED_STEPS] + [(PED_DIE[0], PED_DIE[2], 1.75)] * PED_DIE[1] + \
              [(a, h, 1.9) for a, h in PED_CORNICE]
    n = len(courses)
    depth = 1.1
    z = GROUND
    for ci, (a, h, bl) in enumerate(courses):
        t0 = TC_PED[0] + (TC_PED[1] - TC_PED[0]) * ci / n
        t1 = TC_PED[0] + (TC_PED[1] - TC_PED[0]) * (ci + 1) / n
        blocks = []
        for s in range(4):
            rot = s * math.pi / 2
            c, sn = math.cos(rot), math.sin(rot)
            full = (s + ci) % 2 == 0                    # this side runs over the corners
            lo_, hi_ = (-a, a) if full else (-a + depth, a - depth)
            nb_ = max(int(round((hi_ - lo_) / bl)), 1)
            w = (hi_ - lo_) / nb_
            for i in range(nb_):
                u = lo_ + (i + 0.5) * w
                v = -a + depth / 2
                blocks.append((c * u - sn * v, sn * u + c * v, w - 0.02, rot))
        for k, (x, y, w, rot) in enumerate(blocks):
            pb.add(G.box(x, y, z, w, depth, h - 0.015, rot), t_on=t0 + (t1 - t0) * k / len(blocks), mat=0)
        pb.add(G.box(0.0, 0.0, z, 2 * a - 2 * depth - 0.1, 2 * a - 2 * depth - 0.1, h - 0.02), t_on=t1 - 1e-3, mat=1)
        z += h
    pb.finalize()
    return pb


# ================================================================== the statue
def mat_bronze():
    """Fresh bronze sheet: each plate its own shade, dark seams, rivet rows
    beside them, a hammered surface; polished, so it mirrors sun and sky."""
    m, nb, out = SC.new_material('BronzePlates')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    seam = nb.attr('seam').outputs['Fac']
    tone = nb.attr('ptone').outputs['Fac']
    base = nb.mix(tone, (0.66, 0.40, 0.19, 1), (0.80, 0.52, 0.27, 1))
    far = nb.smooth(0.02, 0.09, SC.pixel_footprint(nb))
    line = nb.math('SUBTRACT', 1.0, nb.smooth(0.022, 0.05, seam))
    line = nb.mix(far, line, nb.math('MULTIPLY', line, 0.4), dtype='FLOAT')
    vor = nb.new('ShaderNodeTexVoronoi')
    nb.feed(vor.inputs['Vector'], pos)
    vor.inputs['Scale'].default_value = 4.2
    band = nb.math('MULTIPLY', nb.smooth(0.05, 0.07, seam), nb.smooth(0.12, 0.1, seam))
    dot = nb.math('SUBTRACT', 1.0, nb.smooth(0.12, 0.2, vor.outputs['Distance']))
    rivet = nb.math('MULTIPLY', nb.math('MULTIPLY', band, dot), nb.math('SUBTRACT', 1.0, far))
    col = nb.mix(nb.math('MULTIPLY', line, 0.85), base, (0.10, 0.06, 0.03, 1))
    col = nb.mix(nb.math('MULTIPLY', rivet, 0.5), col, (0.95, 0.70, 0.42, 1))
    ham = nb.noise(pos, 3.2, 3.0, 0.55).outputs['Fac']
    rough = nb.math('ADD', 0.24, nb.math('MULTIPLY', nb.noise(pos, 0.7, 3.0, 0.6).outputs['Fac'], 0.18))
    b = SC.principled(nb, col, rough=rough, metal=1.0, spec=0.5)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.04
    nb.feed(bump.inputs['Height'], nb.math('ADD', nb.math('MULTIPLY', ham, 0.25),
                                           nb.math('ADD', nb.math('MULTIPLY', line, -1.0), nb.math('MULTIPLY', rivet, 0.8))))
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_iron():
    m, nb, out = SC.new_material('Iron')
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    n = nb.noise(pos, 1.3, 3.0, 0.6).outputs['Fac']
    col = nb.mix(nb.smooth(0.45, 0.7, n), (0.07, 0.065, 0.06, 1), (0.22, 0.10, 0.05, 1))
    b = SC.principled(nb, col, rough=0.62, metal=0.7, spec=0.4)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def statue_matrix():
    return Matrix.Translation((0.0, 0.0, PT)) @ Matrix.Rotation(STATUE_YAW, 4, 'Z')


def build_statue(S, coll):
    d = HL.build()
    S.hl = d
    S.m_bronze_plates = mat_bronze()
    S.m_iron = mat_iron()
    S.skin = SC.link(bpy.data.objects.new('Colossus', bpy.data.meshes.new('Colossus')), coll)
    S.crown = SC.link(bpy.data.objects.new('Crown', bpy.data.meshes.new('Crown')), coll)
    for o in (S.skin, S.crown):
        o.matrix_world = statue_matrix()
        o.pass_index = SC.PASS['statue']
    S.skin_level = None
    # iron frame and stone fill: timed hexahedra in the statue's frame
    ab = G.HexBatch('armature')
    for x0, y0, z0, x1, y1, z1, bz in d['bars']:
        if abs(z1 - z0) < 1e-3 and math.hypot(x1 - x0, y1 - y0) < 1e-3:
            continue
        ab.add(G.beam([x0, y0, z0], [x1, y1, z1], 0.22), t_on=bz, mat=0)
    ab.finalize()
    S.arm_batch = ab
    S.arm_obj = SC.link(bpy.data.objects.new('Armature', bpy.data.meshes.new('Armature')), coll)
    fb = G.HexBatch('fill')
    for x, y, z, sx, sy, sz, bz in d['fill']:
        fb.add(G.box(x, y, z, sx, sy, sz), t_on=bz, mat=0)
    fb.finalize()
    S.fill_batch = fb
    S.fill_obj = SC.link(bpy.data.objects.new('StoneFill', bpy.data.meshes.new('StoneFill')), coll)
    for o in (S.arm_obj, S.fill_obj):
        o.matrix_world = statue_matrix()
        o.pass_index = SC.PASS['statue']


def _skin_mesh(d, faces, name, mat):
    V = d['V']
    me = SC.mesh_from_arrays(name, V, faces, mats=[mat], smooth=True)
    for an, key in (('seam', 'seam'), ('ptone', 'tone')):
        a = me.attributes.new(an, 'FLOAT', 'POINT')
        a.data.foreach_set('value', d[key].astype(np.float32))
    return me


def level(tc):
    """Height of the finished bronze above the pedestal (m)."""
    a, b = TC_STATUE
    return HL.HEIGHT * clamp((tc - a) / (b - a))


def set_statue(S, tc):
    d = S.hl
    L = level(tc) if tc < TC_STATUE[1] else HL.HEIGHT + 3.0
    key = round(L, 3)
    if key != S.skin_level:
        S.skin_level = key
        sel = d['plate_z'][d['face_plate']] <= L
        old = S.skin.data
        S.skin.data = _skin_mesh(d, d['F'][sel], 'Colossus', S.m_bronze_plates)
        if old.users == 0:
            bpy.data.meshes.remove(old)
        csel = d['crown_z'] <= (L if tc < TC_CROWN[0] else HL.HEIGHT + 3.0 * clamp((tc - TC_CROWN[0]) / (TC_CROWN[1] - TC_CROWN[0])))
        cm = SC.mesh_from_arrays('Crown', d['crown_V'], d['crown_F'][csel], mats=[S.m_bronze_plates])
        a = cm.attributes.new('seam', 'FLOAT', 'POINT')
        a.data.foreach_set('value', np.ones(len(d['crown_V']), np.float32))
        a = cm.attributes.new('ptone', 'FLOAT', 'POINT')
        a.data.foreach_set('value', np.full(len(d['crown_V']), 0.5, np.float32))
        old = S.crown.data
        S.crown.data = cm
        if old.users == 0:
            bpy.data.meshes.remove(old)
    S.skin.hide_render = tc < TC_STATUE[0]
    building = TC_STATUE[0] - 0.02 <= tc < TC_STATUE[1] + 0.3
    ab = S.arm_batch
    sel = building & (ab.t_on <= L + LEAD) & (ab.t_on >= L - 2.5)
    SC.set_dynamic_mesh(S.arm_obj, 'Armature', ab, sel, [S.m_iron])
    fb = S.fill_batch
    sel = building & (fb.t_on <= L + FILL_LEAD) & (fb.t_on >= L - 3.0)
    SC.set_dynamic_mesh(S.fill_obj, 'StoneFill', fb, sel, [S.m_quay])
    return L


# ================================================================== the mound
def cone_r(z):
    """Radius of the mound's flank at height z."""
    return R_BASE - (z - GROUND) * COT


def ramp_phi(z):
    """Angle travelled along the spiral ramp from its foot to height z."""
    return math.log(R_BASE / cone_r(z)) / (RAMP_G * COT)


def ramp_phi_max(M):
    return ramp_phi(max(min(M, M_MAX), GROUND))


def ramp_point(phi, side=0.5):
    """Point on the spiral ramp after turning phi from its foot (side 0 = outer
    edge, 1 = inner edge) and the uphill heading there."""
    z = GROUND + (R_BASE - R_BASE * math.exp(-phi * RAMP_G * COT)) / COT
    r = cone_r(z) - RAMP_W * (0.15 + 0.7 * side)
    th = RAMP_TH0 + phi
    return (r * math.cos(th), r * math.sin(th), z), th + math.pi / 2


def mound_top(tc):
    """Top of the earth (world z), in whole layers."""
    if tc < 0.8:
        return GROUND
    if tc <= TC_REVEAL[0]:
        m1 = GROUND + (PT - GROUND) * clamp((tc - 0.8) / 0.8)
        m2 = PT + level(tc) - M_GAP
        m = min(max(m1, m2), M_MAX)
        return GROUND + math.floor((m - GROUND) / LAYER + 1e-6) * LAYER
    u = clamp((tc - TC_REVEAL[0]) / (TC_REVEAL[1] - TC_REVEAL[0]))
    m = M_MAX - u * (M_MAX - GROUND)
    return GROUND + math.ceil((m - GROUND) / LAYER - 1e-6) * LAYER


def mound_heights(R, TH, M):
    """Height field of the mound (world z) at polar (R, TH) for top M."""
    h = np.minimum(GROUND + (R_BASE - R) / COT, M)
    h = np.maximum(h, GROUND - 0.3)
    k_ = RAMP_G * COT
    base = np.mod(TH - RAMP_TH0, 2 * math.pi)
    for k in range(3):
        phi = base + 2 * math.pi * k
        zr = GROUND + (R_BASE - R_BASE * np.exp(-phi * k_)) / COT       # ramp height after turning phi
        rr = cone_r(zr)
        on = (zr <= M + 0.01) & (R >= rr - RAMP_W) & (R <= rr + 0.3)
        h = np.where(on, np.minimum(h, zr), h)
    return h


def mat_earth():
    """Heaped terra rossa: red-brown with clods and stones, darker compacted
    lines between the layers, the trodden ramp and top dustier and paler."""
    m, nb, out = SC.new_material('Earth')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    z = nb.sep(pos)[2]
    nz = nb.sep(geo.outputs['Normal'])[2]
    n1 = nb.noise(pos, 0.35, 4.0, 0.6).outputs['Fac']
    n2 = nb.noise(pos, 2.5, 3.0, 0.6).outputs['Fac']
    n3 = nb.noise(pos, 7.0, 2.0, 0.6).outputs['Fac']
    col = nb.mix(n1, (0.15, 0.075, 0.04, 1), (0.30, 0.16, 0.08, 1))
    far = nb.smooth(0.02, 0.08, SC.pixel_footprint(nb))
    stones = nb.math('MULTIPLY', nb.smooth(0.66, 0.72, n3), nb.math('SUBTRACT', 1.0, far))
    col = nb.mix(nb.math('MULTIPLY', stones, 0.8), col, (0.42, 0.37, 0.30, 1))
    lay = nb.math('FRACT', nb.math('ADD', nb.math('SUBTRACT', z, GROUND), nb.math('MULTIPLY', n2, 0.06)))
    line = nb.math('MULTIPLY', nb.smooth(0.88, 0.97, lay), nb.smooth(0.6, 0.3, nz))
    col = nb.mix(nb.math('MULTIPLY', line, 0.5), col, (0.08, 0.045, 0.025, 1))
    flat = nb.smooth(0.8, 0.95, nz)
    trod = nb.math('MULTIPLY', flat, nb.smooth(0.3, 0.7, nb.noise(pos, 0.9, 3.0, 0.6).outputs['Fac']))
    col = nb.mix(nb.math('MULTIPLY', trod, 0.5), col, (0.36, 0.24, 0.14, 1))
    b = SC.principled(nb, col, rough=0.95, spec=0.2)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.7
    nb.feed(bump.inputs['Height'], nb.math('ADD', nb.math('ADD', n2, nb.math('MULTIPLY', n3, 0.5)),
                                           nb.math('MULTIPLY', line, -0.6)))
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_logs():
    m, nb, out = SC.new_material('Logs')
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    n = nb.noise(pos, 1.7, 3.0, 0.6).outputs['Fac']
    col = nb.mix(n, (0.07, 0.045, 0.03, 1), (0.17, 0.11, 0.065, 1))
    b = SC.principled(nb, col, rough=0.9, spec=0.25)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_mound(S, coll):
    rs = np.concatenate([np.arange(0.0, R_BASE + 2.01, 0.4)])
    ths = np.linspace(-math.pi, math.pi, 1000, endpoint=False)
    Rg, Tg = np.meshgrid(rs, ths, indexing='ij')
    S.mound_R, S.mound_T = Rg.ravel(), Tg.ravel()
    X, Y = S.mound_R * np.cos(S.mound_T), S.mound_R * np.sin(S.mound_T)
    S.mound_bumps = (0.18 * G.fbm(X / 1.3, Y / 1.3, 3, seed=91) + 0.1 * G.fbm(X / 0.5, Y / 0.5, 2, seed=92)).astype(float)
    V = np.stack([S.mound_R * np.cos(S.mound_T), S.mound_R * np.sin(S.mound_T), np.full(Rg.size, GROUND)], 1)
    nr, nt = len(rs), len(ths)
    idx = np.arange(nr * nt).reshape(nr, nt)
    nxt = np.roll(idx, -1, axis=1)
    Q = np.stack([idx[:-1].ravel(), nxt[:-1].ravel(), nxt[1:].ravel(), idx[1:].ravel()], 1)
    me = SC.mesh_from_arrays('Mound', V, Q, mats=[mat_earth()], smooth=True)
    S.mound = SC.link(bpy.data.objects.new('Mound', me), coll)
    S.mound.pass_index = SC.PASS['terrain']
    S.mound_M = None
    # timber cribs: rings of logs in the flank, gaps where the ramp crosses
    cb = G.HexBatch('cribs')
    zs = np.arange(GROUND + CRIB_DZ, M_MAX, CRIB_DZ)
    for zk in zs:
        r = cone_r(zk) + 0.12
        n = max(int(2 * math.pi * r / 3.6), 8)
        for i in range(n):
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
            am = 0.5 * (a0 + a1)
            ph = np.mod(am - RAMP_TH0, 2 * math.pi)
            clear = True
            for k in range(3):
                zr = GROUND + (R_BASE - R_BASE * math.exp(-(ph + 2 * math.pi * k) * RAMP_G * COT)) / COT
                if abs(zr - zk) < 2.2:
                    clear = False
            if not clear:
                continue
            p0 = (r * math.cos(a0), r * math.sin(a0), zk)
            p1 = (r * math.cos(a1), r * math.sin(a1), zk)
            cb.add(G.beam(p0, p1, 0.32, 0.3), t_on=zk, mat=0)
    cb.finalize()
    S.crib_batch = cb
    S.crib_obj = SC.link(bpy.data.objects.new('Cribs', bpy.data.meshes.new('Cribs')), coll)
    S.crib_obj.pass_index = SC.PASS['timber']


def set_mound(S, tc):
    M = mound_top(tc)
    if M != S.mound_M:
        S.mound_M = M
        z = mound_heights(S.mound_R, S.mound_T, M) + S.mound_bumps
        V = np.stack([S.mound_R * np.cos(S.mound_T), S.mound_R * np.sin(S.mound_T), z], 1).astype(np.float32)
        S.mound.data.vertices.foreach_set('co', V.ravel())
        S.mound.data.update()
        sel = S.crib_batch.t_on <= M - 0.35
        SC.set_dynamic_mesh(S.crib_obj, 'Cribs', S.crib_batch, sel, [S.m_logs])
    S.mound.hide_render = M <= GROUND + 0.05
    S.crib_obj.hide_render = S.mound.hide_render
    return M


# ================================================================== scaffold round the head
def statue_world_vertices(d):
    V = d['V']
    return np.stack([-V[:, 1], V[:, 0], V[:, 2] + PT], 1)          # the model turned to look west, on the pedestal


SCAF_ARC = (math.radians(-86.0), math.radians(150.0))   # the scaffold stands behind and beside the head


def build_head_scaffold(d):
    """Standards on an arc behind and beside head and raised arm (the face and
    the hand stay open to the sea side), standing on the mound top; ledgers,
    planked lifts every 2.2 m, putlogs and boards reaching in to the bronze,
    ladders.  t_on: the lift's height (compared with the bronze level); t_off:
    struck top-down (tc)."""
    from scipy.spatial import cKDTree
    Vw = statue_world_vertices(d)
    tree = cKDTree(Vw[::3])
    sb = G.HexBatch('head_scaffold')
    cx, cy = SCAF_C
    z0 = M_MAX
    top = PT + HL.HEIGHT + 3.5
    lifts = np.arange(z0 + 2.2, top + 0.01, 2.2)
    a0_, a1_ = SCAF_ARC
    n = 9
    angs = np.linspace(a0_, a1_, n + 1)
    for li, zl in enumerate(lifts):
        t_on = (zl - PT) - 2.2                      # compared with the bronze level L
        t_off = TC_SCAF_DOWN[1] - (TC_SCAF_DOWN[1] - TC_SCAF_DOWN[0]) * li / len(lifts)
        for i in range(n + 1):
            a = angs[i]
            p0 = (cx + SCAF_R * math.cos(a), cy + SCAF_R * math.sin(a))
            sb.add(G.beam((p0[0], p0[1], zl - 2.2), (p0[0], p0[1], zl + 0.02), 0.16), t_on=t_on, t_off=t_off, mat=0)
            if i == n:
                continue
            b = angs[i + 1]
            p1 = (cx + SCAF_R * math.cos(b), cy + SCAF_R * math.sin(b))
            sb.add(G.beam((p0[0], p0[1], zl), (p1[0], p1[1], zl), 0.13), t_on=t_on, t_off=t_off, mat=0)
            sb.add(G.beam((p0[0], p0[1], zl + 1.0), (p1[0], p1[1], zl + 1.0), 0.08), t_on=t_on, t_off=t_off, mat=0)  # guard rail
            am = 0.5 * (a + b)
            rm = SCAF_R - 0.45
            ch = 2 * rm * math.sin(0.5 * (b - a))
            sb.add(G.box(cx + rm * math.cos(am), cy + rm * math.sin(am), zl + 0.07, ch, 0.9, 0.07, am + math.pi / 2),
                   t_on=t_on, t_off=t_off, mat=1)
            # a putlog and a board from the lift in towards the bronze (stops 0.8 m short of it)
            r_in = None
            for r in np.arange(SCAF_R - 0.9, 0.5, -0.25):
                q = (cx + r * math.cos(am), cy + r * math.sin(am), zl + 0.5)
                if tree.query(q)[0] < 0.9:
                    r_in = r + 0.2
                    break
            if r_in is None or SCAF_R - 0.9 - r_in < 0.4:
                continue
            p_out = (cx + (SCAF_R - 0.9) * math.cos(am), cy + (SCAF_R - 0.9) * math.sin(am), zl + 0.1)
            p_in = (cx + r_in * math.cos(am), cy + r_in * math.sin(am), zl + 0.1)
            sb.add(G.beam(p_out, p_in, 0.4, 0.06), t_on=t_on, t_off=t_off, mat=1)
        a = angs[1 + (li % 3) * 3] + 0.12                        # a ladder to the next lift
        sb.add(G.beam((cx + (SCAF_R + 0.5) * math.cos(a), cy + (SCAF_R + 0.5) * math.sin(a), zl - 2.2),
                      (cx + (SCAF_R + 0.5) * math.cos(a + 0.06), cy + (SCAF_R + 0.5) * math.sin(a + 0.06), zl + 0.1), 0.1),
               t_on=t_on, t_off=t_off, mat=0)
    # diagonal braces in the outer bays
    for i in range(n):
        a, b = angs[i], angs[i + 1]
        for li in range(0, len(lifts), 2):
            zl = lifts[li]
            t_on = (zl - PT) - 2.2
            t_off = TC_SCAF_DOWN[1] - (TC_SCAF_DOWN[1] - TC_SCAF_DOWN[0]) * li / len(lifts)
            sb.add(G.beam((cx + SCAF_R * math.cos(a), cy + SCAF_R * math.sin(a), zl - 2.2),
                          (cx + SCAF_R * math.cos(b), cy + SCAF_R * math.sin(b), zl), 0.1), t_on=t_on, t_off=t_off, mat=0)
    sb.finalize()
    return sb


def statue_radius_table(d, dz=0.5, n_ang=48):
    """Largest distance of the bronze from the axis, per height band (world z)
    and bearing: where trestles and people can stand round the figure."""
    Vw = statue_world_vertices(d)
    zi = np.floor((Vw[:, 2] - PT) / dz).astype(int)
    ai = (np.floor(np.mod(np.arctan2(Vw[:, 1], Vw[:, 0]), 2 * math.pi) / (2 * math.pi) * n_ang)).astype(int) % n_ang
    nz = zi.max() + 1
    tab = np.zeros((nz, n_ang))
    np.maximum.at(tab, (zi, ai), np.hypot(Vw[:, 0], Vw[:, 1]))
    return tab, dz, n_ang


def statue_radius(S, z0, z1, ang):
    tab, dz, n = S.rtab
    i0 = max(int((z0 - PT) / dz), 0)
    i1 = min(int((z1 - PT) / dz) + 1, len(tab))
    if i1 <= i0:
        return 0.0
    a = int(np.floor(np.mod(ang, 2 * math.pi) / (2 * math.pi) * n)) % n
    return float(tab[i0:i1, [(a - 1) % n, a, (a + 1) % n]].max())


def trestle_batch(S, M, z_work):
    """A ring of trestles on the mound top round the figure: a planked walk
    ~3 m up, 1 m clear of the bronze, with posts and ladders."""
    tb = G.HexBatch('trestles')
    n = 28
    h = min(z_work - M, 3.2)
    if h < 1.2:
        tb.finalize()
        return tb
    top_r = cone_r(M) - 1.2
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r = statue_radius(S, M + 0.3, M + h + 1.8, a) + 1.1
        r = min(max(r, 2.5), top_r)
        pts.append((r * math.cos(a), r * math.sin(a)))
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        L_ = math.hypot(x1 - x0, y1 - y0)
        if L_ > 4.0:
            continue
        rot = math.atan2(y1 - y0, x1 - x0)
        tb.add(G.box((x0 + x1) / 2, (y0 + y1) / 2, M + h, L_ + 0.1, 1.1, 0.08, rot), mat=1)
        if i % 2 == 0:
            for off in (-0.45, 0.45):
                nx, ny = -math.sin(rot) * off, math.cos(rot) * off
                tb.add(G.beam((x0 + nx, y0 + ny, M - 0.2), (x0 + nx, y0 + ny, M + h), 0.12), mat=0)
        if i % 7 == 3:
            r0 = math.hypot(x0, y0)
            ux, uy = x0 / r0, y0 / r0
            tb.add(G.beam((x0 + ux * 2.2, y0 + uy * 2.2, M), (x0 + ux * 0.6, y0 + uy * 0.6, M + h + 0.1), 0.09), mat=0)
    tb.finalize()
    return tb


def set_scaffold(S, tc, L):
    sb = S.scaf_batch
    if tc < TC_STATUE[1]:
        sel = (sb.t_on <= L) & (L > M_MAX - PT + M_GAP - 0.5)
    else:
        sel = tc < sb.t_off
    SC.set_dynamic_mesh(S.scaf_obj, 'HeadScaffold', sb, sel, [S.m_wood, S.m_plank])


# ================================================================== props
def mat_clay():
    """Furnace clay: fired ochre, blackened with soot towards the mouth."""
    m, nb, out = SC.new_material('FurnaceClay')
    oz = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[2]
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    n = nb.noise(pos, 2.0, 3.0, 0.6).outputs['Fac']
    col = nb.mix(n, (0.36, 0.22, 0.13, 1), (0.50, 0.33, 0.20, 1))
    soot = nb.smooth(0.9, 1.9, nb.math('ADD', oz, nb.math('MULTIPLY', n, 0.5)))
    col = nb.mix(soot, col, (0.04, 0.035, 0.03, 1))
    b = SC.principled(nb, col, rough=0.95, spec=0.2)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_glow(name, key, col=(1.0, 0.42, 0.08), strength=30.0):
    m, nb, out = SC.new_material(name)
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    tw = nb.value(0.0, key + '_t')
    n = nb.noise(pos, 3.0, 3.0, 0.6, w=tw, dims='4D').outputs['Fac']
    em = nb.new('ShaderNodeEmission')
    nb.feed(em.inputs['Color'], nb.mix(n, col + (1,), (1.0, 0.75, 0.3, 1)))
    k = nb.value(0.0, key)
    nb.feed(em.inputs['Strength'], nb.math('MULTIPLY', k, nb.math('ADD', strength * 0.5, nb.math('MULTIPLY', n, strength))))
    nb.feed(out.inputs['Surface'], em.outputs[0])
    return m


FURNACES = 2


def build_foundry(S):
    """Open-air foundry for the mound top: two shaft furnaces (clay, glowing
    mouths, a light each), bag bellows, a charcoal heap, a stack of plates,
    a gin wheel with a plate on its rope.  Placed per frame on the current top."""
    coll = bpy.context.scene.collection
    S.m_clay = mat_clay()
    S.m_furnace_glow = mat_glow('FurnaceGlow', 'furnace_k')
    S.m_charcoal = SC.mat_simple('Charcoal', (0.025, 0.024, 0.023), 0.9)
    S.m_leather = SC.mat_simple('Leather', (0.22, 0.13, 0.07), 0.7)
    S.m_bronze_sheet = SC.mat_simple('BronzeSheet', (0.72, 0.46, 0.22), 0.3, 1.0)
    S.furnaces = []
    for i in range(FURNACES):
        body = SC.prism(f'Furnace{i}', 0.85, 0.0, 1.9, 14, 0.55, (0, 0), [S.m_clay])
        fo = SC.link(bpy.data.objects.new(f'Furnace{i}', body), coll)
        mouth = SC.prism(f'FurnaceMouth{i}', 0.44, 1.86, 1.93, 12, 0.42, (0, 0), [S.m_furnace_glow])
        mo = SC.link(bpy.data.objects.new(f'FurnaceMouth{i}', mouth), coll)
        tap = SC.prism(f'FurnaceTap{i}', 0.16, 0.25, 0.45, 8, 0.16, (0.84, 0), [S.m_furnace_glow])
        to = SC.link(bpy.data.objects.new(f'FurnaceTap{i}', tap), coll)
        ld = bpy.data.lights.new(f'FurnaceLight{i}', 'POINT')
        ld.color = (1.0, 0.45, 0.14)
        ld.shadow_soft_size = 0.35
        lo = SC.link(bpy.data.objects.new(f'FurnaceLight{i}', ld), coll)
        bel = []
        for j in range(2):                                          # bag bellows: a leather bag, a board on top
            bb = G.HexBatch(f'bellows{i}{j}')
            bb.add(G.box(0, 0, 0.0, 0.9, 0.62, 1.0), mat=0)
            bb.add(G.box(0, 0, 1.0, 0.95, 0.66, 0.06), mat=1)
            bb.add(G.beam([0.45, 0, 0.3], [1.2, 0, 0.2], 0.12), mat=2)  # nozzle to the tuyere
            bb.finalize()
            o = SC.link(bpy.data.objects.new(f'Bellows{i}{j}', SC.hex_mesh(f'Bellows{i}{j}', bb, np.ones(3, bool),
                                                                             [S.m_leather, S.m_wood, S.m_clay])), coll)
            bel.append(o)
        for o in (fo, mo, to):
            o.pass_index = SC.PASS['props']
        S.furnaces.append(dict(body=fo, mouth=mo, tap=to, light=lo, bellows=bel))
    # charcoal heap, plate stack with its rack, a few ingots
    cb = G.HexBatch('foundry_stock')
    rng = np.random.default_rng(71)
    for k in range(9):
        cb.add(G.box(rng.uniform(-0.1, 0.1), rng.uniform(-0.08, 0.08), 0.03 * k, 1.5, 1.2, 0.028,
                     rng.uniform(-0.06, 0.06)), mat=1)
    for sgn in (-1, 1):
        cb.add(G.beam([sgn * 0.9, -0.8, 0.0], [sgn * 0.9, -0.8, 1.4], 0.12), mat=2)
    cb.add(G.beam([-0.9, -0.8, 1.35], [0.9, -0.8, 1.35], 0.1), mat=2)
    for k in range(4):                                              # sheets leaning on the rack
        cb.add(G.box(-0.5 + 0.33 * k, -0.55, 0.0, 0.3, 0.03, 1.3, 0.0), mat=1)
    cb.finalize()
    S.stock = SC.link(bpy.data.objects.new('FoundryStock', SC.hex_mesh('FoundryStock', cb, np.ones(len(cb.t_on), bool),
                                                                        [S.m_charcoal, S.m_bronze_sheet, S.m_wood])), coll)
    S.stock.pass_index = SC.PASS['props']
    V, F = life.lathe([(0.0, 0.0), (1.4, 0.0), (1.0, 0.35), (0.45, 0.62), (0.0, 0.75)], 12)
    S.charcoal = SC.link(bpy.data.objects.new('CharcoalHeap', SC.mesh_from_arrays('CharcoalHeap', V, F, mats=[S.m_charcoal],
                                                                                smooth=True)), coll)
    S.charcoal.pass_index = SC.PASS['props']
    # gin wheel: a jib out of the scaffold top, a rope, a plate on the rope
    gb = G.HexBatch('gin')
    gb.add(G.box(0, 0, -0.62, 1.45, 0.03, 1.2), mat=1)
    gb.finalize()
    S.gin_plate = SC.link(bpy.data.objects.new('GinPlate', SC.hex_mesh('GinPlate', gb, np.ones(1, bool),
                                                                        [S.m_charcoal, S.m_bronze_sheet])), coll)
    S.gin_rope = SC.link(bpy.data.objects.new('GinRope', bpy.data.meshes.new('GinRope')), coll)
    for o in (S.gin_plate, S.gin_rope):
        o.pass_index = SC.PASS['crane']
    hide_foundry(S)


def hide_foundry(S):
    for fz in S.furnaces:
        for o in [fz['body'], fz['mouth'], fz['tap'], fz['light']] + fz['bellows']:
            o.hide_render = True
    for o in (S.stock, S.charcoal, S.gin_plate, S.gin_rope):
        o.hide_render = True


def pose_foundry(S, spots, M, t, glow=1.0, pump=True, stock=None, charcoal=None, light=None):
    """spots: [(x, y, heading)] of the furnaces on the mound top at height M."""
    hide_foundry(S)
    S.m_furnace_glow.node_tree.nodes['furnace_k'].outputs[0].default_value = glow
    S.m_furnace_glow.node_tree.nodes['furnace_k_t'].outputs[0].default_value = t * 1.5
    for i, (x, y, hd) in enumerate(spots[:FURNACES]):
        fz = S.furnaces[i]
        Mw = Matrix.Translation((x, y, M - 0.1)) @ Matrix.Rotation(hd, 4, 'Z')
        for o in (fz['body'], fz['mouth'], fz['tap']):
            o.matrix_world = Mw
            o.hide_render = False
        breath = 0.85 + 0.15 * math.sin(t * 2 * math.pi * 0.8 + i)
        lo = fz['light']
        lo.location = (x, y, M + 2.4)
        lk = glow if light is None else light
        lo.data.energy = 900.0 * lk * breath
        lo.hide_render = lk <= 0.01
        for j, o in enumerate(fz['bellows']):
            ph = t * 2 * math.pi * 0.8 + j * math.pi + i
            sz = 0.55 + 0.35 * (0.5 + 0.5 * math.cos(ph)) if pump else 0.8
            o.matrix_world = (Mw @ Matrix.Translation((-2.2, (j - 0.5) * 0.9, 0.0)) @ Matrix.Diagonal((1.0, 1.0, sz * 0.6, 1.0)))
            o.hide_render = False
    if stock is not None:
        x, y, hd = stock
        S.stock.matrix_world = Matrix.Translation((x, y, M - 0.05)) @ Matrix.Rotation(hd, 4, 'Z')
        S.stock.hide_render = False
    if charcoal is not None:
        x, y = charcoal
        S.charcoal.location = (x, y, M - 0.15)
        S.charcoal.hide_render = False


def build_altar(S):
    """Marble altar before the pedestal: a sacrifice to Helios burns on it."""
    coll = bpy.context.scene.collection
    ab = G.HexBatch('altar')
    x, y = ALTAR
    ab.add(G.box(x, y, GROUND, 3.0, 2.2, 0.3), mat=0)
    ab.add(G.box(x, y, GROUND + 0.3, 2.5, 1.7, 0.95), mat=0)
    ab.add(G.box(x, y, GROUND + 1.25, 2.8, 2.0, 0.22), mat=0)
    for sgn in (-1, 1):                                            # the horns of the altar
        ab.add(G.box(x, y + sgn * 0.85, GROUND + 1.47, 2.8, 0.3, 0.3), mat=0)
    ab.finalize()
    S.altar = SC.link(bpy.data.objects.new('Altar', SC.hex_mesh('Altar', ab, np.ones(len(ab.t_on), bool), [S.m_stone])), coll)
    S.altar.pass_index = SC.PASS['masonry']
    S.m_altar_fire = mat_glow('AltarFire', 'altar_k', col=(1.0, 0.36, 0.06), strength=24.0)
    S.altar_flames = []
    for i in range(6):
        a = i * 2 * math.pi / 6
        r = 0.0 if i == 0 else 0.4
        me = SC.prism(f'AltarFlame{i}', 0.34 if i == 0 else 0.22, 0.0, 1.5 if i == 0 else 0.95, 8, 0.02, (0, 0), [S.m_altar_fire])
        o = SC.link(bpy.data.objects.new(f'AltarFlame{i}', me), coll)
        o.location = (x + r * math.cos(a), y + r * math.sin(a), GROUND + 1.47)
        o.visible_shadow = False
        o.pass_index = SC.PASS['fire']
        S.altar_flames.append(o)
    ld = bpy.data.lights.new('AltarLight', 'POINT')
    ld.color = (1.0, 0.5, 0.18)
    ld.shadow_soft_size = 0.4
    S.altar_light = SC.link(bpy.data.objects.new('AltarLight', ld), coll)
    S.altar_light.location = (x, y, GROUND + 2.6)
    pose_altar(S, 0.0, 0.0)


ALTAR = (-15.0, 0.0)


def pose_altar(S, k, t):
    S.altar.hide_render = k < 0.0
    S.m_altar_fire.node_tree.nodes['altar_k'].outputs[0].default_value = max(k, 0.0)
    S.m_altar_fire.node_tree.nodes['altar_k_t'].outputs[0].default_value = t * 2.0
    for i, o in enumerate(S.altar_flames):
        o.hide_render = k <= 0.0
        sz = 0.8 + 0.35 * SC.smooth_rand(i + 70, t, 7.0)
        o.scale = (sz, sz, sz * (0.8 + 0.5 * SC.smooth_rand(i + 90, t, 9.0)))
        o.rotation_euler = (0.2 * (SC.smooth_rand(i + 20, t, 5.0) - 0.5) + 0.15, 0.2 * (SC.smooth_rand(i + 30, t, 5.0) - 0.5), 0)
    S.altar_light.data.energy = 1400.0 * max(k, 0.0) * (0.85 + 0.15 * SC.smooth_rand(5, t, 11.0))
    S.altar_light.hide_render = k <= 0.0


def build_cargo(S):
    """What the harbour brings for the Colossus, on the mole (S1): copper and
    tin ingots, bundles of iron bars, and the broken-up siege engines of
    Demetrios (Helepolis timbers, its great wheels and iron armour plates)."""
    coll = bpy.context.scene.collection
    m_copper = SC.mat_simple('Copper', (0.46, 0.20, 0.09), 0.45, 0.85)
    m_tin = SC.mat_simple('Tin', (0.52, 0.53, 0.54), 0.4, 0.8)
    cb = G.HexBatch('cargo')
    rng = np.random.default_rng(55)
    for (x, y) in CARGO['copper']:                                   # oxhide ingots, crosswise
        for k in range(11):
            for j in range(2):
                rot = (k % 2) * math.pi / 2
                ox, oy = (0.0, (j - 0.5) * 0.44) if k % 2 == 0 else ((j - 0.5) * 0.44, 0.0)
                cb.add(G.box(x + ox, y + oy, GROUND + 0.065 * k, 0.62, 0.42, 0.06, rot + rng.uniform(-0.05, 0.05)),
                       mat=0, tone=rng.random())
    for (x, y) in CARGO['tin']:
        for k in range(8):
            for j in range(3):
                cb.add(G.box(x + (j - 1) * 0.3, y, GROUND + 0.09 * k, 0.26, 0.55, 0.085, (k % 2) * 0.1), mat=1)
    for (x, y, hd) in CARGO['iron']:                                  # bundles of bars on two sleepers
        c, s_ = math.cos(hd), math.sin(hd)
        for sl in (-1.2, 1.2):
            cb.add(G.box(x + c * sl, y + s_ * sl, GROUND, 0.2, 1.1, 0.12, hd + math.pi / 2), mat=3)
        for r in range(4):
            for q in range(6):
                off = (q - 2.5) * 0.09
                z = GROUND + 0.12 + 0.085 * r
                cb.add(G.beam([x - c * 2.0 - s_ * off, y - s_ * 2.0 + c * off, z], [x + c * 2.0 - s_ * off, y + s_ * 2.0 + c * off, z],
                              0.075), mat=2)
    for (x0, y0, hd, n_layers) in CARGO['timbers']:                    # squared siege timbers, stacked with spacers
        c, s_ = math.cos(hd), math.sin(hd)
        for layer in range(n_layers):
            z = GROUND + 0.1 + layer * 0.68
            for q in range(5):
                off = (q - 2) * 0.72
                ln = 11.0 - 1.4 * (q % 2) - rng.uniform(0, 1.5)
                cb.add(G.beam([x0 - c * ln / 2 - s_ * off, y0 - s_ * ln / 2 + c * off, z + 0.3],
                              [x0 + c * ln / 2 - s_ * off, y0 + s_ * ln / 2 + c * off, z + 0.3], 0.58), mat=3, tone=rng.random())
            for sp in (-3.5, 0.0, 3.5):
                cb.add(G.box(x0 + c * sp, y0 + s_ * sp, z - 0.1, 0.15, 3.9, 0.1, hd + math.pi / 2), mat=3)
    for (x, y, z0, tilt, hd) in CARGO['wheels']:                       # the Helepolis wheels (4 m, iron tyres)
        n = 18
        R = 2.0
        M_ = Matrix.Translation((x, y, z0)) @ Matrix.Rotation(hd, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X')
        for k in range(n):
            a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            p0 = M_ @ Vector((R * math.cos(a0), 0.0, R * math.sin(a0)))
            p1 = M_ @ Vector((R * math.cos(a1), 0.0, R * math.sin(a1)))
            cb.add(G.beam(p0, p1, 0.22, 0.62, up=tuple(M_.to_3x3() @ Vector((0, 1, 0)))), mat=2)          # iron tyre
            q0 = M_ @ Vector((R * 0.9 * math.cos(a0), 0.0, R * 0.9 * math.sin(a0)))
            q1 = M_ @ Vector((R * 0.9 * math.cos(a1), 0.0, R * 0.9 * math.sin(a1)))
            cb.add(G.beam(q0, q1, 0.3, 0.6, up=tuple(M_.to_3x3() @ Vector((0, 1, 0)))), mat=3)             # felloe
        for k in range(6):                                                                                   # planked disc
            a = math.pi * k / 6
            p0 = M_ @ Vector((-R * 0.85 * math.cos(a), 0.0, -R * 0.85 * math.sin(a)))
            p1 = M_ @ Vector((R * 0.85 * math.cos(a), 0.0, R * 0.85 * math.sin(a)))
            cb.add(G.beam(p0, p1, 0.5, 0.25, up=tuple(M_.to_3x3() @ Vector((0, 1, 0)))), mat=3)
        cb.add(G.beam(M_ @ Vector((0, -0.5, 0)), M_ @ Vector((0, 0.5, 0)), 0.7), mat=2)                    # hub
    for (x, y) in CARGO['plates']:                                     # iron armour plates of the siege tower
        for k in range(10):
            cb.add(G.box(x + rng.uniform(-0.08, 0.08), y + rng.uniform(-0.08, 0.08), GROUND + 0.035 * k, 1.8, 1.1, 0.03,
                         rng.uniform(-0.08, 0.08)), mat=2, tone=rng.random())
    cb.finalize()
    S.cargo = SC.link(bpy.data.objects.new('Cargo', SC.hex_mesh('Cargo', cb, np.ones(len(cb.t_on), bool),
                                                              [m_copper, m_tin, S.m_iron, S.m_logs])), coll)
    S.cargo.pass_index = SC.PASS['props']
    S.cargo.hide_render = True
    # the smithy on the mole: a hearth under a tiled lean-to, an anvil
    sb = G.HexBatch('smithy')
    x, y = SMITHY
    for (dx, dy, h) in ((-2.4, -1.8, 2.6), (2.4, -1.8, 2.6), (-2.4, 1.8, 3.2), (2.4, 1.8, 3.2)):
        sb.add(G.beam([x + dx, y + dy, GROUND], [x + dx, y + dy, GROUND + h], 0.18), mat=0)
    sb.add(G.box(x, y, GROUND + 2.9, 5.6, 4.4, 0.14, 0.0), mat=1)
    sb.add(G.box(x + 0.4, y + 0.9, GROUND, 1.6, 1.2, 0.85), mat=2)                                   # hearth
    sb.add(G.box(x - 1.2, y - 0.4, GROUND, 0.35, 0.35, 0.55), mat=0)                                 # anvil block
    sb.add(G.box(x - 1.2, y - 0.4, GROUND + 0.55, 0.6, 0.22, 0.2), mat=3)                            # anvil
    sb.finalize()
    S.smithy = SC.link(bpy.data.objects.new('Smithy', SC.hex_mesh('Smithy', sb, np.ones(len(sb.t_on), bool),
                                                                [S.m_wood, S.m_roof, S.m_quay, S.m_iron])), coll)
    S.smithy.pass_index = SC.PASS['props']
    S.smithy_glow = SC.link(bpy.data.objects.new('SmithyGlow', SC.prism('SmithyGlow', 0.4, GROUND + 0.85, GROUND + 0.9, 8, 0.35,
                                                                         (x + 0.4, y + 0.9), [S.m_furnace_glow])), coll)
    ld = bpy.data.lights.new('SmithyLight', 'POINT')
    ld.color = (1.0, 0.45, 0.14)
    S.smithy_light = SC.link(bpy.data.objects.new('SmithyLight', ld), coll)
    S.smithy_light.location = (x + 0.4, y + 0.9, GROUND + 1.6)
    for o in (S.smithy, S.smithy_glow, S.smithy_light):
        o.hide_render = True


CARGO = dict(
    copper=[(4.0, -143.5), (4.2, -146.8), (1.2, -145.0), (5.6, -131.5)],
    tin=[(4.4, -133.4)],
    iron=[(8.2, -126.0, math.pi / 2), (5.4, -125.2, math.pi / 2), (2.6, -127.0, math.pi / 2 + 0.1)],
    timbers=[(-6.5, -146.0, math.pi / 2, 3), (-7.5, -131.0, math.pi / 2 + 0.03, 2)],
    wheels=[(-10.6, -139.0, 0.25, -0.2, math.pi / 2), (-10.9, -124.5, 0.2, -0.25, math.pi / 2 + 0.2),
            (-3.0, -121.5, 0.32, math.pi / 2, 0.3)],
    plates=[(-2.0, -154.0), (0.8, -151.5)])
SMITHY = (-7.0, -108.0)


def show_cargo(S, on, glow=0.0, t=0.0):
    for o in (S.cargo, S.smithy, S.smithy_glow):
        o.hide_render = not on
    S.smithy_light.hide_render = not on
    S.smithy_light.data.energy = 300.0 * (0.85 + 0.15 * SC.smooth_rand(3, t, 6.0))


def build_site_stock(S):
    """Material on the statue platform: marble for the pedestal (used up as it
    rises), charcoal and plates by the ramp's foot, an earth heap from the carts."""
    coll = bpy.context.scene.collection
    sb = G.HexBatch('site_stock')
    rng = np.random.default_rng(66)
    for (x, y, hd) in ((26.0, -30.0, 0.8), (-30.0, 24.0, -0.7), (30.0, 26.0, 0.7), (-26.0, -32.0, -0.8)):
        c, s_ = math.cos(hd), math.sin(hd)
        k = 0
        for layer in range(3):
            for i in range(4 - layer):
                for j in range(2):
                    px, py = (i - 1.5 + layer * 0.5) * 2.0, (j - 0.5) * 1.3
                    t_off = TC_PED[0] + (TC_PED[1] - TC_PED[0]) * (1.0 - 0.07 * k) * 0.95
                    sb.add(G.box(x + c * px - s_ * py, y + s_ * px + c * py, GROUND + layer * 0.8, 1.9, 1.2, 0.78, hd),
                           t_off=t_off, mat=0, tone=rng.random())
                    k += 1
    sb.finalize()
    S.site_stock = sb
    S.site_stock_obj = SC.link(bpy.data.objects.new('SiteStock', bpy.data.meshes.new('SiteStock')), coll)
    S.site_stock_obj.pass_index = SC.PASS['props']
    S.site_stock_tc = None


def pose_site_stock(S, tc):
    key = round(tc, 3)
    if key != S.site_stock_tc:
        S.site_stock_tc = key
        SC.set_dynamic_mesh(S.site_stock_obj, 'SiteStock', S.site_stock, S.site_stock.select(tc), [S.m_stone])


# ================================================================== build / pose
class State:
    pass


def build(res=(1280, 720)):
    SC.P = SC.PALETTES['bright']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    S = State()
    S.look = 'bright'
    coll = sc.collection
    P = SC.P
    S.m_stone = SC.mat_masonry('Marble', (0.86, 0.83, 0.77), (0.60, 0.57, 0.51), var=0.05, width=0.035, grime=0.08)
    S.m_quay = SC.mat_masonry('QuayStone', *P['stone'])
    S.m_paving = SC.mat_masonry('Paving', *P['paving'], width=0.035)
    S.m_wood = SC.mat_wood('Timber', P['wood'])
    S.m_plank = SC.mat_wood('Planks', P['plank'], width=0.04)
    S.m_logs = mat_logs()
    S.m_rope = SC.mat_simple('Rope', P['rope'], 0.9)
    S.m_cloth = SC.mat_simple('Canvas', P['cloth'], 0.9)
    S.m_cloth2 = SC.mat_simple('CanvasDark', P['cloth2'], 0.9)
    S.m_hull = SC.mat_wood('Hull', P['hull'], textured=False)
    S.m_sail = SC.mat_simple('Sail', P['sail'], 0.9)
    S.m_worker = SC.mat_objcolor('Worker')
    S.m_city = mat_houses()
    S.m_roof = mat_roof()
    S.m_fire = SC.mat_fire()
    S.m_torch = SC.mat_torch()
    S.world = SC.build_world()
    S.flat_world = SC.build_flat_world()
    S.ground = build_ground(coll)
    S.sea, S.ocean = SC.build_sea(coll, height_fn=rhodes_height, extent=(-700.0, 800.0, -600.0, 500.0))
    S.ocean.wave_scale = 0.75                  # a fresh breeze, not a gale: the harbour must look safe
    S.ocean.wind_velocity = 10.0
    S.ocean.foam_coverage = 0.0
    S.cloud_shadow, S.m_cshadow = SC.build_cloud_shadows(coll)
    S.quays = build_quay_walls(coll, S.m_quay)
    S.breakwater = build_breakwater(coll)
    S.paving = build_paving(coll, S.m_paving)
    S.city = build_city(coll, S.m_city, S.m_roof, S.m_stone)
    S.trees = build_trees(coll)
    S.ped_batch = build_pedestal()
    S.ped_obj = SC.link(bpy.data.objects.new('Pedestal', bpy.data.meshes.new('Pedestal')), coll)
    S.ped_obj.pass_index = SC.PASS['masonry']
    S.ped_mats = [S.m_stone, S.m_quay]
    build_statue(S, coll)
    build_mound(S, coll)
    S.scaf_batch = build_head_scaffold(S.hl)
    S.rtab = statue_radius_table(S.hl)
    S.trestle_obj = SC.link(bpy.data.objects.new('Trestles', bpy.data.meshes.new('Trestles')), coll)
    S.trestle_obj.pass_index = SC.PASS['timber']
    S.trestle_key = None
    S.scaf_obj = SC.link(bpy.data.objects.new('HeadScaffold', bpy.data.meshes.new('HeadScaffold')), coll)
    S.scaf_obj.pass_index = SC.PASS['timber']
    build_foundry(S)
    build_altar(S)
    build_cargo(S)
    build_site_stock(S)
    # sun, moon
    ld = bpy.data.lights.new('Sun', 'SUN')
    ld.angle = math.radians(1.0)
    S.sun = SC.link(bpy.data.objects.new('Sun', ld), coll)
    ld = bpy.data.lights.new('Moon', 'SUN')
    ld.angle = math.radians(1.5)
    ld.color = (0.55, 0.68, 1.0)
    S.moon = SC.link(bpy.data.objects.new('Moon', ld), coll)
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 35.0
    cd.sensor_width = 36
    cd.clip_start = 0.5
    cd.clip_end = 40000
    S.cam = SC.link(bpy.data.objects.new('Cam', cd), coll)
    sc.camera = S.cam
    S.ped_tc = None
    return S


def pose_site(S, tc):
    """Construction state at construction time tc: pedestal, statue, mound, scaffold."""
    key = round(tc, 4)
    if key != S.ped_tc:
        S.ped_tc = key
        SC.set_dynamic_mesh(S.ped_obj, 'Pedestal', S.ped_batch, S.ped_batch.select(tc), S.ped_mats)
    pose_site_stock(S, tc)
    L = set_statue(S, tc)
    M = set_mound(S, tc)
    set_scaffold(S, tc, L)
    working = TC_STATUE[0] + 0.1 < tc < TC_STATUE[1] and M > GROUND + 0.5 and 1.5 < PT + L - M < M_GAP + 0.8
    key = (round(M, 2), round(L, 1)) if working else None
    if key != S.trestle_key:
        S.trestle_key = key
        tb = trestle_batch(S, M, PT + L) if working else G.HexBatch('trestles')
        if not working:
            tb.finalize()
        SC.set_dynamic_mesh(S.trestle_obj, 'Trestles', tb, np.ones(len(tb.t_on), bool), [S.m_wood, S.m_plank])
    return dict(level=L, mound=M, working=working)


def pose(S, t, **kw):
    """Environment (sky, sun, sea) + site for film time t; kw as scene.pose()."""
    hour = kw.get('hour', 9.0)
    zen, hor = SC.pose_environment(S, t, **dict(kw, hour=hour))
    site = pose_site(S, kw.get('tc', 0.0))
    if 'cam' in kw:
        loc, tgt, lens = kw['cam']
        S.cam.data.lens = lens
        SC.look_at(S.cam, loc, tgt)
    el, _ = TL.sun_angles(hour)
    return dict(t=t, hour=hour, sun_el=math.degrees(el), day=TL.smoothstep(math.radians(-7), math.radians(5), el),
                height=site['level'], fire=0.0, horizon=hor, zenith=zen, **site)
