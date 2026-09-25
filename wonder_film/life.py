"""Life around the Pharos site for the 20-s film: rowing boats whose oars
move with their rowers, small sailing boats, ships at anchor, smoke, pennants
and the clutter of a working quay.  Built once by build(), placed per frame by
film_lighthouse20.py.

Physics kept honest:
  * rowing: the blade is in the water only on the drive (catch to finish),
    lifted on the recovery; the boat surges on the drive; rowers sit facing aft
  * one wind for everything: the Etesian north-north-westerly, blowing towards
    SSE.  Smoke drifts and pennants stream that way; sails only run before it.
  * smoke rises, spreads and thins with age; a puff is recycled only once it
    has faded out, so nothing pops.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import geometry as G
import scene as SC

WIND = np.array([0.38, -0.92])
WIND = WIND / np.linalg.norm(WIND)           # towards bearing ~158 deg (SSE)
WIND_HEADING = math.atan2(WIND[1], WIND[0])  # CCW from +x


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ================================================================= small helpers
def lathe(profile, n=10):
    """Solid of revolution about +z; profile = [(radius, z), ...] bottom to top."""
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = np.array([(r * math.cos(a), r * math.sin(a), z) for r, z in profile for a in ang])
    F = []
    for i in range(len(profile) - 1):
        for k in range(n):
            a, b = i * n + k, i * n + (k + 1) % n
            F.append([a, b, b + n, a + n])
    return V, np.array(F)


AMPHORA = [(0.0, 0.0), (0.035, 0.02), (0.11, 0.18), (0.17, 0.42), (0.16, 0.6), (0.075, 0.72),
           (0.055, 0.86), (0.075, 0.9), (0.0, 0.9)]
PITHOS = [(0.0, 0.0), (0.2, 0.02), (0.36, 0.3), (0.4, 0.62), (0.3, 0.95), (0.22, 1.05), (0.26, 1.1), (0.0, 1.1)]
BASKET = [(0.0, 0.0), (0.2, 0.0), (0.26, 0.28), (0.24, 0.28), (0.0, 0.22)]


def transform(V, M):
    """Apply a 4x4 (mathutils) matrix to an (N,3) array."""
    A = np.array(M)
    return V @ A[:3, :3].T + A[:3, 3]


def merge(parts):
    """[(V, F, mat_index), ...] -> V, F, mat_idx."""
    Vs, Fs, Ms = [], [], []
    n = 0
    for V, F, mi in parts:
        Vs.append(V)
        Fs.append(F + n)
        Ms.append(np.full(len(F), mi))
        n += len(V)
    return np.concatenate(Vs), np.concatenate(Fs), np.concatenate(Ms)


def hull_geometry(L, B, depth, sheer0, rise_aft, rise_fwd, ns=22, nk=6, fine=0.4):
    """Round-bilged planked hull (bow +x, port +y, waterline z=0): V, Q, uv, sheer_d."""
    ss = np.linspace(0, 1, ns)
    x = (ss - 0.5) * L
    b = 0.5 * B * np.sin(np.pi * np.clip(ss, 0, 1) ** 0.97) ** fine
    keel = -depth * np.sin(np.pi * ss) ** 0.25 + 0.2 * (1 - np.sin(np.pi * ss) ** 0.25)
    sheer = sheer0 + rise_aft * (1 - ss) ** 3 + rise_fwd * ss ** 3
    V, SD = [], []
    for i in range(ns):
        for j in range(-nk + 1, nk):
            k = abs(j) / (nk - 1)
            y = math.copysign(b[i] * math.sin(0.5 * math.pi * k) ** 0.45, j)
            z = keel[i] + (sheer[i] - keel[i]) * k ** 1.5
            V.append([x[i], y, z])
            SD.append(sheer[i] - z)
    V = np.array(V)
    nj = 2 * nk - 1
    Q = np.array([[i * nj + j, i * nj + j + 1, (i + 1) * nj + j + 1, (i + 1) * nj + j]
                  for i in range(ns - 1) for j in range(nj - 1)])
    girth = np.zeros(len(V))
    for i in range(ns):
        row = V[i * nj:(i + 1) * nj]
        g = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(row, axis=0), axis=1))])
        girth[i * nj:(i + 1) * nj] = np.abs(g - g[nk - 1])
    uv = np.stack([V[Q.ravel(), 0], girth[Q.ravel()]], 1)
    return V, Q, uv, np.array(SD)[Q].mean(1), (x, b, keel, sheer)


# ================================================================= rowing
SKIFF_L, SKIFF_B = 7.4, 2.1
SKIFF_FLOOR = -0.2                 # floorboards (m above the waterline)
PIVOT_Z = 0.5                      # thole pins on the gunwale
OAR_IN, OAR_OUT = 0.75, 2.7
THWARTS = [1.35, -0.05]            # rowers' hips (x); each pulls an oar pivoted 0.45 m aft of him
ROW_Y = 0.5
A_CATCH, A_FINISH = math.radians(38.0), math.radians(-22.0)
E_DRIVE, E_REC = math.radians(-15.0), math.radians(-4.0)
STROKE_T = 2.5                     # s per stroke (24 a minute)
SKIFF_V = 1.6                      # mean speed, m/s


def stroke(ph):
    """Oar sweep a (rad, + = blade towards the bow) and elevation e (rad, - = blade down)."""
    ph %= 1.0
    if ph < 0.42:
        u = ph / 0.42
        a = A_CATCH + (A_FINISH - A_CATCH) * (0.5 - 0.5 * math.cos(math.pi * u))
    else:
        u = (ph - 0.42) / 0.58
        a = A_FINISH + (A_CATCH - A_FINISH) * (0.5 - 0.5 * math.cos(math.pi * u))
    k = smoothstep(0.95, 1.0, ph) if ph > 0.9 else 1.0 - smoothstep(0.38, 0.46, ph)
    return a, E_REC + (E_DRIVE - E_REC) * k


def oar_dir(a, e, side):
    return np.array([math.sin(a) * math.cos(e), side * math.cos(a) * math.cos(e), math.sin(e)])


def pivot(px, side):
    return np.array([px, side * (SKIFF_B / 2 - 0.06), PIVOT_Z])


def rower_frame(hx, side):
    """Boat -> rower-local: the rower sits at (hx, side*ROW_Y) facing aft (-x);
    local +y = his front, +x = his right (= boat +y), z from the floorboards."""
    def to_local(p):
        return np.array([p[1] - side * ROW_Y, -(p[0] - hx), p[2] - SKIFF_FLOOR])
    return to_local


def rower_targets(ph, side):
    """Hands on the loom and the lean that keeps them in reach, in the rower's frame."""
    hx = THWARTS[0]
    px = hx - 0.45
    a, e = stroke(ph)
    d = oar_dir(a, e, side)
    handle = pivot(px, side) - OAR_IN * d
    grip2 = handle + 0.22 * d
    loc = rower_frame(hx, side)
    h1, h2 = loc(handle), loc(grip2)
    # inboard hand (on the handle end) is his left on the port oar, his right on starboard
    hand_l, hand_r = (h1, h2) if side > 0 else (h2, h1)
    # lean: forward to the catch, back at the finish, following the handle's reach
    ya, _ = stroke(0.0)
    yf, _ = stroke(0.42)
    y_c = loc(pivot(px, side) - OAR_IN * oar_dir(ya, E_DRIVE, side))[1]
    y_f = loc(pivot(px, side) - OAR_IN * oar_dir(yf, E_DRIVE, side))[1]
    w = (h1[1] - y_f) / max(y_c - y_f, 1e-6)
    lean = -0.28 + 0.85 * min(max(w, 0.0), 1.0)
    return hand_l, hand_r, lean


