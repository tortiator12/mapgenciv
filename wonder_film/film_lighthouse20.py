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
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

import geometry as G
import life
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
def bake(name, J, E, R, mat, subsurf=2, skin=None, extra=None):
    """Skin figure baked into a plain mesh.  With skin=True every face gets a
    'region' attribute (tunic, skin, hair, beard, belt, sandal, basket) that
    the person material turns into colours (per-person variation)."""
    o = SC.skin_figure(name, J, E, R, mat, subsurf)
    SC.link(o)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    bpy.data.objects.remove(o)
    if not skin:
        return me
    V = np.array([v.co[:] for v in me.vertices])
    F = [list(p.vertices) for p in me.polygons]
    C = np.array([V[f].mean(axis=0) for f in F])
    reg = person_regions(C, np.array(J, float))
    if extra is not None:                          # e.g. a basket: appended with its own region
        Vx, Fx, rx = extra
        F += [list(np.asarray(f) + len(V)) for f in Fx]
        V = np.concatenate([V, Vx])
        reg = np.concatenate([reg, np.full(len(Fx), rx)])
    Q = np.array([f if len(f) == 4 else f + [f[-1]] * (4 - len(f)) for f in F])
    bpy.data.meshes.remove(me)
    return SC.mesh_from_arrays(name, V, Q, face_attrs={'region': ('FLOAT', reg)}, mats=[mat], smooth=True)


R_TUNIC, R_SKIN, R_HAIR, R_BEARD, R_BELT, R_SANDAL, R_BASKET, R_POT, R_WOOD = range(9)
BONES = [(0, 1), (1, 2), (0, 18), (2, 3), (2, 4), (4, 5), (5, 6), (2, 7), (7, 8), (8, 9),
         (0, 10), (10, 11), (11, 12), (12, 13), (0, 14), (14, 15), (15, 16), (16, 17), (3, 19)]


def person_regions(C, J):
    """Classify faces by the nearest bone: an exomis (tunic over the left
    shoulder, right shoulder bare), belt, hair or head cloth, beard, sandals."""
    d = np.full((len(C), len(BONES)), 1e9)
    for k, (a, b) in enumerate(BONES):
        A, Bv = J[a], J[b]
        ab = Bv - A
        t = np.clip(((C - A) @ ab) / max(ab @ ab, 1e-9), 0, 1)
        d[:, k] = np.linalg.norm(C - (A + t[:, None] * ab), axis=1)
    nb = np.argmin(d, axis=1)
    reg = np.full(len(C), R_SKIN, float)
    torso = np.isin(nb, [0, 1, 2])
    reg[torso] = R_TUNIC
    reg[torso & (np.abs(C[:, 2] - (J[0][2] + 0.02)) < 0.05)] = R_BELT
    reg[(nb == 4) | ((nb == 5) & (np.linalg.norm(C - J[4], axis=1) < 0.12))] = R_TUNIC   # left shoulder
    thigh = np.isin(nb, [10, 11, 14, 15]) & (C[:, 2] > J[18][2] - 0.02)
    reg[thigh] = R_TUNIC
    head = J[3]
    hd = np.isin(nb, [3, 18])
    rel = C - head
    reg[hd & (rel[:, 2] > 0.015) & (rel[:, 1] < 0.06)] = R_HAIR
    reg[hd & (rel[:, 2] > -0.02) & (rel[:, 1] < -0.06)] = R_HAIR
    reg[hd & (rel[:, 2] < -0.02) & (rel[:, 2] > -0.14) & (rel[:, 1] > 0.02)] = R_BEARD
    reg[np.isin(nb, [13, 17]) | (np.isin(nb, [12, 16]) & (C[:, 2] < J[12][2] + 0.03))] = R_SANDAL
    return reg


