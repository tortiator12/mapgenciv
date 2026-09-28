"""The 20-s Civ1 wonder film "Magellans Expedition" (wunderfilm_08_magellan).

The "wonder" is the fitting-out of the fleet (seville.py, ships.py,
storyboards/runde1_fehlende_wunder.md):
  S1  0.0- 3.0 s  the Arenal at Seville, a summer morning, the Torre del Oro beyond:
                  barrels, sacks, bronze guns and coils of rope on ox carts and in
                  stacks, merchants and soldiers; four naos moored with their bows
                  to the bank
  S2  3.0- 9.0 s  time-lapse: the Victoria lies careened, hove down towards the shore
                  by tackles from her mastheads, her bottom towards the river; men on
                  a raft scrape the weed off from the stern forwards, the pitch kettle
                  smokes on the beach; she is righted in steps, sheer legs set her
                  topmasts, then yards and sails go up; the other ships in other
                  stages round her
  S3  9.0-12.0 s  on her deck: a barrel lowered into the hold from the main yard, the
                  compass and an astrolabe carried aft, the flag hoisted
  S4 12.0-15.0 s  the departure: the five ships run down the river with all sails set
                  (time-lapse), the people on the Arenal wave
  S5 15.0-20.0 s  September 1522, sunrise at Sanlucar: the Victoria comes in alone
                  under patched sails, the people on the beach, the church tower on
                  its hill, her salute gun smokes

One wind for everything: the northerly down the valley (the fleet runs before it,
smoke drifts south).
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import film_colossus20 as FC
import film_lighthouse20 as L
import geometry as G
import life
import scene as SC
import seville as SV
import ships as SH
import timeline as TL

TL.LATITUDE = math.radians(SV.LATITUDE_DEG)
TL.DECLINATION = math.radians(10.0)          # late summer

FPS = 24
DURATION = 20.0
NFRAMES = int(round(FPS * DURATION))
LOOK = 'bright'
SHOTS = [('S1', 0.0, 3.0), ('S2', 3.0, 9.0), ('S3', 9.0, 12.0), ('S4', 12.0, 15.0), ('S5', 15.0, 20.0)]
CUTS = [s[1] for s in SHOTS[1:]]
GRADE = dict(warm={'S1': (0.8, 4.5), 'S2': (0.6, 4.0), 'S3': (0.7, 4.5), 'S4': (0.6, 4.0), 'S5': (1.8, 7.0)},
             gain={'S1': 0.95, 'S2': 0.95, 'S3': 0.95, 'S4': 0.96, 'S5': 0.97},
             dust={'S1': 0.2, 'S2': 0.16, 'S3': 0.05, 'S4': 0.14, 'S5': 0.08})
lerp3 = FC.lerp3
NAMES = ['Trinidad', 'SanAntonio', 'Concepcion', 'Victoria', 'Santiago']
SCALE = [1.06, 1.1, 0.98, 1.0, 0.92]


def shot_at(v):
    for name, a, b in SHOTS:
        if a <= v < b:
            return name, a, b
    return SHOTS[-1]


# ================================================================== people
def mat_person_1519():
    """The lighthouse figures in 1519: doublets and hose, jerkins, a few morion
    helmets (steel); skin only on head and hands; the doublet's colour from the object."""
    m, nb, out = SC.new_material('Person1519')
    oi = nb.new('ShaderNodeObjectInfo')
    rnd = oi.outputs['Random']
    reg = nb.attr('region').outputs['Fac']
    oz = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[2]
    coat = oi.outputs['Color']
    skin = nb.mix(rnd, (0.52, 0.36, 0.26, 1), (0.64, 0.46, 0.34, 1))
    hair = nb.mix(nb.math('FRACT', nb.math('MULTIPLY', rnd, 3.17)), (0.05, 0.035, 0.025, 1), (0.22, 0.15, 0.09, 1))
    steel = nb.math('GREATER_THAN', nb.math('FRACT', nb.math('MULTIPLY', rnd, 7.31)), 0.72)
    hair = nb.mix(steel, hair, (0.55, 0.56, 0.58, 1))
    hose = nb.mix(nb.math('FRACT', nb.math('MULTIPLY', rnd, 5.73)), (0.14, 0.10, 0.08, 1), (0.42, 0.10, 0.08, 1))
    is_skin = nb.math('COMPARE', reg, float(L.R_SKIN), 0.5)
    head = nb.math('GREATER_THAN', oz, 1.5)
    legs = nb.math('LESS_THAN', oz, 0.85)
    col = coat
    col = nb.mix(nb.math('MULTIPLY', is_skin, legs), col, hose)
    col = nb.mix(nb.math('MULTIPLY', is_skin, head), col, skin)
    for k, c in ((L.R_HAIR, hair), (L.R_BEARD, (0.08, 0.06, 0.04, 1)), (L.R_BELT, (0.10, 0.07, 0.05, 1)), (L.R_SANDAL, (0.08, 0.05, 0.03, 1)),
                 (L.R_BASKET, (0.52, 0.39, 0.2, 1)), (L.R_POT, (0.55, 0.25, 0.12, 1)), (L.R_WOOD, (0.30, 0.20, 0.11, 1))):
        f = nb.math('COMPARE', reg, float(k), 0.5)
        col = nb.mix(f, col, c)
    metal = nb.math('MULTIPLY', steel, nb.math('COMPARE', reg, float(L.R_HAIR), 0.5))
    b = SC.principled(nb, col, rough=nb.math('SUBTRACT', 0.85, nb.math('MULTIPLY', metal, 0.5)), spec=0.3)
    nb.feed(b.inputs['Metallic'], metal)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