class Skiff:
    pass


def build_skiffs(S, F, n=3):
    """Open harbour boats: four oarsmen on two thwarts, a helmsman aft."""
    bands = [(0.20, 0.30, 0.42), (0.46, 0.12, 0.07), (0.62, 0.52, 0.30)]
    V, Q, uv, sd, (x, b, keel, sheer) = hull_geometry(SKIFF_L, SKIFF_B, 0.55, 0.42, 0.35, 0.3, fine=0.45)
    hull_meshes = []
    for k in range(min(n, len(bands))):
        m_hull = F.mat_planking(f'SkiffHull{k}', (0.38, 0.27, 0.16), bands[k], (0.03, 0.025, 0.02), strake=0.2, butt=3.1)
        hull_meshes.append(SC.mesh_from_arrays(f'SkiffHull{k}', V, Q, uv=uv, face_attrs={'sheer_d': ('FLOAT', sd)},
                                               mats=[m_hull], smooth=True))
    tb = G.HexBatch('skiff')
    ns = len(x)
    for i in range(1, ns - 2):                                       # gunwale
        for sg in (-1, 1):
            tb.add(G.beam([x[i], sg * (b[i] + 0.02), sheer[i]], [x[i + 1], sg * (b[i + 1] + 0.02), sheer[i + 1]],
                          0.07, 0.08), mat=0)
    for hx in THWARTS + [-2.2]:                                      # thwarts + stern seat
        i = int(np.argmin(np.abs(x - hx)))
        tb.add(G.beam([hx, -b[i] * 0.95, 0.2], [hx, b[i] * 0.95, 0.2], 0.24, 0.05), mat=1)
    tb.add(G.box(0.0, 0.0, SKIFF_FLOOR - 0.04, SKIFF_L * 0.7, SKIFF_B * 0.55, 0.04), mat=1)   # floorboards
    for hx in THWARTS:                                               # thole pins
        for sg in (-1, 1):
            p = pivot(hx - 0.45, sg)
            tb.add(G.beam(p - [0, 0, 0.12], p + [0, 0, 0.12], 0.04), mat=0)
    L2 = SKIFF_L / 2
    tb.add(G.beam([-L2 + 0.3, 0, sheer[0] - 0.5], [-L2 - 0.15, 0, sheer[0] + 0.45], 0.14), mat=0)  # stern post
    tb.add(G.beam([L2 - 0.3, 0, -0.3], [L2 + 0.12, 0, sheer[-1] + 0.3], 0.12), mat=0)            # stem
    top = np.array([-L2 + 1.0, 0.45, sheer[2] + 0.5])                # steering oar
    piv = np.array([-L2 + 0.35, 0.95, sheer[1] - 0.05])
    low = piv + (piv - top) / np.linalg.norm(piv - top) * 1.6
    tb.add(G.beam(top, low, 0.07), mat=0)
    dv = (low - piv) / np.linalg.norm(low - piv)
    tb.add(G.beam(low - dv * 0.1, low + dv * 0.9, 0.3, 0.04, up=(0, 1, 0)), mat=0)
    tb.finalize()
    fit = SC.hex_mesh('SkiffFit', tb, np.ones(len(tb.t_on), bool), [S.m_wood, S.m_plank])
    ob = G.HexBatch('oar')                                           # pivot at origin, outboard +x
    ob.add(G.beam([-OAR_IN, 0, 0], [OAR_OUT - 0.55, 0, 0], 0.065), mat=0)
    ob.add(G.beam([OAR_OUT - 0.62, 0, 0], [OAR_OUT, 0, 0], 0.025, 0.17), mat=0)
    ob.finalize()
    oar_me = SC.hex_mesh('Oar', ob, np.ones(len(ob.t_on), bool), [S.m_wood])
    S.skiffs = []
    for k in range(n):
        sk = Skiff()
        sk.root = SC.link(bpy.data.objects.new(f'Skiff{k}', None))
        sk.hull = SC.link(bpy.data.objects.new(f'SkiffHull{k}', hull_meshes[k % len(hull_meshes)]))
        sk.fit = SC.link(bpy.data.objects.new(f'SkiffFit{k}', fit))
        for o in (sk.hull, sk.fit):
            o.parent = sk.root
            o.pass_index = SC.PASS['ship']
        sk.oars = []
        for hx in THWARTS:
            for sg in (1, -1):
                o = SC.link(bpy.data.objects.new(f'Oar{k}', oar_me))
                o.pass_index = SC.PASS['ship']
                sk.oars.append((o, hx - 0.45, sg))
        sk.lamp = None
        S.skiffs.append(sk)
    hide_skiffs(S)