def mat_person():
    """Tunic colour from the object, skin tone, hair or head cloth, beard and
    sandals varied per person with Object Info > Random."""
    m, nb, out = SC.new_material('Person')
    oi = nb.new('ShaderNodeObjectInfo')
    rnd = oi.outputs['Random']
    reg = nb.attr('region').outputs['Fac']
    r2 = nb.math('FRACT', nb.math('MULTIPLY', rnd, 7.31))
    r3 = nb.math('FRACT', nb.math('MULTIPLY', rnd, 3.17))
    r4 = nb.math('FRACT', nb.math('MULTIPLY', rnd, 5.73))
    skin = nb.mix(rnd, (0.33, 0.19, 0.115, 1), (0.50, 0.32, 0.20, 1))
    dark_hair = nb.mix(r3, (0.025, 0.018, 0.014, 1), (0.07, 0.045, 0.03, 1))
    cloth = nb.mix(r4, (0.80, 0.77, 0.68, 1), (0.62, 0.50, 0.32, 1))
    hair = nb.mix(nb.math('GREATER_THAN', r2, 0.62), dark_hair, cloth)
    beard = nb.mix(nb.math('GREATER_THAN', r3, 0.45), skin, dark_hair)
    sandal = nb.mix(nb.math('GREATER_THAN', r4, 0.35), skin, (0.19, 0.11, 0.055, 1))
    tunic = oi.outputs['Color']
    col = tunic
    for k, c in ((R_SKIN, skin), (R_HAIR, hair), (R_BEARD, beard), (R_BELT, (0.13, 0.075, 0.04, 1)),
                 (R_SANDAL, sandal), (R_BASKET, (0.52, 0.39, 0.2, 1)), (R_POT, (0.55, 0.25, 0.12, 1)),
                 (R_WOOD, (0.30, 0.20, 0.11, 1))):
        f = nb.math('COMPARE', reg, float(k), 0.5)
        col = nb.mix(f, col, c)
    b = SC.principled(nb, col, rough=0.85, spec=0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def basket_geometry(cz, r0=0.19, r1=0.24, h=0.2, n=10):
    """A wicker basket (open truncated cone) sitting at height cz on the head."""
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    bot = np.stack([r0 * np.cos(ang), r0 * np.sin(ang), np.full(n, cz)], 1)
    top = np.stack([r1 * np.cos(ang), r1 * np.sin(ang), np.full(n, cz + h)], 1)
    fill = np.stack([r1 * 0.9 * np.cos(ang), r1 * 0.9 * np.sin(ang), np.full(n, cz + h * 0.8)], 1)
    V = np.concatenate([bot, top, fill, [[0, 0, cz], [0, 0, cz + h * 0.95]]])
    F = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    F += [[3 * n, (i + 1) % n, i, i] for i in range(n)]
    F += [[3 * n + 1, 2 * n + i, 2 * n + (i + 1) % n, 2 * n + (i + 1) % n] for i in range(n)]
    return V, F


HUMAN_E = [(0, 1), (1, 2), (2, 3), (2, 4), (4, 5), (5, 6), (2, 7), (7, 8), (8, 9), (0, 10), (10, 11),
           (11, 12), (12, 13), (0, 14), (14, 15), (15, 16), (16, 17), (0, 18), (3, 19)]
HUMAN_R = [0.16, 0.17, 0.065, 0.1, 0.07, 0.05, 0.045, 0.07, 0.05, 0.045, 0.085, 0.065, 0.05, 0.04,
           0.085, 0.065, 0.05, 0.04, 0.2, 0.095]


def human_joints(mode, ph=0.0):
    """Joints of a man in a short tunic, facing +y.  mode: walk / carry / stand / haul."""
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
    elif mode == 'carry':     # walking with a basket on the head, right hand steadying it
        bob = 0.02 * math.cos(2 * ph)
        for s in (-1, 1):
            psi = ph + (0 if s < 0 else math.pi)
            fy = 0.26 * math.sin(psi)
            lift = 0.09 * max(0.0, math.cos(psi))
            legs.append(((s * 0.1, 0.5 * fy + 0.06 + 0.06 * max(0.0, math.cos(psi)), 0.5 + 0.5 * lift),
                         (s * 0.1, fy, 0.08 + lift)))
            if s > 0:
                arms.append(((0.27, 0.02, 1.62), (0.2, 0.0, 1.8)))
            else:
                hy = -0.18 * math.sin(psi)
                arms.append(((-0.23, 0.5 * hy, 1.17), (-0.25, hy, 0.95)))
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
    J.append(tilt((0, 0.0, 1.71 + bob)))           # crown of the head
    return J


def _ik(root, target, l1, l2, pole):
    """Two-bone IK: middle joint and (reach-clamped) end for root -> target."""
    a = np.asarray(root, float)
    d = np.asarray(target, float) - a
    L = float(np.linalg.norm(d))
    u = d / max(L, 1e-9)
    L = min(L, (l1 + l2) * 0.999)
    x = (l1 * l1 - l2 * l2 + L * L) / (2 * L)
    r = math.sqrt(max(l1 * l1 - x * x, 0.0))
    p = np.asarray(pole, float)
    p = p - u * (p @ u)
    p = p / max(np.linalg.norm(p), 1e-9)
    return tuple(a + u * x + p * r), tuple(a + u * L)


def figure_joints(pelvis, lean, ankles, hands, skirt=None, knee_pole=(0, 1, 0.2), turn=0.0):
    """The 20 figure joints from a pelvis position, a forward lean (rad, towards
    +y), ankle and hand targets (knees and elbows by IK).  Same layout as
    human_joints, so the region painting (tunic, belt, hair...) still fits."""
    px, py, pz = pelvis
    cl, sl = math.cos(lean), math.sin(lean)

    def up(h, x=0.0, y=0.0):         # a point h above the pelvis on the leaning trunk
        return (px + x, py + y + h * sl, pz + h * cl)
    J = [(px, py, pz), up(0.27), up(0.5), up(0.65, 0, 0.01)]
    for s, hand in zip((-1, 1), hands):
        sh = np.array(up(0.45, s * 0.19))
        el, ha = _ik(sh, hand, 0.30, 0.28, (s * 0.5, -0.4, -1.0))
        J += [tuple(sh), el, ha]
    for s, ank in zip((-1, 1), ankles):
        hip = (px + s * 0.1, py, pz - 0.05)
        kn, an = _ik(hip, ank, 0.42, 0.42, (s * knee_pole[0] * 0.3 + knee_pole[0] * s, knee_pole[1], knee_pole[2]))
        toe = (an[0], an[1] + 0.13, max(an[2] - 0.05, 0.02))
        J += [hip, kn, an, toe]
    J.append(skirt if skirt is not None else (px, py, pz - 0.33))
    J.append(up(0.76, 0, 0.0))
    return J


def _walk_ankles(ph, stride=0.30, lift=0.10):
    out = []
    for s in (-1, 1):
        psi = ph + (0 if s < 0 else math.pi)
        out.append((s * 0.1, stride * math.sin(psi), 0.08 + lift * max(0.0, math.cos(psi))))
    return out


def action_joints(mode, ph=0.0):
    """More trades on the site: drag (a rope over the shoulder), hammer (a mason
    dressing a block), sit, scribe (cross-legged), point (an overseer),
    shoulder (an amphora on the shoulder), pour (water under a sledge),
    torch (walking with a torch held up)."""
    bob = 0.025 * math.cos(2 * ph)
    if mode == 'drag':
        lean = 0.32
        pel = (0, 0, 0.93 + bob)
        c = (0.0, 0.33, 1.28 + bob)
        return figure_joints(pel, lean, _walk_ankles(ph, 0.34, 0.09), [(c[0] - 0.08, c[1], c[2]), (c[0] + 0.1, c[1] + 0.06, c[2] + 0.1)])
    if mode == 'hammer':
        lean = 0.38
        swing = 0.5 + 0.5 * math.cos(ph)
        pel = (0, 0, 0.9)
        return figure_joints(pel, lean, [(-0.16, 0.08, 0.08), (0.16, -0.12, 0.08)],
                             [(-0.1, 0.55, 0.78), (0.14, 0.5 - 0.12 * swing, 0.86 + 0.5 * swing)])
    if mode == 'sit':
        pel = (0, 0, 0.47)
        return figure_joints(pel, 0.12, [(-0.15, 0.5, 0.08), (0.15, 0.48, 0.08)],
                             [(-0.16, 0.38, 0.55), (0.16, 0.38, 0.55)], skirt=(0, 0.22, 0.42),
                             knee_pole=(0, 0.3, 1.0))
    if mode == 'scribe':
        pel = (0, 0, 0.2)
        return figure_joints(pel, 0.18, [(0.14, 0.28, 0.07), (-0.14, 0.3, 0.07)],
                             [(-0.12, 0.34, 0.42), (0.12, 0.36, 0.46)], skirt=(0, 0.2, 0.15),
                             knee_pole=(1.0, 0.4, 0.3))
    if mode == 'point':
        return figure_joints((0, 0, 0.95), -0.04, [(-0.11, 0.02, 0.08), (0.12, -0.05, 0.08)],
                             [(-0.26, 0.05, 0.93), (0.36, 0.58, 1.52)])
    if mode == 'shoulder':
        pel = (0, 0, 0.95 + bob)
        hy = -0.2 * math.sin(ph)
        return figure_joints(pel, 0.05, _walk_ankles(ph, 0.27, 0.09), [(-0.25, hy, 0.95 + bob), (0.24, 0.08, 1.62 + bob)])
    if mode == 'pour':
        return figure_joints((0, 0, 0.9), 0.42, [(-0.14, 0.12, 0.08), (0.15, -0.14, 0.08)],
                             [(-0.14, 0.55, 0.82), (0.14, 0.5, 1.0)])
    if mode == 'torch':
        pel = (0, 0, 0.95 + bob)
        hy = -0.2 * math.sin(ph)
        return figure_joints(pel, 0.0, _walk_ankles(ph, 0.28, 0.09), [(-0.25, hy, 0.95 + bob), (0.26, 0.2, 1.62 + bob)])
    raise ValueError(mode)


def rower_joints(ph, side):
    """A seated oarsman facing aft, hands on his oar's loom (see life.stroke)."""
    hl, hr, lean = life.rower_targets(ph / (2 * math.pi), side)
    return figure_joints((0, 0, 0.45), lean, [(-0.15, 0.62, 0.1), (0.15, 0.62, 0.1)], [hl, hr],
                         skirt=(0, 0.2, 0.42), knee_pole=(0, 0.3, 1.0))


def amphora_on(J, where):
    """Amphora geometry for 'shoulder' (lying on the right shoulder) and 'pour' (in both hands)."""
    Va, Fa = life.lathe(life.AMPHORA, 8)
    if where == 'shoulder':
        sh = np.array(J[7])
        M = (Matrix.Translation(tuple(sh + np.array([0.02, -0.02, 0.2]))) @ Matrix.Rotation(math.radians(-70), 4, 'X')
             @ Matrix.Translation((0, 0, -0.5)))
    else:
        c = 0.5 * (np.array(J[6]) + np.array(J[9]))
        M = (Matrix.Translation(tuple(c + np.array([0, 0.05, -0.1]))) @ Matrix.Rotation(math.radians(115), 4, 'X')
             @ Matrix.Translation((0, 0, -0.45)))
    return life.transform(Va, M), [list(f) for f in Fa]


ACTIONS = dict(drag=12, hammer=6, sit=1, scribe=1, point=1, shoulder=12, pour=1, torch=12)


def build_people(S, n_walk=12, n_haul=6, n_people=170):
    m = mat_person()
    S.walk_meshes = [bake(f'Walk{k}', human_joints('walk', 2 * math.pi * k / n_walk), HUMAN_E, HUMAN_R, m, skin=True)
                     for k in range(n_walk)]
    S.carry_meshes = []
    for k in range(n_walk):
        Jc = human_joints('carry', 2 * math.pi * k / n_walk)
        S.carry_meshes.append(bake(f'Carry{k}', Jc, HUMAN_E, HUMAN_R, m, skin=True,
                                   extra=basket_geometry(Jc[19][2] + 0.04) + (R_BASKET,)))
    S.haul_meshes = [bake(f'Haul{k}', human_joints('haul', 2 * math.pi * k / n_haul), HUMAN_E, HUMAN_R, m, skin=True)
                     for k in range(n_haul)]
    S.stand_mesh = bake('Stand', human_joints('stand'), HUMAN_E, HUMAN_R, m, skin=True)
    S.pose_meshes = dict(walk=S.walk_meshes, carry=S.carry_meshes, haul=S.haul_meshes, stand=[S.stand_mesh])
    for mode, n in ACTIONS.items():
        meshes = []
        for k in range(n):
            J = action_joints(mode, 2 * math.pi * k / n)
            extra = None
            if mode in ('shoulder', 'pour'):
                Va, Fa = amphora_on(J, mode)
                extra = (Va, Fa, R_POT)
            elif mode == 'torch':
                hand = np.array(J[9])
                st = G.beam(hand - [0.0, 0.02, 0.25], hand + [0.0, 0.03, 0.3], 0.05).reshape(-1, 3)
                extra = (st, [[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]], R_WOOD)
            meshes.append(bake(f'{mode}{k}', J, HUMAN_E, HUMAN_R, m, skin=True, extra=extra))
        S.pose_meshes[mode] = meshes
    for side, key in ((1, 'row_p'), (-1, 'row_s')):
        S.pose_meshes[key] = [bake(f'{key}{k}', rower_joints(2 * math.pi * k / 16, side), HUMAN_E, HUMAN_R, m, skin=True)
                              for k in range(16)]
    S.people = []
    pal = SC.P['workers']
    rng = np.random.default_rng(12)
    for i in range(n_people):
        o = SC.link(bpy.data.objects.new(f'Person{i}', S.stand_mesh))
        o.color = pal[(i * 5 + 1) % len(pal)] + (1.0,)
        o.pass_index = SC.PASS['worker']
        o.hide_render = True
        o['size'] = float(rng.uniform(0.93, 1.06))
        S.people.append(o)


def place_person(S, i, loc, heading, mode='stand', ph=0.0):
    o = S.people[i]
    o.hide_render = False
    meshes = S.pose_meshes[mode]
    o.data = meshes[int(ph / (2 * math.pi) * len(meshes)) % len(meshes)]
    o.location = loc
    o.rotation_euler = (0, 0, heading - math.pi / 2)   # figure faces +y; heading is CCW from +x
    o.scale = (o.get('size', 1.0),) * 3
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


def pose_gulls(S, t, centre, n_show, z0=0.0):
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
        z = z0 + h + 1.2 * math.sin(0.9 * t + i * 1.7)
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


def mat_planking(name, base, band, pitch, strake=0.32, butt=4.6, role='hull'):
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
    tex = None
    if SC.use_textures():     # photographed weathered planks, at their real size
        tex = SC.tex_sample(nb, role, nb.comb(u, v, 0.0), detail=0.9, normal_uv='UVMap', normal_strength=0.8)
        col = SC.mul_col(nb, col, tex[0])
    oz = nb.sep(nb.new('ShaderNodeTexCoord').outputs['Object'])[2]
    top = nb.attr('sheer_d').outputs['Fac']            # distance below the sheer (m)
    bandm = nb.math('MULTIPLY', nb.smooth(0.25, 0.35, top), nb.smooth(0.95, 0.85, top))
    col = nb.mix(bandm, col, band + (1,))
    col = nb.mix(nb.smooth(0.35, 0.15, oz), col, pitch + (1,))
    col = nb.mix(nb.math('MULTIPLY', seam, 0.7 if tex is None else 0.35), col, (0.02, 0.015, 0.01, 1))
    b = SC.principled(nb, col, rough=0.75, spec=0.35)
    if tex is not None:
        nb.feed(b.inputs['Normal'], tex[1])
        nb.feed(b.inputs['Roughness'], nb.math('ADD', 0.3, nb.math('MULTIPLY', tex[2], 0.65)))
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
    tex = None
    if SC.use_textures():     # linen weave (grey detail only)
        tex = SC.tex_sample(nb, 'linen', nb.comb(u, v, 0.0), detail=0.6, gray=True, normal_uv='UVMap', normal_strength=0.5)
        col = SC.mul_col(nb, col, tex[0])
    col = nb.mix(nb.math('MULTIPLY', grid, 0.55), col, (0.36, 0.26, 0.16, 1))
    b = SC.principled(nb, col, rough=0.9, spec=0.2)
    if tex is not None:
        nb.feed(b.inputs['Normal'], tex[1])
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
                          strake=0.24, butt=5.3, role='deck')
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


