"""The 20-s Civ1 wonder film 'Koloss von Rhodos' (wunderfilm_03_colossus).

Five shots from the one Rhodes scene (rhodes.py, storyboards/runde1_fehlende_wunder.md):
  S1  0.0- 3.0 s  the harbour, morning, real time: ships unload copper, tin and
                  iron, the siege engines of Demetrios lie broken up on the mole
  S2  3.0- 8.0 s  time-lapse, total: marble pedestal, the legs on their iron
                  frame, the mound rising round the figure, a night of forge fires
  S3  8.0-11.5 s  on top of the mound, afternoon: furnaces and bellows, plates
                  set on the head from the scaffold
  S4 11.5-15.0 s  time-lapse, total: the mound carried away, the bronze appears
                  from the top down
  S5 15.0-20.0 s  sunset: a merchant galley rows past the Colossus towards the
                  harbour, a sacrifice burns at the pedestal, gulls

Each shot drives rhodes.pose() with its own clocks (construction time tc,
hour of day, animation) and adds the life it needs.  The figures, carts,
gulls, ships and boats are those of the lighthouse film (film_lighthouse20,
life.py).  No text in the picture; the game shows the titles.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import film_lighthouse20 as L
import geometry as G
import life
import rhodes as RH
import scene as SC
import timeline as TL

TL.LATITUDE = math.radians(36.4)      # Rhodes (the sun, the moon and the stars follow)
FPS = 24
DURATION = 20.0
NFRAMES = int(round(FPS * DURATION))   # 480
LOOK = 'bright'
SHOTS = [('S1', 0.0, 3.0), ('S2', 3.0, 8.0), ('S3', 8.0, 11.5), ('S4', 11.5, 15.0), ('S5', 15.0, 20.0)]
CUTS = [s[1] for s in SHOTS[1:]]
# the grade of each shot (stylize.py --film): warm shift (a*, b*), gain, warm dust haze
GRADE = dict(warm={'S1': (0.8, 4.5), 'S2': (0.6, 4.0), 'S3': (0.5, 3.5), 'S4': (0.3, 3.0), 'S5': (1.6, 6.0)},
             gain={'S1': 0.93, 'S2': 0.94, 'S3': 0.95, 'S4': 0.96, 'S5': 0.97},
             dust={'S1': 0.28, 'S2': 0.12, 'S3': 0.15, 'S4': 0.14, 'S5': 0.1})


def shot_at(v):
    for name, a, b in SHOTS:
        if a <= v < b:
            return name, a, b
    return SHOTS[-1]


def lerp3(a, b, u):
    return tuple(a[i] + (b[i] - a[i]) * u for i in range(3))


def bearing_pos(bearing_deg, dist, z, centre=(0.0, 0.0)):
    b = math.radians(bearing_deg)
    return (centre[0] + dist * math.sin(b), centre[1] + dist * math.cos(b), z)


# ------------------------------------------------------------------ clocks
def _daylight(hour):
    el, _ = TL.sun_angles(hour)
    return TL.smoothstep(math.radians(-7), math.radians(5), el)


class Lapse:
    """Time-lapse clocks of a shot: hour of day by keys, construction time tc
    advancing with the daylight (work slows to a crawl at night)."""

    def __init__(self, v0, v1, hour_keys, tc0, tc1, night_rate=0.1):
        self.v0, self.v1, self.keys, self.tc0, self.tc1 = v0, v1, hour_keys, tc0, tc1
        self.V = np.linspace(v0, v1, 1201)
        R = np.array([night_rate + (1 - night_rate) * _daylight(self.hour(v)) for v in self.V])
        W = np.concatenate([[0.0], np.cumsum(0.5 * (R[1:] + R[:-1]) * np.diff(self.V))])
        self.W = W / W[-1]

    def hour(self, v):
        return TL._pchip([k[0] for k in self.keys], [k[1] for k in self.keys], v)

    def tc(self, v, ease=1.0):
        w = float(np.interp(v, self.V, self.W))
        return self.tc0 + (self.tc1 - self.tc0) * w ** ease


# S2: a day's work, a short night of forge fires, the next morning
S2_LAPSE = Lapse(3.0, 8.0, [(3.0, 8.4), (5.75, 17.3), (6.15, 18.5), (6.45, 19.4), (6.8, 29.0), (7.15, 29.9),
                            (8.0, 32.2)], 0.12, 6.9)
# S4: one day, the mound carried away (starts with the crown in place, the scaffold standing)
S4_LAPSE = Lapse(11.5, 15.0, [(11.5, 8.6), (15.0, 16.4)], 9.3, 12.35, night_rate=0.2)

S1_SKY, S2_SKY, S3_SKY, S4_SKY, S5_SKY = 2.2, 0.4, 1.1, 3.0, 4.4   # where the photographed clouds sit (rad)


# ================================================================== build
def build(res=(1280, 720)):
    S = RH.build(res)
    _compat(S)
    L.build_lighter(S)
    L.build_quay_crane(S)
    L.build_people(S, n_people=230)
    L.build_carts(S, n=4)
    L.build_gulls(S, n=14)
    L.build_ship(S)
    life.build(S, L)
    _emissive_smoke(S)
    life.build_clutter(S, CLUTTER)
    build_oars(S)
    build_torches(S)
    build_baskets(S)
    return S


def _compat(S):
    """The objects the lighthouse helpers expect: crane 5 (the quay crane with
    its treadwheel), a site crane (0) and the lighters (barges)."""
    cm, S.crane_tip = SC.crane_mesh([S.m_wood, S.m_rope])
    rope_b = G.HexBatch('rope')
    rope_b.add(G.beam([0, 0, -1.0], [0, 0, 0.0], 0.09), mat=0)
    rope_b.finalize()
    rope_me = SC.hex_mesh('RopeUnit', rope_b, np.ones(1, bool), [S.m_rope])
    load_b = G.HexBatch('load')
    load_b.add(G.box(0, 0, -1.0, 1.4, 1.0, 0.7), mat=0)
    load_b.finalize()
    load_me = SC.hex_mesh('Load', load_b, np.ones(1, bool), [S.m_stone])
    ingot_b = G.HexBatch('ingot_load')
    for k in range(6):
        ingot_b.add(G.box(0, 0, -1.0 + 0.065 * k, 0.62, 0.42, 0.06, (k % 2) * math.pi / 2), mat=0)
    ingot_b.add(G.beam([-0.4, 0, -1.0], [0, 0, 0.0], 0.04), mat=1)
    ingot_b.add(G.beam([0.4, 0, -1.0], [0, 0, 0.0], 0.04), mat=1)
    ingot_b.finalize()
    S.ingot_load_me = SC.hex_mesh('IngotLoad', ingot_b, np.ones(len(ingot_b.t_on), bool),
                                  [bpy.data.materials['Copper'], S.m_rope])
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
    S.barges = []
    for i in range(2):
        objs = []
        for nm in ('Barge', 'BargeRig', 'BargeCargo'):
            o = SC.link(bpy.data.objects.new(f'{nm}{i}', bpy.data.meshes.new(f'{nm}{i}')))
            o.pass_index = SC.PASS['ship']
            o.hide_render = True
            objs.append(o)
        objs[1].parent = objs[0]
        objs[2].parent = objs[0]
        S.barges.append(tuple(objs))
    cg = G.HexBatch('barge_cargo')                  # ingots and iron bars in the lighter's hold
    for k in range(4):
        cg.add(G.box(-3.0 + 2.0 * k, 0.0, 1.1, 1.3, 1.0, 0.55), mat=0)
    for k in range(10):
        cg.add(G.beam([2.5, -1.2 + 0.24 * k, 1.2], [6.3, -1.2 + 0.24 * k, 1.2], 0.09), mat=1)
    cg.finalize()
    me = SC.hex_mesh('BargeCargo', cg, np.ones(len(cg.t_on), bool), [bpy.data.materials['Copper'], S.m_iron])
    for h, r, c in S.barges:
        c.data = me


def mat_smoke_lit(name, lo, hi):
    """Smoke puff lit by a per-frame value instead of by light samples: at the
    film's six samples a diffuse/translucent puff breaks up into dark specks.
    Same soft falloff and evolving noise as life.mat_smoke; the top of each
    puff a little brighter, as if lit from above."""
    m, nb, out = SC.new_material(name)
    tc = nb.new('ShaderNodeTexCoord')
    u, v, _ = nb.sep(tc.outputs['UV'])
    du, dv = nb.math('SUBTRACT', u, 0.5), nb.math('SUBTRACT', v, 0.5)
    r = nb.math('MULTIPLY', nb.math('SQRT', nb.math('ADD', nb.math('MULTIPLY', du, du), nb.math('MULTIPLY', dv, dv))), 2.0)
    fall = nb.smooth(1.0, 0.05, r)
    oi = nb.new('ShaderNodeObjectInfo')
    dens, glow, seed = nb.sep(oi.outputs['Color'])
    age = oi.outputs['Alpha']
    w = nb.math('ADD', nb.math('MULTIPLY', seed, 37.0), nb.math('MULTIPLY', age, 1.3))
    # coarse noise only: fine octaves on small, distant puffs turn into pixel specks
    n1 = nb.noise(nb.comb(u, v, 0.0), 1.3, 1.2, 0.45, w=w, dims='4D').outputs['Fac']
    body = nb.smooth(0.18, 0.72, nb.math('ADD', n1, nb.math('MULTIPLY', fall, 0.3)))
    alpha = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.math('POWER', fall, 0.7), body), dens, clamp=True)
    col = nb.mix(nb.math('MULTIPLY', n1, 0.6), tuple(lo) + (1,), tuple(hi) + (1,))
    shade = nb.math('ADD', 0.72, nb.math('MULTIPLY', v, 0.4))
    light = nb.rgb((1.0, 1.0, 1.0), 'smoke_light')
    em = nb.new('ShaderNodeEmission')
    nb.feed(em.inputs['Color'], SC.mul_col(nb, SC.mul_col(nb, col, light), nb.comb(shade, shade, shade)))
    em.inputs['Strength'].default_value = 1.0
    fire = nb.new('ShaderNodeEmission')
    fire.inputs['Color'].default_value = (1.0, 0.45, 0.14, 1)
    nb.feed(fire.inputs['Strength'], nb.math('MULTIPLY', glow, 6.0))
    add = nb.new('ShaderNodeAddShader')
    nb.feed(add.inputs[0], em.outputs[0])
    nb.feed(add.inputs[1], fire.outputs[0])
    tp = nb.new('ShaderNodeBsdfTransparent')
    mix = nb.new('ShaderNodeMixShader')
    nb.feed(mix.inputs[0], alpha)
    nb.feed(mix.inputs[1], tp.outputs[0])
    nb.feed(mix.inputs[2], add.outputs[0])
    nb.feed(out.inputs['Surface'], mix.outputs[0])
    return m


def _emissive_smoke(S):
    S.m_smoke_lit = mat_smoke_lit('SmokeLit', (0.62, 0.60, 0.57), (0.80, 0.78, 0.74))
    S.m_dust_lit = mat_smoke_lit('DustLit', (0.52, 0.42, 0.30), (0.70, 0.58, 0.42))
    S.smoke[0].data.materials[0] = S.m_smoke_lit
    S.dust[0].data.materials[0] = S.m_dust_lit


def smoke(S, plumes, clock, kind=0):
    """Puffs of `plumes` (life.Plume) for postsmoke.py: the same rise, drift and
    spread as life.pose_smoke, but drawn by the stylizer (see postsmoke.py)."""
    for pl in plumes:
        for i in range(pl.n):
            f = (clock / pl.life + (i + 0.37 * pl.seed) / pl.n) % 1.0
            a = f * pl.life
            h = pl.rise * a * (1.0 - 0.25 * f)
            sway = 0.25 * math.sin(0.7 * a + i * 2.1 + pl.seed) * (0.3 + a * 0.2)
            p = pl.pos + np.array([0, 0, h]) + pl.wind * (pl.drift * a ** 1.15) \
                + np.array([-pl.wind[1], pl.wind[0], 0]) * sway
            dens = pl.dens * life.smoothstep(0.0, 0.08, f) * (1.0 - f) ** 1.6
            if dens < 0.01:
                continue
            glow = pl.glow * math.exp(-h / 6.0)
            S.post_smoke.append([float(p[0]), float(p[1]), float(p[2]), float(pl.size0 + pl.grow * a), float(dens),
                                 float(glow), float((pl.seed * 0.137 + i * 0.0731) % 1.0), float(f), int(kind)])


def smoke_light(S, hour, fires=0.0):
    """Radiance of a sunlit puff at this hour: sun (warm when low) and sky; at night only the fires."""
    el, _ = TL.sun_angles(hour)
    day = TL.smoothstep(math.radians(-7), math.radians(5), el)
    sun = S.sun.data.color if not S.sun.hide_render else (0.0, 0.0, 0.0)
    e_sun = S.sun.data.energy * 0.6 if not S.sun.hide_render else 0.0   # a puff always has a sunlit side
    e_sky = 1.3 * day + 0.04
    rgb = [(e_sun * sun[i] + e_sky * (0.85, 0.92, 1.0)[i]) / math.pi + 0.25 * fires * (1.0, 0.5, 0.2)[i] for i in range(3)]
    for m in (S.m_smoke_lit, S.m_dust_lit):
        m.node_tree.nodes['smoke_light'].outputs[0].default_value = tuple(rgb) + (1.0,)
    S.smoke_rgb = [float(c) for c in rgb]


GALLEY_OARS = 11           # a side


def build_oars(S):
    """Oars for the hero ship when she comes in as a galley (S5)."""
    ob = G.HexBatch('galley_oar')
    ob.add(G.beam([-1.9, 0, 0], [5.4, 0, 0], 0.1), mat=0)
    ob.add(G.beam([5.2, 0, 0], [6.6, 0, 0], 0.03, 0.26), mat=0)
    ob.finalize()
    me = SC.hex_mesh('GalleyOar', ob, np.ones(len(ob.t_on), bool), [S.m_wood])
    s, x, b, keel, sheer = S.ship_st
    S.oars = []
    idx = np.linspace(9, 31, GALLEY_OARS).astype(int)
    for sg in (1, -1):
        for i in idx:
            o = SC.link(bpy.data.objects.new('GalleyOar', me))
            o.pass_index = SC.PASS['ship']
            o.hide_render = True
            S.oars.append((o, np.array([x[i], sg * (b[i] + 0.05), sheer[i] - 0.35]), sg))


GALLEY_T = 3.2


def galley_stroke(ph):
    """Sweep a (+ = blade to the bow) and elevation e (- = blade down) of a galley oar."""
    ph %= 1.0
    if ph < 0.4:
        u = ph / 0.4
        a = math.radians(32) + math.radians(-58) * (0.5 - 0.5 * math.cos(math.pi * u))
        e = math.radians(-24)
    else:
        u = (ph - 0.4) / 0.6
        a = math.radians(-26) + math.radians(58) * (0.5 - 0.5 * math.cos(math.pi * u))
        e = math.radians(-24) + math.radians(12) * math.sin(math.pi * min(u * 1.2, 1.0))
    return a, e


def pose_oars(S, t, on=True):
    M = S.ship_root.matrix_world
    ph = t / GALLEY_T
    for k, (o, piv, sg) in enumerate(S.oars):
        o.hide_render = not on
        if not on:
            continue
        a, e = galley_stroke(ph + 0.012 * (k % GALLEY_OARS))
        yaw = (math.pi / 2 - a) if sg > 0 else (a - math.pi / 2)
        o.matrix_world = M @ Matrix.Translation(tuple(piv)) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(-e, 4, 'Y')


def furl(S):
    """In harbour and under oars the sail is furled on the yard."""
    S.ship['sail'].hide_render = True
    S.ship['lines'].hide_render = True
    if not hasattr(S, 'furled'):
        fb = G.HexBatch('furled')
        xm, zy = S.ship_mast_x, S.ship_masthead - 1.2
        fb.add(G.beam([xm + 0.12, -6.8, zy - 0.28], [xm + 0.12, 6.8, zy - 0.28], 0.46, 0.5), mat=0)
        fb.finalize()
        S.furled = SC.link(bpy.data.objects.new('FurledSail', SC.hex_mesh('FurledSail', fb, np.ones(1, bool), [S.m_sailcloth])))
        S.furled.parent = S.ship_root
        S.furled.pass_index = SC.PASS['ship']
        S.ship['furled'] = S.furled
    S.furled.hide_render = False


N_TORCH = 18


def build_torches(S):
    S.torches = []
    t_me = SC.prism('TorchFlame', 0.24, 0.0, 0.8, 6, 0.02, (0, 0), [S.m_torch])
    post = G.HexBatch('torch_post')
    post.add(G.beam([0, 0, -2.2], [0, 0, 0.0], 0.08), mat=0)
    post.finalize()
    p_me = SC.hex_mesh('TorchPost', post, np.ones(1, bool), [S.m_wood])
    for i in range(N_TORCH):
        ld = bpy.data.lights.new(f'Torch{i}', 'POINT')
        ld.color = (1.0, 0.5, 0.2)
        ld.shadow_soft_size = 0.3
        lo = SC.link(bpy.data.objects.new(f'Torch{i}', ld))
        fo = SC.link(bpy.data.objects.new(f'TorchFlame{i}', t_me))
        po = SC.link(bpy.data.objects.new(f'TorchPost{i}', p_me))
        fo.pass_index = SC.PASS['torch']
        fo.visible_shadow = False
        po.pass_index = SC.PASS['props']
        S.torches.append((lo, fo, po))
    hide_torches(S)


def hide_torches(S):
    for trip in S.torches:
        for o in trip:
            o.hide_render = True


def pose_torches(S, spots, k, t):
    S.m_torch.node_tree.nodes['torch_k'].outputs[0].default_value = k
    for i, (lo, fo, po) in enumerate(S.torches):
        if i >= len(spots) or k <= 0.01:
            lo.hide_render = fo.hide_render = po.hide_render = True
            continue
        x, y, z = spots[i]
        fl = 0.8 + 0.2 * SC.smooth_rand(i + 200, t, 8.0)
        po.location = (x, y, z + 2.2)
        fo.location = (x, y, z + 2.2)
        fo.scale = (fl,) * 3
        lo.location = (x, y, z + 2.8)
        lo.data.energy = 700.0 * k * fl
        lo.hide_render = fo.hide_render = po.hide_render = False


def build_baskets(S):
    """Heaps of loose earth tipped from the baskets on the mound top (time-lapse)."""
    V, F = life.lathe([(0.0, 0.0), (0.9, 0.0), (0.55, 0.25), (0.0, 0.38)], 9)
    me = SC.mesh_from_arrays('EarthHeap', V, F, mats=[bpy.data.materials['Earth']], smooth=True)
    S.heaps = []
    for i in range(10):
        o = SC.link(bpy.data.objects.new(f'EarthHeap{i}', me))
        o.pass_index = SC.PASS['terrain']
        o.hide_render = True
        S.heaps.append(o)


def hide_extras(S):
    for o in S.people + S.gulls + [S.tread] + S.heaps:
        o.hide_render = True
    for c, wheels, oxen in S.carts:
        c.hide_render = True
        for w, _ in wheels:
            w.hide_render = True
        for o, _ in oxen:
            o.hide_render = True
    for o in S.ship.values():
        o.hide_render = True
    for trip in S.cranes + S.barges:
        for o in trip:
            o.hide_render = True
    for o, _, _ in S.oars:
        o.hide_render = True
    life.hide_all(S)
    RH.hide_foundry(S)
    RH.show_cargo(S, False)
    RH.pose_altar(S, -1.0, 0.0)
    hide_torches(S)
    S.post_smoke = []


def place_cart(S, i, pos, heading, dist, z):
    """lighthouse place_cart with an explicit ground height."""
    c, wheels, oxen = S.carts[i]
    x, y = pos
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


def gz(x, y):
    return RH.ground_z(x, y)


# ================================================================== site life (S2, S4)
def mound_z(S, x, y):
    """Height of the ground or the mound at (x, y)."""
    r = math.hypot(x, y)
    th = math.atan2(y, x)
    if S.mound_M is not None and r < RH.R_BASE + 1 and S.mound_M > RH.GROUND + 0.05:
        return float(RH.mound_heights(np.array([r]), np.array([th]), S.mound_M)[0])
    return RH.GROUND


def site_life(S, tc, hop_t, day, t_anim, M, L_, removing=False, crowd=1.0):
    """Time-lapse crowd: carriers on the ramp (earth up, or down when the mound
    is taken away), carts on the ramp, workers on the top and the trestles,
    people and carts at the foot.  Returns the next free person."""
    k = 0
    active = 0.3 + 0.7 * day
    phi_top = RH.ramp_phi_max(M) if M > RH.GROUND + 0.5 else 0.0
    # carriers on the ramp: loaded going up (building) or down (removal)
    n_ramp = int(34 * crowd) if phi_top > 0.3 else 0
    for i in range(n_ramp):
        if SC.hop(i + 700, hop_t, 2.2) > active:
            continue
        u = SC.hop(i + 740, hop_t, 2.2)
        phi = u * phi_top
        side = 0.2 + 0.6 * SC.hop(i + 760, hop_t, 2.2)
        (x, y, z), hd = RH.ramp_point(phi, side)
        if removing:
            hd += math.pi
        L.place_person(S, k, (x, y, z), hd, 'carry', 2 * math.pi * SC.hop(i + 780, hop_t, 2.2))
        k += 1
    # carts on the ramp
    for ci in range(2 if phi_top > 0.6 else 0):
        if SC.hop(ci + 800, hop_t, 1.4) > active:
            continue
        phi = (0.1 + 0.8 * SC.hop(ci + 810, hop_t, 1.4)) * phi_top
        (x, y, z), hd = RH.ramp_point(phi, 0.45)
        place_cart(S, ci, (x, y), hd + (math.pi if removing else 0.0), 30.0 * SC.hop(ci + 820, hop_t, 1.4), z)
    # workers on the top of the mound (round the figure) and on the trestles
    if M > RH.GROUND + 0.5:
        top_r = RH.cone_r(M) - 1.0
        for i in range(int(18 * crowd)):
            if SC.hop(i + 900, hop_t, 2.0) > active:
                continue
            a = 2 * math.pi * SC.hop(i + 920, hop_t, 2.0)
            r0 = RH.statue_radius(S, M, M + 2.0, a) + 1.6
            r = r0 + (top_r - r0) * SC.hop(i + 940, hop_t, 2.0)
            if r > top_r:
                continue
            mode = ('hammer', 'haul', 'stand', 'carry', 'point', 'walk')[i % 6]
            L.place_person(S, k, (r * math.cos(a), r * math.sin(a), M + 0.05), a + math.pi, mode,
                           2 * math.pi * SC.hop(i + 960, hop_t, 2.0))
            k += 1
        if S.trestle_key is not None:
            h = min(RH.PT + L_ - M, 3.2)
            for i in range(int(10 * crowd)):
                if SC.hop(i + 1000, hop_t, 2.0) > active:
                    continue
                a = 2 * math.pi * SC.hop(i + 1020, hop_t, 2.0)
                r = RH.statue_radius(S, M + 0.3, M + h + 1.8, a) + 1.1
                if r > top_r:
                    continue
                L.place_person(S, k, (r * math.cos(a), r * math.sin(a), M + h + 0.05), a + math.pi,
                               ('hammer', 'haul', 'stand')[i % 3], 2 * math.pi * SC.hop(i + 1040, hop_t, 2.0))
                k += 1
    # at the foot: the carts from the mole, people at the stacks
    for i in range(int(22 * crowd)):
        if SC.hop(i + 1100, hop_t, 1.6) > active:
            continue
        a = 2 * math.pi * SC.hop(i + 1120, hop_t, 1.6)
        r = RH.R_BASE + 1.5 + 6.0 * SC.hop(i + 1140, hop_t, 1.6)
        x, y = r * math.cos(a), r * math.sin(a)
        if not RH.built_mask(np.array([x]), np.array([y]))[0]:
            continue
        L.place_person(S, k, (x, y, RH.GROUND), a + math.pi / 2 + (math.pi if i % 2 else 0.0),
                       ('walk', 'carry', 'stand', 'haul')[i % 4], 2 * math.pi * SC.hop(i + 1160, hop_t, 1.6))
        k += 1
    for ci in (2, 3):
        if SC.hop(ci + 1200, hop_t, 1.2) > active * 0.9:
            continue
        y = -60.0 - 150.0 * SC.hop(ci + 1210, hop_t, 1.2)
        hd = math.pi / 2 if (ci + int(hop_t * 1.2)) % 2 else -math.pi / 2
        place_cart(S, ci, (-4.0 if hd > 0 else 4.0, y), hd, 25.0 * SC.hop(ci + 1220, hop_t, 1.2), RH.GROUND)
    return k


def furnace_spots(S, M, n=2):
    """Where the furnaces stand on the top of the mound (outside the trestles)."""
    top_r = RH.cone_r(M)
    out = []
    for a in (math.radians(215.0), math.radians(160.0))[:n]:
        r = min(RH.statue_radius(S, M, M + 3.0, a) + 5.0, top_r - 2.2)
        out.append((r * math.cos(a), r * math.sin(a), a + math.pi / 2))
    return out


def site_torches(M, phi_top):
    spots = []
    for j in range(8):                                   # along the ramp
        phi = phi_top * (j + 0.5) / 8
        (x, y, z), _ = RH.ramp_point(phi, 0.05)
        spots.append((x, y, z))
    if M > RH.GROUND + 0.5:
        r = RH.cone_r(M) - 1.0
        for j in range(6):                               # round the top
            a = 2 * math.pi * j / 6 + 0.3
            spots.append((r * math.cos(a), r * math.sin(a), M))
    for (x, y) in ((-6.0, -60.0), (6.0, -60.0), (40.0, 30.0)):
        spots.append((x, y, RH.GROUND))
    return spots


def site_plumes(S, M, working, fast=1.0, glow=0.0):
    pl = []
    if working and M > RH.GROUND + 0.5:
        for i, (x, y, hd) in enumerate(furnace_spots(S, M)):
            pl.append(life.Plume((x, y, M + 1.9), n=8, life=9.0 / fast, rise=1.4 * fast, drift=1.6 * fast, size0=0.7,
                                 grow=0.55, dens=0.85, glow=glow, seed=i + 1))
    for i, (x, y) in enumerate(((-7.0, -108.0),)):
        pl.append(life.Plume((x, y, RH.GROUND + 3.0), n=6, life=9.0 / fast, rise=1.2 * fast, drift=1.4 * fast, size0=0.7,
                             grow=0.5, dens=0.6, seed=9 + i))
    return pl


# ================================================================== shots
CLUTTER = dict(amphorae=(10.8, -153.0, RH.GROUND, math.pi / 2), jars=(-1.0, -135.0, RH.GROUND, 0.0),
               baskets=(10.0, -130.5, RH.GROUND, 0.0), coils=(11.6, -150.0, RH.GROUND, 0.0),
               levers=(-3.6, -118.0, RH.GROUND, math.pi / 2), awning=(2.4, -131.0, RH.GROUND, 0.0))
S1_CAM0 = ((27.0, -178.0, 6.2), (4.0, -125.0, 3.4))
S1_CAM1 = ((25.3, -171.0, 6.2), (2.0, -118.0, 3.4))
QUAY_CRANE = (10.4, -139.0, RH.GROUND)
SHIP_S1 = (17.9, -112.0)
LIGHTER_S1 = (17.4, -139.5)


def shot_S1(S, v):
    """The harbour, 07:30, real time: a working morning on the mole."""
    u = v / 3.0
    e = TL.ease_io(u)
    hour = 7.35 + 0.2 * u
    cam = (lerp3(S1_CAM0[0], S1_CAM1[0], e), lerp3(S1_CAM0[1], S1_CAM1[1], e), 32.0)
    meta = RH.pose(S, v, tc=0.12, hour=hour, sea_t=40.0 + v, water_t=16.0 + 0.4 * v, cloud_t=hour * 0.75,
                   shadow_t=hour * 124.0, cover=0.35, cloud_gain=7.0, shadow_cover=0.3, hdri=1.0,
                   hdri_rot=S1_SKY + 0.002 * v, cam=cam)
    smoke_light(S, hour)
    RH.show_cargo(S, True, t=v)
    life.show_clutter(S, True)
    # the merchantman alongside, her crew passing out copper; the lighter at the crane
    k = L.pose_ship(S, SHIP_S1, -math.pi / 2, 30.0 + v, math.radians(4.0), 1.0, lantern=0.0, sailors=True, first_person=0)
    furl(S)
    h, r, cg = S.barges[0]
    h.location = (LIGHTER_S1[0], LIGHTER_S1[1], 0.1 + 0.05 * math.sin(1.3 * v))
    h.rotation_euler = (0.01 * math.sin(0.9 * v), 0, math.pi / 2)
    h.hide_render = r.hide_render = cg.hide_render = False
    # the quay crane swings a sling of copper ingots from the lighter onto the mole
    c, rope, load = S.cranes[5]
    slew = math.radians(-10.0 + 60.0 * TL.ease_io(u))
    c.matrix_world = Matrix.Translation(QUAY_CRANE) @ Matrix.Rotation(slew, 4, 'Z')
    c.hide_render = False
    tip = c.matrix_world @ Vector(S.crane_tip)
    lift = 0.5 * u
    lz = RH.GROUND + 2.4 + lift
    load.data = S.ingot_load_me
    load.hide_render = rope.hide_render = False
    load.matrix_world = Matrix.Translation((tip.x, tip.y, lz)) @ Matrix.Rotation(slew, 4, 'Z')
    rope.matrix_world = Matrix.Translation(tip) @ Matrix.Diagonal((1, 1, tip.z - lz, 1))
    ang = lift / L.DRUM_R
    k = L.pose_treadwheel(S, ang, walkers=2, first_person=k, walk_ph=ang * (L.WHEEL_R - 0.06) / 1.45 * 2 * math.pi)
    # dockers: ingots from the ship to the piles, iron bars, a scribe, smiths
    z = RH.GROUND
    k = L.place_walkers(S, k, [
        ((12.6, -146.0), math.radians(160), 1.1, 0.0, 'carry'), ((9.0, -139.0), math.radians(-20), 1.2, 1.1, 'walk'),
        ((12.0, -134.0), math.radians(200), 1.0, 2.0, 'carry'), ((1.0, -148.0), math.radians(80), 1.2, 0.4, 'walk'),
        ((-1.5, -140.0), math.radians(95), 1.1, 1.7, 'shoulder'), ((2.0, -125.0), math.radians(-85), 1.2, 2.4, 'walk'),
        ((-2.0, -112.0), math.radians(-90), 1.1, 0.8, 'carry'), ((4.5, -104.0), math.radians(95), 1.2, 1.5, 'walk'),
        ((-4.0, -98.0), math.radians(-80), 1.0, 2.9, 'walk'), ((0.0, -160.0), math.radians(90), 1.2, 0.6, 'walk')],
        v, lambda x, y: z)
    busy = [(12.9, -142.0, 200, 'haul'), (12.2, -143.5, 190, 'haul'), (14.3, -136.3, 240, 'point'),
            (5.6, -143.0, 90, 'stand'), (2.8, -146.0, 30, 'hammer'), (6.8, -132.5, 150, 'stand'),
            (2.4, -131.8, 180, 'scribe'), (3.8, -130.0, 200, 'point'),
            (-8.2, -108.5, 0, 'hammer'), (-6.0, -106.4, 250, 'stand'),
            (-4.0, -143.0, 80, 'haul'), (-3.4, -140.5, 75, 'haul'), (-9.0, -133.0, 20, 'point'),
            (7.0, -125.8, 180, 'sit'), (-0.8, -134.2, 90, 'pour'), (5.0, -151.0, 60, 'stand')]
    for j, (x, y, hd, mode) in enumerate(busy):
        L.place_person(S, k, (x, y, z), math.radians(hd), mode, 2.6 * v + j * 1.7)
        k += 1
    # ox carts: one taking copper to the site, one being loaded, one coming back
    place_cart(S, 0, (-1.2, -128.0 + 0.9 * v), math.pi / 2, 0.9 * v, z)
    place_cart(S, 1, (-1.0, -151.0), math.pi / 2, 0.0, z)
    place_cart(S, 2, (1.6, -100.0 - 0.9 * v), -math.pi / 2, 0.9 * v, z)
    # boats in the harbour
    d0 = life.skiff_distance(v)
    hd0 = math.radians(-20.0)
    k = life.pose_skiff(S, L, 0, (36.0 + math.cos(hd0) * d0, -128.0 + math.sin(hd0) * d0), hd0, v, k, seed=0)
    d1 = life.skiff_distance(v + 3.0, 1.4)
    hd1 = math.radians(110.0)
    k = life.pose_skiff(S, L, 1, (48.0 + math.cos(hd1) * d1, -160.0 + math.sin(hd1) * d1), hd1, v + 3.0, k, seed=2)
    life.pose_anchored(S, [(70.0, -95.0, math.radians(100)), (95.0, -150.0, math.radians(80)), (120.0, -60.0, 1.2)], v)
    L.pose_gulls(S, v, (16.0, -136.0), 10, z0=RH.GROUND)
    mast = S.ship_root.matrix_world @ Vector((S.ship_mast_x, 0.0, S.ship_masthead + 0.2))
    life.pose_pennants(S, [((tip.x, tip.y, tip.z + 0.2), 2.2, 0.45, 0), (tuple(mast), 2.6, 0.5, 1)], v)
    smoke(S, [life.Plume((RH.SMITHY[0] + 0.4, RH.SMITHY[1] + 0.9, RH.GROUND + 3.0), n=9, life=11.0, rise=1.0,
                         drift=1.3, size0=1.3, grow=0.7, dens=0.6, seed=9)], 40.0 + v)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


def s2_cam(v, tc):
    u = TL.ease_io((v - 3.0) / 5.0) * 0.8 + 0.2 * (v - 3.0) / 5.0
    M = RH.mound_top(tc)
    tz = 10.0 + 0.62 * (M - RH.GROUND)
    b = 232.0 - 34.0 * u
    dist = 172.0 - 40.0 * u
    return bearing_pos(b, dist, 40.0 + 0.32 * (M - RH.GROUND)), (0.0, 0.0, tz), 36.0 + 4.0 * u


def shot_S2(S, v):
    lp = S2_LAPSE
    hour = lp.hour(v)
    tc = lp.tc(v, ease=1.6)            # the pedestal and the legs stay a little longer in view
    cam = s2_cam(v, tc)
    meta = RH.pose(S, v, tc=tc, hour=hour, sea_t=60.0 + v * 6.0, water_t=30.0 + v * 3.0, cloud_t=hour * 0.9,
                   shadow_t=hour * 200.0, cover=0.3 + 0.06 * math.sin(v), cloud_gain=7.0, shadow_cover=0.32,
                   hdri=1.0, hdri_rot=S2_SKY + 0.05 * (v - 3.0), sky_log=True, cam=cam)
    day = meta['day']
    smoke_light(S, hour, fires=1.0 - day)
    M = meta['mound']
    hop_t = 2.0 * v
    k = site_life(S, tc, hop_t, day, v, M, meta['level'])
    working = meta.get('working', False)
    glow = 0.35 + 0.65 * (1.0 - day)
    if working:
        RH.pose_foundry(S, furnace_spots(S, M), M, v, glow=glow, pump=False, light=glow * (1.0 - 0.8 * day))
    # a crane at the pedestal while it is built
    c, rope, load = S.cranes[0]
    if tc < RH.TC_PED[1] + 0.05:
        slew = 2 * math.pi * SC.smooth_rand(7, hop_t, 1.6)
        c.matrix_world = Matrix.Translation((14.0, -14.0, RH.GROUND)) @ Matrix.Rotation(slew, 4, 'Z')
        c.hide_render = rope.hide_render = load.hide_render = False
        tip = c.matrix_world @ Vector(S.crane_tip)
        lz = RH.GROUND + 1.0 + SC.hop(31, hop_t, 3.0) * (tip.z - RH.GROUND - 3.0)
        load.matrix_world = Matrix.Translation((tip.x, tip.y, lz)) @ Matrix.Rotation(slew, 4, 'Z')
        rope.matrix_world = Matrix.Translation(tip) @ Matrix.Diagonal((1, 1, max(tip.z - lz, 0.3), 1))
    phi_top = RH.ramp_phi_max(M) if M > RH.GROUND + 0.5 else 0.0
    pose_torches(S, site_torches(M, phi_top), TL.smoothstep(0.55, 0.1, day), v)
    smoke(S, site_plumes(S, M, working, fast=3.0, glow=0.6 * (1.0 - day)), 100.0 + v * 3.0)
    life.pose_anchored(S, [(90.0, -90.0, math.radians(100)), (150.0, -150.0, math.radians(80)), (200.0, -40.0, 1.2)], v,
                       lamp=1.0 - day)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.6)
    return meta


S3_TC = 8.86                       # the last plates go on the top of the head; the crown comes next
S3_FURNACES = [(-10.8, -1.4, math.radians(-120.0)), (-5.0, -5.5, math.radians(120.0))]
S3_CAM0 = ((-15.5, -7.3, 2.2), (0.0, 1.5, 4.8))
S3_CAM1 = ((-14.9, -6.2, 2.3), (-0.1, 1.8, 4.9))


def shot_S3(S, v):
    """On the top of the mound, 15:40, real time: the foundry and the head."""
    u = (v - 8.0) / 3.5
    e = TL.ease_io(u)
    hour = 15.6 + 0.12 * u
    M = RH.mound_top(S3_TC)
    c0 = tuple(np.add(S3_CAM0[0], (0, 0, M))), tuple(np.add(S3_CAM0[1], (0, 0, M)))
    c1 = tuple(np.add(S3_CAM1[0], (0, 0, M))), tuple(np.add(S3_CAM1[1], (0, 0, M)))
    cam = (lerp3(c0[0], c1[0], e), lerp3(c0[1], c1[1], e), 26.0)
    meta = RH.pose(S, v, tc=S3_TC, hour=hour, sea_t=90.0 + v, water_t=40.0 + 0.4 * v, cloud_t=hour * 0.75,
                   shadow_t=hour * 124.0, cover=0.3, cloud_gain=7.0, shadow_cover=0.3, hdri=1.0,
                   hdri_rot=S3_SKY + 0.002 * v, cam=cam)
    smoke_light(S, hour, fires=0.3)
    RH.pose_foundry(S, S3_FURNACES, M, v, glow=0.45, pump=True, stock=(-8.6, -9.6, math.radians(30.0)),
                    charcoal=(-12.9, 1.6), light=0.2)
    k = 0
    # bellows men (two at each pair of bags), the furnace master, stokers
    for i, (x, y, hd) in enumerate(S3_FURNACES):
        Mw = Matrix.Translation((x, y, M)) @ Matrix.Rotation(hd, 4, 'Z')
        for j in range(2):
            p = Mw @ Vector((-2.2, (j - 0.5) * 0.9, 0.0))
            ph = v * 2 * math.pi * 0.8 + j * math.pi + i
            L.place_person(S, k, (p.x - 0.2, p.y, p.z + 0.45 + 0.2 * (0.5 + 0.5 * math.cos(ph))), hd, 'stand', 0.0)
            k += 1
        mx, my = ((-10.0, 0.9), (-6.2, -7.4))[i]               # the furnace masters, off the line of sight
        L.place_person(S, k, (mx, my, M), math.atan2(y - my, x - mx), 'point' if i == 0 else 'haul', 2.0 * v + i)
        k += 1
    L.place_person(S, k, (-9.0, 2.6, M), math.radians(-70), 'carry', 2.4 * v)            # charcoal in a basket
    k += 1
    for j, (x, y, hd, mode) in enumerate(((-9.6, -10.4, 60, 'haul'), (-7.4, -11.2, 120, 'haul'),
                                          (-7.6, 5.0, -30, 'stand'), (-8.2, -8.0, 30, 'hammer'))):
        L.place_person(S, k, (x, y, M), math.radians(hd), mode, 2.6 * v + j)
        k += 1
    # on the scaffold: riveting at the side of the head and at the arm, a plate held up
    zl = [RH.M_MAX + 2.2 * (i + 1) for i in range(6)]
    cx, cy = RH.SCAF_C
    for j, (a_deg, li, mode) in enumerate(((146.0, 1, 'hammer'), (132.0, 2, 'hammer'), (114.0, 3, 'haul'),
                                           (98.0, 2, 'hammer'), (-80.0, 1, 'hammer'), (-68.0, 2, 'stand'),
                                           (-52.0, 3, 'hammer'), (-36.0, 1, 'point'), (140.0, 3, 'stand'))):
        a = math.radians(a_deg)
        r = RH.SCAF_R - 0.45
        L.place_person(S, k, (cx + r * math.cos(a), cy + r * math.sin(a), zl[li - 1] + 0.14), a + math.pi, mode, 3.0 * v + j)
        k += 1
    pl = [life.Plume((x, y, M + 1.95), n=12, life=6.0, rise=1.5, drift=1.6, size0=0.4, grow=0.42, dens=0.5, seed=i + 1)
          for i, (x, y, hd) in enumerate(S3_FURNACES)]
    smoke(S, pl, 50.0 + v)
    L.pose_gulls(S, v, (-6.0, 4.0), 4, z0=M + 6.0)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


def shot_S4(S, v):
    lp = S4_LAPSE
    hour = lp.hour(v)
    tc = lp.tc(v)
    u = (v - 11.5) / 3.5
    e = TL.ease_io(u)
    cam = (bearing_pos(252.0 + 4.0 * e, 215.0 - 25.0 * e, 24.0), (0.0, 0.0, 25.0), 38.0)
    meta = RH.pose(S, v, tc=tc, hour=hour, sea_t=120.0 + v * 5.0, water_t=60.0 + v * 2.5, cloud_t=hour * 0.9,
                   shadow_t=hour * 200.0, cover=0.28, cloud_gain=7.0, shadow_cover=0.3, hdri=1.0,
                   hdri_rot=S4_SKY + 0.04 * (v - 11.5), cam=cam)
    smoke_light(S, hour)
    M = meta['mound']
    hop_t = 2.0 * v
    k = 0
    if M > RH.GROUND + 0.5 or tc < RH.TC_REVEAL[1] + 0.1:
        k = site_life(S, tc, hop_t, meta['day'], v, M, meta['level'], removing=True, crowd=1.0)
    # dust where the earth is dug out and tipped
    pl = []
    if M > RH.GROUND + 0.5:
        rt = RH.cone_r(M) - 2.0
        for i in range(3):
            a = 2 * math.pi * SC.hop(i + 1300, hop_t, 1.0)
            pl.append(life.Plume((rt * math.cos(a), rt * math.sin(a), M + 0.4), n=6, life=4.0, rise=0.7, drift=1.4,
                                 size0=2.0, grow=1.0, dens=0.35, seed=i + 20))
    smoke(S, pl, 70.0 + v * 3.0, kind=1)
    life.pose_anchored(S, [(90.0, -90.0, math.radians(100)), (150.0, -150.0, math.radians(80)), (200.0, -40.0, 1.2)], v)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


S5_CAM0 = ((-205.0, 148.0, 5.5), (-2.0, -2.0, 23.0))
S5_CAM1 = ((-196.0, 136.0, 5.3), (-2.0, -2.0, 23.0))
GALLEY0 = (-155.0, 79.0)
GALLEY_HD = math.radians(53.5)
GALLEY_V = 2.6


def shot_S5(S, v):
    """Sunset, real time: the galley rows past the Colossus towards the harbour."""
    u = (v - 15.0) / 5.0
    e = TL.ease_io(u)
    hour = 17.3 + 0.15 * u
    cam = (lerp3(S5_CAM0[0], S5_CAM1[0], e), lerp3(S5_CAM0[1], S5_CAM1[1], e), 45.0)
    meta = RH.pose(S, v, tc=14.0, hour=hour, sea_t=150.0 + v, water_t=70.0 + 0.4 * v, cloud_t=hour * 0.75,
                   shadow_t=hour * 124.0, cover=0.3, cloud_gain=7.0, shadow_cover=0.3, hdri=1.0,
                   hdri_rot=S5_SKY + 0.002 * v, cam=cam)
    smoke_light(S, hour, fires=0.4)
    t = v - 15.0
    d = GALLEY_V * t + 0.35 * math.sin(2 * math.pi * t / GALLEY_T)       # surges with each stroke
    pos = (GALLEY0[0] + math.cos(GALLEY_HD) * d, GALLEY0[1] + math.sin(GALLEY_HD) * d)
    k = L.pose_ship(S, pos, GALLEY_HD, 200.0 + v, 0.0, 1.0, lantern=0.35, sailors=True, first_person=0)
    furl(S)
    pose_oars(S, v, True)
    life.add_wake(S, pos, GALLEY_HD, 0.8, 21.0)
    RH.pose_altar(S, 1.0, v)
    # a sacrifice at the altar: priests, a crowd round it, people on the moles
    ax, ay = RH.ALTAR
    rng = np.random.default_rng(3)
    for j in range(22):
        a = rng.uniform(-1.2, 1.2) + math.pi
        r = rng.uniform(3.0, 9.0)
        x, y = ax + r * math.cos(a) * 1.2, ay + r * math.sin(a) * 1.6
        mode = 'torch' if j < 2 else ('point' if j % 7 == 3 else 'stand')
        L.place_person(S, k, (x, y, RH.GROUND), math.atan2(ay - y, ax - x), mode, 2.0 * v + j)
        k += 1
    for j in range(14):
        x = 115.0 + j * 9.0 + rng.uniform(-2, 2)
        y = RH.NMOLE_Y[1] - 2.0 - rng.uniform(0, 3)
        L.place_person(S, k, (x, y, RH.GROUND), math.radians(250.0), 'stand' if j % 4 else 'point', v + j)
        k += 1
    for j in range(10):
        x, y = 44.0 - rng.uniform(0, 4), -20.0 + j * 5.0
        L.place_person(S, k, (x, y, RH.GROUND), math.pi, 'stand' if j % 3 else 'walk', v + j)
        k += 1
    smoke(S, [life.Plume((ax, ay, RH.GROUND + 2.8), n=10, life=10.0, rise=1.1, drift=1.2, size0=0.5,
                         grow=0.55, dens=0.7, glow=0.25, seed=31)], 60.0 + v)
    life.pose_anchored(S, [(95.0, -80.0, math.radians(100)), (150.0, -140.0, math.radians(80)), (210.0, -30.0, 1.2)], v,
                       lamp=0.4)
    L.pose_gulls(S, v, (-150.0, 100.0), 9, z0=-2.0)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


SHOT_FN = dict(S1=shot_S1, S2=shot_S2, S3=shot_S3, S4=shot_S4, S5=shot_S5)


def pose(S, f):
    v = f / FPS
    name, a, b = shot_at(v)
    hide_extras(S)
    meta = SHOT_FN[name](S, v)
    if name != 'S1':
        L.pose_treadwheel(S, 0.8 * v)
    life.apply_wakes(S)
    meta.update(shot=name, shot_t=v - a, t=v, smoke=S.post_smoke, smoke_light=getattr(S, 'smoke_rgb', [1.0, 1.0, 1.0]))
    return meta