def add_skiff_lamp(S, sk, name):
    """A small oil lamp on a post in the stern (night shots)."""
    lamp_me = SC.prism(f'{name}Lamp', 0.09, 0.0, 0.2, 6, 0.07, (0, 0), [S.m_lamp_glow])
    o = SC.link(bpy.data.objects.new(f'{name}Lamp', lamp_me))
    o.parent = sk.root
    o.location = (-SKIFF_L / 2 + 0.7, 0.0, 1.1)
    o.pass_index = SC.PASS['torch']
    o.visible_shadow = False
    ld = bpy.data.lights.new(f'{name}LampLight', 'POINT')
    ld.color = (1.0, 0.56, 0.24)
    ld.shadow_soft_size = 0.1
    lo = SC.link(bpy.data.objects.new(f'{name}LampLight', ld))
    lo.parent = sk.root
    lo.location = (-SKIFF_L / 2 + 0.7, 0.0, 1.35)
    post = G.HexBatch('lamppost')
    post.add(G.beam([-SKIFF_L / 2 + 0.7, 0, 0.1], [-SKIFF_L / 2 + 0.7, 0, 1.1], 0.05), mat=0)
    post.finalize()
    po = SC.link(bpy.data.objects.new(f'{name}LampPost', SC.hex_mesh(f'{name}LampPost', post, np.ones(1, bool), [S.m_wood])))
    po.parent = sk.root
    po.pass_index = SC.PASS['ship']
    sk.lamp = (o, lo, po)


def hide_skiffs(S):
    for sk in S.skiffs:
        for o in [sk.hull, sk.fit] + [o for o, _, _ in sk.oars]:
            o.hide_render = True
        if sk.lamp:
            for o in sk.lamp:
                o.hide_render = True


def skiff_distance(t, v=SKIFF_V):
    """Distance rowed after t seconds: mean speed plus the surge of each drive."""
    ph = t / STROKE_T
    return v * (t + 0.18 * STROKE_T / (2 * math.pi) * math.sin(2 * math.pi * (ph - 0.2)))


def pose_skiff(S, F, k, pos, heading, t, first_person, rowing=True, lamp=0.0, seed=0):
    """Skiff k at pos (x, y) heading (CCW from +x) at time t.  Returns next free person."""
    sk = S.skiffs[k]
    ph = (t / STROKE_T + 0.13 * seed) % 1.0 if rowing else 0.47
    heave = 0.03 * math.sin(1.7 * t + seed)
    pitch = 0.012 * math.sin(2 * math.pi * ph) + 0.01 * math.sin(1.3 * t + seed)
    roll = 0.02 * math.sin(0.9 * t + 2 * seed)
    M = (Matrix.Translation((pos[0], pos[1], heave)) @ Matrix.Rotation(heading, 4, 'Z')
         @ Matrix.Rotation(-pitch, 4, 'Y') @ Matrix.Rotation(roll, 4, 'X'))
    sk.root.matrix_world = M
    sk.hull.hide_render = sk.fit.hide_render = False
    a, e = stroke(ph)
    for o, px, sg in sk.oars:
        o.hide_render = False
        yaw = (math.pi / 2 - a) if sg > 0 else (a - math.pi / 2)
        o.matrix_world = M @ Matrix.Translation(tuple(pivot(px, sg))) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(-e, 4, 'Y')
    kk = first_person
    for hx in THWARTS:
        for sg in (1, -1):
            p = M @ Vector((hx, sg * ROW_Y, SKIFF_FLOOR))
            F.place_person(S, kk, (p.x, p.y, p.z), heading + math.pi, 'row_p' if sg > 0 else 'row_s', 2 * math.pi * ph)
            S.people[kk].rotation_euler = (roll, pitch, heading + math.pi - math.pi / 2)
            kk += 1
    p = M @ Vector((-SKIFF_L / 2 + 1.0, 0.25, SKIFF_FLOOR + 0.25))    # helmsman, standing aft
    F.place_person(S, kk, (p.x, p.y, p.z), heading, 'stand')
    kk += 1
    if sk.lamp:
        on = lamp > 0.01
        for o in sk.lamp:
            o.hide_render = not on
        sk.lamp[1].data.energy = 35.0 * lamp * (0.9 + 0.1 * math.sin(t * 11.0 + seed))
    return kk


