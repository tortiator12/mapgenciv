"""The 20-s Civ1 wonder film "J. S. Bachs Kathedrale" (wunderfilm_13_bach).

Five shots from the Dresden scene (dresden.py, storyboards/runde1_fehlende_wunder.md):
  S1  0.0- 3.0 s  the Elbe landing below the fortress wall, morning: barges with
                  sandstone from the Saxon Switzerland, the treadwheel crane lifting
                  a block ashore, horse carts up the ramp, stonemasons at work
  S2  3.0-10.0 s  time-lapse, from above the city to the south: the walls, piers and
                  stair towers course by course in their scaffold, the bell's foot,
                  the centering, the stone dome ring by ring, the lantern, the
                  centering and the scaffold struck; two days and a night of torches
  S3 10.0-13.0 s  inside, morning light slanting through the high south windows: the
                  organ builders set the pipes into Silbermann's case above the altar,
                  a gilder on his trestle at the retable
  S4 13.0-15.5 s  the Neumarkt at sunset: the church finished, its west front in the
                  last light; the bells ring and the people stream to the portals
  S5 15.5-20.0 s  a winter evening by candlelight, from the upper west gallery: Bach
                  at the organ (from behind, wig and coat), the singers round him on
                  the organ gallery, the congregation in the galleries, chandeliers

Dresden, 51.05 deg N; the autumn sun of the timeline (-9 deg declination).
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import dresden as DR
import figures as FG
import film_colossus20 as FC
import film_lighthouse20 as L
import geometry as G
import life
import scene as SC
import timeline as TL

TL.LATITUDE = math.radians(DR.LATITUDE_DEG)

FPS = 24
DURATION = 20.0
NFRAMES = int(round(FPS * DURATION))
LOOK = 'bright'
SHOTS = [('S1', 0.0, 3.0), ('S2', 3.0, 10.0), ('S3', 10.0, 13.0), ('S4', 13.0, 15.5), ('S5', 15.5, 20.0)]
CUTS = [s[1] for s in SHOTS[1:]]
GRADE = dict(warm={'S1': (0.6, 4.0), 'S2': (0.5, 3.5), 'S3': (1.0, 5.0), 'S4': (1.5, 6.5), 'S5': (1.8, 7.0)},
             gain={'S1': 0.95, 'S2': 0.95, 'S3': 0.92, 'S4': 0.97, 'S5': 0.95},
             dust={'S1': 0.18, 'S2': 0.14, 'S3': 0.0, 'S4': 0.12, 'S5': 0.0})

lerp3 = FC.lerp3


def shot_at(v):
    for name, a, b in SHOTS:
        if a <= v < b:
            return name, a, b
    return SHOTS[-1]


# ================================================================== people and horses
def mat_person_baroque():
    """The lighthouse figures in 1730s Saxony: coats, waistcoats, breeches and
    stockings; skin only on head and hands; the coat's colour from the object."""
    m, nb, out = SC.new_material('PersonBaroque')
    oi = nb.new('ShaderNodeObjectInfo')
    rnd = oi.outputs['Random']
    reg = nb.attr('region').outputs['Fac']
    oz = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[2]
    coat = oi.outputs['Color']
    skin = nb.mix(rnd, (0.55, 0.40, 0.31, 1), (0.66, 0.49, 0.38, 1))
    hair = nb.mix(nb.math('FRACT', nb.math('MULTIPLY', rnd, 3.17)), (0.72, 0.70, 0.64, 1), (0.22, 0.16, 0.10, 1))
    legs = nb.mix(nb.math('FRACT', nb.math('MULTIPLY', rnd, 5.73)), (0.78, 0.76, 0.70, 1), (0.14, 0.12, 0.11, 1))
    is_skin = nb.math('COMPARE', reg, float(L.R_SKIN), 0.5)
    head = nb.math('GREATER_THAN', oz, 1.5)
    low = nb.math('LESS_THAN', oz, 0.55)
    col = coat
    col = nb.mix(nb.math('MULTIPLY', is_skin, low), col, legs)
    col = nb.mix(nb.math('MULTIPLY', is_skin, head), col, skin)
    for k, c in ((L.R_HAIR, hair), (L.R_BEARD, hair), (L.R_BELT, (0.10, 0.07, 0.05, 1)), (L.R_SANDAL, (0.06, 0.05, 0.04, 1)),
                 (L.R_BASKET, (0.52, 0.39, 0.2, 1)), (L.R_POT, (0.55, 0.25, 0.12, 1)), (L.R_WOOD, (0.30, 0.20, 0.11, 1))):
        f = nb.math('COMPARE', reg, float(k), 0.5)
        col = nb.mix(f, col, c)
    b = SC.principled(nb, col, rough=0.85, spec=0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


COATS = [(0.12, 0.10, 0.09, 1), (0.30, 0.22, 0.14, 1), (0.20, 0.24, 0.30, 1), (0.42, 0.12, 0.09, 1), (0.52, 0.48, 0.40, 1),
         (0.16, 0.20, 0.14, 1), (0.36, 0.30, 0.22, 1), (0.06, 0.06, 0.07, 1)]
HORSE_R = [0.36, 0.4, 0.38, 0.17, 0.14, 0.09, 0.03, 0.03, 0.07,
           0.11, 0.06, 0.05, 0.11, 0.06, 0.05, 0.12, 0.065, 0.05, 0.12, 0.065, 0.05]


def horse_joints(ph):
    J = [(0, -0.85, 1.45), (0, 0.0, 1.42), (0, 0.7, 1.46), (0, 1.0, 1.85), (0, 1.22, 2.1),
         (0, 1.56, 1.72), (-0.07, 1.16, 2.28), (0.07, 1.16, 2.28), (0, -1.2, 0.95)]
    for (x, y0, phase) in ((-0.18, 0.72, 0.0), (0.18, 0.72, math.pi), (-0.18, -0.78, math.pi), (0.18, -0.78, 0.0)):
        psi = ph + phase
        fy = 0.3 * math.sin(psi)
        lift = 0.12 * max(0.0, math.cos(psi))
        J += [(x, y0, 1.15), (x, y0 + 0.5 * fy + 0.05, 0.58 + 0.5 * lift), (x, y0 + fy, 0.05 + lift)]
    return J


def build_horses(S, n_pose=10):
    """Draught horses in place of the lighthouse oxen (same skeleton, longer legs,
    a raised neck); the carts are the same."""
    m = SC.mat_simple('Horse', (0.30, 0.18, 0.10), 0.7)
    S.ox_meshes = [L.bake(f'Horse{k}', horse_joints(2 * math.pi * k / n_pose), L.OX_E, HORSE_R, m) for k in range(n_pose)]
    for c, wheels, oxen in S.carts:
        for o, _ in oxen:
            o.data = S.ox_meshes[0]


# ================================================================== build
ORGAN_BUILDER_POSES = [dict(hand_r=(0.2, 0.3, 1.85), hand_l=(-0.05, 0.35, 1.75), lean=0.04, look=(0.0, 1.0, 0.6)),
                       dict(hand_r=(0.15, 0.42, 1.2), hand_l=(-0.12, 0.44, 1.25), lean=0.1, look=(0.0, 1.0, 0.1)),
                       dict(hand_r=(0.22, 0.25, 1.05), hand_l=(-0.21, 0.26, 1.0), lean=0.02, look=(0.3, 1.0, 0.3))]
BACH_POSES = [dict(hand_r=(0.18, 0.5, 0.98), hand_l=(-0.16, 0.5, 1.05), look=(0.0, 1.0, 0.25), lean=0.05),
              dict(hand_r=(0.08, 0.52, 1.05), hand_l=(-0.24, 0.5, 0.98), look=(-0.1, 1.0, 0.3), lean=0.07)]
N_CHANDELIER = 6


def build(res=(1280, 720)):
    S = DR.build(res)
    _compat(S)
    L.build_quay_crane(S)
    L.build_people(S, n_people=200)
    m_p = mat_person_baroque()
    for meshes in S.pose_meshes.values():
        for me in meshes:
            me.materials[0] = m_p
    L.build_carts(S, n=3)
    build_horses(S)
    S.m_sailcloth = L.mat_sailcloth('SailCloth', SC.P['sail'])
    life.build(S, L)
    FC._emissive_smoke(S)
    FC.build_torches(S)
    bpy.data.meshes['Cart'].materials[1] = S.m_stone                     # carts bring sandstone
    S.barges = [SC.link(bpy.data.objects.new(f'Barge{k}', S.barge_me if k < 3 else S.barge_empty)) for k in range(4)]
    for o in S.barges:
        o.pass_index = SC.PASS['ship']
    build_landing_blocks(S)
    build_site_yard(S)
    # the people inside: organ builders, a gilder, Bach, all sculpted
    S.m_figure = FG.mat_figure()
    S.fig_builders = [FG.figure_mesh(f'OrganBuilder{k}', 'craftsman', p, S.m_figure) for k, p in enumerate(ORGAN_BUILDER_POSES)]
    S.builders = []
    for k in range(3):
        o = SC.link(bpy.data.objects.new(f'Builder{k}', S.fig_builders[0]))
        o.pass_index = SC.PASS['worker']
        o.color = ((0.36, 0.25, 0.15, 1.0), (0.28, 0.28, 0.27, 1.0), (0.45, 0.36, 0.22, 1.0))[k]
        S.builders.append(o)
    S.fig_bach = [FG.figure_mesh(f'Bach{k}', 'organist', p, S.m_figure) for k, p in enumerate(BACH_POSES)]
    S.bach = SC.link(bpy.data.objects.new('Bach', S.fig_bach[0]))
    S.bach.color = (0.09, 0.075, 0.065, 1.0)
    S.bach.pass_index = SC.PASS['worker']
    build_trestles(S)
    build_chandeliers(S)
    build_church_air(S)
    return S


def _compat(S):
    """Six cranes (jib, rope, a sandstone block in a sling); crane 5 becomes the
    treadwheel crane of the landing."""
    cm, S.crane_tip = SC.crane_mesh([S.m_wood, S.m_rope])
    rope_b = G.HexBatch('rope')
    rope_b.add(G.beam([0, 0, -1.0], [0, 0, 0.0], 0.07), mat=0)
    rope_b.finalize()
    rope_me = SC.hex_mesh('RopeUnit', rope_b, np.ones(1, bool), [S.m_rope])
    load_b = G.HexBatch('stone_load')
    load_b.add(G.box(0, 0, -1.0, 1.5, 0.9, 0.75), mat=0)
    load_b.add(G.beam([-0.6, 0, -1.0], [0, 0, 0.0], 0.03), mat=1)
    load_b.add(G.beam([0.6, 0, -1.0], [0, 0, 0.0], 0.03), mat=1)
    load_b.finalize()
    load_me = SC.hex_mesh('StoneLoad', load_b, np.ones(3, bool), [S.m_stone, S.m_rope])
    S.cranes = []
    for i in range(6):
        objs = []
        for nm, me in (('Crane', cm), ('Rope', rope_me), ('Load', load_me)):
            o = SC.link(bpy.data.objects.new(f'{nm}{i}', me))
            o.pass_index = SC.PASS['crane']
            o.hide_render = True
            objs.append(o)
        S.cranes.append(tuple(objs))
    S.crane_tip_tall = S.crane_tip


LANDING_BLOCKS = [(-95.0 + 2.1 * i, 232.0 + 1.6 * j, 0.3 * ((i + j) % 3)) for i in range(7) for j in range(3) if (i * 3 + j) % 4]


def build_landing_blocks(S):
    """Sandstone blocks landed on the quay, some dressed, some rough."""
    bb = G.HexBatch('landing_blocks')
    rng = np.random.default_rng(3)
    for (x, y, rot) in LANDING_BLOCKS:
        z = DR.STRAND_Z - 0.2
        h = rng.uniform(0.6, 1.0)
        bb.add(G.box(x, y, z, rng.uniform(1.3, 1.8), rng.uniform(0.8, 1.1), h, rot), mat=0)
        if rng.random() < 0.4:
            bb.add(G.box(x + 0.1, y, z + h, rng.uniform(1.0, 1.4), 0.8, rng.uniform(0.5, 0.8), rot + 0.1), mat=0)
    for k in range(10):                                                  # chips round the masons' benches
        x, y = -84.0 + rng.uniform(-6, 6), 228.0 + rng.uniform(-3, 3)
        bb.add(G.box(x, y, DR.STRAND_Z - 0.18, rng.uniform(0.1, 0.3), rng.uniform(0.1, 0.25), 0.08, rng.uniform(0, 3)), mat=0)
    bb.finalize()
    S.landing_blocks = SC.link(bpy.data.objects.new('LandingBlocks', SC.hex_mesh('LandingBlocks', bb, np.ones(len(bb.t_on), bool), [S.m_stone])))
    S.landing_blocks.pass_index = SC.PASS['props']


def build_site_yard(S):
    """The works on the Neumarkt round the church: stacks of sandstone blocks, the
    masons' lodges, a lime pit, timber for the centering, a saw pit."""
    yb = G.HexBatch('site_yard')
    rng = np.random.default_rng(1726)
    for k in range(26):                                                  # block stacks, in rows
        side = k % 4
        u = rng.uniform(-0.8, 0.8)
        d = rng.uniform(27.0, 36.0)
        x, y = ((d, u * 30.0), (u * 30.0, d), (-d, u * 30.0), (u * 30.0, -d))[side]
        for lay in range(1 + (k % 3)):
            yb.add(G.box(x, y, 0.8 * lay, 3.2, 1.6, 0.78, rng.uniform(-0.05, 0.05) + (math.pi / 2 if side in (0, 2) else 0.0)), mat=0)
    for (x, y, rot) in ((-44.0, -38.0, 0.0), (38.0, -40.0, 0.0), (-44.0, 34.0, 0.3), (34.0, 36.0, -0.2)):
        yb.add(G.box(x, y, 0.0, 12.0, 6.0, 3.2, rot), mat=1)             # masons' lodges
        yb.add(G.tent(x, y, 3.2, 12.6, 6.6, 2.2, rot), mat=2)
    yb.add(G.box(-30.0, 44.0, -0.1, 5.0, 4.0, 0.15), mat=3)              # the lime pit
    for k in range(10):                                                  # timber for the centering
        yb.add(G.box(40.0, -8.0 + 0.4 * (k % 5), 0.35 * (k // 5), 0.35, 12.0, 0.35), mat=1)
    yb.finalize()
    S.site_yard = SC.link(bpy.data.objects.new('SiteYard', SC.hex_mesh('SiteYard', yb, np.ones(len(yb.t_on), bool),
                                                                    [S.m_stone, S.m_wood, S.m_roof,
                                                                     SC.mat_simple('LimePit', (0.86, 0.85, 0.80), 0.9)])))
    S.site_yard.pass_index = SC.PASS['props']


def build_trestles(S):
    """S3: the organ builders' staging in front of the case, the gilder's trestle."""
    tb = G.HexBatch('trestles')
    ox = DR.HALF + 2.0
    for y in (-4.0, 4.0):                                                # a staging on the organ gallery
        for dx in (-0.7, 0.7):
            tb.add(G.beam([ox + 0.9 + dx, y, DR.ORGAN_Z], [ox + 0.9 + dx, y, DR.ORGAN_Z + 3.0], 0.12), mat=0)
    tb.add(G.box(ox + 0.9, 0, DR.ORGAN_Z + 3.0, 1.6, 8.6, 0.08), mat=1)
    ax_ = DR.HALF + DR.APSE_R - 3.0
    for dy in (-1.6, 1.6):                                               # the gilder's trestle at the retable
        for dx in (-0.9, -0.1):
            tb.add(G.beam([ax_ - 1.0 + dx, dy, 0.0], [ax_ - 1.0 + dx, dy, 3.2], 0.1), mat=0)
    tb.add(G.box(ax_ - 1.5, 0, 3.2, 1.2, 3.6, 0.08), mat=1)
    tb.finalize()
    S.trestles = SC.link(bpy.data.objects.new('Trestles', SC.hex_mesh('Trestles', tb, np.ones(len(tb.t_on), bool), [S.m_wood, S.m_plank])))
    S.trestles.pass_index = SC.PASS['timber']


CHANDELIERS = [(0.0, 0.0), (-5.0, -3.6), (-5.0, 3.6), (5.0, -3.6), (5.0, 3.6), (-8.5, 0.0)]


def build_chandeliers(S):
    """Brass chandeliers on long chains in the central space, a ring of candles each."""
    S.chandeliers = []
    cb = G.HexBatch('chandelier')
    n = 12
    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        cb.add(G.beam([1.1 * math.cos(a0), 1.1 * math.sin(a0), 0.0], [1.1 * math.cos(a1), 1.1 * math.sin(a1), 0.0], 0.06), mat=0)
        cb.add(G.beam([0, 0, 0.4], [1.1 * math.cos(a0), 1.1 * math.sin(a0), 0.0], 0.03), mat=0)
        cb.add(G.box(1.1 * math.cos(a0), 1.1 * math.sin(a0), 0.02, 0.05, 0.05, 0.22), mat=1)
    cb.add(G.beam([0, 0, -0.5], [0, 0, 0.6], 0.12), mat=0)
    cb.add(G.beam([0, 0, 0.6], [0, 0, 30.0], 0.025), mat=0)             # the chain up into the dome
    cb.finalize()
    me = SC.hex_mesh('Chandelier', cb, np.ones(len(cb.t_on), bool), [S.m_gold, SC.mat_simple('Wax', (0.85, 0.80, 0.65), 0.6)])
    fb = G.HexBatch('chand_flames')                                     # a small flame on each candle
    for k in range(n):
        a0 = 2 * math.pi * k / n
        fb.add(G.box(1.1 * math.cos(a0), 1.1 * math.sin(a0), 0.0, 0.03, 0.03, 0.07, a0), mat=0)
    fb.finalize()
    fm = SC.hex_mesh('ChandFlames', fb, np.ones(n, bool), [S.m_torch])
    for i, (x, y) in enumerate(CHANDELIERS):
        o = SC.link(bpy.data.objects.new(f'Chandelier{i}', me))
        o.pass_index = SC.PASS['props']
        f = SC.link(bpy.data.objects.new(f'ChandFlames{i}', fm))
        f.visible_shadow = False
        ld = bpy.data.lights.new(f'ChandLight{i}', 'POINT')
        ld.color = (1.0, 0.62, 0.3)
        ld.shadow_soft_size = 0.8
        lo = SC.link(bpy.data.objects.new(f'ChandLight{i}', ld))
        S.chandeliers.append((o, f, lo, (x, y, 14.6 + 0.9 * (i % 2))))
    S.organ_lights = []
    for i, y in enumerate((-3.0, 3.0)):                                  # candles on the organ gallery
        ld = bpy.data.lights.new(f'OrganLight{i}', 'POINT')
        ld.color = (1.0, 0.6, 0.28)
        ld.shadow_soft_size = 0.2
        S.organ_lights.append(SC.link(bpy.data.objects.new(f'OrganLight{i}', ld)))


def build_church_air(S):
    """S3: the dust in the morning light (a thin volume in the church)."""
    vb = G.HexBatch('church_air')
    vb.add(G.box(0, 0, 0.1, 36.0, 36.0, 23.5), mat=0)
    vb.finalize()
    m = bpy.data.materials.new('ChurchAir')
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    vs = nt.nodes.new('ShaderNodeVolumeScatter')
    vs.inputs['Density'].default_value = 0.006
    vs.inputs['Anisotropy'].default_value = 0.5
    o_ = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(vs.outputs[0], o_.inputs['Volume'])
    S.church_air = SC.link(bpy.data.objects.new('ChurchAir', SC.hex_mesh('ChurchAir', vb, np.ones(1, bool), [m])))


def hide_extras(S):
    for o in S.people + S.builders + S.barges + [S.tread, S.bach, S.trestles, S.church_air, S.site_yard]:
        o.hide_render = True
    for c, wheels, oxen in S.carts:
        c.hide_render = True
        for w, _ in wheels:
            w.hide_render = True
        for o, _ in oxen:
            o.hide_render = True
    for trip in S.cranes:
        for o in trip:
            o.hide_render = True
    for o, f, lo, _ in S.chandeliers:
        o.hide_render = f.hide_render = lo.hide_render = True
    for lo in S.organ_lights:
        lo.hide_render = True
    life.hide_all(S)
    FC.hide_torches(S)
    S.post_smoke = []


def env(S, v, hour, cam, tc, rot, **kw):
    return DR.pose(S, v, tc=tc, hour=hour, sea_t=30.0 + v, water_t=10.0 + 0.4 * v, cloud_t=hour * 0.75,
                   shadow_t=hour * 124.0, cover=kw.pop('cover', 0.4), cloud_gain=7.0, shadow_cover=0.35, hdri=kw.pop('hdri', 1.0),
                   hdri_rot=rot, cam=cam, **kw)


def crane_at(S, i, base, slew, hop_t, ground=None, seed=0):
    """Crane i standing at base (on finished masonry or the ground), its load going
    up from the ground below the jib's tip (or from `ground`) to the tip."""
    c, rope, load = S.cranes[i]
    c.matrix_world = Matrix.Translation(base) @ Matrix.Rotation(slew, 4, 'Z')
    c.hide_render = rope.hide_render = load.hide_render = False
    tip = c.matrix_world @ Vector(S.crane_tip)
    gl = DR.ground_z(tip.x, tip.y) if ground is None else ground
    lz = gl + 1.0 + SC.hop(11 + seed, hop_t, 3.0) * (tip.z - gl - 3.0)
    load.matrix_world = Matrix.Translation((tip.x, tip.y, lz)) @ Matrix.Rotation(slew, 4, 'Z')
    rope.matrix_world = Matrix.Translation(tip) @ Matrix.Diagonal((1, 1, max(tip.z - lz, 0.3), 1))
    return tip


# ================================================================== shots
S1_SKY, S2_SKY, S3_SKY, S4_SKY, S5_SKY = 1.2, 2.4, 0.0, 3.4, 5.0
S1_CAM0 = ((-24.0, 266.0, DR.WATER_Z + 5.5), (-120.0, 236.0, -2.5))
S1_CAM1 = ((-27.0, 264.5, DR.WATER_Z + 5.3), (-121.0, 236.5, -2.4))
BARGE_SPOTS = [(-82.0, 248.8, 0.0), (-74.6, 261.0, math.pi / 2 + 0.02), (-110.0, 251.0, -0.03), (-140.0, 283.0, 0.25)]
QUAY_CRANE = (-80.5, 241.0)


def shot_S1(S, v):
    """Morning at the landing, real time: barges alongside, the crane swings a block
    ashore, carts go up the ramp to the gate, masons dress blocks on the quay."""
    u = v / 3.0
    e = TL.ease_io(u)
    hour = 8.1 + 0.1 * u
    cam = (lerp3(S1_CAM0[0], S1_CAM1[0], e), lerp3(S1_CAM0[1], S1_CAM1[1], e), 30.0)
    meta = env(S, v, hour, cam, 0.35, S1_SKY + 0.002 * v)
    FC.smoke_light(S, hour)
    for k, (x, y, r) in enumerate(BARGE_SPOTS):                          # the barges bob a little at their moorings
        z = DR.WATER_Z + 0.35 + 0.04 * math.sin(1.3 * v + k)
        S.barges[k].matrix_world = Matrix.Translation((x, y, z)) @ Matrix.Rotation(r + 0.01 * math.sin(0.9 * v + k), 4, 'Z')
        S.barges[k].hide_render = False
    # the quay crane: a block from the middle barge up and round onto the quay
    c, rope, load = S.cranes[5]
    q = TL.ease_io(np.clip((v - 0.2) / 2.6, 0, 1))
    slew = math.radians(80.0 + 125.0 * q)
    c.matrix_world = Matrix.Translation((QUAY_CRANE[0], QUAY_CRANE[1], DR.STRAND_Z - 0.2)) @ Matrix.Rotation(slew, 4, 'Z')
    c.hide_render = rope.hide_render = load.hide_render = False
    tip = c.matrix_world @ Vector(S.crane_tip)
    lz = tip.z - 3.0 - 2.5 * (1.0 - math.sin(math.pi * q))
    load.matrix_world = Matrix.Translation((tip.x, tip.y, lz)) @ Matrix.Rotation(slew, 4, 'Z')
    rope.matrix_world = Matrix.Translation(tip) @ Matrix.Diagonal((1, 1, max(tip.z - lz, 0.3), 1))
    k = L.pose_treadwheel(S, -0.9 * v, walkers=2, first_person=0, walk_ph=v * 3.0)
    # horse carts: one loading at the quay, two on the ramp up to the gate
    for ci, (x0, y0, x1, y1, d0) in enumerate(((-70.0, 236.0, -70.0, 236.0, 0.0), (-75.0, 226.0, -75.0, 212.0, 0.1),
                                              (-75.0, 229.0, -75.0, 214.0, 0.55))):
        d = min(d0 + 0.12 * v, 1.0)
        x, y = x0 + (x1 - x0) * d, y0 + (y1 - y0) * d
        hd = math.atan2(y1 - y0, x1 - x0) if (x1, y1) != (x0, y0) else math.pi / 2
        FC.place_cart(S, ci, (x, y), hd, 6.0 * v * (0 if ci == 0 else 1), DR.ground_z(x, y) if y > DR.WALL_Y + 12 else
                      DR.STRAND_Z + (DR.WALL_Y + 13.0 - y) / 12.0 * (-0.3 - DR.STRAND_Z))
    rng = np.random.default_rng(8)
    for j in range(12):                                                  # masons, carriers, bargemen
        x, y, _ = LANDING_BLOCKS[(3 * j) % len(LANDING_BLOCKS)]
        x += rng.uniform(-1.2, 1.2)
        y += rng.uniform(-1.5, -0.8)
        L.place_person(S, k, (x, y, DR.STRAND_Z - 0.2), rng.uniform(0, 2 * math.pi), ('hammer', 'hammer', 'carry', 'stand', 'haul')[j % 5],
                       2.0 * v + j)
        S.people[k].color = COATS[j % len(COATS)]
        k += 1
    for j in range(4):
        bx, by, _ = BARGE_SPOTS[j % 3]
        L.place_person(S, k, (bx - 4.0 + 3.0 * j, by, DR.WATER_Z + 1.1), rng.uniform(0, 6), ('haul', 'stand')[j % 2], 2.0 * v + j)
        S.people[k].color = COATS[(j + 3) % len(COATS)]
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


S2_LAPSE = FC.Lapse(3.0, 10.0, [(3.0, 7.4), (5.55, 17.6), (5.85, 18.9), (6.2, 29.5), (6.5, 30.9), (10.0, 40.3)], 0.25, 9.0)


def s2_cam(v):
    u = TL.ease_io((v - 3.0) / 7.0)
    b = math.radians(200.0 - 34.0 * u)                                   # from the south-south-west round to the south
    dist = 185.0 - 25.0 * u
    loc = (dist * math.sin(b), dist * math.cos(b), 72.0 + 14.0 * u)
    return loc, (0.0, 4.0, 22.0 + 16.0 * u), 30.0


def dome_level(tc):
    """Height of the dome's top course at tc."""
    if tc < DR.TC_DOME[0]:
        return 31.0
    return 31.0 + (DR.DOME_TOP - 31.0) * min((tc - DR.TC_DOME[0]) / (DR.TC_DOME[1] - DR.TC_DOME[0]), 1.0)


def shot_S2(S, v):
    lp = S2_LAPSE
    hour = lp.hour(v)
    tc = lp.tc(v)
    cam = s2_cam(v)
    meta = env(S, v, hour, cam, tc, S2_SKY + 0.05 * (v - 3.0), cover=0.35 + 0.06 * math.sin(v), sky_log=True)
    day = meta['day']
    FC.smoke_light(S, hour, fires=1.0 - day)
    hop_t = 2.0 * v
    S.site_yard.hide_render = tc > DR.TC_SCAF_DOWN[1]
    k = 0
    # cranes: on the wall tops while the walls rise, then on the dome's top course
    if tc < DR.TC_WALLS[1]:
        z = S.sched.height(tc)
        for i, (x, y, a0) in enumerate(((-DR.HALF + 1.0, 0.0, 180.0), (0.0, -DR.HALF + 1.0, 270.0), (0.0, DR.HALF - 1.0, 90.0))):
            if z > 3.0:
                crane_at(S, i, (x, y, z), math.radians(a0 + 50.0 * (SC.smooth_rand(20 + i, hop_t, 1.1) - 0.5)), hop_t, seed=i)
    elif tc < DR.TC_LANTERN[1]:
        z = dome_level(tc)
        for i, a in enumerate((200.0, 20.0)):
            r = DR.dome_r(z) - 1.2
            base = (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), z)
            crane_at(S, i, base, math.radians(a + 45.0 * (SC.smooth_rand(30 + i, hop_t, 1.0) - 0.5)), hop_t, seed=5 + i)
    # people: masons on the scaffold and the works, tiny from up here
    top = S.sched.height(tc) if tc < DR.TC_WALLS[1] else dome_level(tc)
    for j in range(24):
        if SC.hop(j + 50, hop_t, 2.0) > 0.8 * (0.3 + 0.7 * day):
            continue
        a = 2 * math.pi * SC.hop(j + 60, hop_t, 2.0)
        if j < 12:
            r = (DR.HALF + 1.0) if tc < DR.TC_WALLS[1] else DR.dome_r(top) + 0.8
            x, y, z = r * math.cos(a), r * math.sin(a), top
        else:
            r = 30.0 + 18.0 * SC.hop(j + 70, hop_t, 2.0)
            x, y = r * math.cos(a), r * math.sin(a)
            z = DR.ground_z(x, y)
        L.place_person(S, k, (x, y, z), a, ('carry', 'hammer', 'haul', 'walk')[j % 4], 2 * math.pi * SC.hop(j + 80, hop_t, 2.0))
        S.people[k].color = COATS[j % len(COATS)]
        k += 1
    # torches round the works at night, a smoking lime kiln by day
    spots = [(34.0 * math.cos(2 * math.pi * i / 10), 34.0 * math.sin(2 * math.pi * i / 10), 0.0) for i in range(10)]
    FC.pose_torches(S, spots, TL.smoothstep(0.55, 0.1, day), v)
    FC.smoke(S, [life.Plume((52.0, -40.0, 4.0), n=8, life=10.0, rise=1.3, drift=1.4, size0=1.5, grow=0.8, dens=0.5, seed=3)],
             60.0 + 2.0 * v)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.6)
    return meta


S3_TC = (8.93, 9.1)                     # the pipes go in one by one, the gilding is finished


def shot_S3(S, v):
    """Inside, 09:30, a slow time-lapse: the organ builders set the pipes, a gilder
    at the retable; the sun slants through the south windows into the dust."""
    u = (v - 10.0) / 3.0
    e = TL.ease_io(u)
    hour = 9.4 + 0.3 * u
    tc = S3_TC[0] + (S3_TC[1] - S3_TC[0]) * u
    c0, c1 = (7.2, -13.4, DR.GALLERIES[1] + 1.7), (7.8, -12.9, DR.GALLERIES[1] + 1.75)
    cam = (lerp3(c0, c1, e), (24.5, 0.5, 15.5), 28.0)
    meta = env(S, v, hour, cam, tc, S3_SKY, cover=0.25)
    S.church_air.hide_render = False
    S.trestles.hide_render = False
    ox = DR.HALF + 2.0
    spots = [((ox + 0.9, -2.0, DR.ORGAN_Z + 3.08), 0.0), ((ox + 0.9, 2.2, DR.ORGAN_Z + 3.08), 0.0),
             ((DR.HALF + DR.APSE_R - 4.5, 0.3, 3.28), 0.0)]
    for j, (pos, _) in enumerate(spots):
        w = S.builders[j]
        kp = int(SC.hop(j + 40, v * 2.0, 1.2) * 2.99) if j < 2 else 0
        w.data = S.fig_builders[kp]
        w.matrix_world = Matrix.Translation(pos) @ Matrix.Rotation(-math.pi / 2, 4, 'Z')    # facing east, to the work
        w.hide_render = False
    meta.update(stars=0.0, expo_mul=0.9)
    return meta


S4_HOURS = (16.55, 16.9)


def shot_S4(S, v):
    """The Neumarkt at sunset: the church finished; the people stream to the portals."""
    u = (v - 13.0) / 2.5
    e = TL.ease_io(u)
    hour = S4_HOURS[0] + (S4_HOURS[1] - S4_HOURS[0]) * u
    c0, c1 = (-51.0, 41.0, 2.0), (-49.0, 39.5, 2.1)
    cam = (lerp3(c0, c1, e), (0.0, 0.0, 34.0), 18.0)
    meta = env(S, v, hour, cam, 9.6, S4_SKY + 0.002 * v, cover=0.3)
    FC.smoke_light(S, hour)
    rng = np.random.default_rng(14)
    k = 0
    for j in range(46):                                                  # walking to the west and north portals
        west = j % 2 == 0
        tx, ty = (-DR.HALF - 1.0, 0.0) if west else (0.0, DR.HALF + 1.0)
        a = rng.uniform(-0.9, 0.9) + (math.radians(150.0) if west else math.radians(95.0))
        d0 = rng.uniform(8.0, 50.0)
        d = d0 - 1.3 * (v - 13.0) * rng.uniform(0.8, 1.2)
        if d < 2.0:
            continue
        x, y = tx + d * math.cos(a), ty + d * math.sin(a)
        L.place_person(S, k, (x, y, DR.ground_z(x, y)), math.atan2(ty - y, tx - x), 'walk', 3.0 * v + j)
        S.people[k].color = COATS[j % len(COATS)]
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


S5_HOUR = 18.3


def shot_S5(S, v):
    """A winter evening by candlelight, from the upper west gallery: Bach at the
    organ, the singers round him, the congregation in the galleries."""
    u = (v - 15.5) / 4.5
    e = TL.ease_io(u)
    c0, c1 = (-16.4, -0.4, DR.GALLERIES[2] + 2.5), (-15.0, -0.3, DR.GALLERIES[2] + 2.45)
    cam = (lerp3(c0, c1, e), (24.0, 0.0, DR.ORGAN_Z + 3.3), 45.0)
    meta = env(S, v, S5_HOUR, cam, 9.6, S5_SKY, cover=0.2, hdri=0.0, moon=0.3)
    for i, (o, f, lo, (x, y, z)) in enumerate(S.chandeliers):
        fl = 0.9 + 0.1 * SC.smooth_rand(i + 300, v, 6.0)
        o.matrix_world = Matrix.Translation((x, y, z))
        f.matrix_world = Matrix.Translation((x, y, z + 0.24)) @ Matrix.Diagonal((1.0, 1.0, fl, 1.0))
        lo.location = (x, y, z + 0.5)
        lo.data.energy = 420.0 * fl
        o.hide_render = f.hide_render = lo.hide_render = False
    S.m_torch.node_tree.nodes['torch_k'].outputs[0].default_value = 1.0
    ox = DR.HALF + 2.0
    for i, lo in enumerate(S.organ_lights):
        lo.location = (ox - 0.2, (-2.4, 2.4)[i], DR.ORGAN_Z + 2.2)
        lo.data.energy = 260.0 * (0.9 + 0.1 * SC.smooth_rand(i + 320, v, 7.0))
        lo.hide_render = False
    S.bach.data = S.fig_bach[int(v * 1.7) % 2]
    S.bach.matrix_world = Matrix.Translation((ox + 0.75, 0.0, DR.ORGAN_Z)) @ Matrix.Rotation(-math.pi / 2, 4, 'Z')
    S.bach.hide_render = False
    k = 0
    rng = np.random.default_rng(21)
    for j in range(9):                                                   # the singers on the organ gallery
        y = -4.4 + 1.1 * j
        if abs(y) < 1.3:
            continue
        L.place_person(S, k, (ox - 0.6 + rng.uniform(-0.3, 0.3), y, DR.ORGAN_Z), math.pi, 'stand', rng.uniform(0, 6))
        S.people[k].color = COATS[(j * 3) % len(COATS)]
        k += 1
    for gi, zg in enumerate(DR.GALLERIES):                               # the congregation at the gallery parapets
        for j in range(22):
            a = math.radians(45.0) + (2 * math.pi - math.radians(90.0)) * (j + 0.5 * gi) / 22
            if math.cos(a) < -0.75 and gi == 2:
                continue                                                 # our own gallery stays clear
            r = DR.PIER_R + 2.0 + 0.4 * (j % 2)
            L.place_person(S, k, (r * math.cos(a), r * math.sin(a), zg), a + math.pi, 'stand', rng.uniform(0, 6))
            S.people[k].color = COATS[(j + gi) % len(COATS)]
            k += 1
    for j in range(30):                                                  # and in the pews
        x = -8.0 + 1.9 * (j % 9)
        y = (1.8 + 2.4 * (j // 9)) * (1 if j % 2 else -1)
        L.place_person(S, k, (x, y, 0.0), 0.0, 'stand', rng.uniform(0, 6))
        S.people[k].color = COATS[j % len(COATS)]
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0, expo_mul=1.0)
    return meta


SHOT_FN = dict(S1=shot_S1, S2=shot_S2, S3=shot_S3, S4=shot_S4, S5=shot_S5)


def pose(S, f):
    v = f / FPS
    name, a, b = shot_at(v)
    hide_extras(S)
    meta = SHOT_FN[name](S, v)
    life.apply_wakes(S)
    meta.update(shot=name, shot_t=v - a, t=v, smoke=S.post_smoke, smoke_light=getattr(S, 'smoke_rgb', [1.0, 1.0, 1.0]))
    return meta
