"""The 20-s Civ1 wonder film 'Der Leuchtturm' (wunderfilm_04_lighthouse).

Five shots cut from the one Pharos scene (storyboards/runde1_fehlende_wunder.md):
  S1  0.0- 3.0 s  the quay on Pharos, morning, real time: barges, crane, ox carts, gulls
  S2  3.0-11.0 s  time-lapse orbit: podium -> square tier -> octagon -> lantern, one short night
  S3 11.0-13.5 s  golden hour, close: the derrick sets the bronze Zeus Soter on the dome
  S4 13.5-16.0 s  sunset, all scaffolding struck: the beacon is lit
  S5 16.0-20.0 s  blue hour: a merchantman, guided by the fire, makes for the Great Harbour

Each shot drives scene.pose() with its own clocks (construction time, hour of
day, animation) and adds what only it needs: walking people, ox carts, gulls,
the hero ship.  No text in the picture; the game shows the titles.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import geometry as G
import scene as SC
import timeline as TL

FPS = 24
DURATION = 20.0
NFRAMES = int(round(FPS * DURATION))   # 480
LOOK = 'bright'
SHOTS = [('S1', 0.0, 3.0), ('S2', 3.0, 11.0), ('S3', 11.0, 13.5), ('S4', 13.5, 16.0), ('S5', 16.0, 20.0)]
CUTS = [s[1] for s in SHOTS[1:]]


def shot_at(v):
    for name, a, b in SHOTS:
        if a <= v < b:
            return name, a, b
    return SHOTS[-1]


# ------------------------------------------------------------------ S2 clocks
# One day of work, a short night by torchlight, the next morning.  Construction
# progress follows this film's daylight (fast by day, a crawl at night).
S2_HOUR = [(3.0, 8.6), (5.9, 17.2), (6.35, 18.2), (6.75, 19.0), (7.05, 29.0), (7.45, 29.8), (7.9, 30.9),
           (11.0, 39.6)]
S2_TC = (1.0, 22.3)


def s2_hour(v):
    return TL._pchip([k[0] for k in S2_HOUR], [k[1] for k in S2_HOUR], v)


def _daylight(hour):
    el, _ = TL.sun_angles(hour)
    return TL.smoothstep(math.radians(-7), math.radians(5), el)


_V2 = np.linspace(3.0, 11.0, 1601)
_R2 = np.array([0.12 + 0.88 * _daylight(s2_hour(v)) for v in _V2])
_W2 = np.concatenate([[0.0], np.cumsum(0.5 * (_R2[1:] + _R2[:-1]) * np.diff(_V2))])
_W2 /= _W2[-1]


def s2_tc(v):
    w = float(np.interp(v, _V2, _W2))
    w0, w1 = TL.work(S2_TC[0]), TL.work(S2_TC[1])
    return float(np.interp(w0 + w * (w1 - w0), TL._WORK, TL._TS))


# orbit: from the east (morning sun behind the camera) round to the south
def s2_cam(v, tc):
    ks = SC.CAM_KEYS
    d, cz, tz = (TL._pchip([k[0] for k in ks], [k[j] for k in ks], tc) for j in (1, 2, 3))
    u = TL.ease_io((v - 3.0) / 8.0) * 0.8 + 0.2 * (v - 3.0) / 8.0
    az = math.radians(90.0 - (200.0 - 60.0 * u))       # camera bearing 200 -> 140 deg
    d *= 1.04
    return (d * math.cos(az), d * math.sin(az), cz), (0.0, 0.0, tz), 38.0


def bearing_pos(bearing_deg, dist, z):
    b = math.radians(bearing_deg)
    return (dist * math.sin(b), dist * math.cos(b), z)


def lerp3(a, b, u):
    return tuple(a[i] + (b[i] - a[i]) * u for i in range(3))


# ================================================================= figures
def bake(name, J, E, R, mat, subsurf=1, skin=None):
    o = SC.skin_figure(name, J, E, R, mat, subsurf)
    SC.link(o)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    bpy.data.objects.remove(o)
    if skin is not None:     # two-tone: tunic from the object colour, bare head, arms and legs
        me.materials.append(skin)
        idx = []
        for p in me.polygons:
            c = p.center
            tunic = 0.58 < c.z < 1.47 and abs(c.x) < 0.2 and abs(c.y) < 0.22
            idx.append(0 if tunic else 1)
        me.polygons.foreach_set('material_index', idx)
    return me


HUMAN_E = [(0, 1), (1, 2), (2, 3), (2, 4), (4, 5), (5, 6), (2, 7), (7, 8), (8, 9), (0, 10), (10, 11),
           (11, 12), (12, 13), (0, 14), (14, 15), (15, 16), (16, 17), (0, 18)]
HUMAN_R = [0.16, 0.17, 0.065, 0.105, 0.07, 0.05, 0.045, 0.07, 0.05, 0.045, 0.085, 0.065, 0.05, 0.04,
           0.085, 0.065, 0.05, 0.04, 0.2]


def human_joints(mode, ph=0.0):
    """Joints of a man in a short tunic, facing +y.  mode: walk / stand / haul."""
    bob = 0.0
    lean = 0.0
    legs = []
    arms = []
    if mode == 'walk':
        bob = 0.025 * math.cos(2 * ph)
        for s in (-1, 1):
            psi = ph + (0 if s < 0 else math.pi)
            fy = 0.30 * math.sin(psi)
            lift = 0.10 * max(0.0, math.cos(psi))
            ank = (s * 0.1, fy, 0.08 + lift)
            knee = (s * 0.1, 0.5 * fy + 0.06 + 0.07 * max(0.0, math.cos(psi)), 0.5 + 0.5 * lift)
            legs.append((knee, ank))
            hy = -0.22 * math.sin(psi)
            arms.append(((s * 0.23, 0.5 * hy, 1.17), (s * 0.25, hy, 0.95)))
    elif mode == 'haul':      # hauling on a rope, hand over hand, leaning back
        lean = -0.10 - 0.05 * math.sin(ph)
        for s in (-1, 1):
            fy = 0.18 * s
            legs.append(((s * 0.12, fy * 0.5 + 0.05, 0.5), (s * 0.13, fy, 0.08)))
            reach = 0.32 + 0.16 * math.sin(ph + (0 if s < 0 else math.pi))
            arms.append(((s * 0.17, 0.5 * reach, 1.25), (s * 0.06, reach, 1.18)))
    else:                     # stand
        for s in (-1, 1):
            legs.append(((s * 0.1, 0.02, 0.5), (s * 0.11, 0.0, 0.08)))
            arms.append(((s * 0.24, 0.0, 1.16), (s * 0.26, 0.03, 0.93)))
    pz = 0.95 + bob

    def tilt(p):   # lean the upper body about the hips
        x, y, z = p
        dz = z - pz
        return (x, y + dz * math.sin(lean), pz + dz * math.cos(lean))
    J = [(0, 0, pz), tilt((0, 0, 1.22 + bob)), tilt((0, 0, 1.45 + bob)), tilt((0, 0.01, 1.6 + bob))]
    for s, (el, ha) in zip((-1, 1), arms):
        J += [tilt((s * 0.19, 0, 1.40 + bob)), tilt((el[0], el[1], el[2] + bob)), tilt((ha[0], ha[1], ha[2] + bob))]
    for s, (kn, an) in zip((-1, 1), legs):
        J += [(s * 0.1, 0, 0.9 + bob), kn, an, (an[0], an[1] + 0.13, max(an[2] - 0.05, 0.02))]
    J.append((0, 0, 0.62 + bob))
    return J


def build_people(S, n_walk=12, n_haul=6):
    m = S.m_worker
    sk = SC.mat_simple('Skin', (0.40, 0.24, 0.15), 0.6)
    S.walk_meshes = [bake(f'Walk{k}', human_joints('walk', 2 * math.pi * k / n_walk), HUMAN_E, HUMAN_R, m, skin=sk)
                     for k in range(n_walk)]
    S.haul_meshes = [bake(f'Haul{k}', human_joints('haul', 2 * math.pi * k / n_haul), HUMAN_E, HUMAN_R, m, skin=sk)
                     for k in range(n_haul)]
    S.stand_mesh = bake('Stand', human_joints('stand'), HUMAN_E, HUMAN_R, m, skin=sk)
    S.people = []
    pal = SC.P['workers']
    for i in range(24):
        o = SC.link(bpy.data.objects.new(f'Person{i}', S.stand_mesh))
        o.color = pal[(i * 5 + 1) % len(pal)] + (1.0,)
        o.pass_index = SC.PASS['worker']
        o.hide_render = True
        S.people.append(o)


def place_person(S, i, loc, heading, mode='stand', ph=0.0):
    o = S.people[i]
    o.hide_render = False
    if mode == 'walk':
        o.data = S.walk_meshes[int(ph / (2 * math.pi) * len(S.walk_meshes)) % len(S.walk_meshes)]
    elif mode == 'haul':
        o.data = S.haul_meshes[int(ph / (2 * math.pi) * len(S.haul_meshes)) % len(S.haul_meshes)]
    else:
        o.data = S.stand_mesh
    o.location = loc
    o.rotation_euler = (0, 0, heading - math.pi / 2)   # figure faces +y; heading is CCW from +x
    return o


def ground_z(x, y):
    return float(SC.island_height(np.array([x]), np.array([y]))[0])


# ================================================================= ox carts
OX_E = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (4, 6), (4, 7), (0, 8),
        (2, 9), (9, 10), (10, 11), (2, 12), (12, 13), (13, 14),
        (0, 15), (15, 16), (16, 17), (0, 18), (18, 19), (19, 20)]
OX_R = [0.42, 0.5, 0.47, 0.28, 0.19, 0.13, 0.045, 0.045, 0.05,
        0.13, 0.08, 0.07, 0.13, 0.08, 0.07, 0.13, 0.08, 0.07, 0.13, 0.08, 0.07]


def ox_joints(ph):
    J = [(0, -0.95, 1.22), (0, 0.0, 1.28), (0, 0.75, 1.32), (0, 1.2, 1.15), (0, 1.55, 0.95),
         (0, 1.85, 0.78), (-0.32, 1.5, 1.2), (0.32, 1.5, 1.2), (0, -1.2, 0.55)]
    for (x, y0, phase) in ((-0.22, 0.72, 0.0), (0.22, 0.72, math.pi), (-0.22, -0.82, math.pi), (0.22, -0.82, 0.0)):
        psi = ph + phase
        fy = 0.24 * math.sin(psi)
        lift = 0.09 * max(0.0, math.cos(psi))
        J += [(x, y0, 1.0), (x, y0 + 0.5 * fy + 0.04, 0.52 + 0.5 * lift), (x, y0 + fy, 0.06 + lift)]
    return J


def build_carts(S, n=2, n_pose=10):
    m_ox = SC.mat_simple('Ox', (0.42, 0.30, 0.20) if SC.P is SC.PALETTES['bright'] else (0.2, 0.14, 0.1), 0.85)
    S.ox_meshes = [bake(f'Ox{k}', ox_joints(2 * math.pi * k / n_pose), OX_E, OX_R, m_ox) for k in range(n_pose)]
    cb = G.HexBatch('cart')
    cb.add(G.box(0, 0, 0.95, 1.7, 2.6, 0.14), mat=0)                        # bed
    for s in (-1, 1):
        cb.add(G.box(s * 0.82, 0, 1.09, 0.08, 2.6, 0.45), mat=0)            # side boards
        cb.add(G.beam([s * 0.3, 1.2, 1.0], [s * 0.05, 4.6, 1.15], 0.14), mat=0)   # shafts
    cb.add(G.box(0, -1.26, 1.09, 1.7, 0.08, 0.45), mat=0)
    cb.add(G.beam([-1.0, 4.55, 1.3], [1.0, 4.55, 1.3], 0.16), mat=0)          # yoke
    cb.add(G.beam([-1.05, 0, 0.62], [1.05, 0, 0.62], 0.13), mat=0)            # axle
    cb.add(G.box(0.1, 0.15, 1.09, 1.2, 0.9, 0.75), mat=1)                    # limestone block
    cb.finalize()
    cart_me = SC.hex_mesh('Cart', cb, np.ones(len(cb.t_on), bool), [S.m_wood, S.m_stone])
    wb = G.HexBatch('wheel')
    for k in range(3):                                                    # three-plank disc wheel
        y = (k - 1) * 0.36
        h = math.sqrt(max(0.62 ** 2 - y * y, 0.05))
        wb.add(G.beam([0, y, -h], [0, y, h], 0.1, 0.35), mat=0)
    wb.add(G.beam([0, -0.55, -0.12], [0, 0.55, -0.12], 0.14, 0.1), mat=0)    # battens
    wb.add(G.beam([0, -0.55, 0.12], [0, 0.55, 0.12], 0.14, 0.1), mat=0)
    wb.finalize()
    wheel_me = SC.hex_mesh('Wheel', wb, np.ones(len(wb.t_on), bool), [S.m_plank])
    S.carts = []
    for i in range(n):
        c = SC.link(bpy.data.objects.new(f'Cart{i}', cart_me))
        c.pass_index = SC.PASS['props']
        wheels = []
        for s in (-1, 1):
            w = SC.link(bpy.data.objects.new(f'Wheel{i}{s}', wheel_me))
            w.pass_index = SC.PASS['props']
            wheels.append((w, s))
        oxen = []
        for s in (-1, 1):
            o = SC.link(bpy.data.objects.new(f'Ox{i}{s}', S.ox_meshes[0]))
            o.pass_index = SC.PASS['worker']
            oxen.append((o, s))
        S.carts.append((c, wheels, oxen))
    for c, wheels, oxen in S.carts:
        for o in [c] + [w for w, _ in wheels] + [o for o, _ in oxen]:
            o.hide_render = True


def place_cart(S, i, pos, heading, dist):
    """Cart centre at pos (x, y), heading (rad, CCW from +x), dist = metres driven."""
    c, wheels, oxen = S.carts[i]
    x, y = pos
    z = ground_z(x, y)
    rot = heading - math.pi / 2
    M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(rot, 4, 'Z')
    c.matrix_world = M
    c.hide_render = False
    for w, s in wheels:
        w.matrix_world = M @ Matrix.Translation((s * 1.0, 0, 0.62)) @ Matrix.Rotation(-dist / 0.62, 4, 'X')
        w.hide_render = False
    n = len(S.ox_meshes)
    for o, s in oxen:
        ph = dist / 1.6 * 2 * math.pi + (0.6 if s > 0 else 0.0)
        o.data = S.ox_meshes[int(ph / (2 * math.pi) * n) % n]
        o.matrix_world = M @ Matrix.Translation((s * 0.66, 3.7, 0.0))
        o.hide_render = False


# ================================================================= gulls
def build_gulls(S, n=7, n_pose=8):
    m_w = SC.mat_simple('GullWhite', (0.92, 0.92, 0.9), 0.6)
    m_g = SC.mat_simple('GullGrey', (0.55, 0.57, 0.6), 0.6)
    m_k = SC.mat_simple('GullTip', (0.05, 0.05, 0.05), 0.6)
    S.gull_meshes = []
    for k in range(n_pose):
        a = math.radians(38) * math.cos(2 * math.pi * k / n_pose)      # wing beat
        gb = G.HexBatch('gull')
        gb.add(G.beam([0, -0.26, 0], [0, 0.2, 0.02], 0.12, 0.12), mat=0)
        gb.add(G.beam([0, 0.18, 0.02], [0, 0.3, 0.04], 0.08, 0.08), mat=0)
        for s in (-1, 1):
            p0 = np.array([0.0, 0.0, 0.0])
            p1 = np.array([s * 0.3 * math.cos(a), 0.0, 0.3 * math.sin(a)])
            a2 = a - math.radians(18) * math.sin(2 * math.pi * k / n_pose)
            p2 = p1 + np.array([s * 0.36 * math.cos(a2), -0.05, 0.36 * math.sin(a2)])
            for q0, q1, w, mat in ((p0, p1, 0.2, 1), (p1, p2, 0.16, 2)):
                gb.add(G.beam(q0 + [0, 0.02, 0], q1 + [0, 0.02, 0], w, 0.02), mat=mat)
        gb.finalize()
        S.gull_meshes.append(SC.hex_mesh(f'Gull{k}', gb, np.ones(len(gb.t_on), bool), [m_w, m_g, m_k]))
    S.gulls = []
    for i in range(n):
        o = SC.link(bpy.data.objects.new(f'Gull{i}', S.gull_meshes[0]))
        o.pass_index = SC.PASS['props']
        o.hide_render = True
        S.gulls.append(o)


def pose_gulls(S, t, centre, n_show):
    rng = np.random.default_rng(5)
    for i, o in enumerate(S.gulls):
        if i >= n_show:
            o.hide_render = True
            continue
        r = rng.uniform(10, 26)
        h = rng.uniform(9, 24)
        w = rng.uniform(0.28, 0.45) * (1 if i % 3 else -1)
        a0 = rng.uniform(0, 2 * math.pi)
        a = a0 + w * t
        x = centre[0] + r * math.cos(a) + 3 * math.sin(0.7 * t + i)
        y = centre[1] + r * math.sin(a)
        z = h + 1.2 * math.sin(0.9 * t + i * 1.7)
        head = a + (math.pi / 2 if w > 0 else -math.pi / 2)
        bank = math.copysign(math.radians(20), w)
        flap = (math.sin(0.8 * t + i * 2.3) > -0.1)
        k = int((t * 3.2 + i * 0.37) * len(S.gull_meshes)) % len(S.gull_meshes) if flap else 2
        o.data = S.gull_meshes[k]
        o.hide_render = False
        o.matrix_world = (Matrix.Translation((x, y, z)) @ Matrix.Rotation(head - math.pi / 2, 4, 'Z')
                          @ Matrix.Rotation(-bank, 4, 'Y'))


# ================================================================= hero ship
SHIP_L, SHIP_B = 21.0, 6.4


def ship_stations(ns=40):
    s = np.linspace(0.0, 1.0, ns)
    b = 0.5 * SHIP_B * np.sin(np.pi * np.clip(s, 0, 1) ** 0.92) ** 0.5
    keel = -(1.75 * np.sin(np.pi * s) ** 0.3) + 0.25 * (1 - np.sin(np.pi * s) ** 0.3)
    sheer = 1.45 + 1.7 * (1 - s) ** 4 + 0.9 * s ** 4
    x = (s - 0.5) * SHIP_L
    return s, x, b, keel, sheer


def mat_planking(name, base, band, pitch, strake=0.32, butt=4.6):
    """Hull planking with continuous UVs: strakes along u, staggered butts,
    a painted band below the sheer and black pitch under the waterline."""
    m, nb, out = SC.new_material(name)
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    u, v, _ = nb.sep(uv)
    k = nb.math('FLOOR', nb.math('DIVIDE', v, strake))
    fv = nb.math('FRACT', nb.math('DIVIDE', v, strake))
    fu = nb.math('FRACT', nb.math('DIVIDE', nb.math('ADD', u, nb.math('MULTIPLY', k, 1.7)), butt))
    seam = nb.math('MAXIMUM', nb.smooth(0.07, 0.0, fv), nb.math('MULTIPLY', nb.smooth(0.012, 0.0, fu), 0.8))
    wn = nb.new('ShaderNodeTexWhiteNoise', noise_dimensions='2D')
    nb.feed(wn.inputs['Vector'], nb.comb(k, nb.math('FLOOR', nb.math('DIVIDE', nb.math('ADD', u, nb.math('MULTIPLY', k, 1.7)), butt)), 0.0))
    tone = nb.math('ADD', 0.85, nb.math('MULTIPLY', wn.outputs['Value'], 0.3))
    col = nb.mix(1.0, base + (1,), nb.comb(tone, tone, tone), blend='MULTIPLY')
    oz = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[2]
    top = nb.attr('sheer_d').outputs['Fac']            # distance below the sheer (m)
    bandm = nb.math('MULTIPLY', nb.smooth(0.25, 0.35, top), nb.smooth(0.95, 0.85, top))
    col = nb.mix(bandm, col, band + (1,))
    col = nb.mix(nb.smooth(0.35, 0.15, oz), col, pitch + (1,))
    col = nb.mix(nb.math('MULTIPLY', seam, 0.7), col, (0.02, 0.015, 0.01, 1))
    b = SC.principled(nb, col, rough=0.75, spec=0.35)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_sailcloth(name, base):
    m, nb, out = SC.new_material(name)
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    u, v, _ = nb.sep(uv)
    fu = nb.math('FRACT', nb.math('DIVIDE', u, 1.15))
    fv = nb.math('FRACT', nb.math('DIVIDE', v, 0.95))
    grid = nb.math('MAXIMUM', nb.smooth(0.05, 0.0, fu), nb.smooth(0.06, 0.0, fv))
    n = nb.noise(nb.comb(u, v, 0.0), 0.8, 3.0, 0.6).outputs['Fac']
    k = nb.math('ADD', 0.88, nb.math('MULTIPLY', n, 0.2))
    col = nb.mix(1.0, base + (1,), nb.comb(k, k, k), blend='MULTIPLY')
    col = nb.mix(nb.math('MULTIPLY', grid, 0.55), col, (0.36, 0.26, 0.16, 1))
    b = SC.principled(nb, col, rough=0.9, spec=0.2)
    tr = nb.new('ShaderNodeBsdfTranslucent')
    nb.feed(tr.inputs['Color'], col)
    mix = nb.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = 0.25
    nb.feed(mix.inputs[1], b.outputs[0])
    nb.feed(mix.inputs[2], tr.outputs[0])
    nb.feed(out.inputs['Surface'], mix.outputs[0])
    return m


def build_ship(S):
    """A Hellenistic merchantman (after the Kyrenia wreck, enlarged): round
    carvel hull, swan-neck stern post, twin steering oars, single mast with a
    brailed square sail, deckhouse and a stern lantern."""
    pal = SC.P
    m_hull = mat_planking('ShipHull', pal['hull'] if LOOK != 'bright' else (0.34, 0.22, 0.13),
                          (0.42, 0.10, 0.06), (0.03, 0.025, 0.02))
    m_deck = mat_planking('ShipDeck', (0.52, 0.40, 0.27), (0.52, 0.40, 0.27), (0.52, 0.40, 0.27),
                          strake=0.24, butt=5.3)
    m_wood = S.m_wood
    m_paint = SC.mat_simple('ShipPaint', (0.40, 0.09, 0.05), 0.7)
    m_rope = S.m_rope
    S.m_sailcloth = mat_sailcloth('SailCloth', pal['sail'])
    ns, nk = 40, 9
    s, x, b, keel, sheer = ship_stations(ns)
    # --- hull shell: stations x girth, continuous UVs (u along, v girth)
    V, UV, SD = [], [], []
    for i in range(ns):
        for j in range(-nk + 1, nk):
            k = abs(j) / (nk - 1)
            y = math.copysign(b[i] * math.sin(0.5 * math.pi * k) ** 0.55, j)
            z = keel[i] + (sheer[i] - keel[i]) * k ** 1.35
            V.append([x[i], y, z])
            SD.append(sheer[i] - z)
    V = np.array(V)
    nj = 2 * nk - 1
    Q = []
    for i in range(ns - 1):
        for j in range(nj - 1):
            a = i * nj + j
            Q.append([a, a + 1, a + nj + 1, a + nj])
    Q = np.array(Q)
    # girth coordinate: arc length from the keel along each station
    girth = np.zeros(len(V))
    for i in range(ns):
        row = V[i * nj:(i + 1) * nj]
        d = np.linalg.norm(np.diff(row, axis=0), axis=1)
        g = np.concatenate([[0], np.cumsum(d)])
        g -= g[nk - 1]
        girth[i * nj:(i + 1) * nj] = np.abs(g)
    uv = np.stack([V[Q.ravel(), 0], girth[Q.ravel()]], 1)
    sd = np.array(SD)[Q].mean(axis=1)
    hull = SC.mesh_from_arrays('HeroHull', V, Q, uv=uv, face_attrs={'sheer_d': ('FLOAT', sd)},
                               mats=[m_hull], smooth=True)
    # --- deck (between the bulwarks, 0.5 m below the sheer)
    DV, DQ = [], []
    for i in range(ns):
        zd = sheer[i] - 0.5
        kd = 0.9
        bd = b[i] * math.sin(0.5 * math.pi * kd) ** 0.55 * 0.97
        for y in (-bd, bd):
            DV.append([x[i], y, zd])
    for i in range(ns - 1):
        DQ.append([2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2])
    DV = np.array(DV)
    DQ = np.array(DQ)
    duv = np.stack([DV[DQ.ravel(), 0], DV[DQ.ravel(), 1] + 5.0], 1)
    deck = SC.mesh_from_arrays('HeroDeck', DV, DQ, uv=duv, face_attrs={'sheer_d': ('FLOAT', np.zeros(len(DQ)))},
                               mats=[m_deck])
    # --- timber details
    tb = G.HexBatch('ship_timber')
    for i in range(1, ns - 2):
        for sg in (-1, 1):
            for dz, w, mat in ((0.0, 0.14, 0), (-0.55, 0.2, 2), (-1.25, 0.18, 2)):
                p0 = [x[i], sg * (b[i] + 0.03), sheer[i] + dz]
                p1 = [x[i + 1], sg * (b[i + 1] + 0.03), sheer[i + 1] + dz]
                tb.add(G.beam(p0, p1, w, 0.16), mat=mat)
    L2 = SHIP_L / 2
    zs0, zs1 = sheer[0], sheer[-1]
    neck = [(-L2 + 0.4, zs0 - 1.2), (-L2 - 0.35, zs0 + 0.2), (-L2 - 0.75, zs0 + 1.3), (-L2 - 0.6, zs0 + 2.3),
            (-L2 - 0.1, zs0 + 2.9), (-L2 + 0.5, zs0 + 2.85), (-L2 + 0.85, zs0 + 2.45)]
    for k in range(len(neck) - 1):
        w = 0.42 - 0.03 * k
        tb.add(G.beam([neck[k][0], 0, neck[k][1]], [neck[k + 1][0], 0, neck[k + 1][1]], w, w), mat=0)
    stem = [(L2 - 0.6, -1.3), (L2 + 0.2, zs1 - 0.6), (L2 + 0.45, zs1 + 0.35), (L2 + 0.55, zs1 + 0.8)]
    for k in range(len(stem) - 1):
        tb.add(G.beam([stem[k][0], 0, stem[k][1]], [stem[k + 1][0], 0, stem[k + 1][1]], 0.34, 0.3), mat=0)
    # steering oars on both quarters
    ib = 3
    for sg in (-1, 1):
        top = np.array([x[ib] + 1.2, sg * (b[ib] - 0.2), sheer[ib] + 0.9])
        piv = np.array([x[ib] - 0.2, sg * (b[ib] + 0.35), sheer[ib] - 0.1])
        low = piv + (piv - top) / np.linalg.norm(piv - top) * 3.2
        tb.add(G.beam(top, low, 0.16), mat=0)
        d = (low - piv) / np.linalg.norm(low - piv)
        tb.add(G.beam(low - d * 0.2, low + d * 2.2, 0.62, 0.1, up=(0, 1, 0)), mat=0)
        tb.add(G.beam([x[ib] - 0.2, sg * (b[ib] - 0.3), sheer[ib] - 0.1], piv, 0.18), mat=0)
    # deckhouse aft, cargo forward
    idh = 7
    zd = sheer[idh] - 0.5
    tb.add(G.box(x[idh], 0, zd, 2.6, 3.0, 1.5), mat=0)
    tb.add(G.box(x[idh], 0, zd + 1.5, 3.0, 3.4, 0.12), mat=2)
    rng = np.random.default_rng(8)
    for k in range(10):
        i = 26 + k % 5
        yy = (k // 5 - 0.5) * 1.3
        tb.add(G.box(x[i] + rng.uniform(-0.2, 0.2), yy, sheer[i] - 0.5, 0.9, 0.9, 0.6 + 0.2 * (k % 2)), mat=3)
    tb.finalize()
    timber = SC.hex_mesh('HeroTimber', tb, np.ones(len(tb.t_on), bool), [m_wood, m_rope, m_paint, S.m_cloth])

    # --- mast, yard and standing rigging (the yard is braced round in pose)
    im = 22
    S.ship_mast_x = x[im]
    S.ship_deck_z = sheer[im] - 0.5
    mh = S.ship_deck_z + 16.0
    S.ship_masthead = mh
    rb = G.HexBatch('ship_rig')
    rb.add(G.beam([x[im], 0, -0.8], [x[im], 0, mh], 0.36, 0.36), mat=0)
    rb.add(G.box(x[im], 0, mh - 0.2, 0.5, 0.5, 0.45), mat=0)
    rb.add(G.beam([x[im], 0, mh], [L2 + 0.45, 0, zs1 + 0.5], 0.05), mat=1)          # forestay
    rb.add(G.beam([x[im], 0, mh], [x[5], 0, sheer[5] + 0.3], 0.05), mat=1)            # backstay
    for sg in (-1, 1):
        for dx in (-0.9, -0.3, 0.3):
            ii = int(np.argmin(np.abs(x - (x[im] + dx))))
            rb.add(G.beam([x[im], 0, mh - 0.5], [x[ii], sg * b[ii], sheer[ii]], 0.04), mat=1)
    rb.finalize()
    rig = SC.hex_mesh('HeroRig', rb, np.ones(len(rb.t_on), bool), [m_wood, m_rope])

    objs = {}
    for name, me in (('hull', hull), ('deck', deck), ('timber', timber), ('rig', rig)):
        o = SC.link(bpy.data.objects.new('Hero' + name.title(), me))
        o.pass_index = SC.PASS['ship']
        objs[name] = o
    for name in ('yard', 'sail', 'lines'):
        o = SC.link(bpy.data.objects.new('Hero' + name.title(), bpy.data.meshes.new('Hero' + name)))
        o.pass_index = SC.PASS['ship']
        objs[name] = o
    # stern lantern: a small glowing box on a post + a warm point light
    lb = G.HexBatch('lantern')
    lx = x[4]
    lz = sheer[4] - 0.5
    lb.add(G.beam([lx, 0, lz], [lx, 0, lz + 2.3], 0.1), mat=0)
    lb.finalize()
    post = SC.link(bpy.data.objects.new('HeroLanternPost', SC.hex_mesh('LanternPost', lb, np.ones(1, bool), [m_wood])))
    post.pass_index = SC.PASS['ship']
    glow = SC.mat_simple('LanternGlow', (1.0, 0.7, 0.35), 0.5, emit=(1.0, 0.62, 0.28), emit_strength=0.0)
    S.m_lantern = glow
    me = SC.prism('LanternBox', 0.2, lz + 2.3, lz + 2.75, 6, 0.14, (lx, 0), [glow])
    box = SC.link(bpy.data.objects.new('HeroLanternBox', me))
    box.pass_index = SC.PASS['torch']
    ld = bpy.data.lights.new('HeroLantern', 'POINT')
    ld.color = (1.0, 0.55, 0.22)
    ld.shadow_soft_size = 0.15
    light = SC.link(bpy.data.objects.new('HeroLanternLight', ld))
    light.location = (lx, 0, lz + 2.5)
    objs.update(post=post, lbox=box, light=light)
    root = SC.link(bpy.data.objects.new('HeroShip', None))
    for o in objs.values():
        o.parent = root
    S.ship = objs
    S.ship_root = root
    S.ship_st = (s, x, b, keel, sheer)
    for o in list(objs.values()):
        o.hide_render = True


def sail_mesh(S, brace, brail, t):
    """Yard + billowing square sail, brailed up by `brail` (0 full .. 1 furled)."""
    xm = S.ship_mast_x
    zy = S.ship_masthead - 1.2
    half = 7.0
    ca, sa = math.cos(brace), math.sin(brace)

    def rot(px, py, pz):   # brace the yard about the mast
        return [xm + px * ca - py * sa, px * sa + py * ca, pz]
    yb = G.HexBatch('yard')
    yb.add(G.beam(rot(0, -half - 0.4, zy), rot(0, half + 0.4, zy), 0.24, 0.24), mat=0)
    # the sail: grid, foot raised by the brails, scallops between brail lines
    h_full = 10.2
    h = h_full * (1.0 - 0.62 * brail)
    nu, nv = 18, 12
    V, UV = [], []
    for jv in range(nv + 1):
        w = jv / nv
        for iu in range(nu + 1):
            u = -1 + 2 * iu / nu
            foot_sc = 0.55 * brail * abs(math.sin(math.pi * (u + 1) * 3.5)) * w ** 3
            z = zy - 0.3 - w * h + foot_sc
            belly = (1.1 - 0.5 * brail) * (1 - u * u) * math.sin(math.pi * min(0.15 + 0.85 * w, 1.0)) ** 0.8
            belly *= 1.0 + 0.04 * math.sin(3.1 * t + 2.0 * u + 3 * w)
            V.append(rot(0.18 + belly, u * half * (1 - 0.04 * w), z))
            UV.append((u * half, (zy - z)))
    Q = []
    for jv in range(nv):
        for iu in range(nu):
            a = jv * (nu + 1) + iu
            Q.append([a, a + 1, a + nu + 2, a + nu + 1])
    Q = np.array(Q)
    uv = np.array(UV)[Q.ravel()]
    V = np.array(V)
    sail = SC.mesh_from_arrays('HeroSail', V, Q, uv=uv, mats=[S.m_sailcloth], smooth=True)
    # brails: down the front of the sail, over the yard, aft to the deckhouse
    lb = G.HexBatch('lines')
    xs = S.ship_st[1]
    for u in (-0.78, -0.47, -0.16, 0.16, 0.47, 0.78):
        iu = int(round((u + 1) / 2 * nu))
        pts = [V[jv * (nu + 1) + iu] + np.array([0.06, 0, 0]) for jv in range(0, nv + 1, 2)]
        for p0, p1 in zip(pts[:-1], pts[1:]):
            lb.add(G.beam(p0, p1, 0.035), mat=0)
        yt = np.array(rot(0.1, u * half, zy + 0.15))
        lb.add(G.beam(pts[0], yt, 0.035), mat=0)
        lb.add(G.beam(yt, [xs[7] + 1.2, u * 1.2, S.ship_st[4][7] + 1.0], 0.03), mat=0)
    lb.add(G.beam([xm, 0, S.ship_masthead - 0.3], rot(0, 0, zy + 0.15), 0.06), mat=0)            # halyard
    for sg in (-1, 1):
        lb.add(G.beam([xm, 0, S.ship_masthead], rot(0, sg * half, zy + 0.1), 0.035), mat=0)     # lifts
        clew = V[nv * (nu + 1) + (0 if sg < 0 else nu)]
        ii = 10
        lb.add(G.beam(clew, [xs[ii], sg * S.ship_st[2][ii], S.ship_st[4][ii]], 0.04), mat=0)    # sheets
    yb.finalize()
    lb.finalize()
    return (SC.hex_mesh('HeroYard', yb, np.ones(len(yb.t_on), bool), [S.m_wood]), sail,
            SC.hex_mesh('HeroLines', lb, np.ones(len(lb.t_on), bool), [S.m_rope]))


def pose_ship(S, pos, heading, t, brace, brail, lantern=1.0, sailors=True, first_person=0):
    root = S.ship_root
    pitch = 0.018 * math.sin(0.9 * t + 0.3)
    roll = 0.03 * math.sin(0.62 * t)
    heave = 0.12 * math.sin(1.1 * t + 1.0) - 0.15
    root.matrix_world = (Matrix.Translation((pos[0], pos[1], heave)) @ Matrix.Rotation(heading, 4, 'Z')
                         @ Matrix.Rotation(pitch, 4, 'Y') @ Matrix.Rotation(roll, 4, 'X'))
    yard, sail, lines = sail_mesh(S, brace, brail, t)
    for key, me in (('yard', yard), ('sail', sail), ('lines', lines)):
        old = S.ship[key].data
        S.ship[key].data = me
        if old is not None and old.users == 0:
            bpy.data.meshes.remove(old)
    for o in S.ship.values():
        o.hide_render = False
    S.ship['light'].data.energy = 220.0 * lantern * (0.9 + 0.1 * math.sin(t * 13.0))
    S.m_lantern.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = 60.0 * lantern
    if not sailors:
        return first_person
    s, x, b, keel, sheer = S.ship_st
    M = root.matrix_world
    crew = [(8, -0.9, 'haul', 0.0, math.pi), (9, 0.9, 'haul', 2.0, math.pi), (4, 0.8, 'stand', 0, 0.0),
            (30, 0.4, 'stand', 0, 0.0), (21, -1.2, 'stand', 0, -1.2)]
    for k, (i, yy, mode, ph0, hd) in enumerate(crew):
        p = M @ Vector((x[i], yy, sheer[i] - 0.5))
        head = heading + hd
        ph = ph0 + t * 2.4
        place_person(S, first_person + k, (p.x, p.y, p.z), head, mode, ph)
    return first_person + len(crew)


# ================================================================= build
def build_sledge(S):
    sb = G.HexBatch('sledge')
    for s in (-0.55, 0.55):
        sb.add(G.beam([s, -1.2, 0.08], [s, 1.3, 0.12], 0.16, 0.16), mat=0)
    sb.add(G.box(0, 0, 0.2, 1.4, 2.0, 0.1), mat=0)
    sb.add(G.box(0, -0.1, 0.3, 1.1, 1.7, 0.9), mat=1)
    for s in (-0.5, 0.5):                                    # hauling ropes to the team
        sb.add(G.beam([s * 0.6, 1.3, 0.25], [s * 1.2, 4.9, 1.15], 0.035), mat=2)
    sb.finalize()
    S.sledge = SC.link(bpy.data.objects.new('Sledge', SC.hex_mesh('Sledge', sb, np.ones(len(sb.t_on), bool),
                                                                   [S.m_wood, S.m_stone, S.m_rope])))
    S.sledge.pass_index = SC.PASS['props']
    S.sledge.hide_render = True


def build(res=(1280, 720)):
    S = SC.build(res, look=LOOK, derrick=True)
    build_sledge(S)
    build_people(S)
    build_carts(S)
    build_gulls(S)
    build_ship(S)
    return S


def hide_extras(S):
    for o in S.people + S.gulls + [S.sledge]:
        o.hide_render = True
    for c, wheels, oxen in S.carts:
        c.hide_render = True
        for w, _ in wheels:
            w.hide_render = True
        for o, _ in oxen:
            o.hide_render = True
    for o in S.ship.values():
        o.hide_render = True


# ================================================================= shots
QUAY_CRANE = (38.6, -92.0, 2.95)
STATUE_YAW = math.radians(80.0)


def shot_S1(S, v):
    """The quay, 08:00, real time."""
    u = v / 3.0
    hour = 8.0 + 0.25 * u
    cam = (lerp3((61.0, -113.0, 8.5), (56.5, -116.0, 8.5), TL.ease_io(u)),
           lerp3((37.5, -89.0, 5.0), (34.5, -87.5, 5.0), TL.ease_io(u)), 30.0)
    meta = SC.pose(S, v, tc=0.95, hour=hour, life=v, hop_t=0.3, sea_t=40.0 + v, water_t=16.0 + 0.4 * v,
                   cloud_t=hour * 0.75, shadow_t=hour * 124.0, cover=0.02, cloud_gain=7.0, shadow_cover=0.3,
                   traffic=False, crane5_loc=QUAY_CRANE, statue_yaw=STATUE_YAW, cam=cam)
    # barges: one moored alongside the jetty being unloaded, one coming in
    for i, (h, r, cg) in enumerate(S.barges):
        h.hide_render = r.hide_render = cg.hide_render = i > 1
    h, r, cg = S.barges[0]
    h.location = (47.6, -91.0, 0.1 + 0.05 * math.sin(1.3 * v))
    h.rotation_euler = (0.01 * math.sin(0.9 * v), 0, math.pi / 2)
    h, r, cg = S.barges[1]
    x = 71.0 - 1.0 * v
    h.location = (x, -73.5, 0.1 + 0.05 * math.sin(1.1 * v + 1))
    h.rotation_euler = (0, 0, math.pi)
    # quay crane: swings a block from the barge onto the jetty (real time)
    c, rope, load = S.cranes[5]
    slew = math.radians(15.0 + 45.0 * TL.ease_io(u))
    c.matrix_world = Matrix.Translation(QUAY_CRANE) @ Matrix.Rotation(slew, 4, 'Z')
    tip = c.matrix_world @ Vector(S.crane_tip)
    lz = 4.2 + 1.6 * TL.ease_io(min(u * 1.6, 1.0))
    swing = 0.25 * math.sin(2.1 * v)
    load.hide_render = rope.hide_render = False
    load.matrix_world = Matrix.Translation((tip.x + swing * 0.3, tip.y, lz)) @ Matrix.Rotation(slew, 4, 'Z')
    rope.matrix_world = Matrix.Translation(tip) @ Matrix.Diagonal((1, 1, tip.z - lz, 1))
    # people: walkers on the jetty and the track, a crew at the crane and on the barge
    k = 0
    walkers = [((33.0, -100.0), math.radians(90), 1.25, 0.0), ((38.0, -70.0), math.radians(-90), 1.2, 1.0),
               ((31.5, -80.0), math.radians(95), 1.3, 2.0), ((36.0, -60.0), math.radians(125), 1.15, 0.5),
               ((24.0, -46.0), math.radians(130), 1.1, 1.5), ((41.0, -84.0), math.radians(-88), 1.2, 2.5),
               ((29.0, -55.0), math.radians(-50), 1.25, 3.0)]
    for (x0, y0), hd, spd, ph0 in walkers:
        dist = spd * v
        x = x0 + math.cos(hd) * dist
        y = y0 + math.sin(hd) * dist
        z = 2.95 if (29.5 < x < 42.5 and -108 < y < -64) else ground_z(x, y)
        place_person(S, k, (x, y, z), hd, 'walk', ph0 + dist / 1.45 * 2 * math.pi)
        k += 1
    for (x, y, z, hd, mode) in ((41.0, -95.5, 2.95, math.radians(180), 'haul'), (39.2, -96.8, 2.95, math.radians(160), 'haul'),
                                (46.4, -85.8, 1.3, math.radians(200), 'stand'), (48.8, -85.6, 1.3, math.radians(250), 'haul'),
                                (35.5, -63.0, ground_z(35.5, -63.0), math.radians(40), 'stand')):
        place_person(S, k, (x, y, z), hd, mode, 1.3 * v * 2 + k)
        k += 1
    # a team dragging a block on a sledge up the jetty (towards the shore)
    sx, sy = 35.2, -97.5 + 0.55 * v
    S.sledge.hide_render = False
    S.sledge.location = (sx, sy, 2.95)
    for j, (dx, dy) in enumerate(((-0.6, 3.2), (0.6, 3.6), (-0.6, 4.4), (0.6, 4.8))):
        place_person(S, k, (sx + dx, sy + dy, 2.95), math.radians(90), 'walk', 0.55 * v / 1.45 * 2 * math.pi + j * 1.9)
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    # ox carts: one leaving for the building site, one waiting at the jetty
    place_cart(S, 0, (30.0 - 0.95 * v * 0.6, -57.0 + 0.95 * v * 0.8), math.atan2(0.8, -0.6), 0.95 * v)
    place_cart(S, 1, (38.5, -56.5), math.radians(100), 0.0)
    pose_gulls(S, v, (40.0, -92.0), 7)
    meta.update(stars=0.0)
    return meta


def shot_S2(S, v):
    tc = s2_tc(v)
    hour = s2_hour(v)
    cam = s2_cam(v, tc)
    meta = SC.pose(S, v, tc=tc, hour=hour, life=v, hop_t=v, sea_t=v * 2.2, water_t=v * 0.9,
                   cloud_t=hour * 0.75, shadow_t=hour * 124.0, cover=0.04 + 0.04 * math.sin(v * 0.7),
                   cloud_gain=7.0, shadow_cover=0.3, moon=0.0, crane5_loc=QUAY_CRANE, statue_yaw=STATUE_YAW,
                   cam=cam)
    meta.update(stars=0.0)
    return meta


S3_CAM = (bearing_pos(156.0, 60.0, 105.5), (-2.5, 0.0, 106.3), 42.0)


TAG_MEN = [(-7.6, -3.9), (-3.3, -7.3)]


def shot_S3(S, v):
    u = (v - 11.0) / 2.5
    hour = 40.85 + 0.12 * u
    p = min(1.0, 0.1 + 0.95 * u)
    loc, tgt, lens = S3_CAM
    loc = lerp3(loc, bearing_pos(146.0, 58.0, 105.5), TL.ease_io(u))
    meta = SC.pose(S, v, tc=22.95, hour=hour, life=v, hop_t=11.0 + (v - 11.0) * 0.5, sea_t=v * 1.5,
                   water_t=v * 0.6, cloud_t=hour * 0.75, shadow_t=hour * 124.0, cover=0.06, cloud_gain=7.0,
                   shadow_cover=0.3, statue_p=p, statue_yaw=STATUE_YAW, crane5_loc=QUAY_CRANE,
                   cam=(loc, tgt, lens))
    # tag-line men on the octagon roof, leaning on their lines
    statue = S.statue.location
    k = 0
    for (bx, by) in TAG_MEN:
        z = SC.T2_ROOF
        hd = math.atan2(statue.y - by, statue.x - bx)
        place_person(S, k, (bx, by, z), hd, 'haul', 1.0 + k * 2 + v * 1.5)
        k += 1
    # windlass crew
    wx, wy = SC.DERRICK_WINCH
    ta = SC.DERRICK_PHI - math.pi / 2
    for s in (-1, 1):
        px = wx + 1.0 * math.cos(ta) + s * 0.6 * math.cos(SC.DERRICK_PHI)
        py = wy + 1.0 * math.sin(ta) + s * 0.6 * math.sin(SC.DERRICK_PHI)
        place_person(S, k, (px, py, SC.T2_ROOF), ta + math.pi, 'haul', v * 3 + s)
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    set_taglines(S, TAG_MEN, p)
    meta.update(stars=0.0)
    return meta


def set_taglines(S, anchors, p):
    if not hasattr(S, 'taglines'):
        S.taglines = SC.link(bpy.data.objects.new('TagLines', bpy.data.meshes.new('TagLines')))
        S.taglines.pass_index = SC.PASS['crane']
    lb = G.HexBatch('tag')
    st = S.statue.location
    if 0.0 < p < 0.97:
        for (bx, by) in anchors:
            a = np.array([bx, by, SC.T2_ROOF + 1.2])
            d = np.array([bx - st.x, by - st.y, 0.0])
            d /= max(np.linalg.norm(d), 1e-6)
            hem = np.array([st.x, st.y, st.z + 0.5]) + d * 0.7
            lb.add(G.beam(hem, a, 0.035), mat=0)
    lb.finalize()
    SC.set_dynamic_mesh(S.taglines, 'TagLines', lb, np.ones(len(lb.t_on), bool), [S.m_rope])


S4_CAM0 = (bearing_pos(214.0, 262.0, 20.0), (0.0, 0.0, 53.0), 38.0)
S4_CAM1 = (bearing_pos(209.0, 250.0, 19.0), (0.0, 0.0, 55.0), 38.0)


def shot_S4(S, v):
    u = (v - 13.5) / 2.5
    hour = 89.52 + 0.2 * u
    fire = TL.ease((v - 13.95) / 0.8)
    surge = 0.7 * max(0.0, 1 - (v - 13.95) / 0.6) * (v > 13.95)
    a, b = S4_CAM0, S4_CAM1
    e = TL.ease_io(u)
    cam = (lerp3(a[0], b[0], e), lerp3(a[1], b[1], e), 38.0)
    meta = SC.pose(S, v, tc=25.2, hour=hour, life=v, hop_t=v * 0.8, sea_t=v * 1.2, water_t=v * 0.5,
                   cloud_t=hour * 0.75, shadow_t=hour * 124.0, cover=0.1, cloud_gain=6.0, shadow_cover=0.25,
                   fire=fire, fire_surge=surge, crane5_loc=QUAY_CRANE, statue_yaw=STATUE_YAW, cam=cam)
    pose_gulls(S, v, (0.0, -60.0), 0)
    meta.update(stars=0.0)
    return meta


S5_CAM = (bearing_pos(47.0, 292.0, 4.8), (0.0, 0.0, 46.0), 35.0)


def shot_S5(S, v):
    u = (v - 16.0) / 4.0
    hour = 138.33 + 0.004 * u
    loc, tgt, lens = S5_CAM
    loc = lerp3(loc, bearing_pos(45.5, 290.0, 4.9), u)
    meta = SC.pose(S, v, tc=29.0, hour=hour, life=v, hop_t=5.0, sea_t=300.0 + v, water_t=120.0 + 0.4 * v,
                   cloud_t=hour * 0.75, shadow_t=hour * 124.0, cover=0.12, cloud_gain=5.0, shadow_cover=0.25,
                   fire=1.0, traffic=False, moon=1.0, crane5_loc=QUAY_CRANE, statue_yaw=STATUE_YAW,
                   cam=(loc, tgt, lens))
    heading_b = 150.0
    hd = math.radians(90.0 - heading_b)
    p0 = np.array([158.5, 181.9])
    pos = p0 + 2.2 * (v - 16.0) * np.array([math.cos(hd), math.sin(hd)])
    brail = 0.1 + 0.5 * TL.ease_io(u)
    n = pose_ship(S, pos, hd, v, math.radians(25.0), brail)
    for i in range(n, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=1.0)
    return meta


SHOT_FN = dict(S1=shot_S1, S2=shot_S2, S3=shot_S3, S4=shot_S4, S5=shot_S5)


def pose(S, f):
    v = f / FPS
    name, a, b = shot_at(v)
    hide_extras(S)
    if hasattr(S, 'taglines'):
        S.taglines.hide_render = name != 'S3'
    meta = SHOT_FN[name](S, v)
    meta.update(shot=name, shot_t=v - a, t=v)
    return meta