# ================================================================= sailing boats, ships at anchor
def build_sailboats(S, F, n=6):
    """Small coasting boats with a brailed square sail (distant life)."""
    V, Q, uv, sd, (x, b, keel, sheer) = hull_geometry(9.0, 2.8, 0.9, 0.7, 0.9, 0.5, fine=0.4)
    m_hull = F.mat_planking('BoatHull', (0.34, 0.24, 0.14), (0.44, 0.14, 0.08), (0.03, 0.025, 0.02), strake=0.24)
    hull = SC.mesh_from_arrays('BoatHull', V, Q, uv=uv, face_attrs={'sheer_d': ('FLOAT', sd)}, mats=[m_hull], smooth=True)
    rb = G.HexBatch('boat_rig')
    rb.add(G.beam([0.6, 0, -0.3], [0.6, 0, 8.2], 0.18), mat=0)                  # mast
    rb.add(G.beam([0.6, 0, 8.2], [4.6, 0, sheer[-1] + 0.2], 0.03), mat=1)        # forestay
    rb.add(G.beam([0.6, 0, 8.2], [-4.2, 0, sheer[0] + 0.2], 0.03), mat=1)        # backstay
    rb.add(G.beam([-4.5, 0, sheer[0] - 0.6], [-4.8, 0, sheer[0] + 0.9], 0.2), mat=0)
    rb.add(G.box(-2.6, 0, 0.35, 1.6, 1.8, 0.5), mat=2)                          # cargo under a cloth
    rb.finalize()
    rig = SC.hex_mesh('BoatRig', rb, np.ones(len(rb.t_on), bool), [S.m_wood, S.m_rope, S.m_cloth])
    # sail: bellied forward (+x), foot raised by the brails
    nu, nv = 10, 7
    Vs, UV = [], []
    for jv in range(nv + 1):
        w = jv / nv
        for iu in range(nu + 1):
            u = -1 + 2 * iu / nu
            belly = 0.55 * (1 - u * u) * math.sin(math.pi * min(0.15 + 0.85 * w, 1.0)) ** 0.8
            Vs.append([0.95 + belly, u * 3.2 * (1 - 0.05 * w), 7.55 - w * 5.2])
            UV.append((u * 3.2, w * 5.2))
    Qs = np.array([[jv * (nu + 1) + iu, jv * (nu + 1) + iu + 1, (jv + 1) * (nu + 1) + iu + 1, (jv + 1) * (nu + 1) + iu]
                   for jv in range(nv) for iu in range(nu)])
    yard = G.beam([0.8, -3.4, 7.7], [0.8, 3.4, 7.7], 0.12)             # yard: braced with the sail
    Vy = yard.reshape(-1, 3)
    Qy = np.array([[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]) + len(Vs)
    UVall = np.concatenate([np.array(UV)[Qs.ravel()], np.zeros((len(Qy) * 4, 2))])
    sail = SC.mesh_from_arrays('BoatSail', np.concatenate([np.array(Vs), Vy]), np.concatenate([Qs, Qy]), uv=UVall,
                               mats=[S.m_sailcloth, S.m_wood], mat_idx=np.concatenate([np.zeros(len(Qs)), np.ones(len(Qy))]),
                               smooth=True)
    S.boats = []
    for k in range(n):
        root = SC.link(bpy.data.objects.new(f'Boat{k}', None))
        parts = []
        for nm, me in (('Hull', hull), ('Rig', rig), ('Sail', sail)):
            o = SC.link(bpy.data.objects.new(f'Boat{nm}{k}', me))
            o.parent = root
            o.pass_index = SC.PASS['ship']
            o.hide_render = True
            parts.append(o)
        S.boats.append((root, parts))


def pose_boat(S, k, pos, heading, t, seed=0.0):
    root, parts = S.boats[k]
    heave = 0.08 * math.sin(1.1 * t + seed)
    roll = 0.035 * math.sin(0.7 * t + seed) + 0.04        # heeled a little by the wind
    pitch = 0.015 * math.sin(0.9 * t + 2 * seed)
    root.matrix_world = (Matrix.Translation((pos[0], pos[1], heave)) @ Matrix.Rotation(heading, 4, 'Z')
                         @ Matrix.Rotation(-pitch, 4, 'Y') @ Matrix.Rotation(roll, 4, 'X'))
    for o in parts:
        o.hide_render = False
    # the yard is braced square to the wind: rotate the sail+yard about the mast
    rel = WIND_HEADING - heading
    brace = max(-0.6, min(0.6, math.atan2(math.sin(rel), math.cos(rel)) * 0.5))
    parts[2].matrix_world = root.matrix_world @ Matrix.Translation((0.6, 0, 0)) @ Matrix.Rotation(brace, 4, 'Z') @ Matrix.Translation((-0.6, 0, 0))


def hide_boats(S):
    for root, parts in S.boats:
        for o in parts:
            o.hide_render = True


def build_anchored(S, n=3):
    """Merchantmen riding at anchor in the Great Harbour, sails furled."""
    S.anchored = []
    rng = np.random.default_rng(44)
    for k in range(n):
        hull, rig = SC.ship_mesh([S.m_hull, S.m_sail], length=float(rng.uniform(19, 25)), sail=False, mast=True)
        h = SC.link(bpy.data.objects.new(f'Anchored{k}', hull))
        r = SC.link(bpy.data.objects.new(f'AnchoredRig{k}', rig))
        r.parent = h
        h.pass_index = r.pass_index = SC.PASS['ship']
        lamp_me = SC.prism(f'AnchLamp{k}', 0.14, 0.0, 0.3, 6, 0.1, (0, 0), [S.m_lamp_glow])
        lo = SC.link(bpy.data.objects.new(f'AnchLamp{k}', lamp_me))
        lo.parent = h
        lo.location = (-8.0, 0.0, 3.6)
        lo.pass_index = SC.PASS['torch']
        ld = bpy.data.lights.new(f'AnchLampLight{k}', 'POINT')
        ld.color = (1.0, 0.56, 0.24)
        ld.shadow_soft_size = 0.1
        ll = SC.link(bpy.data.objects.new(f'AnchLampLight{k}', ld))
        ll.parent = h
        ll.location = (-8.0, 0.0, 3.9)
        for o in (h, r, lo, ll):
            o.hide_render = True
        S.anchored.append((h, r, lo, ll))


def pose_anchored(S, spots, t, lamp=0.0):
    for k, (h, r, lo, ll) in enumerate(S.anchored):
        if k >= len(spots):
            for o in (h, r, lo, ll):
                o.hide_render = True
            continue
        x, y, hd = spots[k]
        swing = 0.05 * math.sin(0.11 * t + k)          # swinging to the anchor cable
        h.location = (x, y, 0.25 + 0.1 * math.sin(0.8 * t + k))
        h.rotation_euler = (0.02 * math.sin(0.5 * t + 2 * k), 0.01 * math.sin(0.7 * t + k), hd + swing)
        h.hide_render = r.hide_render = False
        lo.hide_render = ll.hide_render = lamp <= 0.01
        ll.data.energy = 60.0 * lamp * (0.92 + 0.08 * math.sin(9.0 * t + k))


# ================================================================= smoke
def mat_smoke():
    """Billboard puff: Object colour = (density, glow, seed), Object alpha = age.
    Soft round falloff times evolving noise; diffuse + a little translucency, so
    the sun, the beacon and the torches light it like real smoke."""
    m, nb, out = SC.new_material('Smoke')
    tc = nb.new('ShaderNodeTexCoord')
    u, v, _ = nb.sep(tc.outputs['UV'])
    du, dv = nb.math('SUBTRACT', u, 0.5), nb.math('SUBTRACT', v, 0.5)
    r = nb.math('MULTIPLY', nb.math('SQRT', nb.math('ADD', nb.math('MULTIPLY', du, du), nb.math('MULTIPLY', dv, dv))), 2.0)
    fall = nb.smooth(1.0, 0.05, r)
    oi = nb.new('ShaderNodeObjectInfo')
    dens, glow, seed = nb.sep(oi.outputs['Color'])
    age = oi.outputs['Alpha']
    w = nb.math('ADD', nb.math('MULTIPLY', seed, 37.0), nb.math('MULTIPLY', age, 1.3))
    n1 = nb.noise(nb.comb(u, v, 0.0), 1.7, 4.0, 0.6, w=w, dims='4D').outputs['Fac']
    body = nb.smooth(0.22, 0.68, nb.math('ADD', n1, nb.math('MULTIPLY', fall, 0.3)))
    alpha = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.math('POWER', fall, 0.7), body), dens, clamp=True)
    col = nb.mix(nb.math('MULTIPLY', n1, 0.6), (0.62, 0.60, 0.57, 1), (0.80, 0.78, 0.74, 1))
    dif = nb.new('ShaderNodeBsdfDiffuse')
    nb.feed(dif.inputs['Color'], col)
    tr = nb.new('ShaderNodeBsdfTranslucent')
    nb.feed(tr.inputs['Color'], col)
    sh = nb.new('ShaderNodeMixShader')
    sh.inputs[0].default_value = 0.35
    nb.feed(sh.inputs[1], dif.outputs[0])
    nb.feed(sh.inputs[2], tr.outputs[0])
    em = nb.new('ShaderNodeEmission')                  # fire-lit underside of the beacon smoke
    em.inputs['Color'].default_value = (1.0, 0.45, 0.14, 1)
    nb.feed(em.inputs['Strength'], nb.math('MULTIPLY', glow, 6.0))
    add = nb.new('ShaderNodeAddShader')
    nb.feed(add.inputs[0], sh.outputs[0])
    nb.feed(add.inputs[1], em.outputs[0])
    tp = nb.new('ShaderNodeBsdfTransparent')
    mix = nb.new('ShaderNodeMixShader')
    nb.feed(mix.inputs[0], alpha)
    nb.feed(mix.inputs[1], tp.outputs[0])
    nb.feed(mix.inputs[2], add.outputs[0])
    nb.feed(out.inputs['Surface'], mix.outputs[0])
    return m


