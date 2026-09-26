"""Frombork (Frauenburg) on the Vistula Lagoon, c. 1512-1543: the cathedral
hill of Warmia and the brick observation tower of Nicolaus Copernicus.

The world of wunderfilm_10_copernicus (film_copernicus20.py).  It borrows the
sky, sun, sea, cloud shadows and materials of scene.py and rhodes.py and adds:

  ground     the cathedral hill (a plateau 22 m above the lagoon, steep to the
             north), the town terrace on the shore, rolling Warmian farmland,
             the Vistula Spit as a dark line on the horizon
  brick      Baltic brick Gothic: a world-space Gothic bond (header, stretcher)
             with dark glazed headers, whitewashed blind panels on the gables
  cathedral  the hall church (1329-1388) with its west gable and four turrets
  walls      the fortified close with towers, the canons' houses
  tower      the wonder: a square brick tower at the south-west corner of the
             close, built in lifts with its scaffold and treadwheel crane, then
             crenellations, the roof beams and a flat platform with a parapet
  town       Frombork below the hill: brick and timber-framed houses, a harbour

Coordinates: metres, +x east, +y north, lagoon level z = 0.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix

import geometry as G
import rhodes as RH
import scene as SC

LATITUDE_DEG = 54.36
PLATEAU = 22.0                       # the courtyard of the cathedral hill
HILL_C = (0.0, 5.0)
HILL_HALF = (162.0, 113.0)
CLOSE = [(-125.0, -75.0), (128.0, -75.0), (136.0, 82.0), (-131.0, 86.0)]    # the walls of the close
CATH = dict(x0=-38.0, x1=54.0, y0=-6.0, y1=18.0, wall=18.5, roof=22.0)
TOWER_C = (-125.0, -75.0)            # the new tower at the south-west corner of the close
TOWER_A = 4.6                        # half width (outer)
TOWER_T = 1.35                       # wall thickness
TOWER_H = 24.0                       # courtyard to the platform
LIFT = 0.6                           # the walls rise in lifts of 0.6 m
TOWER_TOP = PLATEAU + TOWER_H        # 46 m
PARAPET = 1.9


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


# ================================================================== ground
def shore_y(X):
    return 205.0 + 35.0 * np.sin(np.asarray(X, float) / 420.0 + 0.6) + 12.0 * G.fbm(np.asarray(X, float) / 150.0, 0.2, 3, seed=11)


def hill_sd(X, Y):
    qx = np.abs(X - HILL_C[0]) - HILL_HALF[0]
    qy = np.abs(Y - HILL_C[1]) - HILL_HALF[1]
    return (np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - 25.0
            + 9.0 * G.fbm(X / 90, Y / 90, 3, seed=5))


def height(X, Y):
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    farm = 13.0 + 9.0 * G.fbm(X / 700.0, Y / 700.0, 4, seed=21) + 0.012 * np.maximum(-Y - 150.0, 0.0)
    d = hill_sd(X, Y)
    north = np.clip((Y - HILL_C[1]) / 60.0, 0, 1)
    w = 55.0 - 30.0 * north
    hill = np.where(d <= 0, PLATEAU + 0.35 * G.fbm(X / 40, Y / 40, 2, seed=6),
                    PLATEAU - (PLATEAU - 4.0) * np.clip(d / w, 0, 1) ** 1.4)
    h = np.maximum(farm, hill)
    t = shore_y(X) - Y                                            # > 0 on land (south of the shore)
    terrace = 0.8 + 0.06 * t + 0.004 * np.maximum(t - 60.0, 0.0) ** 2
    return np.where(t > 0, np.minimum(h, terrace), np.maximum(-4.0, -0.5 + 0.03 * t))


def ground_z(x, y):
    return float(height(np.array([x]), np.array([y]))[0])


def mat_ground():
    """Grass on the hill and the terrace, fields in strips on the farmland, bare
    trodden earth in the close and round the kilns, reeds at the shore."""
    m, nb, out = SC.new_material('FromborkGround')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    nz = nb.sep(geo.outputs['Normal'])[2]
    x_, y_, z = nb.sep(pos)
    n1 = nb.noise(pos, 0.05, 4.0, 0.6).outputs['Fac']
    n2 = nb.noise(pos, 0.6, 3.0, 0.6).outputs['Fac']
    grass = nb.mix(n1, (0.14, 0.20, 0.06, 1), (0.30, 0.33, 0.12, 1))
    grass = nb.mix(nb.smooth(0.55, 0.75, n2), grass, (0.36, 0.34, 0.16, 1))
    # fields: long strips of stubble, green and ploughed earth south of the hill
    fx = nb.math('FRACT', nb.math('DIVIDE', nb.math('ADD', x_, nb.math('MULTIPLY', y_, 0.12)), 38.0))
    fid = nb.math('FLOOR', nb.math('DIVIDE', nb.math('ADD', x_, nb.math('MULTIPLY', y_, 0.12)), 38.0))
    wn = nb.new('ShaderNodeTexWhiteNoise', noise_dimensions='2D')
    nb.feed(wn.inputs['Vector'], nb.comb(fid, nb.math('FLOOR', nb.math('DIVIDE', y_, 160.0)), 0.0))
    fcol = nb.ramp(wn.outputs['Value'], [(0.0, (0.42, 0.33, 0.16)), (0.35, (0.55, 0.47, 0.24)), (0.6, (0.22, 0.26, 0.09)),
                                         (1.0, (0.30, 0.20, 0.12))])
    farm = nb.math('MULTIPLY', nb.smooth(-70.0, -140.0, y_), nb.smooth(0.03, 0.08, nb.math('MINIMUM', fx, nb.math('SUBTRACT', 1.0, fx))))
    col = nb.mix(nb.math('MULTIPLY', farm, 0.85), grass, fcol)
    earth = nb.mix(n2, (0.28, 0.21, 0.13, 1), (0.40, 0.31, 0.20, 1))
    close = nb.math('MULTIPLY', nb.smooth(PLATEAU - 0.8, PLATEAU - 0.2, z), nb.smooth(0.25, 0.6, nb.noise(pos, 0.08, 3.0, 0.6).outputs['Fac']))
    col = nb.mix(nb.math('MULTIPLY', close, 0.6), col, earth)
    steep = nb.smooth(0.9, 0.7, nz)
    col = nb.mix(nb.math('MULTIPLY', steep, 0.5), col, (0.25, 0.22, 0.12, 1))
    shore = nb.smooth(1.4, 0.4, z)
    col = nb.mix(nb.math('MULTIPLY', shore, 0.8), col, (0.32, 0.30, 0.14, 1))
    b = SC.principled(nb, col, rough=0.95, spec=0.25)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.4
    nb.feed(bump.inputs['Height'], nb.noise(pos, 2.2, 3.0, 0.6).outputs['Fac'])
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_ground(coll):
    xs = RH._graded(-6000.0, 6000.0, -320.0, 320.0, 1.6, growth=1.1)
    ys = RH._graded(-6000.0, 1200.0, -260.0, 260.0, 1.6, growth=1.1)
    X, Y = np.meshgrid(xs, ys)
    Z = height(X, Y)
    V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    nx = len(xs)
    idx = np.arange(len(ys) * nx).reshape(len(ys), nx)
    Q = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
    me = SC.mesh_from_arrays('FromborkGround', V, Q, mats=[mat_ground()], smooth=True)
    o = SC.link(bpy.data.objects.new('FromborkGround', me), coll)
    o.pass_index = SC.PASS['terrain']
    # the Vistula Spit: a low, wooded dune ridge across the lagoon
    xs = np.linspace(-26000, 26000, 400)
    ys = np.linspace(8600, 9800, 16)
    X, Y = np.meshgrid(xs, ys)
    c = (Y - 9200.0) / 600.0
    Z = np.maximum(0.0, 1.0 - c ** 2) * (16.0 + 10.0 * G.fbm(X / 900.0, Y / 300.0, 3, seed=31)) - 1.5
    V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    nx = len(xs)
    idx = np.arange(len(ys) * nx).reshape(len(ys), nx)
    Q = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
    spit = SC.link(bpy.data.objects.new('Spit', SC.mesh_from_arrays('Spit', V, Q, mats=[SC.mat_simple('SpitForest', (0.06, 0.08, 0.04), 0.9)],
                                                                    smooth=True)), coll)
    spit.pass_index = SC.PASS['terrain']
    return o


# ================================================================== brick
def mat_brick(name='Brick', base=((0.34, 0.11, 0.05), (0.52, 0.20, 0.09)), glazed=True, plaster_panels=False):
    """Baltic brick Gothic in world space: courses of 9.5 cm, Gothic bond (a
    header and a stretcher by turns, every course shifted), mortar joints
    that fade to their mean tone once thinner than a pixel, a dark glazed
    header now and then, soot and weather streaks."""
    m, nb, out = SC.new_material(name)
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    nrm = geo.outputs['Normal']
    x_, y_, z_ = nb.sep(pos)
    nx, ny, nz = nb.sep(nrm)
    # horizontal coordinate along the face: position . (-ny, nx, 0) (normalised)
    hl = nb.math('SQRT', nb.math('MAXIMUM', nb.math('ADD', nb.math('MULTIPLY', nx, nx), nb.math('MULTIPLY', ny, ny)), 1e-6))
    u = nb.math('DIVIDE', nb.math('ADD', nb.math('MULTIPLY', x_, nb.math('MULTIPLY', ny, -1.0)), nb.math('MULTIPLY', y_, nx)), hl)
    course = nb.math('FLOOR', nb.math('DIVIDE', z_, 0.095))
    fv = nb.math('FRACT', nb.math('DIVIDE', z_, 0.095))
    off = nb.math('MULTIPLY', nb.math('FRACT', nb.math('MULTIPLY', course, 0.5)), 0.43)
    uu = nb.math('ADD', u, off)
    cell = nb.math('FLOOR', nb.math('DIVIDE', uu, 0.43))
    fu = nb.math('MULTIPLY', nb.math('FRACT', nb.math('DIVIDE', uu, 0.43)), 0.43)
    header = nb.math('LESS_THAN', fu, 0.145)
    du = nb.math('MINIMUM', nb.math('MINIMUM', fu, nb.math('ABSOLUTE', nb.math('SUBTRACT', fu, 0.145))),
                 nb.math('SUBTRACT', 0.43, fu))
    dv = nb.math('MULTIPLY', nb.math('MINIMUM', fv, nb.math('SUBTRACT', 1.0, fv)), 0.095)
    dj = nb.math('MINIMUM', du, dv)
    fp = SC.pixel_footprint(nb)
    w_eff = nb.math('MAXIMUM', 0.006, nb.math('MULTIPLY', fp, 0.9))
    joint = nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, nb.smooth(0.0, 1.0, nb.math('DIVIDE', dj, w_eff))),
                    nb.math('DIVIDE', 0.006, w_eff))
    wn = nb.new('ShaderNodeTexWhiteNoise', noise_dimensions='3D')
    nb.feed(wn.inputs['Vector'], nb.comb(course, cell, nb.math('ADD', header, nb.math('MULTIPLY', nb.math('FLOOR', nb.math('DIVIDE', u, 40.0)), 3.0))))
    tone = wn.outputs['Value']
    col = nb.mix(tone, base[0] + (1,), base[1] + (1,))
    far = nb.smooth(0.01, 0.05, fp)
    if glazed:                                   # glazed headers in a diaper: every 7th header, stepped
        band = nb.math('LESS_THAN', nb.math('FRACT', nb.math('DIVIDE', course, 9.0)), 0.34)          # diaper bands only
        dia = nb.math('MULTIPLY', band, nb.math('LESS_THAN', nb.math('ABSOLUTE', nb.math('SUBTRACT', nb.math('FRACT', nb.math('DIVIDE', nb.math('ADD', cell, nb.math('MULTIPLY', course, 0.5)), 9.0)), 0.5)), 0.06))
        gl = nb.math('MULTIPLY', nb.math('MULTIPLY', header, dia), nb.math('SUBTRACT', 1.0, far))
        col = nb.mix(nb.math('MULTIPLY', gl, 0.7), col, (0.06, 0.05, 0.045, 1))
        col = nb.mix(nb.math('MULTIPLY', far, 0.025), col, (0.06, 0.05, 0.045, 1))
    col = nb.mix(joint, col, (0.50, 0.47, 0.42, 1))
    # weather: dark streaks down the walls, soot, green at the base; horizontal faces get dust
    streak = nb.smooth(0.55, 0.8, nb.noise(nb.comb(nb.math('MULTIPLY', x_, 1.5), nb.math('MULTIPLY', y_, 1.5), nb.math('MULTIPLY', z_, 0.12)), 1.2, 4.0, 0.6).outputs['Fac'])
    col = nb.mix(nb.math('MULTIPLY', streak, 0.35), col, (0.08, 0.05, 0.04, 1))
    up = nb.smooth(0.6, 0.9, nz)
    col = nb.mix(nb.math('MULTIPLY', up, 0.5), col, (0.40, 0.33, 0.25, 1))
    b = SC.principled(nb, col, rough=nb.math('SUBTRACT', 0.9, nb.math('MULTIPLY', header, 0.0)), spec=0.3)
    bump = nb.new('ShaderNodeBump', invert=True)
    bump.inputs['Strength'].default_value = 0.4
    bump.inputs['Distance'].default_value = 0.02
    nb.feed(bump.inputs['Height'], nb.math('ADD', joint, nb.math('MULTIPLY', nb.noise(pos, 9.0, 2.0, 0.6).outputs['Fac'], 0.25)))
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


# ================================================================== the cathedral and the close
def mat_glass():
    m, nb, out = SC.new_material('LeadGlass')
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    n = nb.noise(pos, 3.0, 2.0, 0.5).outputs['Fac']
    col = nb.mix(n, (0.02, 0.025, 0.035, 1), (0.06, 0.07, 0.08, 1))
    b = SC.principled(nb, col, rough=0.15, spec=0.6)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_cathedral(coll, m_brick, m_roof, m_plaster, m_glass, m_copper):
    c = CATH
    cb = G.HexBatch('cathedral')
    z0 = PLATEAU - 1.0
    x0, x1, y0, y1 = c['x0'], c['x1'], c['y0'], c['y1']
    wall = c['wall']
    L = x1 - x0
    # walls (hall church: the aisles as high as the nave)
    cb.add(G.box(0.5 * (x0 + x1), y0 + 0.8, z0, L, 1.6, wall + 1.0), mat=0)
    cb.add(G.box(0.5 * (x0 + x1), y1 - 0.8, z0, L, 1.6, wall + 1.0), mat=0)
    cb.add(G.box(x1 - 0.8, 0.5 * (y0 + y1), z0, 1.6, y1 - y0, wall + 1.0), mat=0)
    cb.add(G.box(x0 + 0.8, 0.5 * (y0 + y1), z0, 1.6, y1 - y0, wall + 1.0), mat=0)
    cb.add(G.box(0.5 * (x0 + x1), 0.5 * (y0 + y1), z0 + wall - 0.4, L - 2, y1 - y0 - 2, 0.4), mat=0)   # vault top
    # buttresses and tall windows between them, both sides
    bays = 9
    for k in range(bays + 1):
        x = x0 + 6.0 + (L - 12.0) * k / bays
        for sy, yw in ((-1, y0), (1, y1)):
            cb.add(G.box(x, yw + sy * 1.1, z0, 1.6, 2.2, wall - 1.5), mat=0)
            cb.add(G.box(x, yw + sy * 1.4, z0 + wall - 1.5, 1.2, 1.2, 1.4), mat=0)
            if k < bays:
                xm = x + (L - 12.0) / bays * 0.5
                cb.add(G.box(xm, yw + sy * 0.02, z0 + 4.0, 3.2, 0.12, wall - 7.5), mat=2)          # window glass
                cb.add(G.box(xm, yw + sy * 0.05, z0 + 4.0 + (wall - 7.5), 2.0, 0.12, 1.4), mat=2)  # pointed head
                for mx in (-0.55, 0.55):                                                           # mullions
                    cb.add(G.box(xm + mx, yw + sy * 0.09, z0 + 4.0, 0.16, 0.14, wall - 7.0), mat=0)
    # roof: one steep saddle roof over the hall
    eave = z0 + wall + 1.0
    ph = c['roof']
    cb.add(G.tent(0.5 * (x0 + x1), 0.5 * (y0 + y1), eave, L + 0.6, y1 - y0 + 2.4, ph), mat=1)
    # east and west gables: stepped, with whitewashed blind panels
    for xg, sgn, steps in ((x1 - 0.8, 1, 6), (x0 + 0.8, -1, 7)):
        for k in range(steps):
            zb = eave + ph * k / steps
            hw = (y1 - y0) * 0.5 * (1.0 - k / steps) + 0.5
            cb.add(G.box(xg, 0.5 * (y0 + y1), zb, 1.6, 2 * hw, ph / steps + 0.02), mat=0)
            for j in range(-2, 3):
                if abs(j) * 2.4 < hw - 1.3:
                    cb.add(G.box(xg + sgn * 0.82, 0.5 * (y0 + y1) + j * 2.4, zb + 0.45, 0.06, 1.25, ph / steps - 0.9), mat=3)
    cb.add(G.box(x0 - 0.05, 0.5 * (y0 + y1), z0 + 0.0, 0.2, 5.0, 8.0), mat=4)                            # the portal
    cb.finalize()
    me = SC.hex_mesh('Cathedral', cb, np.ones(len(cb.t_on), bool), [m_brick, m_roof, m_glass, m_plaster, SC.mat_simple('Door', (0.12, 0.07, 0.04), 0.8)])
    o = SC.link(bpy.data.objects.new('Cathedral', me), coll)
    o.pass_index = SC.PASS['masonry']
    # turrets: octagonal brick shafts with spires
    parts = []
    for (tx, ty, r, h) in ((x0 - 0.5, y0 - 0.5, 2.3, wall + 22.0), (x0 - 0.5, y1 + 0.5, 2.3, wall + 22.0),
                           (x0 - 0.3, 0.5 * (y0 + y1) - 5.0, 1.4, wall + 16.0), (x0 - 0.3, 0.5 * (y0 + y1) + 5.0, 1.4, wall + 16.0),
                           (x1 + 0.3, y0 - 0.3, 1.5, wall + 8.0), (x1 + 0.3, y1 + 0.3, 1.5, wall + 8.0)):
        me = SC.prism(f'Turret{len(parts)}', r, z0, z0 + h, 8, r, (tx, ty), [m_brick])
        to = SC.link(bpy.data.objects.new(f'Turret{len(parts)}', me), coll)
        sp = SC.prism(f'Spire{len(parts)}', r * 1.05, z0 + h, z0 + h + r * 4.2, 8, 0.05, (tx, ty), [m_copper])
        so = SC.link(bpy.data.objects.new(f'Spire{len(parts)}', sp), coll)
        for ob in (to, so):
            ob.pass_index = SC.PASS['masonry']
        parts += [to, so]
    return [o] + parts


def mat_copper_roof():
    m, nb, out = SC.new_material('CopperGreen')
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    n = nb.noise(pos, 0.8, 3.0, 0.6).outputs['Fac']
    col = nb.mix(n, (0.10, 0.28, 0.20, 1), (0.22, 0.42, 0.32, 1))
    b = SC.principled(nb, col, rough=0.6, metal=0.3, spec=0.4)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def close_wall_segments():
    pts = CLOSE + [CLOSE[0]]
    return list(zip(pts[:-1], pts[1:]))


def build_close(coll, m_brick, m_roof, m_plaster, m_houses):
    """The walls of the close with a wall walk and crenellations, towers at the
    corners (not the south-west one: that is where the new tower rises) and
    along the sides, the south gate, the canons' houses along the north wall."""
    wb = G.HexBatch('close')
    z0 = PLATEAU - 9.0
    wh = 9.5
    for (a, b) in close_wall_segments():
        a, b = np.array(a), np.array(b)
        L = float(np.linalg.norm(b - a))
        d = (b - a) / L
        n = np.array([d[1], -d[0]])                                  # outward
        rot = math.atan2(d[1], d[0])
        s0 = 0.0 if not np.allclose(a, CLOSE[0]) else TOWER_A + 0.6
        s1 = L if not np.allclose(b, CLOSE[0]) else L - TOWER_A - 0.6
        m = a + d * (s0 + s1) * 0.5
        wb.add(G.box(m[0] - n[0] * 0.9, m[1] - n[1] * 0.9, z0, s1 - s0, 1.8, wh + 9.0, rot), mat=0)
        k = 0
        s = s0 + 0.6
        while s < s1 - 0.8:                                         # merlons
            p = a + d * s
            wb.add(G.box(p[0] - n[0] * 0.3, p[1] - n[1] * 0.3, PLATEAU + wh, 1.1, 0.6, 1.3, rot), mat=0)
            s += 2.0
            k += 1
        for u in np.arange(0.18, 0.95, 0.32):                       # towers along the sides
            p = a + d * (s0 + (s1 - s0) * u)
            if np.linalg.norm(p - np.array(CLOSE[0])) < 20:
                continue
            wb.add(G.box(p[0] + n[0] * 1.5, p[1] + n[1] * 1.5, z0, 6.5, 6.5, wh + 15.0, rot), mat=0)
            wb.add(G.tent(p[0] + n[0] * 1.5, p[1] + n[1] * 1.5, PLATEAU + wh + 6.0, 7.0, 7.0, 6.5, rot), mat=1)
    for (cx, cy) in CLOSE[1:]:                                      # corner towers (round-ish: octagons)
        me = SC.prism('CornerTower', 4.2, z0, PLATEAU + wh + 8.0, 8, 4.2, (cx, cy), [m_brick])
        o = SC.link(bpy.data.objects.new('CornerTower', me), coll)
        o.pass_index = SC.PASS['masonry']
        sp = SC.prism('CornerSpire', 4.6, PLATEAU + wh + 8.0, PLATEAU + wh + 16.0, 8, 0.1, (cx, cy), [m_roof])
        so = SC.link(bpy.data.objects.new('CornerSpire', sp), coll)
        so.pass_index = SC.PASS['masonry']
    # the south gate: a gatehouse with a stepped gable over the road
    gx, gy = 20.0, -75.0
    wb.add(G.box(gx, gy, z0, 11.0, 9.0, wh + 18.0), mat=0)
    wb.add(G.tent(gx, gy, PLATEAU + wh + 9.0, 11.4, 9.4, 7.0, math.pi / 2), mat=1)
    wb.add(G.box(gx, gy - 4.52, PLATEAU - 0.5, 3.4, 0.1, 5.0), mat=4)                              # the gate
    # canons' houses along the north wall (inside), and the bishop's palace in the north-east
    for k in range(8):
        x = -110.0 + k * 16.5
        y = 70.0 + 0.03 * x
        h = 8.0 + (k % 3) * 1.2
        wb.add(G.box(x, y, PLATEAU - 1.0, 13.5, 10.0, h + 1.0), mat=0 if k % 3 else 2)
        wb.add(G.tent(x, y, PLATEAU + h, 14.0, 10.6, 5.5, 0.0), mat=1)
    wb.add(G.box(100.0, 55.0, PLATEAU - 1.0, 26.0, 16.0, 13.0), mat=0)
    wb.add(G.tent(100.0, 55.0, PLATEAU + 12.0, 26.6, 16.6, 8.0, 0.0), mat=1)
    wb.finalize()
    me = SC.hex_mesh('Close', wb, np.ones(len(wb.t_on), bool), [m_brick, m_roof, m_houses, m_plaster,
                                                             SC.mat_simple('GateWood', (0.13, 0.08, 0.05), 0.8)])
    o = SC.link(bpy.data.objects.new('Close', me), coll)
    o.pass_index = SC.PASS['masonry']
    return o