CLOTHES = [(0.45, 0.10, 0.07, 1), (0.12, 0.10, 0.09, 1), (0.55, 0.42, 0.18, 1), (0.30, 0.28, 0.22, 1), (0.18, 0.22, 0.34, 1),
           (0.62, 0.56, 0.44, 1), (0.36, 0.20, 0.10, 1), (0.08, 0.08, 0.09, 1)]


# ================================================================== props
def barrel(bb, x, y, z, r=0.32, h=0.85, upright=True, rot=0.0, mat=0):
    """A cask as an octagonal prism (three hexahedra), standing or lying."""
    P = G.oct_poly(r)
    for q in ((0, 1, 2, 3), (0, 3, 4, 7), (4, 5, 6, 7)):
        if upright:
            bb.add(G._hexa(P[list(q)] + [x, y], P[list(q)] + [x, y], z, z + h), mat=mat)
        else:
            c = G._hexa(P[list(q)], P[list(q)], -h / 2, h / 2)
            c = c[:, [2, 0, 1]]                                           # lie along x
            cr, sr = math.cos(rot), math.sin(rot)
            c = np.stack([c[:, 0] * cr - c[:, 1] * sr + x, c[:, 0] * sr + c[:, 1] * cr + y, c[:, 2] + z + r], 1)
            bb.add(c, mat=mat)