def build_smoke(S, n=150):
    m = mat_smoke()
    V = np.array([[-0.5, -0.5, 0], [0.5, -0.5, 0], [0.5, 0.5, 0], [-0.5, 0.5, 0]])
    Q = np.array([[0, 1, 2, 3]])
    me = SC.mesh_from_arrays('Puff', V, Q, uv=np.array([[0, 0], [1, 0], [1, 1], [0, 1]]), mats=[m])
    S.smoke = []
    for i in range(n):
        o = SC.link(bpy.data.objects.new(f'Puff{i}', me))
        o.pass_index = SC.PASS['props']
        o.visible_shadow = False
        o.visible_diffuse = False
        o.hide_render = True
        S.smoke.append(o)


class Plume:
    """A column of puffs.  clock: seconds of smoke time (runs fast in the time-lapse)."""

    def __init__(self, pos, n=8, life=9.0, rise=1.1, drift=1.6, size0=0.8, grow=0.45, dens=0.55,
                 glow=0.0, seed=0.0, wind=WIND):
        self.pos, self.n, self.life, self.rise, self.drift = np.array(pos, float), n, life, rise, drift
        self.size0, self.grow, self.dens, self.glow, self.seed = size0, grow, dens, glow, seed
        self.wind = np.array([wind[0], wind[1], 0.0])