def build_lighter(S):
    """Stone lighter for the quay: a beamy planked hull without a mast, low
    bulwarks, a rubbing wale, a steering oar; replaces the plain barge hulls."""
    m_hull = mat_planking('LighterHull', (0.36, 0.25, 0.15), (0.30, 0.20, 0.12), (0.03, 0.025, 0.02))
    m_deck = mat_planking('LighterDeck', (0.50, 0.39, 0.26), (0.50, 0.39, 0.26), (0.50, 0.39, 0.26),
                          strake=0.26, butt=4.2, role='deck')
    L, Bm, ns, nk = 16.0, 6.4, 30, 8
    ss = np.linspace(0, 1, ns)
    x = (ss - 0.5) * L
    b = 0.5 * Bm * np.sin(np.pi * np.clip(ss, 0, 1) ** 0.97) ** 0.33
    keel = -1.15 * np.sin(np.pi * ss) ** 0.22 + 0.25 * (1 - np.sin(np.pi * ss) ** 0.22)
    sheer = 1.3 + 0.55 * (1 - ss) ** 3 + 0.45 * ss ** 3
    V, SD = [], []
    for i in range(ns):
        for j in range(-nk + 1, nk):
            k = abs(j) / (nk - 1)
            y = math.copysign(b[i] * math.sin(0.5 * math.pi * k) ** 0.4, j)
            z = keel[i] + (sheer[i] - keel[i]) * k ** 1.6
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
    hull = SC.mesh_from_arrays('LighterHull', V, Q, uv=uv, face_attrs={'sheer_d': ('FLOAT', np.array(SD)[Q].mean(1))},
                               mats=[m_hull], smooth=True)
    tb = G.HexBatch('lighter')
    zd = 1.08
    tb.add(G.box(0, 0, zd - 0.12, L * 0.84, Bm * 0.8, 0.12), mat=0)            # deck
    for i in range(1, ns - 2):
        for sg in (-1, 1):
            for dz, w, h in ((0.02, 0.12, 0.12), (-0.45, 0.2, 0.18)):
                tb.add(G.beam([x[i], sg * (b[i] + 0.03), sheer[i] + dz], [x[i + 1], sg * (b[i + 1] + 0.03), sheer[i + 1] + dz],
                              w, h), mat=1)
    for xx in np.linspace(-L * 0.36, L * 0.36, 7):                               # deck beams / thwarts
        tb.add(G.beam([xx, -Bm * 0.42, zd + 0.02], [xx, Bm * 0.42, zd + 0.02], 0.16, 0.12), mat=1)
    top = np.array([-L * 0.5 + 1.6, 0.9, sheer[2] + 0.9])                         # steering oar
    piv = np.array([-L * 0.5 + 0.4, 1.9, sheer[1]])
    low = piv + (piv - top) / np.linalg.norm(piv - top) * 2.6
    tb.add(G.beam(top, low, 0.14), mat=1)
    dv = (low - piv) / np.linalg.norm(low - piv)
    tb.add(G.beam(low - dv * 0.2, low + dv * 1.6, 0.5, 0.08, up=(0, 1, 0)), mat=1)
    tb.add(G.beam([-L * 0.5 + 0.2, 0, sheer[0] - 0.6], [-L * 0.5 - 0.35, 0, sheer[0] + 0.5], 0.3, 0.3), mat=1)
    tb.add(G.beam([L * 0.5 - 0.3, 0, -0.9], [L * 0.5 + 0.25, 0, sheer[-1] + 0.3], 0.28, 0.26), mat=1)
    for k in range(3):                                                             # rope coils
        tb.add(G.box(L * 0.36, (k - 1) * 0.9, zd, 0.6, 0.6, 0.18), mat=2)
    tb.finalize()
    rig = SC.hex_mesh('LighterRig', tb, np.ones(len(tb.t_on), bool), [m_deck, S.m_wood, S.m_rope])
    for h, r, cg in S.barges:
        h.data = hull
        r.data = rig


