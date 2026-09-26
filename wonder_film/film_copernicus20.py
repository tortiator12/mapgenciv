"""The 20-s Civ1 wonder film "Kopernikus' Observatorium" (wunderfilm_10_copernicus).

Five shots from the Frombork scene (frombork.py, storyboards/runde1_fehlende_wunder.md):
  S1  0.0- 3.0 s  the cathedral hill above the lagoon, a late-autumn morning: the
                  brick kilns smoke, carts bring bricks, the footing of the tower
  S2  3.0- 9.0 s  time-lapse: the brick tower rises lift by lift in its scaffold,
                  a treadwheel crane on the wall; crenellations, the roof beams,
                  a flat platform with a parapet; sun and cloud shadows pass
  S3  9.0-12.5 s  the workshop, slanting morning light: the carpenter planes the
                  rules of the triquetrum, Copernicus at his table (from behind)
  S4 12.5-15.5 s  sunset on the platform: the instruments are set up, the
                  armillary sphere catches the last light
  S5 15.5-20.0 s  night: Copernicus, a silhouette, sights the rising moon with the
                  triquetrum; the stars wheel round the pole (54 deg up), moonlight
                  on the lagoon, the cathedral roof below; it ends on the stars

Late autumn (sun at -9 deg declination): sunrise ~07:10, sunset ~17:10.  The
moon, two days past full (+12 deg), rises in the ENE over the lagoon about
19:00, as it must at 54 deg N.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import film_colossus20 as FC
import film_lighthouse20 as L
import frombork as FB
import geometry as G
import instruments as IN
import life
import scene as SC
import timeline as TL

TL.LATITUDE = math.radians(FB.LATITUDE_DEG)
MOON_DEC = math.radians(12.0)
MOON_LAG = math.radians(212.0)          # the moon's hour angle trails the sun's by 212 deg


def moon_dir(hour):
    """The waning gibbous moon: declination +12 deg, hour angle = the sun's - 212 deg."""
    Hs = math.radians(15.0 * ((hour % 24.0) - 12.0))
    H = Hs - MOON_LAG
    lat = TL.LATITUDE
    sin_el = math.sin(lat) * math.sin(MOON_DEC) + math.cos(lat) * math.cos(MOON_DEC) * math.cos(H)
    el = math.asin(max(-1.0, min(1.0, sin_el)))
    az_c = math.atan2(math.sin(H), math.cos(H) * math.sin(lat) - math.tan(MOON_DEC) * math.cos(lat)) + math.pi
    az = math.radians(90.0) - az_c
    return np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])


TL.moon_dir = moon_dir

FPS = 24
DURATION = 20.0
NFRAMES = int(round(FPS * DURATION))
LOOK = 'bright'
SHOTS = [('S1', 0.0, 3.0), ('S2', 3.0, 9.0), ('S3', 9.0, 12.5), ('S4', 12.5, 15.5), ('S5', 15.5, 20.0)]
CUTS = [s[1] for s in SHOTS[1:]]
GRADE = dict(warm={'S1': (0.6, 4.0), 'S2': (0.5, 3.5), 'S3': (0.9, 5.0), 'S4': (1.6, 6.5), 'S5': (-0.4, -3.0)},
             gain={'S1': 0.94, 'S2': 0.95, 'S3': 0.92, 'S4': 0.97, 'S5': 1.0},
             dust={'S1': 0.22, 'S2': 0.14, 'S3': 0.0, 'S4': 0.1, 'S5': 0.0})


def shot_at(v):
    for name, a, b in SHOTS:
        if a <= v < b:
            return name, a, b
    return SHOTS[-1]


lerp3 = FC.lerp3