def pose_smoke(S, plumes, clock, cam_loc):
    cam = np.array(cam_loc, float)
    k = 0
    for pl in plumes:
        for i in range(pl.n):
            if k >= len(S.smoke):
                break
            f = (clock / pl.life + (i + 0.37 * pl.seed) / pl.n) % 1.0      # age fraction
            a = f * pl.life
            h = pl.rise * a * (1.0 - 0.25 * f)                               # slows as it cools
            sway = 0.25 * math.sin(0.7 * a + i * 2.1 + pl.seed) * (0.3 + a * 0.2)
            p = pl.pos + np.array([0, 0, h]) + pl.wind * (pl.drift * a ** 1.15) \
                + np.array([-pl.wind[1], pl.wind[0], 0]) * sway
            size = pl.size0 + pl.grow * a
            dens = pl.dens * smoothstep(0.0, 0.08, f) * (1.0 - f) ** 1.6
            o = S.smoke[k]
            k += 1
            if dens < 0.01:
                o.hide_render = True
                continue
            zc = cam - p
            zc /= max(np.linalg.norm(zc), 1e-6)
            xc = np.cross([0.0, 0.0, 1.0], zc)
            xc /= max(np.linalg.norm(xc), 1e-6)
            yc = np.cross(zc, xc)
            spin = 0.6 * (i % 3 - 1) + 0.15 * a
            cs, sn = math.cos(spin), math.sin(spin)
            xr, yr = xc * cs + yc * sn, -xc * sn + yc * cs
            R = np.stack([xr * size, yr * size, zc], 1)
            M = Matrix(((R[0, 0], R[0, 1], R[0, 2], p[0]), (R[1, 0], R[1, 1], R[1, 2], p[1]),
                        (R[2, 0], R[2, 1], R[2, 2], p[2]), (0, 0, 0, 1)))
            o.matrix_world = M
            glow = pl.glow * math.exp(-h / 6.0)
            o.color = (dens, glow, (pl.seed * 0.137 + i * 0.0731) % 1.0, f)
            o.hide_render = False
    for o in S.smoke[k:]:
        o.hide_render = True


# ================================================================= pennants
def mat_pennant(name, col):
    m, nb, out = SC.new_material(name)
    b = SC.principled(nb, tuple(col) + (1,), 0.9, 0.0, 0.2)
    tr = nb.new('ShaderNodeBsdfTranslucent')
    tr.inputs['Color'].default_value = tuple(col) + (1,)
    mix = nb.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = 0.3
    nb.feed(mix.inputs[1], b.outputs[0])
    nb.feed(mix.inputs[2], tr.outputs[0])
    nb.feed(out.inputs['Surface'], mix.outputs[0])
    return m


def build_pennants(S, n=10):
    S.m_pennants = [mat_pennant('PennantRed', (0.62, 0.09, 0.05)), mat_pennant('PennantWhite', (0.85, 0.82, 0.74)),
                    mat_pennant('PennantBlue', (0.12, 0.2, 0.45))]
    S.pennants = []
    for i in range(n):
        o = SC.link(bpy.data.objects.new(f'Pennant{i}', bpy.data.meshes.new(f'Pennant{i}')))
        o.pass_index = SC.PASS['props']
        o.hide_render = True
        S.pennants.append(o)


def pose_pennants(S, mounts, t):
    """mounts: [(point (x,y,z), length, width, colour index), ...]; streams downwind."""
    d = np.array([WIND[0], WIND[1], 0.0])
    side = np.array([-WIND[1], WIND[0], 0.0])
    for i, o in enumerate(S.pennants):
        if i >= len(mounts):
            o.hide_render = True
            continue
        base, L, W, ci = mounts[i]
        base = np.array(base, float)
        nu = 12
        V = []
        for iu in range(nu + 1):
            f = iu / nu
            ph = 2 * math.pi * (1.4 * f - 1.9 * t) + i * 1.3
            lat = 0.16 * L * f * math.sin(ph)
            vert = -0.08 * L * f * f + 0.04 * L * f * math.sin(ph * 0.7 + 1.0)
            c = base + d * L * f * (1 - 0.05 * math.sin(ph) ** 2) + side * lat + np.array([0, 0, vert])
            w = W * (1.0 - 0.75 * f)
            V.append(c + np.array([0, 0, 0.5 * w]))
            V.append(c - np.array([0, 0, 0.5 * w]))
        Q = np.array([[2 * iu, 2 * iu + 2, 2 * iu + 3, 2 * iu + 1] for iu in range(nu)])
        old = o.data
        o.data = SC.mesh_from_arrays(f'Pennant{i}', np.array(V), Q, mats=[S.m_pennants[ci % 3]], smooth=True)
        if old is not None and old.users == 0:
            bpy.data.meshes.remove(old)
        o.hide_render = False