WHEEL_C = (-2.2, 0.0, 1.9)        # treadwheel axle in the quay crane's frame
WHEEL_R = 1.6
DRUM_R = 0.25


def build_quay_crane(S):
    """Slewing quay crane on a timber turntable, driven by a treadwheel on the
    counterweight side.  Same mast and jib as the site cranes (same hook
    position); the wheel turns with the hoist: rope speed = drum radius x
    wheel rate, the men inside walk at the wheel's rim speed."""
    tip = np.array(S.crane_tip)
    cb = G.HexBatch('quay_crane')
    cb.add(G.box(-1.3, 0, 0.0, 4.8, 3.4, 0.25), mat=1)                        # turntable deck
    cb.add(G.beam([0, 0, 0.25], [0, 0, 9.0], 0.36), mat=0)                    # mast
    cb.add(G.beam([0, 0, 1.0], tip, 0.3), mat=0)                              # jib
    cb.add(G.beam([0, 0, 9.0], tip, 0.06), mat=2)                             # jib stay
    for sg in (-1, 1):
        cb.add(G.beam([0, 0, 9.0], [-3.6, sg * 1.6, 0.3], 0.05), mat=2)       # back stays
        for x0 in (-3.4, -1.0):                                               # wheel trestles
            cb.add(G.beam([x0, sg * 0.8, 0.25], [WHEEL_C[0], sg * 0.8, WHEEL_C[2]], 0.18), mat=0)
    cb.add(G.beam([WHEEL_C[0], 0, WHEEL_C[2]], [-0.25, 0, 0.9], 0.05), mat=2)   # rope: drum -> mast sheave
    cb.add(G.beam([0.2, 0, 1.25], tip + np.array([0, 0, -0.3]), 0.05), mat=2)   # hoist fall along the jib
    cb.add(G.box(-3.3, 0, 0.25, 0.9, 2.6, 0.9), mat=3)                        # counterweight stones
    cb.finalize()
    S.cranes[5][0].data = SC.hex_mesh('QuayCrane', cb, np.ones(len(cb.t_on), bool),
                                      [S.m_wood, S.m_plank, S.m_rope, S.m_stone])
    wb = G.HexBatch('wheel')
    n = 16
    for side in (-0.55, 0.55):
        pts = [(WHEEL_R * math.cos(2 * math.pi * k / n), side, WHEEL_R * math.sin(2 * math.pi * k / n)) for k in range(n)]
        for k in range(n):
            wb.add(G.beam(pts[k], pts[(k + 1) % n], 0.13, 0.12, up=(0, 1, 0)), mat=0)
            if k % 2 == 0:
                wb.add(G.beam((0, side, 0), pts[k], 0.09, 0.09, up=(0, 1, 0)), mat=0)
    for k in range(2 * n):                                                    # treads
        a = 2 * math.pi * (k + 0.5) / (2 * n)
        c, s_ = math.cos(a) * (WHEEL_R - 0.06), math.sin(a) * (WHEEL_R - 0.06)
        wb.add(G.beam((c, -0.58, s_), (c, 0.58, s_), 0.13, 0.05, up=(math.cos(a), 0, math.sin(a))), mat=1)
    wb.add(G.beam((0, -0.95, 0), (0, 0.95, 0), 2 * DRUM_R, 2 * DRUM_R), mat=0)   # axle with rope drum
    wb.finalize()
    S.tread = SC.link(bpy.data.objects.new('Treadwheel', SC.hex_mesh('Treadwheel', wb, np.ones(len(wb.t_on), bool),
                                                                      [S.m_wood, S.m_plank])))
    S.tread.pass_index = SC.PASS['crane']
    S.tread.hide_render = True


def pose_treadwheel(S, angle, walkers=None, first_person=0, walk_ph=0.0):
    """Wheel on crane 5 (follows its slew).  walkers: number of men inside."""
    c = S.cranes[5][0]
    if c.hide_render:
        S.tread.hide_render = True
        return first_person
    M = c.matrix_world
    S.tread.matrix_world = M @ Matrix.Translation(WHEEL_C) @ Matrix.Rotation(angle, 4, 'Y')
    S.tread.hide_render = False
    k = first_person
    for j in range(walkers or 0):
        p = M @ Vector((WHEEL_C[0] + 0.3, (j - 0.5) * 0.46, WHEEL_C[2] - WHEEL_R + 0.1))
        yaw = math.atan2(M[1][0], M[0][0])
        place_person(S, k, (p.x, p.y, p.z), yaw, 'walk', walk_ph + j * 1.7)
        k += 1
    return k


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
    sb.finalize()
    me = SC.hex_mesh('Sledge', sb, np.ones(len(sb.t_on), bool), [S.m_wood, S.m_stone])
    S.sledges = []
    for i in range(3):
        o = SC.link(bpy.data.objects.new(f'Sledge{i}', me))
        o.pass_index = SC.PASS['props']
        o.hide_render = True
        S.sledges.append(o)
    S.sledge = S.sledges[0]