def build_town(coll, m_brick, m_roof, m_houses):
    """Frombork on the terrace below the hill: gabled houses facing the street,
    a few warehouses at the harbour, a wooden pier."""
    tb = G.HexBatch('town')
    rng = np.random.default_rng(81)
    for x in np.arange(-420.0, 460.0, 9.5):
        for row in range(3):
            ys = float(shore_y(np.array([x]))[0])
            y = ys - 38.0 - row * 26.0 + rng.uniform(-2, 2)
            if hill_sd(np.array([x]), np.array([y]))[0] < 30 or rng.random() < 0.18:
                continue
            z = ground_z(x, y)
            h = rng.uniform(6.0, 9.5)
            w = rng.uniform(7.5, 9.0)
            dpt = rng.uniform(10.0, 14.0)
            tb.add(G.box(x, y, z - 1.5, w, dpt, h + 1.5), mat=0 if rng.random() < 0.55 else 2, tone=rng.random())
            tb.add(G.tent(x, y, z + h, dpt + 0.4, w + 0.4, w * 0.9, math.pi / 2), mat=1, tone=rng.random())
    for k in range(5):                                                   # warehouses by the harbour
        x = -60.0 + k * 22.0
        y = float(shore_y(np.array([x]))[0]) - 14.0
        z = ground_z(x, y)
        tb.add(G.box(x, y, z - 1.0, 18.0, 11.0, 9.0), mat=0)
        tb.add(G.tent(x, y, z + 8.0, 18.4, 11.4, 7.0, 0.0), mat=1)
    ys0 = float(shore_y(np.array([10.0]))[0])
    for k in range(14):                                                  # the pier
        tb.add(G.box(10.0, ys0 - 2.0 + k * 3.0, -1.5, 3.0, 3.0, 2.6), mat=3)
    tb.finalize()
    me = SC.hex_mesh('Town', tb, np.ones(len(tb.t_on), bool), [m_brick, m_roof, m_houses, SC.mat_wood('PierWood', (0.30, 0.22, 0.14))])
    o = SC.link(bpy.data.objects.new('Town', me), coll)
    o.pass_index = SC.PASS['city']
    return o