# ================================================================= quay clutter
def mat_terracotta():
    m, nb, out = SC.new_material('Terracotta')
    oi = nb.new('ShaderNodeObjectInfo')
    geo = nb.new('ShaderNodeNewGeometry')
    n = nb.noise(geo.outputs['Position'], 3.0, 3.0, 0.5).outputs['Fac']
    col = nb.mix(nb.math('ADD', nb.math('MULTIPLY', n, 0.5), 0.1), (0.52, 0.24, 0.12, 1), (0.66, 0.40, 0.24, 1))
    b = SC.principled(nb, col, 0.75, 0.0, 0.35)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_clutter(S, spots):
    """Amphorae, water jars, baskets, rope coils and levers where the work is.
    spots: dict name -> (x, y, z, heading)."""
    rng = np.random.default_rng(9)
    m_pot = mat_terracotta()
    m_wicker = SC.mat_simple('Wicker', (0.50, 0.37, 0.19), 0.9)
    parts = []
    Va, Fa = lathe(AMPHORA, 10)
    Vp, Fp = lathe(PITHOS, 12)
    Vb, Fb = lathe(BASKET, 10)
    if 'amphorae' in spots:                        # amphorae standing in rows, leaning on each other
        x0, y0, z0, hd = spots['amphorae']
        for r in range(2):
            for c in range(7):
                tilt = math.radians(rng.uniform(4, 10))
                M = (Matrix.Translation((x0, y0, z0)) @ Matrix.Rotation(hd, 4, 'Z')
                     @ Matrix.Translation(((c - 3) * 0.33 + 0.16 * r, r * 0.34, 0.0))
                     @ Matrix.Rotation(rng.uniform(0, 6.3), 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X'))
                parts.append((transform(Va, M), Fa, 0))
    if 'jars' in spots:                            # big water jars in the shade
        x0, y0, z0, hd = spots['jars']
        for j in range(3):
            M = Matrix.Translation((x0 + j * 0.9 * math.cos(hd), y0 + j * 0.9 * math.sin(hd), z0))
            parts.append((transform(Vp, M), Fp, 0))
    if 'baskets' in spots:
        x0, y0, z0, hd = spots['baskets']
        for j in range(7):
            M = (Matrix.Translation((x0 + rng.uniform(-1.2, 1.2), y0 + rng.uniform(-0.8, 0.8), z0))
                 @ Matrix.Rotation(rng.uniform(0, 6.3), 4, 'Z'))
            parts.append((transform(Vb, M), Fb, 1))
    V, F, mi = merge(parts) if parts else (np.zeros((0, 3)), np.zeros((0, 4), int), np.zeros(0, int))
    me = SC.mesh_from_arrays('Clutter', V, F, mats=[m_pot, m_wicker], mat_idx=mi, smooth=True)
    o = SC.link(bpy.data.objects.new('Clutter', me))
    o.pass_index = SC.PASS['props']
    # timber clutter: rope coils, levers, planks, an awning for the scribe
    tb = G.HexBatch('clutter_t')
    if 'coils' in spots:
        x0, y0, z0, hd = spots['coils']
        for j in range(3):
            cx, cy = x0 + j * 0.9, y0 + (j % 2) * 0.5
            for q in range(10):
                a0, a1 = 2 * math.pi * q / 10, 2 * math.pi * (q + 1) / 10
                for ring in range(3):
                    rr = 0.32 - 0.06 * ring
                    tb.add(G.beam([cx + rr * math.cos(a0), cy + rr * math.sin(a0), z0 + 0.05 + 0.07 * ring],
                                  [cx + rr * math.cos(a1), cy + rr * math.sin(a1), z0 + 0.05 + 0.07 * ring], 0.07), mat=2)
    if 'levers' in spots:
        x0, y0, z0, hd = spots['levers']
        for j in range(4):
            a = hd + rng.uniform(-0.15, 0.15)
            dx, dy = math.cos(a), math.sin(a)
            ox, oy = -dy * j * 0.35, dx * j * 0.35
            tb.add(G.beam([x0 + ox, y0 + oy, z0 + 0.07], [x0 + ox + 3.2 * dx, y0 + oy + 3.2 * dy, z0 + 0.07], 0.13), mat=0)
        for j in range(3):
            tb.add(G.box(x0 + 1.0, y0 - 1.2 - j * 0.02, z0 + j * 0.06, 3.6, 0.35, 0.06, hd), mat=1)
    if 'awning' in spots:
        x0, y0, z0, hd = spots['awning']
        c, s = math.cos(hd), math.sin(hd)
        corners = [(-1.4, -1.1), (1.4, -1.1), (1.4, 1.1), (-1.4, 1.1)]
        for (ax, ay) in corners:
            px, py = x0 + ax * c - ay * s, y0 + ax * s + ay * c
            tb.add(G.beam([px, py, z0], [px, py, z0 + 2.3 + 0.2 * (ay < 0)], 0.09), mat=0)
        tb.add(G.box(x0, y0, z0 + 0.0, 1.2, 0.7, 0.72, hd), mat=0)                 # the scribe's table
        tb.add(G.box(x0 + 0.3 * c, y0 + 0.3 * s, z0 + 0.72, 0.3, 0.22, 0.04, hd), mat=1)   # tablets
    tb.finalize()
    to = SC.link(bpy.data.objects.new('ClutterT', SC.hex_mesh('ClutterT', tb, np.ones(len(tb.t_on), bool),
                                                               [S.m_wood, S.m_plank, S.m_rope])))
    to.pass_index = SC.PASS['props']
    S.clutter = [o, to]
    if 'awning' in spots:                          # the sunshade cloth, sagging a little
        x0, y0, z0, hd = spots['awning']
        c, s = math.cos(hd), math.sin(hd)
        Vc = []
        for j in range(5):
            for i in range(7):
                ax, ay = -1.5 + 3.0 * i / 6, -1.2 + 2.4 * j / 4
                sag = 0.12 * math.sin(math.pi * i / 6) * math.sin(math.pi * j / 4)
                Vc.append([x0 + ax * c - ay * s, y0 + ax * s + ay * c, z0 + 2.4 + 0.1 * (ay < 0) * 0 - 0.1 * ay / 1.2 - sag])
        Qc = np.array([[j * 7 + i, j * 7 + i + 1, (j + 1) * 7 + i + 1, (j + 1) * 7 + i] for j in range(4) for i in range(6)])
        co = SC.link(bpy.data.objects.new('Awning', SC.mesh_from_arrays('Awning', np.array(Vc), Qc, mats=[S.m_cloth2], smooth=True)))
        co.pass_index = SC.PASS['props']
        S.clutter.append(co)
    for o in S.clutter:
        o.hide_render = True


def show_clutter(S, on):
    for o in getattr(S, 'clutter', []):
        o.hide_render = not on


# ================================================================= build
def build(S, F):
    S.m_lamp_glow = SC.mat_simple('LampGlow', (1.0, 0.7, 0.4), 0.5, emit=(1.0, 0.6, 0.28), emit_strength=25.0)
    build_skiffs(S, F, n=3)
    for k, sk in enumerate(S.skiffs):
        add_skiff_lamp(S, sk, f'Skiff{k}')
    build_sailboats(S, F, n=6)
    build_anchored(S, n=3)
    build_smoke(S)
    build_pennants(S)


def hide_all(S):
    hide_skiffs(S)
    hide_boats(S)
    pose_anchored(S, [], 0.0)
    for o in S.smoke + S.pennants:
        o.hide_render = True
    show_clutter(S, False)
    show_site_dressing(S, False)


# ================================================================= the working site
SHEDS = [(-48.0, -28.0, 0.3), (44.0, -22.0, -0.2), (-30.0, 40.0, 0.1), (30.0, 42.0, -0.4)]
RUBBLE = [(-36.0, -34.0, 3.6), (-35.0, 36.0, 3.0), (24.0, 38.0, 2.8), (38.0, -24.0, 3.2)]
MORTAR = [(-4.0, -42.0), (-40.0, -18.0)]


def build_site_dressing(S, ground_z):
    """Masons' sheds (posts and a reed roof), heaps of stone chips, lime-mortar pits."""
    tb = G.HexBatch('site')
    rng = np.random.default_rng(71)
    for (x, y, rot) in SHEDS:
        z = ground_z(x, y)
        c, s = math.cos(rot), math.sin(rot)
        for ax in (-2.5, 0.0, 2.5):
            for ay in (-1.75, 1.75):
                px, py = x + ax * c - ay * s, y + ax * s + ay * c
                tb.add(G.beam([px, py, z - 0.2], [px, py, z + 2.5 + 0.25 * (ay > 0)], 0.16), mat=0)
        for ay in (-1.75, 1.75):
            p0 = [x - 2.7 * c - ay * s, y - 2.7 * s + ay * c, z + 2.5 + 0.25 * (ay > 0)]
            p1 = [x + 2.7 * c - ay * s, y + 2.7 * s + ay * c, z + 2.5 + 0.25 * (ay > 0)]
            tb.add(G.beam(p0, p1, 0.14), mat=0)
        roof = [(-2.9, -2.0), (2.9, -2.0), (2.9, 2.0), (-2.9, 2.0)]
        q = [(x + ax * c - ay * s, y + ax * s + ay * c) for ax, ay in roof]
        tb.add(G.quad_slab(q, z + 2.62, z + 2.74), mat=1)
        for j in range(3):                                         # a block being dressed under it
            tb.add(G.box(x + (j - 1) * 1.6 * c, y + (j - 1) * 1.6 * s, z - 0.1, 1.2, 0.8, 0.75, rot), mat=2,
                   tone=rng.random())
    tb.finalize()
    S.m_reed = SC.mat_simple('Reed', (0.60, 0.49, 0.29), 0.95)
    o = SC.link(bpy.data.objects.new('Sheds', SC.hex_mesh('Sheds', tb, np.ones(len(tb.t_on), bool),
                                                         [S.m_wood, S.m_reed, S.m_stone])))
    o.pass_index = SC.PASS['props']
    parts = []
    for (x, y, r) in RUBBLE:                                      # conical heaps of chips
        z = ground_z(x, y)
        prof = [(0.0, -0.2), (r, -0.2), (r * 0.8, 0.25 * r * 0.35), (r * 0.45, 0.7 * r * 0.35), (0.0, r * 0.35)]
        V, F = lathe(prof, 14)
        V = V + [x, y, z]
        V[:, 2] += 0.08 * np.sin(V[:, 0] * 3.1) * np.cos(V[:, 1] * 2.7)
        parts.append((V, F, 0))
    for (x, y) in MORTAR:                                         # a low ring wall round white lime
        z = ground_z(x, y)
        V, F = lathe([(0.0, 0.05), (1.6, 0.05), (1.9, 0.35), (2.2, 0.35), (2.3, -0.2)], 16)
        parts.append((V + [x, y, z], F, 1))
    V, F, mi = merge(parts)
    m_lime = SC.mat_simple('Lime', (0.74, 0.72, 0.66), 0.8)
    h = SC.link(bpy.data.objects.new('Heaps', SC.mesh_from_arrays('Heaps', V, F, mats=[S.m_stone, m_lime], mat_idx=mi,
                                                                  smooth=True)))
    h.pass_index = SC.PASS['props']
    S.site_dressing = [o, h]


def show_site_dressing(S, on):
    for o in getattr(S, 'site_dressing', []):
        o.hide_render = not on