# where the quay's clutter lies (x, y, z, heading): clear of every path in S1
QUAY_SPOTS = dict(amphorae=(43.4, -102.6, 2.95, 0.0), jars=(31.0, -87.5, 2.95, math.pi / 2),
                  baskets=(39.6, -79.5, 2.95, 0.0), coils=(38.3, -99.0, 2.95, 0.0),
                  levers=(35.8, -86.0, 2.95, math.pi / 2), awning=(36.8, -76.0, 2.95, 0.0))
SIGNAL_POLE = (41.8, -65.0, 2.95, 7.0)


def build_signal_pole(S):
    x, y, z, h = SIGNAL_POLE
    pb = G.HexBatch('pole')
    pb.add(G.beam([x, y, z], [x, y, z + h], 0.16), mat=0)
    pb.finalize()
    S.pole = SC.link(bpy.data.objects.new('SignalPole', SC.hex_mesh('SignalPole', pb, np.ones(1, bool), [S.m_wood])))
    S.pole.pass_index = SC.PASS['props']
    S.pole.hide_render = True


def build(res=(1280, 720)):
    S = SC.build(res, look=LOOK, derrick=True, n_workers=230)
    build_lighter(S)
    build_quay_crane(S)
    build_sledge(S)
    build_people(S)
    build_carts(S)
    build_gulls(S, n=12)
    build_ship(S)
    life.build(S, sys.modules[__name__])
    life.build_clutter(S, QUAY_SPOTS)
    life.build_site_dressing(S, ground_z)
    build_signal_pole(S)
    return S


def hide_extras(S):
    for o in S.people + S.gulls + S.sledges + [S.tread, S.pole]:
        o.hide_render = True
    for c, wheels, oxen in S.carts:
        c.hide_render = True
        for w, _ in wheels:
            w.hide_render = True
        for o, _ in oxen:
            o.hide_render = True
    for o in S.ship.values():
        o.hide_render = True
    life.hide_all(S)


def crane_tip(S, idx):
    c = S.cranes[idx][0]
    return c.matrix_world @ Vector(S.crane_tip_tall if idx == 4 else S.crane_tip)


# ================================================================= shots
QUAY_CRANE = (38.6, -92.0, 2.95)
STATUE_YAW = math.radians(80.0)
QUAY_Z = 2.95
CAMP_FIRES = [(-58.0, -8.0), (-70.0, 12.0), (-52.0, 30.0)]
SMITHY = (-28.0, -50.0)


def site_plumes(fast=1.0):
    """Cooking fires in the workers' camp and the smithy by the yard."""
    pl = [life.Plume((x, y, ground_z(x, y) + 0.6), n=7, life=11.0, rise=0.9, drift=1.3, size0=1.0, grow=0.45,
                     dens=0.6, seed=i) for i, (x, y) in enumerate(CAMP_FIRES)]
    x, y = SMITHY
    pl.append(life.Plume((x, y, ground_z(x, y) + 2.2), n=8, life=10.0, rise=1.3, drift=1.4, size0=0.8, grow=0.5,
                         dens=0.8, seed=7))
    return pl


def place_walkers(S, k, walkers, v, z_of=None):
    """(start (x, y), heading, speed, phase0, mode) walking in a straight line."""
    for (x0, y0), hd, spd, ph0, mode in walkers:
        dist = spd * v
        x = x0 + math.cos(hd) * dist
        y = y0 + math.sin(hd) * dist
        z = z_of(x, y) if z_of else ground_z(x, y)
        stride = 1.45 if mode in ('walk', 'carry', 'shoulder', 'torch') else 1.1
        place_person(S, k, (x, y, z), hd, mode, ph0 + dist / stride * 2 * math.pi)
        k += 1
    return k


def on_quay(x, y):
    if (29.5 < x < 42.5 and -108 < y < -64) or (24.5 < x < 47.5 and -108.5 < y < -99.5):
        return QUAY_Z
    return ground_z(x, y)


def sledge_team(S, idx, k, pos, heading, ph, z=None):
    """Sledge idx with a block at pos, dragged towards `heading` by two ropes of
    three men each, the rope over the right shoulder.  Returns (next person, rope segments)."""
    sx, sy = pos
    z = ground_z(sx, sy) if z is None else z
    o = S.sledges[idx]
    o.hide_render = False
    o.location = (sx, sy, z)
    o.rotation_euler = (0, 0, heading - math.pi / 2)
    c, s_ = math.cos(heading - math.pi / 2), math.sin(heading - math.pi / 2)

    def w(lx, ly, lz):                      # sledge-local (x right, y forward) -> world
        return (sx + lx * c - ly * s_, sy + lx * s_ + ly * c, z + lz)
    segs = []
    for rx in (-0.6, 0.6):
        pts = [w(rx * 0.5, 1.3, 0.25)]
        for j, dy in enumerate((3.0, 4.2, 5.4)):
            hx, hy, hz = w(rx - 0.19, dy, 0.0)
            pj = ph + j * 2.1 + (1.0 if rx > 0 else 0.0)
            place_person(S, k, (hx, hy, hz), heading, 'drag', pj)
            k += 1
            pts.append(w(rx, dy + 0.14, 1.42 + 0.025 * math.cos(2 * pj)))
        last = pts[-1]
        pts.append(w(rx, 5.4 + 0.84, 1.07))
        segs += list(zip(pts[:-1], pts[1:]))
    return k, segs


S1_CAM0 = ((61.0, -113.0, 8.5), (41.5, -88.0, 5.0))
S1_CAM1 = ((56.5, -116.0, 8.5), (38.5, -86.5, 5.0))