def build_trees(coll):
    """Oaks, limes and beeches in groups on the slopes and the farmland, pines
    and spruces in dark stands, orchards by the town."""
    from scipy.spatial import ConvexHull
    rng = np.random.default_rng(91)
    m_leaf = SC.mat_simple('Leaves', (0.10, 0.17, 0.05), 0.85)
    m_leaf2 = SC.mat_simple('Leaves2', (0.20, 0.24, 0.08), 0.85)
    m_conifer = SC.mat_simple('Conifer', (0.04, 0.08, 0.035), 0.85)
    m_bark = SC.mat_simple('Bark', (0.16, 0.12, 0.08), 0.9)
    N = 120000
    X = rng.uniform(-2500, 2500, N)
    Y = rng.uniform(-2500, 180, N)
    Hh = height(X, Y)
    grove = 0.5 + 0.5 * G.fbm(X / 220.0, Y / 220.0, 3, seed=93)
    d = hill_sd(X, Y)
    p = np.where(d < -10, 0.0, 0.08 + 0.9 * np.clip(grove - 0.45, 0, 1) ** 1.2)
    p = np.where((d > 0) & (d < 45) & (Y > 60), 0.35, p)                  # the north slope is wooded
    fx = np.mod(X + 0.12 * Y, 38.0)
    hedge = (Y < -90) & ((fx < 2.5) | (fx > 35.5)) & (rng.random(N) < 0.5)
    p = np.where(hedge, np.maximum(p, 0.6), p)
    keep = (Hh > 1.5) & (rng.random(N) < p * 0.45) & (np.abs(X - TOWER_C[0]) + np.abs(Y - TOWER_C[1]) > 30)
    X, Y, Hh = X[keep][:12000], Y[keep][:12000], Hh[keep][:12000]
    V, F, M = [], [], []

    def add(verts, faces, mat):
        b = len(V)
        V.extend(verts)
        F.extend([[b + i for i in f] for f in faces])
        M.extend([mat] * len(faces))
    ring = np.linspace(0, 2 * math.pi, 7, endpoint=False)
    for x, y, z in zip(X, Y, Hh):
        if rng.random() < 0.3:                                               # conifer
            h, r = rng.uniform(14, 24), rng.uniform(2.2, 3.4)
            lo = [(x + r * math.cos(a), y + r * math.sin(a), z + h * 0.18) for a in ring]
            add(lo + [(x, y, z + h)], [[i, (i + 1) % 7, 7, 7] for i in range(7)], 2)
            tr = [(x + 0.3 * math.cos(a), y + 0.3 * math.sin(a), z - 0.2) for a in ring[::2]]
            tt = [(x + 0.25 * math.cos(a), y + 0.25 * math.sin(a), z + h * 0.2) for a in ring[::2]]
            add(tr + tt, [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)], 3)
            continue
        r = rng.uniform(3.5, 6.5)
        hc = rng.uniform(7, 13)
        c = np.array([x, y, z + hc])
        q = rng.normal(size=(14, 3))
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        pts = c + q * [r, r * rng.uniform(0.85, 1.1), r * 0.8]
        hull = ConvexHull(pts)
        fs = []
        for sm in hull.simplices:
            a, b, cc = sm
            if np.dot(np.cross(pts[b] - pts[a], pts[cc] - pts[a]), pts[a] - c) < 0:
                b, cc = cc, b
            fs.append([a, b, cc, cc])
        add([tuple(p_) for p_ in pts], fs, 0 if rng.random() < 0.6 else 1)
        tr = [(x + 0.35 * math.cos(a), y + 0.35 * math.sin(a), z - 0.2) for a in ring[::2]]
        tt = [(x + 0.3 * math.cos(a), y + 0.3 * math.sin(a), z + hc - r * 0.5) for a in ring[::2]]
        add(tr + tt, [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)], 3)
    me = SC.mesh_from_arrays('Trees', np.array(V), np.array(F), mats=[m_leaf, m_leaf2, m_conifer, m_bark], mat_idx=np.array(M))
    o = SC.link(bpy.data.objects.new('Trees', me), coll)
    o.pass_index = SC.PASS['terrain']
    return o