def build_props(S):
    """The Arenal's cargo: stacks of casks, sacks, bronze guns on their carriages,
    coils of rope, crates; the pitch kettle on its tripod; the careening capstans."""
    pb = G.HexBatch('arenal')
    rng = np.random.default_rng(1519)
    for (cx, cy) in ((14.0, -20.0), (22.0, -55.0), (10.0, -85.0), (26.0, 5.0)):
        for i in range(10):                                               # casks, two tiers
            x, y = cx + (i % 5) * 0.72, cy + (i // 5) * 0.72
            barrel(pb, x, y, SV.ground_z(x, y) - 0.05, mat=0)
            if i % 3 == 0:
                barrel(pb, x + 0.36, y + 0.36, SV.ground_z(x, y) + 0.8, mat=0)
        for i in range(8):                                                # sacks
            x, y = cx + 4.5 + rng.uniform(0, 2.4), cy + rng.uniform(-1.0, 1.0)
            pb.add(G.box(x, y, SV.ground_z(x, y) - 0.05, 0.9, 0.55, 0.45 + 0.1 * (i % 2), rng.uniform(0, 3)), mat=1)
    for k, (x, y, rot) in enumerate(((18.0, -34.0, 0.3), (20.0, -38.0, -0.2), (6.0, -64.0, 1.2))):     # bronze guns
        z = SV.ground_z(x, y)
        pb.add(G.box(x, y, z, 1.6, 0.8, 0.45, rot), mat=2)
        c, s_ = math.cos(rot), math.sin(rot)
        pb.add(G.beam([x - 1.3 * c, y - 1.3 * s_, z + 0.7], [x + 1.4 * c, y + 1.4 * s_, z + 0.62], 0.34, 0.34), mat=3)
    for (x, y) in ((12.0, -46.0), (13.4, -47.0), (24.0, -10.0)):          # coils of rope
        z = SV.ground_z(x, y)
        P = G.oct_poly(0.55)
        for q in range(8):
            pb.add(G.beam(np.append(P[q] + [x, y], z + 0.12), np.append(P[(q + 1) % 8] + [x, y], z + 0.12), 0.22, 0.22), mat=4)
    for i in range(6):                                                    # crates
        x, y = 30.0 + rng.uniform(-3, 3), -30.0 + i * 1.3
        pb.add(G.box(x, y, SV.ground_z(x, y) - 0.05, 1.0, 0.9, 0.8, rng.uniform(-0.2, 0.2)), mat=5)
    # the pitch kettle on a tripod over its fire, by the careened ship
    kx, ky = KETTLE
    kz = SV.ground_z(kx, ky)
    for a in (0.0, 2.1, 4.2):
        pb.add(G.beam([kx + 1.2 * math.cos(a), ky + 1.2 * math.sin(a), kz], [kx, ky, kz + 2.2], 0.1), mat=5)
    barrel(pb, kx, ky, kz + 0.55, r=0.45, h=0.7, mat=6)
    for a in (0.0, 1.6, 3.2, 4.7):                                        # firewood
        pb.add(G.beam([kx + 0.7 * math.cos(a), ky + 0.7 * math.sin(a), kz + 0.1], [kx, ky, kz + 0.35], 0.12), mat=5)
    for (x, y) in CAPSTANS:                                               # the careening capstans ashore
        z = SV.ground_z(x, y)
        barrel(pb, x, y, z - 0.1, r=0.45, h=1.1, mat=5)
        pb.add(G.beam([x - 1.4, y, z + 0.9], [x + 1.4, y, z + 0.9], 0.1), mat=5)
        pb.add(G.beam([x, y - 1.4, z + 0.9], [x, y + 1.4, z + 0.9], 0.1), mat=5)
    pb.finalize()
    mats = [SC.mat_wood('Casks', (0.40, 0.27, 0.15)), SC.mat_simple('Sacks', (0.62, 0.54, 0.40), 0.95),
            S.m_wood, SC.mat_simple('Bronze', (0.55, 0.38, 0.20), 0.35, metal=1.0), S.m_rope, S.m_plank,
            SC.mat_simple('KettleIron', (0.08, 0.07, 0.07), 0.5, metal=0.6)]
    S.props = SC.link(bpy.data.objects.new('ArenalProps', SC.hex_mesh('ArenalProps', pb, np.ones(len(pb.t_on), bool), mats)))
    S.props.pass_index = SC.PASS['props']
    fl = SC.prism('KettleFire', 0.5, 0.0, 0.7, 7, 0.05, (0, 0), [S.m_torch])
    S.kettle_fire = SC.link(bpy.data.objects.new('KettleFire', fl))
    S.kettle_fire.location = (kx, ky, kz + 0.05)
    S.kettle_fire.visible_shadow = False
    # the raft the scrapers stand on, the sheer legs, the careening tackles (built per frame)
    rb = G.HexBatch('raft')
    for i in range(6):
        rb.add(G.beam([-5.0, -1.2 + 0.48 * i, 0.0], [5.0, -1.2 + 0.48 * i, 0.0], 0.42, 0.3), mat=0)
    rb.add(G.beam([-4.6, -1.4, 0.2], [-4.6, 1.4, 0.2], 0.2, 0.2), mat=0)
    rb.add(G.beam([4.6, -1.4, 0.2], [4.6, 1.4, 0.2], 0.2, 0.2), mat=0)
    rb.finalize()
    S.raft = SC.link(bpy.data.objects.new('Raft', SC.hex_mesh('Raft', rb, np.ones(len(rb.t_on), bool), [S.m_wood])))
    S.raft.pass_index = SC.PASS['props']
    lb = G.HexBatch('sheerlegs')
    lb.add(G.beam([0.0, -3.0, 0.0], [0.0, -0.2, 24.0], 0.34), mat=0)
    lb.add(G.beam([0.0, 3.0, 0.0], [0.0, 0.2, 24.0], 0.34), mat=0)
    lb.add(G.beam([0.0, 0.0, 24.0], [-12.0, 0.0, 0.0], 0.06), mat=1)        # the back guy
    lb.finalize()
    S.sheerlegs = SC.link(bpy.data.objects.new('SheerLegs', SC.hex_mesh('SheerLegs', lb, np.ones(len(lb.t_on), bool), [S.m_wood, S.m_rope])))
    S.sheerlegs.pass_index = SC.PASS['crane']
    S.tackles = SC.link(bpy.data.objects.new('Tackles', bpy.data.meshes.new('Tackles')))
    S.tackles.pass_index = SC.PASS['crane']
    S.cargo = SC.link(bpy.data.objects.new('Cargo', bpy.data.meshes.new('Cargo')))
    S.cargo.pass_index = SC.PASS['props']


VICTORIA_CAREEN = (-6.0, 62.0)               # where she lies hove down, parallel to the bank, bow north
KETTLE = (6.0, 50.0)
CAPSTANS = [(14.0, 56.0), (14.0, 68.0)]


# ================================================================== build
def build(res=(1280, 720)):
    S = SV.build(res)
    L.build_people(S, n_people=160)
    m_p = mat_person_1519()
    for meshes in S.pose_meshes.values():
        for me in meshes:
            me.materials[0] = m_p
    S.cranes = []
    L.build_carts(S, n=3)
    S.m_sailcloth = L.mat_sailcloth('SailCloth', SC.P['sail'])
    life.build(S, L)
    FC._emissive_smoke(S)
    S.ships = []
    for k, nm in enumerate(NAMES):
        spec = dict(SH.NAO)
        sc_ = SCALE[k]
        spec.update(L=SH.NAO['L'] * sc_, B=SH.NAO['B'] * sc_, draft=SH.NAO['draft'] * sc_)
        S.ships.append(SH.build(S, spec, nm, patched=False))
    S.victoria = S.ships[3]
    build_props(S)
    bpy.data.meshes['Cart'].materials[1] = SC.mat_wood('CartCrates', (0.40, 0.27, 0.15))
    return S


def hide_extras(S):
    for o in S.people + [S.raft, S.sheerlegs, S.tackles, S.cargo, S.kettle_fire]:
        o.hide_render = True
    for c, wheels, oxen in S.carts:
        c.hide_render = True
        for w, _ in wheels:
            w.hide_render = True
        for o, _ in oxen:
            o.hide_render = True
    for sh in S.ships:
        SH.hide(sh)
    life.hide_all(S)
    S.post_smoke = []
    S.sea.hide_render = False
    S.sea2.hide_render = True


def env(S, v, hour, cam, rot, **kw):
    return SV.pose(S, v, hour=hour, sea_t=30.0 + v, water_t=10.0 + 0.4 * v, cloud_t=hour * 0.75, shadow_t=hour * 124.0,
                   cover=kw.pop('cover', 0.35), cloud_gain=7.0, shadow_cover=0.3, hdri=kw.pop('hdri', 1.0), hdri_rot=rot, cam=cam, **kw)


def moored(S, t, which=(0, 1, 2, 4), rig=3.0, sails=0.0):
    """The ships at their moorings along the Arenal, bows to the bank."""
    spots = {0: (-15.0, -40.0), 1: (-16.0, -84.0), 2: (-17.0, 12.0), 3: (-15.0, 22.0), 4: (-19.0, -118.0)}
    for k in which:
        x, y = spots[k]
        SH.pose(S.ships[k], (x, y, 0.1 + 0.03 * math.sin(0.9 * t + k)), 0.0 + 0.01 * math.sin(0.5 * t + k), t,
                sails=sails, heel=0.01 * math.sin(0.7 * t + k), rig=rig)


def people_on_arenal(S, k, t, n, box, seed, modes=('walk', 'carry', 'stand', 'haul'), heading=None, avoid=None):
    rng = np.random.default_rng(seed)
    (x0, x1, y0, y1) = box
    for j in range(n):
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if avoid is not None and math.hypot(x - avoid[0], y - avoid[1]) < avoid[2]:
            continue
        mode = modes[j % len(modes)]
        hd = rng.uniform(0, 2 * math.pi) if heading is None else heading + rng.uniform(-0.5, 0.5)
        if mode == 'walk':
            x += 1.2 * t * math.cos(hd)
            y += 1.2 * t * math.sin(hd)
        L.place_person(S, k, (x, y, SV.ground_z(x, y)), hd, mode, 2.0 * t + j)
        S.people[k].color = CLOTHES[(j + seed) % len(CLOTHES)]
        k += 1
    return k


# ================================================================== shots
S1_SKY, S2_SKY, S3_SKY, S4_SKY, S5_SKY = 1.0, 2.2, 0.4, 3.0, 4.6


def shot_S1(S, v):
    u = v / 3.0
    e = TL.ease_io(u)
    hour = 8.2 + 0.1 * u
    c0, c1 = (28.0, 10.0), (27.0, 6.0)
    cam = (lerp3((c0[0], c0[1], SV.ground_z(*c0) + 1.8), (c1[0], c1[1], SV.ground_z(*c1) + 1.85), e),
           lerp3((-5.0, -110.0, 5.0), (-6.0, -112.0, 5.0), e), 28.0)
    meta = env(S, v, hour, cam, S1_SKY + 0.002 * v)
    FC.smoke_light(S, hour)
    moored(S, v)
    for ci, (x0, y0, dy) in enumerate(((20.0, 20.0, -1.2), (28.0, -70.0, 1.0), (12.0, -5.0, -0.9))):
        y = y0 + dy * v
        FC.place_cart(S, ci, (x0, y), math.pi / 2 if dy > 0 else -math.pi / 2, abs(dy) * v, SV.ground_z(x0, y))
    k = people_on_arenal(S, 0, v, 34, (4.0, 40.0, -100.0, 30.0), 3, avoid=(cam[0][0], cam[0][1], 14.0))
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


S2_LAPSE = FC.Lapse(3.0, 9.0, [(3.0, 7.6), (9.0, 18.4)], 0.0, 1.0)


def s2_heel(q):
    """Hove down, then righted in steps as the tackles are eased."""
    if q < 0.45:
        return math.radians(50.0)
    steps = [50.0, 36.0, 22.0, 9.0, 0.0]
    i = min(int((q - 0.45) / 0.15 * 4.0), 4)
    return math.radians(steps[i])


def shot_S2(S, v):
    lp = S2_LAPSE
    hour = lp.hour(v)
    q = lp.tc(v)                                          # the refit's progress 0..1
    u = TL.ease_io((v - 3.0) / 6.0)
    vx, vy = VICTORIA_CAREEN
    cam = (lerp3((-62.0, 30.0, 4.5), (-58.0, 44.0, 5.5), u), lerp3((vx + 2.0, vy, 4.5), (vx + 2.0, vy + 2.0, 7.0), u), 32.0)
    meta = env(S, v, hour, cam, S2_SKY + 0.05 * (v - 3.0), cover=0.3 + 0.05 * math.sin(v))
    FC.smoke_light(S, hour)
    hop_t = 2.0 * v
    heel = s2_heel(q)
    rig = 0.0 if q < 0.62 else (1.0 if q < 0.74 else (2.0 if q < 0.86 else 3.0))
    sails = 0.0
    zc = 0.6 * (heel / math.radians(50.0))
    shp = S.victoria
    L_ = shp.spec['L']
    clean = (-0.5 + min(q / 0.42, 1.0)) * L_                              # scraped from the stern forwards
    SH.pose(shp, (vx, vy, zc - 0.1), math.pi / 2, v, sails=sails, heel=heel, rig=rig, foul=1.0, clean_x=clean,
            flag=False)
    # the other ships round her, in other stages of the work
    for k, (x, y, r, sl) in ((0, (-18.0, 0.0, 3.0, 0.0)), (2, (-20.0, 110.0, 1.0, 0.0)), (1, (-24.0, -45.0, 2.0, 0.0)),
                             (4, (-60.0, 95.0, 3.0, 0.0))):
        SH.pose(S.ships[k], (x, y, 0.1), 0.0, v, sails=sl, rig=r)
    k = 0
    if q < 0.45:
        # the raft along her bottom with the scrapers, the tackles from the mastheads to the capstans
        M = shp.root.matrix_world
        S.raft.matrix_world = Matrix.Translation((vx - 5.6, vy, 0.05)) @ Matrix.Rotation(math.pi / 2, 4, 'Z')
        S.raft.hide_render = False
        for j in range(5):
            if SC.hop(j + 10, hop_t, 2.0) > 0.85:
                continue
            yy = vy - 9.0 + 4.0 * j + 1.5 * SC.hop(j + 20, hop_t, 2.0)
            L.place_person(S, k, (vx - 5.2 + 0.4 * (j % 2), yy, 0.3), 0.0, ('hammer', 'haul')[j % 2], 2 * math.pi * SC.hop(j + 30, hop_t, 2.0))
            S.people[k].color = CLOTHES[(j + 2) % len(CLOTHES)]
            k += 1
        tb = G.HexBatch('tackles')
        for mi, (cx, cy) in enumerate(CAPSTANS):
            xm, zd = SH.mast_foot(shp.spec, shp.st, shp.spec['masts'][mi])
            top = M @ Vector((xm, 0.0, zd + shp.spec['masts'][mi].get('top', 10.0)))
            tb.add(G.beam(list(top), [cx, cy, SV.ground_z(cx, cy) + 0.9], 0.12), mat=0)
        tb.finalize()
        SC.set_dynamic_mesh(S.tackles, 'Tackles', tb, np.ones(len(tb.t_on), bool), [S.m_rope])
        S.tackles.hide_render = False
        for j, (cx, cy) in enumerate(CAPSTANS):                          # men at the capstan bars
            for a in (0.0, math.pi):
                L.place_person(S, k, (cx + 1.2 * math.cos(a + 0.6 * v), cy + 1.2 * math.sin(a + 0.6 * v), SV.ground_z(cx, cy)),
                               a + 0.6 * v + math.pi / 2, 'haul', 3.0 * v + j)
                S.people[k].color = CLOTHES[(j * 2 + 1) % len(CLOTHES)]
                k += 1
    if 0.6 < q < 0.8:
        # the sheer legs on the beach over her mainmast, a topmast in its tackle
        xm, zd = SH.mast_foot(shp.spec, shp.st, shp.spec['masts'][0])
        p = shp.root.matrix_world @ Vector((xm, 0.0, 0.0))
        S.sheerlegs.matrix_world = Matrix.Translation((p.x + 9.0, p.y, SV.ground_z(p.x + 9.0, p.y))) @ Matrix.Rotation(0.0, 4, 'Z') \
            @ Matrix.Rotation(-0.36, 4, 'Y')
        S.sheerlegs.hide_render = False
    # the pitch kettle smokes all day
    S.kettle_fire.hide_render = False
    S.m_torch.node_tree.nodes['torch_k'].outputs[0].default_value = 0.8
    kx, ky = KETTLE
    FC.smoke(S, [life.Plume((kx, ky, SV.ground_z(kx, ky) + 1.4), n=10, life=9.0, rise=1.0, drift=1.2, size0=0.8, grow=0.6, dens=0.7, seed=5)],
             50.0 + 3.0 * v)
    k = people_on_arenal(S, k, v, 14, (2.0, 30.0, 30.0, 90.0), 11, modes=('walk', 'carry', 'haul'))
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


S3_POS = (-15.0, 22.0)                        # the Victoria at her mooring, rigged


def shot_S3(S, v):
    u = (v - 9.0) / 3.0
    e = TL.ease_io(u)
    hour = 11.0 + 0.1 * u
    shp = S.victoria
    x0, y0 = S3_POS
    SH.pose(shp, (x0, y0, 0.1), 0.0, v, sails=0.0, rig=3.0, flag_up=TL.smoothstep(0.1, 0.95, u))
    M = shp.root.matrix_world
    st = shp.st
    zq = float(np.interp(0.24, st[0], st[4])) + 2.2
    c0 = M @ Vector((-8.4, -1.6, zq + 1.6))
    c1 = M @ Vector((-8.0, -1.4, zq + 1.65))
    tg = M @ Vector((3.0, 0.4, zq - 0.6))
    cam = (tuple(c0.lerp(c1, e)), tuple(tg), 26.0)
    meta = env(S, v, hour, cam, S3_SKY, cover=0.3)
    FC.smoke_light(S, hour)
    moored(S, v, which=(0, 2, 4), rig=3.0)
    zd = float(np.interp(0.5, st[0], st[4]))
    # a cask lowered from the main yard into the hold
    xm, zm = SH.mast_foot(shp.spec, st, shp.spec['masts'][0])
    arm = Vector((xm + 0.4, -2.2, zm + 12.6))
    bz = zd + 6.0 - 7.0 * TL.smoothstep(0.0, 0.85, u)
    cb = G.HexBatch('cargo')
    barrel(cb, 0.0, 0.0, 0.0, r=0.36, h=0.95)
    cb.add(G.beam([0, 0, 0.95], [0, 0, 0.95 + (arm.z - bz)], 0.04), mat=1)
    cb.finalize()
    SC.set_dynamic_mesh(S.cargo, 'Cargo', cb, np.ones(len(cb.t_on), bool), [SC.mat_wood('Casks2', (0.40, 0.27, 0.15)), S.m_rope])
    S.cargo.matrix_world = M @ Matrix.Translation((arm.x, arm.y, bz))
    S.cargo.hide_render = False
    k = 0
    for j, (lx, ly, mode, hd) in enumerate(((0.8, -1.2, 'haul', math.pi / 2), (1.6, -1.6, 'haul', math.pi / 2),
                                             (-2.0, 1.1, 'carry', math.pi), (-4.2, 0.6, 'walk', math.pi),
                                             (4.0, 1.2, 'stand', math.pi), (-1.0, 2.0, 'haul', 0.0))):
        if mode == 'walk':
            lx -= 1.0 * u
        p = M @ Vector((lx, ly, zd - 0.45))
        L.place_person(S, k, (p.x, p.y, p.z), hd, mode, 2.0 * v + j)
        S.people[k].color = CLOTHES[(j + 4) % len(CLOTHES)]
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


def shot_S4(S, v):
    """The departure, time-lapse: the five ships run down the river before the wind."""
    u = (v - 12.0) / 3.0
    e = TL.ease_io(u)
    hour = 9.0 + 1.5 * u
    cam = (lerp3((-2.0, -205.0, 4.0), (-3.0, -202.0, 4.3), e), (-48.0, -40.0, 10.0), 26.0)
    meta = env(S, v, hour, cam, S4_SKY + 0.02 * v, cover=0.3)
    FC.smoke_light(S, hour)
    for k in range(5):
        y = 120.0 - 42.0 * k - 55.0 * (v - 12.0)
        x = -72.0 + 6.0 * math.sin(0.02 * y + k)
        SH.pose(S.ships[k], (x, y, 0.15), -math.pi / 2 + 0.03 * math.sin(0.3 * v + k), v, sails=1.0, rig=3.0,
                heel=math.radians(3.0), pitch=0.01 * math.sin(1.1 * v + k), billow=1.0)
        life.add_wake(S, (x, y), -math.pi / 2, 0.6, S.ships[k].spec['L'])
    k = people_on_arenal(S, 0, v, 40, (2.0, 30.0, -140.0, -20.0), 21, modes=('hammer', 'stand', 'hammer', 'walk'),
                         heading=math.pi)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    meta.update(stars=0.0)
    return meta


S5_SHIP0 = (-200.0, -165.0)


def shot_S5(S, v):
    """6 September 1522, sunrise at Sanlucar: the Victoria alone, patched, fires a salute."""
    u = (v - 15.0) / 5.0
    e = TL.ease_io(u)
    hour = 6.05 + 0.25 * u
    sx, sy = SV.SANLUCAR
    S.sea.hide_render = True
    S.sea2.hide_render = False
    S.ocean2.time = 40.0 + v * 2.2
    S.sea2.data.materials[0].node_tree.nodes['water_time'].outputs[0].default_value = 12.0 + 0.9 * v
    c0, c1 = (sx - 330.0, sy - 185.0, 3.6), (sx - 328.0, sy - 181.0, 3.7)        # from the sea, into the sunrise
    cam = (lerp3(c0, c1, e), (sx + 200.0, sy + 40.0, 14.0), 30.0)
    meta = env(S, v, hour, cam, S5_SKY, cover=0.25)
    FC.smoke_light(S, hour)
    shp = S.victoria
    x = sx + S5_SHIP0[0]
    y = sy + S5_SHIP0[1] + 2.6 * (v - 15.0) + 60.0
    x += 1.5 * (v - 15.0)
    SH.pose(shp, (x, y, 0.12), math.radians(60.0), v, sails={'course': 1.0, 'topsail': 0.0, 'lateen': 1.0, 'sprit': 1.0},
            rig=3.0, heel=math.radians(4.0), pitch=0.012 * math.sin(1.0 * v), billow=0.8, patched=True)
    life.add_wake(S, (x, y), math.radians(60.0), 0.4, shp.spec['L'])
    # the salute: a gun on her starboard side (towards the beach) smokes at 16.4 s
    if v > 16.4:
        age = v - 16.4
        gp = shp.root.matrix_world @ Vector((2.0, -3.9, 2.6))
        out = (shp.root.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
        for i in range(9):                                                # a burst of powder smoke, drifting south
            a = age * (0.55 + 0.08 * i)
            d = 7.0 * (1.0 - math.exp(-2.5 * a)) * (0.6 + 0.08 * i)
            p = gp + out * d + Vector((0.0, -1.3 * a, 0.5 * a + 0.3 * math.sin(i)))
            S.post_smoke.append([p.x, p.y, p.z, 1.6 + 2.4 * a ** 0.8, max(0.0, 0.85 - 0.17 * a), 0.0, (i * 0.137) % 1.0,
                                 min(a / 4.0, 1.0), 0])
    k = 0
    rng = np.random.default_rng(1522)
    for j in range(24):                                                   # people on the beach, waving
        x_ = sx + rng.uniform(-8.0, 30.0)
        y_ = sy + rng.uniform(-130.0, -20.0)
        L.place_person(S, k, (x_, y_, SV.ground_z(x_, y_)), math.pi + rng.uniform(-0.4, 0.4), ('hammer', 'stand')[j % 2],
                       3.0 * v + j)
        S.people[k].color = CLOTHES[j % len(CLOTHES)]
        k += 1
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
    life.apply_wakes(S)
    meta.update(shot=name, shot_t=v - a, t=v, smoke=S.post_smoke, smoke_light=getattr(S, 'smoke_rgb', [1.0, 1.0, 1.0]))
    return meta