def shot_S1(S, v):
    """The quay, 08:00, real time: a working morning."""
    u = v / 3.0
    hour = 8.0 + 0.25 * u
    e = TL.ease_io(u)
    cam = (lerp3(S1_CAM0[0], S1_CAM1[0], e), lerp3(S1_CAM0[1], S1_CAM1[1], e), 30.0)
    meta = SC.pose(S, v, tc=0.95, hour=hour, life=v, hop_t=0.3, sea_t=40.0 + v, water_t=16.0 + 0.4 * v,
                   cloud_t=hour * 0.75, shadow_t=hour * 124.0, cover=0.02, cloud_gain=7.0, shadow_cover=0.3,
                   traffic=False, crane5_loc=QUAY_CRANE, statue_yaw=STATUE_YAW, cam=cam)
    dress_workers(S, 0.3)
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
    life.add_wake(S, (x, -73.5), math.pi, 0.4, 16.0)
    # quay crane: swings a block from the barge onto the jetty (real time)
    c, rope, load = S.cranes[5]
    slew = math.radians(15.0 + 45.0 * TL.ease_io(u))
    c.matrix_world = Matrix.Translation(QUAY_CRANE) @ Matrix.Rotation(slew, 4, 'Z')
    tip = c.matrix_world @ Vector(S.crane_tip)
    lift = 0.5 * u                                     # a treadwheel lifts slowly: ~0.17 m/s
    lz = 5.0 + lift
    swing = 0.25 * math.sin(2.1 * v)
    load.hide_render = rope.hide_render = False
    load.matrix_world = Matrix.Translation((tip.x + swing * 0.3, tip.y, lz)) @ Matrix.Rotation(slew, 4, 'Z')
    rope.matrix_world = Matrix.Translation(tip) @ Matrix.Diagonal((1, 1, tip.z - lz, 1))
    # people on the jetty and the track
    k = place_walkers(S, 0, [
        ((30.8, -100.0), math.radians(90), 1.25, 0.0, 'walk'), ((38.0, -70.0), math.radians(-90), 1.1, 1.0, 'carry'),
        ((31.5, -80.0), math.radians(95), 1.3, 2.0, 'walk'), ((36.0, -60.0), math.radians(125), 1.1, 0.5, 'carry'),
        ((24.0, -46.0), math.radians(130), 1.1, 1.5, 'walk'), ((40.3, -84.0), math.radians(-90), 1.2, 2.5, 'walk'),
        ((29.0, -55.0), math.radians(-50), 1.1, 3.0, 'carry'), ((39.6, -66.0), math.radians(-90), 1.0, 0.7, 'shoulder'),
        ((44.5, -100.8), math.radians(180), 0.9, 2.2, 'shoulder')], v, on_quay)
    # two men walking in the treadwheel; the rope drum winds exactly the lifted length
    ang = lift / DRUM_R
    k = pose_treadwheel(S, ang, walkers=2, first_person=k, walk_ph=ang * (WHEEL_R - 0.06) / 1.45 * 2 * math.pi)
    # a guide line from the load to the man steadying it
    lb = load.matrix_world @ Vector((0.9, 0.0, -1.0))
    lines = [((lb.x, lb.y, lb.z), (41.0, -95.2, QUAY_Z + 1.2))]
    busy = [(41.0, -95.5, QUAY_Z, 180, 'haul'), (39.2, -96.8, QUAY_Z, 160, 'haul'),
            (46.4, -85.8, 1.3, 200, 'stand'), (48.8, -85.6, 1.3, 250, 'haul'), (46.2, -94.0, 1.3, 165, 'point'),
            (35.5, -63.0, ground_z(35.5, -63.0), 40, 'stand'),
            (36.8, -75.2, QUAY_Z, -90, 'scribe'), (38.9, -77.6, QUAY_Z, -91, 'point'),       # scribe, overseer
            (34.95, -80.6, QUAY_Z, 180, 'hammer'), (34.95, -77.3, QUAY_Z, 180, 'hammer'),   # masons
            (35.1, -70.3, QUAY_Z, 180, 'hammer'), (31.9, -86.6, QUAY_Z, 180, 'pour'),        # water for the crew
            (41.4, -84.0, QUAY_Z, 180, 'sit'), (41.4, -77.0, QUAY_Z, 170, 'sit')]            # a rest on the bollards
    for j, (x, y, z, hd, mode) in enumerate(busy):
        place_person(S, k, (x, y, z), math.radians(hd), mode, 2.6 * v + j * 1.7)
        k += 1
    # a team dragging a block on a sledge up the jetty, the rope over their right shoulders
    k, rl = sledge_team(S, 0, k, (32.2, -97.5 + 0.55 * v), math.radians(90), 0.55 * v / 1.1 * 2 * math.pi, QUAY_Z)
    set_lines(S, lines + rl)
    # the island behind: carriers and walkers on the track, a rest by the cooking fires
    k = place_walkers(S, k, [
        ((26.0, -52.0), math.radians(150), 1.2, 0.3, 'walk'), ((18.0, -46.0), math.radians(-30), 1.1, 1.1, 'carry'),
        ((8.0, -42.0), math.radians(160), 1.2, 2.3, 'shoulder'), ((-5.0, -48.0), math.radians(10), 1.0, 0.9, 'walk'),
        ((-20.0, -38.0), math.radians(200), 1.1, 1.7, 'carry'), ((-35.0, -30.0), math.radians(30), 1.2, 0.4, 'walk'),
        ((-45.0, -15.0), math.radians(-60), 1.0, 2.8, 'shoulder'), ((10.0, -58.0), math.radians(120), 1.2, 1.9, 'walk'),
        ((0.0, -55.0), math.radians(80), 1.1, 0.2, 'carry'), ((-12.0, -60.0), math.radians(-20), 1.2, 1.4, 'walk')], v)
    for j, (x, y, hd, mode) in enumerate(((-55.5, -9.5, 60, 'sit'), (-60.0, -6.0, -120, 'sit'), (-57.0, -5.0, 200, 'point'),
                                          (-68.0, 10.0, 30, 'sit'), (-26.0, -48.0, 150, 'hammer'))):
        place_person(S, k, (x, y, ground_z(x, y)), math.radians(hd), mode, 2.6 * v + j)
        k += 1
    # rowing boats: one pulling away from the moored lighter, one crossing further out
    k = life.pose_skiff(S, sys.modules[__name__], 0, (52.0 + 0.79 * life.skiff_distance(v), -78.0 + 0.61 * life.skiff_distance(v)),
                        math.atan2(0.61, 0.79), v, k, seed=0)
    d1 = life.skiff_distance(v + 3.0, 1.4)
    hd1 = math.radians(205.0)
    k = life.pose_skiff(S, sys.modules[__name__], 1, (74.0 + math.cos(hd1) * d1, -46.0 + math.sin(hd1) * d1), hd1, v + 3.0, k, seed=2)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    # ox carts: one leaving for the building site, one waiting at the jetty
    place_cart(S, 0, (30.0 - 0.95 * v * 0.6, -57.0 + 0.95 * v * 0.8), math.atan2(0.8, -0.6), 0.95 * v)
    place_cart(S, 1, (38.5, -56.5), math.radians(100), 0.0)
    pose_gulls(S, v, (44.0, -88.0), 10)
    life.show_clutter(S, True)
    life.show_site_dressing(S, True)
    S.pole.hide_render = False
    x, y, z, h = SIGNAL_POLE
    life.pose_pennants(S, [((x, y, z + h - 0.1), 2.4, 0.5, 0), ((tip.x, tip.y, tip.z + 0.2), 2.2, 0.45, 0)], v)
    life.pose_smoke(S, site_plumes(), 40.0 + v, cam[0])
    meta.update(stars=0.0)
    return meta


S2_POSES = ['stand', 'walk', 'carry', 'hammer', 'haul', 'stand', 'shoulder', 'point', 'walk', 'drag']


def dress_workers(S, hop_t):
    """The scene's time-lapse workers become proper people in varied trades."""
    pal = SC.P['workers']
    for i, o in enumerate(S.workers[:S.n_workers_used]):
        if o.hide_render:
            continue
        slot = int(math.floor(hop_t * 1.5 + (i * 0.618) % 1.0))
        h = G._hash2(np.int64(i), np.int64(slot), 13)
        mode = S2_POSES[int(h * len(S2_POSES)) % len(S2_POSES)]
        meshes = S.pose_meshes[mode]
        o.data = meshes[int(h * 997) % len(meshes)]
        o.color = pal[(i * 5 + 1) % len(pal)] + (1.0,)
        o.scale = (0.97 + 0.08 * ((i * 0.618) % 1.0),) * 3