# ================================================================== the tower (the wonder)
TC_WALLS = (0.0, 8.0)                # the walls, lift by lift, courtyard to the platform
TC_TOP = (8.0, 9.0)                  # roof beams, deck, parapet and crenellations
TC_SCAF_DOWN = (9.0, 9.8)            # scaffold struck, top first
TC_INSTR = (10.0, 10.6)              # the instruments on the platform


def tower_poly(a):
    cx, cy = TOWER_C
    return np.array([[cx - a, cy - a], [cx + a, cy - a], [cx + a, cy + a], [cx - a, cy + a]], float)


def build_tower():
    """Walls in lifts of 0.6 m with a door, slit windows and two rows of
    pointed windows; then the roof beams, the plank deck and the parapet
    with its merlons.  t_on in tc."""
    tb = G.HexBatch('tower')
    n_lifts = int(round(TOWER_H / LIFT))
    cx, cy = TOWER_C
    tb.add(G.box(cx, cy, PLATEAU - 10.0, 2 * TOWER_A + 0.8, 2 * TOWER_A + 0.8, 9.4), t_on=-1.0, mat=3)   # the footing
    z = PLATEAU - 0.6
    for k in range(n_lifts + 1):
        z0, z1 = z, z + LIFT
        t0 = TC_WALLS[0] + (TC_WALLS[1] - TC_WALLS[0]) * k / (n_lifts + 1)
        t1 = TC_WALLS[0] + (TC_WALLS[1] - TC_WALLS[0]) * (k + 1) / (n_lifts + 1)
        h = z0 - PLATEAU
        openings = {}
        if h < 3.0:
            openings[1] = [(0.38, 0.62)]                     # the door, east side (to the courtyard)
        if 6.0 < h < 8.0 or 12.0 < h < 13.8:
            for s in range(4):
                openings.setdefault(s, []).append((0.45, 0.55))    # slits
        if 17.0 < h < 20.5:
            for s in range(4):
                openings.setdefault(s, []).append((0.36, 0.64))    # the upper windows
        pieces = G.ring_course(tower_poly, TOWER_A, TOWER_A, TOWER_T, z0, z1, 2.2, k, openings=openings)
        for corners, order in pieces:
            tb.add(corners, t_on=t0 + (t1 - t0) * order, mat=0)
        z = z1
    # roof beams (the platform's timber floor) and the deck
    zt = PLATEAU + TOWER_H
    t0, t1 = TC_TOP
    a_in = TOWER_A - TOWER_T
    cx, cy = TOWER_C
    for j in range(7):
        y = cy - a_in + (2 * a_in) * (j + 0.5) / 7
        tb.add(G.beam([cx - TOWER_A + 0.3, y, zt - 0.35], [cx + TOWER_A - 0.3, y, zt - 0.35], 0.3), t_on=t0 + 0.25 * j / 7, mat=1)
    for j in range(12):
        x = cx - a_in + (2 * a_in) * (j + 0.5) / 12
        tb.add(G.box(x, cy, zt - 0.2, 2 * a_in / 12 - 0.03, 2 * a_in, 0.08), t_on=t0 + 0.3 + 0.25 * j / 12, mat=2)
    # parapet with merlons, and the lead-covered deck edge
    pieces = G.ring_course(tower_poly, TOWER_A, TOWER_A, 0.7, zt - 0.1, zt + 0.9, 2.2, 0)
    for corners, order in pieces:
        tb.add(corners, t_on=t0 + 0.6 + 0.2 * order, mat=0)
    for s in range(4):
        P = tower_poly(TOWER_A - 0.35)
        a, b = P[s], P[(s + 1) % 4]
        for u in np.linspace(0.08, 0.92, 5):
            p = a + (b - a) * u
            rot = math.atan2(b[1] - a[1], b[0] - a[0])
            tb.add(G.box(p[0], p[1], zt + 0.9, 1.0, 0.7, PARAPET - 0.9, rot), t_on=t0 + 0.8 + 0.15 * u, mat=0)
    tb.finalize()
    return tb