# ================================================================== build
def build(res=(1280, 720)):
    S = FB.build(res)
    _compat(S)
    L.build_quay_crane(S)
    L.build_people(S, n_people=160)
    m_cl = mat_person_clothed()
    for meshes in S.pose_meshes.values():
        for me in meshes:
            me.materials[0] = m_cl
    L.build_carts(S, n=3)
    S.m_sailcloth = L.mat_sailcloth('SailCloth', SC.P['sail'])
    life.build(S, L)
    FC._emissive_smoke(S)
    bpy.data.meshes['Cart'].materials[1] = S.m_brick_new          # carts bring bricks
    S.triquetrum = IN.build_triquetrum('Triquetrum', S.m_wood, S.m_brass)
    S.quadrant = IN.build_quadrant('Quadrant', S.m_wood, S.m_brass)
    S.armillary = IN.build_armillary('Armillary', S.m_wood, S.m_brass, math.radians(FB.LATITUDE_DEG))
    build_kilns(S)
    sb = G.HexBatch('obs_step')
    sb.add(G.box(0, 0, 0.0, 0.9, 0.7, STEP_H - 0.05), mat=0)
    sb.add(G.box(0, 0, STEP_H - 0.05, 1.0, 0.8, 0.05), mat=1)
    sb.finalize()
    S.step = SC.link(bpy.data.objects.new('ObsStep', SC.hex_mesh('ObsStep', sb, np.ones(2, bool), [S.m_wood, S.m_plank])))
    S.step.pass_index = SC.PASS['props']
    lb = G.HexBatch('lantern')                                  # a horn lantern to read the scale by
    lb.add(G.box(0, 0, 0.0, 0.2, 0.2, 0.03), mat=0)
    lb.add(G.box(0, 0, 0.03, 0.16, 0.16, 0.24), mat=1)
    for dx, dy in ((-0.09, -0.09), (0.09, -0.09), (0.09, 0.09), (-0.09, 0.09)):
        lb.add(G.box(dx, dy, 0.03, 0.025, 0.025, 0.24), mat=0)
    lb.add(G.tent(0, 0, 0.27, 0.22, 0.22, 0.1, 0.0), mat=0)
    lb.add(G.beam([0, 0, 0.35], [0, 0, 0.42], 0.015), mat=0)
    lb.finalize()
    m_pane, nb, out = SC.new_material('LanternPane')
    em = nb.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (1.0, 0.6, 0.28, 1)
    em.inputs['Strength'].default_value = 6.0
    nb.feed(out.inputs['Surface'], em.outputs[0])
    S.lantern = SC.link(bpy.data.objects.new('Lantern', SC.hex_mesh('Lantern', lb, np.ones(len(lb.t_on), bool), [S.m_wood, m_pane])))
    S.lantern.pass_index = SC.PASS['props']
    ld = bpy.data.lights.new('LanternLight', 'POINT')
    ld.color = (1.0, 0.58, 0.26)
    ld.shadow_soft_size = 0.06
    S.lantern_light = SC.link(bpy.data.objects.new('LanternLight', ld))
    import figures as FG
    S.fig_observer = [FG.figure_mesh(f'Observer{k}', 'scholar', pose, S.m_figure) for k, pose in enumerate(OBSERVER_POSES)]
    S.observer = SC.link(bpy.data.objects.new('Observer', S.fig_observer[0]))
    S.observer.color = (0.30, 0.06, 0.05, 1.0)
    S.observer.pass_index = SC.PASS['worker']
    S.fig_workers = [FG.figure_mesh(f'PlatformWorker{k}', 'craftsman', pose, S.m_figure) for k, pose in enumerate(WORKER_POSES)]
    S.workers = []
    for k in range(2):
        o = SC.link(bpy.data.objects.new(f'PlatformWorker{k}', S.fig_workers[0]))
        o.pass_index = SC.PASS['worker']
        S.workers.append(o)
    return S