def water_spots(cam, clock, n, d0, d1, seed):
    """n boat positions (x, y, heading, slot) in open water that the camera sees,
    each re-drawn at its own time-lapse moment: sampled in the view cone, off
    the island and the quay."""
    loc, tgt, lens = cam
    base = math.atan2(tgt[1] - loc[1], tgt[0] - loc[0])
    half = math.atan(18.0 / lens) * 0.85
    out = []
    for i in range(n):
        slot = math.floor(clock + (i * 0.618 + seed * 0.37) % 1.0)
        for tries in range(24):
            h = [G._hash2(np.int64(slot * 31 + tries), np.int64(i + 17 * seed), q) for q in (41, 42, 43)]
            a = base + (2 * h[0] - 1) * half
            d = d0 + (d1 - d0) * h[1]
            x, y = loc[0] + d * math.cos(a), loc[1] + d * math.sin(a)
            if SC.island_sd(np.array([x]), np.array([y]))[0] < 12.0:
                continue
            if 15.0 < x < 60.0 and -125.0 < y < -55.0:          # the quay and its berths
                continue
            if any(math.hypot(x - q[0], y - q[1]) < 25.0 for q in out):
                continue
            hd = math.radians(90 - (130 + 90 * h[2]))           # running before the NNW wind
            out.append((x, y, hd, slot))
            break
    return out


def podium_workers(S, k, hop_t, n):
    """Masons, haulers and carriers on the podium round the rising walls (time-lapse jumps)."""
    a_in, a_out = SC.T1_A0 + 2.2, SC.PLAT_A[-1] - 1.0
    for j in range(n):
        slot = math.floor(hop_t * 1.5 + (j * 0.618 + 0.3) % 1.0)
        h = [G._hash2(np.int64(slot), np.int64(j), q) for q in (51, 52, 53, 54)]
        side = int(h[0] * 4)
        along = (2 * h[1] - 1) * a_out
        depth = a_in + (a_out - a_in) * h[2]
        x, y = [(depth, along), (along, depth), (-depth, along), (along, -depth)][side]
        mode = S2_POSES[int(h[3] * len(S2_POSES)) % len(S2_POSES)]
        place_person(S, k, (x, y, SC.PLAT_TOP), 2 * math.pi * h[3] * 7.0, mode, 6.3 * h[1])
        k += 1
    return k


def shot_S2(S, v):
    tc = s2_tc(v)
    hour = s2_hour(v)
    cam = s2_cam(v, tc)
    # calmer time-lapse: people and loads jump about once a second, clouds and
    # their shadows drift steadily instead of racing with the clock at night
    hop_t = v * 0.45
    meta = SC.pose(S, v, tc=tc, hour=hour, life=v, hop_t=hop_t, sea_t=v * 1.4, water_t=v * 0.6,
                   cloud_t=6.0 + v * 1.1, shadow_t=1000.0 + v * 70.0, cover=0.04 + 0.04 * math.sin(v * 0.7),
                   cloud_gain=7.0, shadow_cover=0.3, moon=0.0, crane5_loc=QUAY_CRANE, statue_yaw=STATUE_YAW,
                   cam=cam, crowd=2.5, torch_t=v * 0.08)
    dress_workers(S, hop_t)
    life.show_site_dressing(S, tc < TL.PHASES['scaf2_down'][1])
    day = meta['day']
    # smoke from the camp and the smithy (faster in the time-lapse); coasting boats offshore
    plumes = site_plumes() if day > 0.3 else []
    life.pose_smoke(S, plumes, 200.0 + v * 6.0, cam[0])
    if day > 0.35:
        for kb, (x, y, hd, _) in enumerate(water_spots(cam, hop_t * 0.9, 5, 180.0, 700.0, 7)):
            life.pose_boat(S, kb, (x, y), hd, v, seed=kb)
    # sledge teams and ox carts on the tracks from the quay to the podium (time-lapse jumps)
    k = 0
    segs = []
    building = TL.PHASES['platform'][0] < tc < TL.PHASES['scaf2_down'][0]
    if day > 0.3 and building:
        for j, (a, b) in enumerate((((24.0, -56.0), (9.0, -33.0)), ((40.0, -50.0), (31.0, -33.0)))):
            f = G._hash2(np.int64(math.floor(hop_t * 1.5 + 0.5 * j)), np.int64(j), 31)
            x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            k, sg = sledge_team(S, j + 1, k, (x, y), math.atan2(b[1] - a[1], b[0] - a[0]), 7.0 * f + j)
            segs += sg
        for j, (a, b) in enumerate((((34.0, -62.0), (14.0, -44.0)), ((32.0, -60.0), (44.0, -44.0)))):
            cs = math.floor(hop_t * 1.5 + 0.25 + 0.5 * j)
            f = G._hash2(np.int64(cs), np.int64(j), 37)
            hd = math.atan2(b[1] - a[1], b[0] - a[0]) + (math.pi if G._hash2(np.int64(cs), np.int64(j), 38) > 0.5 else 0)
            place_cart(S, j, (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), hd, 5.0 * f)
        # harbour boats rowing past, and a crowd on the podium round the rising walls
        for kk, (x, y, hd, slot) in enumerate(water_spots(cam, hop_t * 1.5, 3, 90.0, 260.0, 11)):
            k = life.pose_skiff(S, sys.modules[__name__], kk, (x, y), hd, 7.3 * kk + 1.37 * slot, k, seed=kk)
        k = podium_workers(S, k, hop_t, 34)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    set_lines(S, segs)
    # pennants on the cranes working the walls
    mounts = []
    for idx in range(5):
        c = S.cranes[idx][0]
        if not c.hide_render:
            p = crane_tip(S, idx)
            mounts.append(((p.x, p.y, p.z + 0.3), 3.0, 0.6, idx % 3))
    life.pose_pennants(S, mounts, v * 0.9)
    meta.update(stars=0.0)
    return meta


S3_CAM = (bearing_pos(156.0, 60.0, 105.5), (-2.5, 0.0, 106.3), 42.0)
TAG_MEN = [(-7.6, -3.9), (-3.3, -7.3)]
ROOF_CREW = [(110.0, 7.4, 'point'), (138.0, 7.6, 'stand'), (166.0, 7.2, 'stand'), (188.0, 7.6, 'point'),
             (95.0, 8.2, 'stand')]
# on the lantern scaffold (plank rings at 96.2 + 2 m steps, r 4.5..5.9): ready to receive the statue
SCAFFOLD_CREW = [(128.0, 2, 'stand'), (171.0, 2, 'point'), (150.0, 3, 'point'), (205.0, 3, 'stand'), (112.0, 3, 'haul')]
S3_BOATS = [(-487.6, 531.0, 160.0), (-128.6, 874.0, 175.0), (-717.0, 1143.0, 150.0)]


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
    dress_workers(S, 11.0 + (v - 11.0) * 0.5)
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
    # the rest of the roof crew watch the statue come down, the foreman directs
    for j, (b, r, mode) in enumerate(ROOF_CREW):
        x, y = r * math.sin(math.radians(b)), r * math.cos(math.radians(b))
        hd = math.atan2(statue.y - y, statue.x - x)
        place_person(S, k, (x, y, SC.T2_ROOF), hd, mode, v * 2 + j)
        k += 1
    for j, (b, lift_i, mode) in enumerate(SCAFFOLD_CREW):
        x, y = 5.2 * math.sin(math.radians(b)), 5.2 * math.cos(math.radians(b))
        hd = math.atan2(-y, -x)                                   # facing the lantern, the statue above
        place_person(S, k, (x, y, SC.T3_Z0 + 2.0 * lift_i + 2.02), hd, mode, v * 2.4 + j)
        k += 1
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    set_taglines(S, TAG_MEN, p)
    pose_gulls(S, v, (-6.0, 4.0), 6, z0=88.0)
    # boats offshore, a pennant on the derrick mast
    for kb, (x, y, hd) in enumerate(S3_BOATS):
        h = math.radians(90 - hd)
        life.pose_boat(S, kb, (x + math.cos(h) * 2.5 * (v - 11), y + math.sin(h) * 2.5 * (v - 11)), h, v, seed=kb)
    mx, my = SC.DERRICK_C
    life.pose_pennants(S, [((mx, my, SC.T2_ROOF + SC.DERRICK_MAST + 0.2), 3.2, 0.6, 0)], v)
    meta.update(stars=0.0)
    return meta