class Sched:
    """Wall top height <-> tc (for the scaffold that climbs with the work)."""

    def __init__(self):
        n = int(round(TOWER_H / LIFT)) + 1
        self.t = np.linspace(TC_WALLS[0], TC_WALLS[1], n + 1)
        self.z = PLATEAU - 0.6 + LIFT * np.arange(n + 1)

    def height(self, t):
        return float(np.interp(t, self.t, self.z))

    def time_at(self, z):
        if z > self.z[-1]:
            return 1e9
        return float(np.interp(z, self.z, self.t))


def build_tower_scaffold():
    sched = Sched()
    tb = G.HexBatch('tower_scaffold')
    rng = np.random.default_rng(17)
    SC.scaffold_tier(tb, lambda a: tower_poly(a), lambda z: TOWER_A, PLATEAU, TOWER_H + 1.5, sched, TC_SCAF_DOWN, rng,
                     lift=2.0, off=1.4, spacing=3.0, extra_top=1.8, collar=40.0)
    tb.finalize()
    return tb, sched


# ================================================================== the workshop (S3)
ROOM_O = (900.0, -1400.0, 140.0)     # a room of its own, high above the fields (only its window lets light in)
ROOM = dict(w=7.0, d=5.6, h=4.2, win_w=1.4, win_h=2.3, win_sill=1.0)