def mat_person_clothed():
    """The lighthouse figures in 16th-century Warmia: long sleeves and hose, so
    skin shows only on the head (and hands); tunic colour from the object."""
    m, nb, out = SC.new_material('PersonClothed')
    oi = nb.new('ShaderNodeObjectInfo')
    rnd = oi.outputs['Random']
    reg = nb.attr('region').outputs['Fac']
    oz = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[2]
    tunic = oi.outputs['Color']
    skin = nb.mix(rnd, (0.50, 0.36, 0.28, 1), (0.62, 0.45, 0.35, 1))
    hair = nb.mix(nb.math('FRACT', nb.math('MULTIPLY', rnd, 3.17)), (0.05, 0.035, 0.025, 1), (0.30, 0.22, 0.12, 1))
    hose = nb.mix(nb.math('FRACT', nb.math('MULTIPLY', rnd, 5.73)), (0.12, 0.10, 0.09, 1), (0.30, 0.25, 0.18, 1))
    is_skin = nb.math('COMPARE', reg, float(L.R_SKIN), 0.5)
    head = nb.math('GREATER_THAN', oz, 1.5)
    legs = nb.math('LESS_THAN', oz, 0.9)
    col = tunic
    col = nb.mix(nb.math('MULTIPLY', is_skin, legs), col, hose)
    col = nb.mix(nb.math('MULTIPLY', is_skin, head), col, skin)
    for k, c in ((L.R_HAIR, hair), (L.R_BEARD, hair), (L.R_BELT, (0.10, 0.06, 0.035, 1)), (L.R_SANDAL, (0.08, 0.05, 0.03, 1)),
                 (L.R_BASKET, (0.52, 0.39, 0.2, 1)), (L.R_POT, (0.55, 0.25, 0.12, 1)), (L.R_WOOD, (0.30, 0.20, 0.11, 1))):
        f = nb.math('COMPARE', reg, float(k), 0.5)
        col = nb.mix(f, col, c)
    b = SC.principled(nb, col, rough=0.85, spec=0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def _compat(S):
    """Crane 5 (a treadwheel crane: here on the tower's wall top)."""
    cm, S.crane_tip = SC.crane_mesh([S.m_wood, S.m_rope])
    rope_b = G.HexBatch('rope')
    rope_b.add(G.beam([0, 0, -1.0], [0, 0, 0.0], 0.07), mat=0)
    rope_b.finalize()
    rope_me = SC.hex_mesh('RopeUnit', rope_b, np.ones(1, bool), [S.m_rope])
    load_b = G.HexBatch('brick_load')                           # a pallet of bricks in a rope sling
    load_b.add(G.box(0, 0, -1.0, 1.0, 0.7, 0.5), mat=0)
    load_b.add(G.beam([-0.45, 0, -1.0], [0, 0, 0.0], 0.03), mat=1)
    load_b.add(G.beam([0.45, 0, -1.0], [0, 0, 0.0], 0.03), mat=1)
    load_b.finalize()
    load_me = SC.hex_mesh('BrickLoad', load_b, np.ones(3, bool), [S.m_brick_new, S.m_rope])
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


KILNS = [(-232.0, -190.0, 0.5), (-256.0, -170.0, 0.5)]


def build_kilns(S):
    """Brick kilns below the hill: a kiln with fire holes and a chimney each, drying
    sheds, stacks of green and burnt bricks, a clay pit."""
    kb = G.HexBatch('kilns')
    for (x, y, rot) in KILNS:
        z = FB.ground_z(x, y)
        c, s_ = math.cos(rot), math.sin(rot)
        kb.add(G.box(x, y, z - 1.0, 9.0, 6.0, 5.0, rot), mat=0)
        kb.add(G.box(x + 3.0 * c, y + 3.0 * s_, z + 4.0, 1.6, 1.6, 6.0, rot), mat=0)                      # chimney
        for k in range(3):
            kb.add(G.box(x - 3.0 + 3.0 * k, y - 3.05, z, 0.9, 0.2, 1.1, rot), mat=2)                          # fire holes
        for k in range(4):                                                                                  # brick stacks
            px, py = x - 8.0 + 4.0 * k, y + 9.0
            kb.add(G.box(px, py, FB.ground_z(px, py) - 0.2, 2.6, 1.4, 1.5), mat=1 if k % 2 else 3)
        sx, sy = x - 14.0, y + 1.0                                                                          # drying shed
        zs = FB.ground_z(sx, sy)
        for dx in (-5.0, 5.0):
            for dy in (-2.5, 2.5):
                kb.add(G.beam([sx + dx, sy + dy, zs], [sx + dx, sy + dy, zs + 2.8], 0.2), mat=4)
        kb.add(G.tent(sx, sy, zs + 2.8, 11.0, 6.5, 1.8, 0.0), mat=5)
    kb.finalize()
    m_glow = bpy.data.materials.get('FurnaceGlow') or FC.RH.mat_glow('FurnaceGlow', 'furnace_k')
    S.m_kiln_glow = m_glow
    S.kilns = SC.link(bpy.data.objects.new('Kilns', SC.hex_mesh('Kilns', kb, np.ones(len(kb.t_on), bool),
                                                              [S.m_brick, S.m_brick_new, m_glow,
                                                               SC.mat_simple('GreenBrick', (0.42, 0.30, 0.20), 0.9), S.m_wood,
                                                               S.m_roof])))
    S.kilns.pass_index = SC.PASS['props']


def hide_extras(S):
    for o in S.people + S.workers + [S.tread, S.observer, S.step, S.lantern, S.lantern_light]:
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
    life.hide_all(S)
    IN.pose_triquetrum(S.triquetrum, Matrix.Identity(4), 0.5, visible=False)
    S.quadrant.hide_render = True
    IN.pose_armillary(S.armillary, Matrix.Identity(4), visible=False)
    FB.show_workshop(S, False)
    S.post_smoke = []


def tower_top_frame(dx=0.0, dy=0.0, rot=0.0):
    cx, cy = FB.TOWER_C
    return Matrix.Translation((cx + dx, cy + dy, FB.TOWER_TOP - 0.1)) @ Matrix.Rotation(rot, 4, 'Z')


# ================================================================== shots
S1_CAM0 = ((-335.0, -300.0, 52.0), (-40.0, 0.0, 26.0))
S1_CAM1 = ((-318.0, -318.0, 52.0), (-36.0, -4.0, 26.0))
S1_SKY, S2_SKY, S3_SKY, S4_SKY, S5_SKY = 0.7, 1.9, 0.0, 3.6, 5.0


def env(S, v, hour, cam, tc, rot, **kw):
    return FB.pose(S, v, tc=tc, hour=hour, sea_t=30.0 + v, water_t=10.0 + 0.4 * v, cloud_t=hour * 0.75,
                   shadow_t=hour * 124.0, cover=kw.pop('cover', 0.4), cloud_gain=7.0, shadow_cover=0.35, hdri=kw.pop('hdri', 1.0),
                   hdri_rot=rot, cam=cam, **kw)


def shot_S1(S, v):
    u = v / 3.0
    e = TL.ease_io(u)
    hour = 8.3 + 0.15 * u
    cam = (lerp3(S1_CAM0[0], S1_CAM1[0], e), lerp3(S1_CAM0[1], S1_CAM1[1], e), 34.0)
    meta = env(S, v, hour, cam, 0.05, S1_SKY + 0.002 * v)
    FC.smoke_light(S, hour)
    S.m_kiln_glow.node_tree.nodes['furnace_k'].outputs[0].default_value = 0.5
    k = 0
    # carts up the road to the gate, workers at the tower's footing, canons in the close
    gx, gy = 20.0, -75.0
    for ci, (d0, sp) in enumerate(((60.0, 1.0), (140.0, 0.9), (20.0, 1.1))):
        d = d0 - sp * v * (1 if ci != 2 else -1)
        x, y = gx - 40.0 - 0.8 * d, gy - 12.0 - 0.6 * d
        hd = math.atan2(0.6, 0.8) if ci != 2 else math.atan2(-0.6, -0.8)
        FC.place_cart(S, ci, (x, y), hd, sp * v, FB.ground_z(x, y))
    rng = np.random.default_rng(5)
    for j in range(16):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(6.0, 14.0)
        x, y = FB.TOWER_C[0] + 8 + r * math.cos(a), FB.TOWER_C[1] + 8 + r * math.sin(a)
        L.place_person(S, k, (x, y, FB.ground_z(x, y)), a + math.pi, ('carry', 'hammer', 'stand', 'haul')[j % 4], 2.0 * v + j)
        S.people[k].color = FROMBORK_CLOTHES[j % len(FROMBORK_CLOTHES)]
        k += 1
    for j in range(5):                                            # canons crossing the close
        x, y = -20.0 + 6.0 * j + 1.2 * v, -30.0 + 3.0 * j
        L.place_person(S, k, (x, y, FB.PLATEAU), 0.2, 'walk', 2.0 * v + j)
        S.people[k].color = (0.05, 0.045, 0.045, 1.0)
        k += 1
    FC.smoke(S, [life.Plume((x + 3.0 * math.cos(r_), y + 3.0 * math.sin(r_), FB.ground_z(x, y) + 10.0), n=10, life=14.0,
                            rise=1.1, drift=1.6, size0=2.0, grow=0.9, dens=0.6, seed=i) for i, (x, y, r_) in enumerate(KILNS)],
             40.0 + v)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


FROMBORK_CLOTHES = [(0.42, 0.30, 0.18, 1), (0.55, 0.50, 0.40, 1), (0.30, 0.22, 0.16, 1), (0.40, 0.12, 0.08, 1),
                    (0.22, 0.25, 0.30, 1), (0.62, 0.58, 0.48, 1)]
S2_LAPSE = FC.Lapse(3.0, 9.0, [(3.0, 7.6), (9.0, 16.7)], 0.05, 9.25)


def shot_S2(S, v):
    lp = S2_LAPSE
    hour = lp.hour(v)
    tc = lp.tc(v)
    u = TL.ease_io((v - 3.0) / 6.0)
    cx, cy = FB.TOWER_C
    b = math.radians(165.0 + 28.0 * u)
    dist = 92.0 - 10.0 * u
    loc = (cx + dist * math.sin(b), cy + dist * math.cos(b), FB.PLATEAU + 9.0 + 7.0 * u)
    tz = FB.PLATEAU + 6.0 + 0.55 * max(S.sched.height(tc) - FB.PLATEAU, 0.0)
    cam = (loc, (cx + 6.0, cy + 8.0, tz), 32.0)
    meta = env(S, v, hour, cam, tc, S2_SKY + 0.05 * (v - 3.0), cover=0.35 + 0.08 * math.sin(v))
    FC.smoke_light(S, hour)
    hop_t = 2.0 * v
    k = 0
    wall = S.sched.height(tc)
    building = tc < FB.TC_TOP[1]
    # the treadwheel crane on the wall top lifts bricks from the courtyard
    if building and wall > FB.PLATEAU + 2.0:
        c, rope, load = S.cranes[5]
        slew = math.radians(30.0 + 70.0 * SC.smooth_rand(3, hop_t, 1.2))
        base = Vector((cx + 1.2, cy + 1.2, wall))
        c.matrix_world = Matrix.Translation(base) @ Matrix.Rotation(slew, 4, 'Z')
        c.hide_render = rope.hide_render = load.hide_render = False
        tip = c.matrix_world @ Vector(S.crane_tip)
        lz = FB.PLATEAU + 1.0 + SC.hop(11, hop_t, 3.0) * (tip.z - FB.PLATEAU - 3.0)
        load.matrix_world = Matrix.Translation((tip.x, tip.y, lz)) @ Matrix.Rotation(slew, 4, 'Z')
        rope.matrix_world = Matrix.Translation(tip) @ Matrix.Diagonal((1, 1, max(tip.z - lz, 0.3), 1))
        k = L.pose_treadwheel(S, 0.9 * hop_t, walkers=2, first_person=k, walk_ph=hop_t * 3.0)
    # masons on the wall top and the scaffold lifts, hod carriers on the ladders, people below
    for j in range(14 if building else 4):
        if SC.hop(j + 50, hop_t, 2.2) > 0.85:
            continue
        s = SC.hop(j + 60, hop_t, 2.2)
        side = int(s * 4) % 4
        fr = (s * 4) % 1.0
        P = FB.tower_poly(FB.TOWER_A - FB.TOWER_T * 0.5 if j < 7 else FB.TOWER_A + 1.0)
        a, b_ = P[side], P[(side + 1) % 4]
        p = a + (b_ - a) * fr
        z = wall if j < 7 else FB.PLATEAU + 2.0 * max(int((wall - FB.PLATEAU) / 2.0 - SC.hop(j + 70, hop_t, 2.2) * 3), 0)
        L.place_person(S, k, (p[0], p[1], z), math.atan2(cy - p[1], cx - p[0]), ('hammer', 'stand', 'carry', 'haul')[j % 4],
                       2 * math.pi * SC.hop(j + 80, hop_t, 2.2))
        S.people[k].color = FROMBORK_CLOTHES[j % len(FROMBORK_CLOTHES)]
        k += 1
    for j in range(10):
        if SC.hop(j + 90, hop_t, 1.5) > 0.8:
            continue
        a = 2 * math.pi * SC.hop(j + 100, hop_t, 1.5)
        r = 7.0 + 8.0 * SC.hop(j + 110, hop_t, 1.5)
        x, y = cx + 10.0 + r * math.cos(a), cy + 10.0 + r * math.sin(a)
        L.place_person(S, k, (x, y, FB.PLATEAU), a, ('carry', 'walk', 'haul', 'stand')[j % 4], 2 * math.pi * SC.hop(j + 120, hop_t, 1.5))
        S.people[k].color = FROMBORK_CLOTHES[(j + 2) % len(FROMBORK_CLOTHES)]
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


S3_HOUR = 9.8
OBSERVER_POSES = [dict(hand_r=(0.0, 0.34, 1.7), hand_l=(-0.06, 0.6, 1.75 + 0.02 * k), look=(0.0, 1.0, 0.14 + 0.03 * k),
                       stoop=0.02 + 0.02 * k, cap=True, elbow=(1.0, -0.35, -0.25)) for k in range(3)]
OBSERVER_POSES.append(dict(hand_r=(0.1, 0.45, 1.35), hand_l=(-0.12, 0.4, 1.52), look=(0.0, 1.0, 0.05), stoop=0.04, cap=True))   # S4: at the sphere
WORKER_POSES = [dict(hand_r=(0.22, 0.3, 1.72), hand_l=(-0.05, 0.42, 1.3), lean=0.05, look=(0.0, 1.0, 0.5)),     # hammering high
                dict(hand_r=(0.14, 0.45, 0.92), hand_l=(-0.14, 0.45, 0.95), lean=0.16, look=(0.0, 1.0, -0.7)),   # bent to the work
                dict(hand_r=(0.21, 0.2, 1.02), hand_l=(-0.2, 0.24, 1.0), lean=0.02, look=(0.3, 1.0, 0.1))]       # standing by


def shot_S3(S, v):
    u = (v - 9.0) / 3.5
    e = TL.ease_io(u)
    hour = S3_HOUR + 0.05 * u
    el, az = TL.sun_angles(hour)
    M = FB.room_frame(az)
    c0 = M @ Vector((-2.7, -2.1, 1.62))
    c1 = M @ Vector((-2.45, -1.85, 1.6))
    t0 = M @ Vector((0.5, 1.25, 1.05))
    t1 = M @ Vector((0.6, 1.2, 1.05))
    cam = (tuple(c0.lerp(c1, e)), tuple(t0.lerp(t1, e)), 26.0)
    meta = env(S, v, hour, cam, 11.0, S3_SKY, cover=0.25)
    FB.pose_workshop(S, M, v, cop_k=int(v * 0.6) % 2, carp_ph=2 * math.pi * v / 1.6)
    meta.update(stars=0.0, expo_mul=0.85)
    return meta


S4_TC = (9.75, 10.75)
S4_HOURS = (16.3, 16.8)                 # the sun sinks from 7 to 3 deg behind the battlements (WSW)
S4_POS = dict(armillary=(-1.4, -0.3), triquetrum=(-2.0, 2.2), quadrant=(-1.0, -2.6), copernicus=(-1.2, -1.2))


def shot_S4(S, v):
    """From the platform's north-east corner into the sunset: the last rays through the
    crenels, the instruments set up one after another, backlit, the brass glinting."""
    u = (v - 12.5) / 3.0
    e = TL.ease_io(u)
    hour = S4_HOURS[0] + (S4_HOURS[1] - S4_HOURS[0]) * u
    tc = S4_TC[0] + (S4_TC[1] - S4_TC[0]) * u
    cx, cy = FB.TOWER_C
    top = FB.TOWER_TOP
    deck = top - 0.1
    c0 = (cx + 3.3, cy + 2.15, top + 1.3)
    c1 = (cx + 2.9, cy + 1.85, top + 1.22)
    look = Vector((math.cos(math.radians(90.0 - 250.0)), math.sin(math.radians(90.0 - 250.0)), 0.02))
    loc = Vector(lerp3(c0, c1, e))
    cam = (tuple(loc), tuple(loc + look * 20.0), 28.0)
    meta = env(S, v, hour, cam, tc, S4_SKY + 0.002 * v, cover=0.3)
    FC.smoke_light(S, hour)
    q = (tc - FB.TC_INSTR[0]) / (FB.TC_INSTR[1] - FB.TC_INSTR[0])
    P = S4_POS
    if q > 0.0:
        IN.pose_armillary(S.armillary, tower_top_frame(*P['armillary']), spin=0.0)
    if q > 0.35:
        IN.pose_triquetrum(S.triquetrum, tower_top_frame(*P['triquetrum'], math.radians(200.0)), math.radians(55.0))
    if q > 0.7:
        S.quadrant.matrix_world = tower_top_frame(*P['quadrant'], math.radians(90.0))
        S.quadrant.hide_render = False
    # two carpenters: first at the sphere and the parapet, then at the triquetrum and the quadrant
    spots = [(P['armillary'], (-0.2, 0.85)) if q <= 0.35 else (P['triquetrum'], (0.6, -0.55)),
             ((-3.0, 0.4), (1.0, 0.0)) if q <= 0.7 else (P['quadrant'], (0.75, 0.35))]
    for j, ((ix, iy), (ox, oy)) in enumerate(spots):
        w = S.workers[j]
        wx, wy = ix + ox, iy + oy
        k_pose = int(SC.hop(j + 40, v * 2.0, 1.4) * 2.99) if (j == 0 or q > 0.7) else 2
        w.data = S.fig_workers[k_pose]
        w.matrix_world = (Matrix.Translation((cx + wx, cy + wy, deck))
                          @ Matrix.Rotation(math.atan2(iy - wy, ix - wx) - math.pi / 2, 4, 'Z'))
        w.color = ((0.36, 0.25, 0.15, 1.0), (0.28, 0.28, 0.27, 1.0))[j]
        w.hide_render = False
    # Copernicus by the armillary sphere, turned to it
    ax, ay = P['armillary']
    px, py = P['copernicus']
    S.observer.hide_render = False
    S.observer.data = S.fig_observer[3]
    S.observer.matrix_world = (Matrix.Translation((cx + px, cy + py, deck))
                               @ Matrix.Rotation(math.atan2(ay - py, ax - px) - math.pi / 2, 4, 'Z'))
    meta.update(stars=0.0)
    return meta


S5_HOURS = (19.9, 20.5)                 # the moon climbs from 8 to 13 deg in the ENE
S5_CAM = (-2.9, -2.9, 0.9)              # low in the platform's south-west corner, looking NE
S5_OBS = (-0.81, -0.22)                 # where Copernicus stands on his step (from the tower centre): 3/4 from behind
STEP_H = 0.38                           # the step lifts his eye to the triquetrum's eye end


def shot_S5(S, v):
    u = (v - 15.5) / 4.5
    e = TL.ease_io(u)
    hour = S5_HOURS[0] + (S5_HOURS[1] - S5_HOURS[0]) * u
    cx, cy = FB.TOWER_C
    top = FB.TOWER_TOP
    deck = top - 0.1
    md = moon_dir(hour)
    m_az = math.atan2(md[1], md[0])
    m_el = math.asin(max(-1.0, min(1.0, md[2])))
    fwd = Vector((math.cos(m_az), math.sin(m_az), 0.0))
    left = Vector((-math.sin(m_az), math.cos(m_az), 0.0))
    # the camera tilts from Copernicus and the rising moon up into the turning sky
    cam_p = Vector((cx + S5_CAM[0], cy + S5_CAM[1], top + S5_CAM[2]))
    yaw = math.radians(90.0 - 45.0)
    pitch = math.radians(14.0 + 16.0 * e)
    look = Vector((math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
    cam = (tuple(cam_p), tuple(cam_p + look * 50.0), 14.0)
    meta = env(S, v, hour, cam, 12.0, S5_SKY, cover=0.1, hdri=0.0, moon=0.35, moon_light=1.0, moon_halo=0.03)
    FC.smoke_light(S, hour)
    # Copernicus on his step, his eye at the eye end of the triquetrum; the post stands
    # 2.2 m further towards the moon, its rule at the moon's zenith distance
    kk = min(int(u * 3), 2)
    pose_k = OBSERVER_POSES[kk]
    z = math.pi / 2 - max(m_el, math.radians(4.0))
    obs = Vector((cx + S5_OBS[0], cy + S5_OBS[1], deck))
    foot = obs + fwd * (IN.TQ_AB * math.sin(z) + 0.08 + pose_k['stoop']) - left * 0.1
    IN.pose_triquetrum(S.triquetrum, Matrix.Translation(foot) @ Matrix.Rotation(m_az, 4, 'Z'), z)
    rot = Matrix.Rotation(m_az - math.pi / 2, 4, 'Z')
    S.step.matrix_world = Matrix.Translation(obs) @ rot
    S.step.hide_render = False
    S.observer.hide_render = False
    S.observer.data = S.fig_observer[kk]
    S.observer.matrix_world = Matrix.Translation(obs + Vector((0.0, 0.0, STEP_H))) @ rot
    IN.pose_armillary(S.armillary, tower_top_frame(-2.6, -0.2), spin=0.0)
    lp = obs + fwd * 0.85 - left * 0.4                           # the lantern on the deck, right in front of him
    S.lantern.matrix_world = Matrix.Translation(lp) @ rot
    S.lantern_light.location = lp + Vector((0.0, 0.0, 0.16))
    S.lantern_light.data.energy = 9.0 * (0.9 + 0.1 * SC.smooth_rand(7, v, 5.0))
    S.lantern.hide_render = S.lantern_light.hide_render = False
    for i in range(len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.8, star_trail=0.8 + (hour - S5_HOURS[0]), expo_mul=0.7, sky_glow=0.15)
    return meta


SHOT_FN = dict(S1=shot_S1, S2=shot_S2, S3=shot_S3, S4=shot_S4, S5=shot_S5)


def pose(S, f):
    v = f / FPS
    name, a, b = shot_at(v)
    hide_extras(S)
    meta = SHOT_FN[name](S, v)
    if name != 'S2':
        L.pose_treadwheel(S, 0.8 * v)
    life.apply_wakes(S)
    meta.update(shot=name, shot_t=v - a, t=v, smoke=S.post_smoke, smoke_light=getattr(S, 'smoke_rgb', [1.0, 1.0, 1.0]))
    return meta