def set_lines(S, segments):
    """Free rope segments for the current frame (hidden when empty)."""
    if not hasattr(S, 'lines_obj'):
        S.lines_obj = SC.link(bpy.data.objects.new('Lines', bpy.data.meshes.new('Lines')))
        S.lines_obj.pass_index = SC.PASS['crane']
    lb = G.HexBatch('lines')
    for a, b in segments:
        lb.add(G.beam(a, b, 0.035), mat=0)
    lb.finalize()
    SC.set_dynamic_mesh(S.lines_obj, 'Lines', lb, np.ones(len(lb.t_on), bool), [S.m_rope])
    S.lines_obj.hide_render = not segments


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


def beacon_plume(glow):
    return life.Plume((0.0, 0.0, SC.FIRE_POS[2] + 3.4), n=34, life=18.0, rise=1.9, drift=2.2, size0=3.2, grow=1.35,
                      dens=0.34, glow=glow, seed=11)


def podium_crowd(S, k, v, n=34, torches=False):
    """People gathered on the podium to see the fire lit, on the side facing the camera."""
    rng = np.random.default_rng(3)
    a_in, a_out = SC.T1_A0 + 1.2, SC.PLAT_A[-1] - 1.2
    for j in range(n):
        side = rng.uniform(-1, 1)
        depth = rng.uniform(a_in, a_out)
        if j % 2:
            x, y = -depth, side * a_out                   # west face
        else:
            x, y = side * a_out, -depth                   # south face
        hd = math.atan2(-y, -x) + rng.uniform(-0.4, 0.4)
        mode = ['stand', 'point', 'stand', 'walk'][j % 4]
        place_person(S, k, (x, y, SC.PLAT_TOP), hd, mode, rng.uniform(0, 6.3) + (v * 2.0 if mode == 'walk' else 0))
        k += 1
    return k


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
    dress_workers(S, v * 0.8)
    k = podium_crowd(S, 0, v)
    # boats coming home before dark, gulls round the tower
    for kb, (x, y, hd, spd) in enumerate(((-70.0, 135.0, 170.0, 3.0), (125.0, 45.0, 200.0, 2.6), (-160.0, 190.0, 160.0, 2.8))):
        h = math.radians(90 - hd)
        life.pose_boat(S, kb, (x + math.cos(h) * spd * (v - 13.5), y + math.sin(h) * spd * (v - 13.5)), h, v, seed=kb)
    hd1 = math.radians(90 - 200.0)
    d1 = life.skiff_distance(v - 13.5, 1.5)
    k = life.pose_skiff(S, sys.modules[__name__], 0, (80.0 + math.cos(hd1) * d1, 95.0 + math.sin(hd1) * d1), hd1, v, k, seed=1)
    for i in range(k, len(S.people)):
        S.people[i].hide_render = True
    pose_gulls(S, v, (0.0, -10.0), 5, z0=55.0)
    life.pose_smoke(S, [beacon_plume(0.6 * fire)] if fire > 0.05 else [], 60.0 + v, cam[0])
    meta.update(stars=0.0)
    return meta


S5_CAM = (bearing_pos(47.0, 292.0, 4.8), (0.0, 0.0, 46.0), 35.0)
ANCHORAGE = [(75.0, -45.0, math.radians(25.0)), (112.0, -40.0, math.radians(-10.0)), (30.0, -125.0, math.radians(40.0))]


def shot_S5(S, v):
    u = (v - 16.0) / 4.0
    hour = 138.33 + 0.004 * u
    loc, tgt, lens = S5_CAM
    loc = lerp3(loc, bearing_pos(45.5, 290.0, 4.9), u)
    meta = SC.pose(S, v, tc=29.0, hour=hour, life=v, hop_t=5.0, sea_t=300.0 + v, water_t=120.0 + 0.4 * v,
                   cloud_t=hour * 0.75, shadow_t=hour * 124.0, cover=0.12, cloud_gain=5.0, shadow_cover=0.25,
                   fire=1.0, traffic=False, moon=1.0, crane5_loc=QUAY_CRANE, statue_yaw=STATUE_YAW,
                   cam=(loc, tgt, lens))
    dress_workers(S, 5.0)
    heading_b = 150.0
    hd = math.radians(90.0 - heading_b)
    p0 = np.array([158.5, 181.9])
    pos = p0 + 2.2 * (v - 16.0) * np.array([math.cos(hd), math.sin(hd)])
    brail = 0.1 + 0.5 * TL.ease_io(u)
    n = pose_ship(S, pos, hd, v, math.radians(25.0), brail)
    life.add_wake(S, pos, hd, 0.8, SHIP_L)
    # harbour boats with their lamps lit, ships riding at anchor
    for kk, (x, y, hdb, seed) in enumerate(((158.0, 158.0, 137.0, 0), (122.0, 58.0, -43.0, 2))):
        h = math.radians(90 - hdb)
        d = life.skiff_distance(v - 16.0 + 2 * seed, 1.4)
        n = life.pose_skiff(S, sys.modules[__name__], kk, (x + math.cos(h) * d, y + math.sin(h) * d), h, v, n,
                            lamp=1.0, seed=seed)
    life.pose_anchored(S, ANCHORAGE, v, lamp=1.0)
    for i in range(n, len(S.people)):
        S.people[i].hide_render = True
    mast_top = S.ship_root.matrix_world @ Vector((S.ship_mast_x, 0.0, S.ship_masthead + 0.3))
    life.pose_pennants(S, [((mast_top.x, mast_top.y, mast_top.z), 3.0, 0.5, 0)], v)
    life.pose_smoke(S, [beacon_plume(1.0)], 120.0 + v, loc)
    meta.update(stars=1.0, expo_mul=0.72)          # a darker night, as asked
    return meta


SHOT_FN = dict(S1=shot_S1, S2=shot_S2, S3=shot_S3, S4=shot_S4, S5=shot_S5)


def pose(S, f):
    v = f / FPS
    name, a, b = shot_at(v)
    hide_extras(S)
    if hasattr(S, 'taglines'):
        S.taglines.hide_render = name != 'S3'
    if hasattr(S, 'lines_obj'):
        S.lines_obj.hide_render = True
    meta = SHOT_FN[name](S, v)
    if name != 'S1':
        pose_treadwheel(S, 0.8 * v)          # the quay crane keeps its wheel in the wide shots
    life.apply_wakes(S)
    meta.update(shot=name, shot_t=v - a, t=v)
    return meta