def room_frame(sun_az):
    """World matrix of the room: local +y is the window wall's outward normal, turned to face the sun."""
    return Matrix.Translation(ROOM_O) @ Matrix.Rotation(sun_az - math.pi / 2, 4, 'Z')


def mat_parchment():
    """Parchment with the heliocentric system drawn on it: the sun in the middle,
    the orbits of the planets as circles, a few lines of writing."""
    m, nb, out = SC.new_material('Parchment')
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    u, v, _ = nb.sep(uv)
    fs = nb.sep(nb.attr('fsize').outputs['Vector'])
    cu = nb.math('SUBTRACT', u, nb.math('MULTIPLY', fs[0], 0.5))
    cv = nb.math('SUBTRACT', v, nb.math('MULTIPLY', fs[1], 0.55))
    r = nb.math('SQRT', nb.math('ADD', nb.math('MULTIPLY', cu, cu), nb.math('MULTIPLY', cv, cv)))
    ring = nb.math('FRACT', nb.math('DIVIDE', r, 0.035))
    orbit = nb.math('MULTIPLY', nb.smooth(0.93, 0.99, ring), nb.math('LESS_THAN', r, 0.2))
    sun = nb.smooth(0.012, 0.006, r)
    base = nb.mix(nb.noise(nb.comb(u, v, 0.0), 30.0, 3.0, 0.6).outputs['Fac'], (0.78, 0.66, 0.46, 1), (0.88, 0.78, 0.58, 1))
    lines = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.smooth(0.85, 0.95, nb.math('FRACT', nb.math('DIVIDE', v, 0.012))),
                                        nb.math('GREATER_THAN', r, 0.23)),
                    nb.smooth(0.3, 0.6, nb.noise(nb.comb(nb.math('MULTIPLY', u, 3.0), v, 0.0), 60.0, 2.0, 0.5).outputs['Fac']))
    ink = nb.math('MAXIMUM', nb.math('MAXIMUM', orbit, lines), sun)
    col = nb.mix(nb.math('MULTIPLY', ink, 0.85), base, (0.12, 0.08, 0.05, 1))
    b = SC.principled(nb, col, rough=0.8, spec=0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_workshop(S):
    """Plastered walls, a beamed ceiling, a plank floor; a window with a stone
    mullion; the carpenter's bench with the long rules of the triquetrum, tools
    and shavings; Copernicus' table with parchments, books, an hourglass,
    candles, the small armillary sphere.  All in the room's local frame."""
    import figures as FG
    import instruments as IN
    coll = bpy.context.scene.collection
    r = ROOM
    w, d, h = r['w'], r['d'], r['h']
    rb = G.HexBatch('room')
    t = 0.45
    ww, wh, ws = r['win_w'], r['win_h'], r['win_sill']
    rb.add(G.box(0, -d / 2 - t / 2, -0.3, w + 2 * t, t, h + 0.6), mat=0)                  # back wall
    rb.add(G.box(-w / 2 - t / 2, 0, -0.3, t, d + 2 * t, h + 0.6), mat=0)                  # side walls
    rb.add(G.box(w / 2 + t / 2, 0, -0.3, t, d + 2 * t, h + 0.6), mat=0)
    xw = -0.6                                                                            # the window wall (+y) with its opening
    rb.add(G.box((-w / 2 + xw - ww / 2) / 2 - t / 2 + 0.0, d / 2 + t / 2, -0.3, (xw - ww / 2) - (-w / 2) + t, t, h + 0.6), mat=0)
    rb.add(G.box((xw + ww / 2 + w / 2) / 2 + t / 2, d / 2 + t / 2, -0.3, (w / 2) - (xw + ww / 2) + t, t, h + 0.6), mat=0)
    rb.add(G.box(xw, d / 2 + t / 2, -0.3, ww, t, ws + 0.3), mat=0)
    rb.add(G.box(xw, d / 2 + t / 2, ws + wh, ww, t, h - ws - wh + 0.3), mat=0)
    rb.add(G.box(0, 0, -0.3, w + 2 * t, d + 2 * t, 0.3), mat=2)                           # floor
    rb.add(G.box(0, 0, h, w + 2 * t, d + 2 * t, 0.3), mat=1)                              # ceiling boards
    for k in range(6):                                                                   # beams
        x = -w / 2 + w * (k + 0.5) / 6
        rb.add(G.box(x, 0, h - 0.28, 0.24, d, 0.28), mat=1)
    rb.add(G.box(xw, d / 2 + 0.02, ws, 0.12, 0.3, wh), mat=3)                              # stone mullion and transom
    rb.add(G.box(xw, d / 2 + 0.02, ws + wh * 0.62, ww, 0.3, 0.1), mat=3)
    rb.add(G.box(xw, d / 2 - 0.05, ws - 0.08, ww + 0.3, 0.45, 0.08), mat=3)              # the sill
    # the carpenter's bench along the window, the rules of the triquetrum on it
    bx, by = -0.9, 1.35
    rb.add(G.box(bx, by, 0.82, 3.2, 0.8, 0.1), mat=1)
    for sx in (-1.4, 1.4):
        for sy in (-0.3, 0.3):
            rb.add(G.box(bx + sx, by + sy, 0.0, 0.12, 0.12, 0.82), mat=1)
    rb.add(G.box(bx - 0.2, by + 0.05, 0.92, 2.5, 0.09, 0.07), mat=4)                       # the sighting rule
    rb.add(G.box(bx + 0.1, by - 0.22, 0.92, 2.6, 0.08, 0.06), mat=4)                       # the lower rule
    for k in range(9):                                                                   # brass scale strips, pins
        rb.add(G.box(bx - 0.9 + 0.2 * k, by - 0.22, 0.98, 0.015, 0.07, 0.006), mat=5)
    rb.add(G.box(bx + 1.1, by + 0.1, 0.92, 0.28, 0.07, 0.09), mat=4)                       # a plane
    rng = np.random.default_rng(3)
    for k in range(40):                                                                  # shavings on bench and floor
        x, y = bx + rng.uniform(-1.2, 1.4), by + rng.uniform(-0.35, 0.35)
        z = 0.92 if k < 18 else 0.0
        if k >= 18:
            x, y = bx + rng.uniform(-1.3, 1.5), by + rng.uniform(-1.0, 0.6)
        rb.add(G.box(x, y, z, rng.uniform(0.05, 0.14), rng.uniform(0.02, 0.05), 0.008, rng.uniform(0, 3)), mat=4)
    # Copernicus' table against the side wall, parchments, books, hourglass
    tx, ty = 2.2, 0.2
    rb.add(G.box(tx, ty, 0.76, 1.1, 1.8, 0.07), mat=1)
    for sx in (-0.45, 0.45):
        for sy in (-0.8, 0.8):
            rb.add(G.box(tx + sx, ty + sy, 0.0, 0.09, 0.09, 0.76), mat=1)
    for k, (dx, dy, rot) in enumerate(((0.05, 0.25, 0.1), (-0.15, -0.35, -0.2), (0.2, -0.6, 0.4))):
        rb.add(G.box(tx + dx, ty + dy, 0.83, 0.42, 0.55, 0.004, rot), mat=6)
    for k in range(5):                                                                   # a stack of books
        rb.add(G.box(tx + 0.3, ty + 0.65, 0.83 + 0.06 * k, 0.3, 0.22, 0.055, 0.1 * k), mat=7)
    for k in range(12):                                                                  # the shelf of books on the back wall
        rb.add(G.box(-2.8 + k * 0.1, -d / 2 + 0.2, 1.62, 0.07, 0.25, 0.3 + 0.03 * (k % 3)), mat=7)
    rb.add(G.box(-2.3, -d / 2 + 0.2, 1.55, 1.4, 0.34, 0.06), mat=1)
    rb.finalize()
    m_plaster = SC.mat_masonry('RoomPlaster', (0.80, 0.76, 0.68), (0.70, 0.66, 0.58), var=0.03, width=0.001, grime=0.2)
    S.m_brass = IN.mat_brass()
    mats = [m_plaster, S.m_wood, S.m_plank, S.m_stone, SC.mat_wood('Oak', (0.36, 0.24, 0.13)), S.m_brass, mat_parchment(),
            SC.mat_simple('BookLeather', (0.25, 0.10, 0.06), 0.7)]
    S.room = SC.link(bpy.data.objects.new('Workshop', SC.hex_mesh('Workshop', rb, np.ones(len(rb.t_on), bool), mats)), coll)
    S.room.pass_index = SC.PASS['masonry']
    # candles on the table, with flames and small lights
    S.candles = []
    cm = SC.prism('Candle', 0.025, 0.0, 0.22, 8, 0.024, (0, 0), [SC.mat_simple('Wax', (0.85, 0.80, 0.65), 0.6)])
    fm = SC.prism('CandleFlame', 0.012, 0.0, 0.05, 6, 0.002, (0, 0), [S.m_torch])
    for k, (dx, dy) in enumerate(((0.35, -0.2), (0.3, 0.2), (-0.3, 0.75))):
        c = SC.link(bpy.data.objects.new(f'Candle{k}', cm), coll)
        f = SC.link(bpy.data.objects.new(f'CandleFlame{k}', fm), coll)
        f.visible_shadow = False
        ld = bpy.data.lights.new(f'CandleLight{k}', 'POINT')
        ld.color = (1.0, 0.55, 0.22)
        ld.shadow_soft_size = 0.02
        lo = SC.link(bpy.data.objects.new(f'CandleLight{k}', ld), coll)
        S.candles.append((c, f, lo, (tx + dx, ty + dy, 0.83)))
    # the small armillary sphere on the table and the figures
    S.room_armillary = IN.build_armillary('RoomArmillary', S.m_wood, S.m_brass, math.radians(LATITUDE_DEG))
    S.m_figure = FG.mat_figure()
    S.fig_copernicus = [FG.figure_mesh(f'Copernicus{k}', 'scholar', pose, S.m_figure) for k, pose in enumerate(COPERNICUS_POSES)]
    S.fig_carpenter = [FG.figure_mesh(f'Carpenter{k}', 'craftsman', pose, S.m_figure) for k, pose in enumerate(CARPENTER_POSES)]
    S.copernicus = SC.link(bpy.data.objects.new('Copernicus', S.fig_copernicus[0]), coll)
    S.copernicus.color = (0.30, 0.06, 0.05, 1.0)                  # the red coat of the Torun portrait
    S.carpenter = SC.link(bpy.data.objects.new('Carpenter', S.fig_carpenter[0]), coll)
    S.carpenter.color = (0.55, 0.50, 0.42, 1.0)
    for o in (S.copernicus, S.carpenter):
        o.pass_index = SC.PASS['worker']
    # dust in the sunbeam: a thin volume filling the room
    vb = G.HexBatch('room_air')
    vb.add(G.box(0, 0, 0.02, w - 0.05, d - 0.05, h - 0.35), mat=0)
    vb.finalize()
    m_air = bpy.data.materials.new('RoomAir')
    m_air.use_nodes = True
    nt = m_air.node_tree
    nt.nodes.clear()
    vs = nt.nodes.new('ShaderNodeVolumeScatter')
    vs.inputs['Density'].default_value = 0.035
    vs.inputs['Anisotropy'].default_value = 0.45
    o_ = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(vs.outputs[0], o_.inputs['Volume'])
    S.room_air = SC.link(bpy.data.objects.new('RoomAir', SC.hex_mesh('RoomAir', vb, np.ones(1, bool), [m_air])), coll)
    S.room_parts = [S.room, S.room_air, S.copernicus, S.carpenter] + [o for c in S.candles for o in c[:3]]
    show_workshop(S, False)


COPERNICUS_POSES = [dict(hand_r=(0.16, 0.36, 0.98), hand_l=(-0.22, 0.28, 1.0), look=(0.15, 1.0, -0.6), stoop=0.06),
                    dict(hand_r=(0.2, 0.4, 0.97), hand_l=(-0.18, 0.3, 1.02), look=(0.25, 1.0, -0.55), stoop=0.07)]
CARPENTER_POSES = [dict(hand_r=(0.1, 0.35 + 0.1 * k, 0.98), hand_l=(-0.12, 0.42 + 0.1 * k, 0.98), lean=0.08 + 0.04 * k)
                   for k in range(4)]


def show_workshop(S, on):
    for o in S.room_parts:
        o.hide_render = not on
    import instruments as IN
    if not on:
        IN.pose_armillary(S.room_armillary, Matrix.Identity(4), visible=False)


def pose_workshop(S, M, t, cop_k=0, carp_ph=0.0):
    """M: room frame (room_frame(sun azimuth)); carp_ph: the carpenter's planing phase."""
    import instruments as IN
    show_workshop(S, True)
    for o in (S.room, S.room_air):
        o.matrix_world = M
    S.copernicus.data = S.fig_copernicus[cop_k % len(S.fig_copernicus)]
    S.copernicus.matrix_world = M @ Matrix.Translation((1.35, 0.1, 0.0)) @ Matrix.Rotation(-math.pi / 2, 4, 'Z')
    k = int((carp_ph / (2 * math.pi)) * 8) % 8
    k = k if k < 4 else 7 - k                                    # forward and back along the bench
    S.carpenter.data = S.fig_carpenter[k]
    S.carpenter.matrix_world = M @ Matrix.Translation((-0.4, 0.55, 0.0))
    for i, (c, f, lo, (x, y, z)) in enumerate(S.candles):
        fl = 0.85 + 0.15 * SC.smooth_rand(i + 400, t, 7.0)
        c.matrix_world = M @ Matrix.Translation((x, y, z))
        f.matrix_world = M @ Matrix.Translation((x, y, z + 0.22)) @ Matrix.Diagonal((1.0, 1.0, fl, 1.0))
        lo.matrix_world = M @ Matrix.Translation((x, y, z + 0.28))
        lo.data.energy = 4.0 * fl
    IN.pose_armillary(S.room_armillary, M @ Matrix.Translation((2.35, -0.45, 0.83)) @ Matrix.Diagonal((0.28, 0.28, 0.28, 1.0)),
                      spin=0.2 * t)


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
    S.m_brick = mat_brick()
    S.m_brick_new = mat_brick('BrickNew', base=((0.40, 0.12, 0.05), (0.58, 0.22, 0.10)))
    S.m_roof = RH.mat_roof()
    S.m_plaster = SC.mat_simple('Whitewash', (0.82, 0.80, 0.74), 0.9)
    S.m_houses = RH.mat_houses()
    S.m_glass = mat_glass()
    S.m_copper = mat_copper_roof()
    S.m_wood = SC.mat_wood('Timber', P['wood'])
    S.m_plank = SC.mat_wood('Planks', P['plank'], width=0.04)
    S.m_rope = SC.mat_simple('Rope', P['rope'], 0.9)
    S.m_stone = SC.mat_masonry('Stone', *P['stone'])
    S.m_cloth = SC.mat_simple('Canvas', P['cloth'], 0.9)
    S.m_cloth2 = SC.mat_simple('CanvasDark', P['cloth2'], 0.9)
    S.m_hull = SC.mat_wood('Hull', P['hull'], textured=False)
    S.m_sail = SC.mat_simple('Sail', P['sail'], 0.9)
    S.m_torch = SC.mat_torch()
    S.m_city = S.m_houses
    S.world = SC.build_world()
    S.flat_world = SC.build_flat_world()
    S.ground = build_ground(coll)
    S.sea, S.ocean = SC.build_sea(coll, height_fn=height, extent=(-1500.0, 1500.0, -300.0, 900.0), center=(0.0, 900.0), r0=2.0)
    S.ocean.wave_scale = 0.35                   # a lagoon: short, low waves
    S.ocean.wind_velocity = 7.0
    S.ocean.foam_coverage = 0.0
    S.cloud_shadow, S.m_cshadow = SC.build_cloud_shadows(coll)
    S.cathedral = build_cathedral(coll, S.m_brick, S.m_roof, S.m_plaster, S.m_glass, S.m_copper)
    S.close = build_close(coll, S.m_brick, S.m_roof, S.m_plaster, S.m_houses)
    S.town = build_town(coll, S.m_brick, S.m_roof, S.m_houses)
    S.trees = build_trees(coll)
    S.tower_batch = build_tower()
    S.tower_obj = SC.link(bpy.data.objects.new('Tower', bpy.data.meshes.new('Tower')), coll)
    S.tower_obj.pass_index = SC.PASS['masonry']
    S.tower_mats = [S.m_brick_new, S.m_wood, S.m_plank, S.m_stone]
    S.scaf_batch, S.sched = build_tower_scaffold()
    S.scaf_obj = SC.link(bpy.data.objects.new('TowerScaffold', bpy.data.meshes.new('TowerScaffold')), coll)
    S.scaf_obj.pass_index = SC.PASS['timber']
    S.site_tc = None
    build_workshop(S)
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
    cd.clip_start = 0.3
    cd.clip_end = 60000
    S.cam = SC.link(bpy.data.objects.new('Cam', cd), coll)
    sc.camera = S.cam
    return S


def pose_site(S, tc):
    key = round(tc, 4)
    if key != S.site_tc:
        S.site_tc = key
        SC.set_dynamic_mesh(S.tower_obj, 'Tower', S.tower_batch, S.tower_batch.select(tc), S.tower_mats)
        SC.set_dynamic_mesh(S.scaf_obj, 'TowerScaffold', S.scaf_batch, S.scaf_batch.select(tc), [S.m_wood, S.m_plank])
    return dict(level=S.sched.height(tc))


def pose(S, t, **kw):
    hour = kw.get('hour', 9.0)
    zen, hor = SC.pose_environment(S, t, **dict(kw, hour=hour))
    site = pose_site(S, kw.get('tc', 0.0))
    if 'cam' in kw:
        loc, tgt, lens = kw['cam']
        S.cam.data.lens = lens
        SC.look_at(S.cam, loc, tgt)
    import timeline as TL
    el, _ = TL.sun_angles(hour)
    return dict(t=t, hour=hour, sun_el=math.degrees(el), day=TL.smoothstep(math.radians(-7), math.radians(5), el),
                height=site['level'], fire=0.0, horizon=hor, zenith=zen, **site)
