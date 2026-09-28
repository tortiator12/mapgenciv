"""The Colossus of Rhodes: Helios, sculpted as a signed-distance field.

Reconstruction used in the film (storyboards/runde1_fehlende_wunder.md):
an upright nude youth, legs close together (weight on the right leg), a
chlamys hanging from the left shoulder over the left forearm and falling to
the base as the third support, the right hand raised to shade the eyes, a
radiate crown.  Figure 31 m from sole to crown of the head, rays to ~33 m.

The figure is written at human scale (1.80 m, facing +y, right = +x, soles at
z = 0) and scaled by S.  build() returns plain arrays (cached on disk):
  skin     V, F of the bronze surface, per-face plate id, per-vertex seam
           distance and plate tone
  plates   seed position and build height of every bronze plate
  crown    rays (V, F) with their build height
  bars     iron armature: segments (a, b) with build height
  fill     stone blocks inside legs and drapery (centre, size, build height)
"""
import hashlib
import math
import os

import numpy as np

import sculpt as SD

H0 = 1.80                      # model height (m, human scale)
HEIGHT = 31.0                  # sole to top of the head (m)
S = HEIGHT / H0                # 17.2
VOXEL = 0.085                  # statue-scale sampling step (m)
PLATE = 1.45                   # bronze plate width (m)
COURSE = 1.2                   # height of a course of plates (m)
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build', 'cache')


# ------------------------------------------------------------------ anatomy
_CURL_DIRS = np.random.default_rng(5).normal(size=(7, 3))
_CURL_DIRS /= np.linalg.norm(_CURL_DIRS, axis=1, keepdims=True)
_CURL_PH = np.random.default_rng(6).uniform(0, 2 * np.pi, 7)


def _curls(P, d):
    """Short irregular curls on the hair (~1.5 cm, human scale): a sum of
    plane waves in random directions, sharpened into bumps."""
    w = np.sin(P @ _CURL_DIRS.T * 160.0 + _CURL_PH).sum(axis=1) / 7.0
    return d - 0.012 * np.maximum(w, -0.1)


def _folds(axis_x, axis_y, n, amp, z_amp=None):
    """Vertical folds round an (almost) vertical drapery column."""
    def disp(P, d):
        ang = np.arctan2(P[:, 1] - axis_y, P[:, 0] - axis_x)
        a = amp if z_amp is None else amp * (1.0 + z_amp * (1.0 - np.clip(P[:, 2] / 1.0, 0, 1)))
        return d - a * np.cos(n * ang + 3.0 * P[:, 2])
    return disp


def prims():
    C, E = 'cone', 'ell'
    p = []

    def cone(a, b, ra, rb, k=0.02, **kw):
        p.append(SD.Prim(C, k=k, a=a, b=b, ra=ra, rb=rb, **kw))

    def ell(c, r, k=0.02, R=None, op='add', **kw):
        g = dict(c=c, r=r)
        if R is not None:
            g['R'] = R
        p.append(SD.Prim(E, op=op, k=k, **g, **kw))

    # --- torso (classical: broad shoulders, narrow hips, a slight contrapposto)
    ell((0.0, 0.0, 1.335), (0.156, 0.104, 0.165), k=0.0)              # rib cage
    ell((0.0, 0.02, 1.14), (0.122, 0.078, 0.125), k=0.06)             # abdomen
    ell((0.0, -0.006, 0.97), (0.148, 0.102, 0.1), k=0.06,
        R=SD.rot_from_axes((0.0, 1.0, 0.0), up=(0.06, 0.0, 1.0)))      # pelvis, right hip up
    for sx in (1, -1):
        ell((sx * 0.074, 0.07, 1.37), (0.084, 0.04, 0.058), k=0.035,
            R=SD.rot_from_axes((sx * 0.25, 1.0, 0.0)))                 # pectorals
        ell((sx * 0.07, -0.056, 0.9), (0.07, 0.06, 0.088), k=0.045)    # buttocks
        ell((sx * 0.114, 0.012, 1.04), (0.046, 0.066, 0.068), k=0.045)  # obliques over the iliac crest
        ell((sx * 0.08, -0.06, 1.39), (0.058, 0.028, 0.08), k=0.04)     # shoulder blades
        ell((sx * 0.118, -0.018, 1.29), (0.04, 0.045, 0.1), k=0.05)     # latissimus: the V of the back
        ell((sx * 0.088, -0.014, 1.495), (0.09, 0.05, 0.034), k=0.035,
            R=SD.rot_from_axes((sx * 1.0, 0.0, -0.35)))                 # trapezius
    ell((0.0, 0.114, 1.172), (0.0065, 0.01, 0.008), op='sub', k=0.008)  # navel
    cone((0.0, -0.108, 1.44), (0.0, -0.094, 1.03), 0.012, 0.01, k=0.02, op='sub')   # groove of the spine
    ell((0.0, 0.07, 0.878), (0.024, 0.028, 0.03), k=0.02)              # genitals (small, classical)
    cone((0.0, 0.0, 1.46), (0.0, 0.016, 1.605), 0.058, 0.051, k=0.025)  # neck

    # --- head (faces +y): a straight Greek profile
    ell((0.0, -0.004, 1.708), (0.074, 0.093, 0.094), k=0.0)            # cranium
    ell((0.0, 0.034, 1.645), (0.062, 0.066, 0.074), k=0.03)            # face, jaw
    ell((0.0, 0.075, 1.598), (0.03, 0.026, 0.025), k=0.02)             # chin
    ell((0.0, 0.088, 1.692), (0.05, 0.014, 0.011), k=0.02)             # brow
    cone((0.0, 0.1, 1.684), (0.0, 0.116, 1.637), 0.009, 0.0125, k=0.012)  # nose, in line with the brow
    for sx in (1, -1):
        ell((sx * 0.03, 0.099, 1.671), (0.017, 0.013, 0.01), op='sub', k=0.012)   # eye sockets
        ell((sx * 0.029, 0.092, 1.671), (0.012, 0.009, 0.0075), k=0.006)          # eyeballs
        ell((sx * 0.046, 0.074, 1.636), (0.022, 0.02, 0.022), k=0.02)             # cheeks
        ell((sx * 0.074, -0.004, 1.664), (0.012, 0.022, 0.03), k=0.012)           # ears
    ell((0.0, 0.103, 1.619), (0.019, 0.01, 0.005), k=0.006)            # upper lip
    ell((0.0, 0.099, 1.609), (0.016, 0.01, 0.005), k=0.006)            # lower lip
    ell((0.0, -0.014, 1.716), (0.081, 0.099, 0.097), k=0.01, disp=_curls)          # hair
    ell((0.0, -0.05, 1.632), (0.07, 0.06, 0.05), k=0.03, disp=_curls)               # hair on the nape

    # --- right arm raised, hand shading the eyes (palm down, fingers across the brow)
    sh_r, el_r, wr_r = (0.2, 0.0, 1.462), (0.365, 0.17, 1.585), (0.125, 0.19, 1.695)
    ell((0.2, 0.004, 1.478), (0.062, 0.068, 0.076), k=0.035,
        R=SD.rot_from_axes((0.6, 0.6, 0.45)))                          # deltoid
    cone(sh_r, el_r, 0.054, 0.038, k=0.035)                            # upper arm
    ell((0.28, 0.105, 1.54), (0.044, 0.12, 0.042), k=0.025,
        R=SD.rot_from_axes((0.17, 0.17, 0.125)))                       # biceps
    ell((0.3, 0.07, 1.505), (0.04, 0.11, 0.04), k=0.025,
        R=SD.rot_from_axes((0.17, 0.17, 0.125)))                       # triceps
    cone(el_r, wr_r, 0.042, 0.027, k=0.025)                            # forearm
    ell((0.305, 0.176, 1.62), (0.038, 0.075, 0.034), k=0.025,
        R=SD.rot_from_axes((-0.235, 0.02, 0.11)))                      # forearm muscles
    ell((0.06, 0.188, 1.703), (0.054, 0.037, 0.0135), k=0.012,
        R=SD.rot_from_axes((0.0, 1.0, 0.0), up=(0.08, 0.0, 1.0)))       # hand, palm down
    cone((0.1, 0.2, 1.69), (0.083, 0.226, 1.7), 0.012, 0.009, k=0.01)  # thumb

    # --- left arm lowered, holding the cloak
    sh_l, el_l, wr_l = (-0.2, 0.0, 1.455), (-0.24, -0.03, 1.17), (-0.252, 0.09, 0.995)
    ell((-0.203, 0.0, 1.45), (0.062, 0.064, 0.078), k=0.035)            # deltoid
    cone(sh_l, el_l, 0.054, 0.039, k=0.035)
    ell((-0.222, 0.022, 1.33), (0.042, 0.042, 0.1), k=0.025)            # biceps
    cone(el_l, wr_l, 0.042, 0.028, k=0.025)
    ell((-0.252, 0.13, 0.955), (0.023, 0.046, 0.05), k=0.012)           # fist in the cloth

    # --- legs: right straight (weight), left relaxed, knee forward
    for sx, hip, knee, ank, toe in ((1, (0.085, 0.0, 0.94), (0.095, 0.012, 0.5), (0.095, -0.012, 0.078), (0.102, 0.19, 0.018)),
                                    (-1, (-0.085, 0.0, 0.92), (-0.092, 0.05, 0.51), (-0.112, -0.024, 0.088), (-0.158, 0.165, 0.018))):
        cone(hip, knee, 0.094, 0.054, k=0.06)
        mid = np.add(hip, knee) / 2
        ell((mid[0] + sx * 0.014, mid[1] + 0.032, mid[2] - 0.02), (0.06, 0.054, 0.16), k=0.035)  # quadriceps
        ell((mid[0] - sx * 0.036, mid[1] - 0.004, mid[2] + 0.06), (0.048, 0.054, 0.12), k=0.035)  # adductors
        ell((knee[0], knee[1] + 0.036, knee[2] + 0.005), (0.031, 0.021, 0.033), k=0.02)           # knee cap
        cone(knee, ank, 0.05, 0.032, k=0.03)
        ell((knee[0] + sx * 0.004, knee[1] - 0.042, knee[2] - 0.15), (0.05, 0.05, 0.11), k=0.035)  # calf
        ell((ank[0], ank[1] + 0.004, ank[2] - 0.008), (0.031, 0.032, 0.032), k=0.02)              # ankle
        fwd = np.subtract(toe, ank)
        fwd[2] = 0.0
        ell((ank[0] + fwd[0] * 0.42, ank[1] + fwd[1] * 0.42, 0.03), (0.046, 0.13, 0.03), k=0.025,
            R=SD.rot_from_axes(fwd))                                                             # foot
        ell((ank[0] + fwd[0] * 0.2, ank[1] + fwd[1] * 0.2, 0.05), (0.036, 0.07, 0.032), k=0.03,
            R=SD.rot_from_axes(fwd))                                                             # instep
        ell((ank[0] - fwd[0] * 0.1, ank[1] - fwd[1] * 0.1, 0.034), (0.034, 0.042, 0.034), k=0.02)  # heel
        ell((toe[0] - fwd[0] * 0.12, toe[1] - fwd[1] * 0.12, 0.018), (0.044, 0.035, 0.018), k=0.015,
            R=SD.rot_from_axes(fwd))                                                             # toes

    # --- chlamys: over the left shoulder, down the back of the arm, over the
    # forearm, then a heavy fall of pipe folds to the base (third support)
    ell((-0.168, -0.035, 1.475), (0.072, 0.078, 0.046), k=0.03)
    cone((-0.205, -0.075, 1.44), (-0.262, -0.04, 1.08), 0.05, 0.052, k=0.03,
         disp=_folds(-0.23, -0.055, 5, 0.006))
    cone((-0.262, -0.01, 1.03), (-0.272, 0.13, 1.0), 0.046, 0.042, k=0.03)                       # roll over the forearm
    ell((-0.295, 0.025, 0.5), (0.034, 0.042, 0.47), k=0.03)                                       # the sheet behind the folds
    top = np.array([-0.27, 0.05, 0.985])
    for i, (bx, by, r0, r1) in enumerate(((-0.335, -0.015, 0.02, 0.03), (-0.318, 0.04, 0.022, 0.032),
                                           (-0.288, 0.088, 0.02, 0.03), (-0.252, 0.112, 0.018, 0.027),
                                           (-0.31, -0.058, 0.018, 0.027), (-0.24, 0.058, 0.017, 0.025),
                                           (-0.345, 0.025, 0.016, 0.024))):
        tx = top + np.array([0.012 * (i - 2.5), 0.02 * math.sin(i * 1.7), -0.03 * (i % 3)])
        cone(tx, (bx, by, -0.035), r0, r1, k=0.008)                                               # pipe folds (ends in the base)
    ell((-0.29, 0.03, 0.006), (0.1, 0.1, 0.022), k=0.012, disp=_folds(-0.29, 0.03, 11, 0.007))  # hem pooled on the base
    return p


# ------------------------------------------------------------------ build
def _hash(*a):
    return int(hashlib.sha1(repr(a).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _key():
    src = open(os.path.abspath(__file__), 'rb').read() + open(SD.__file__, 'rb').read()
    return hashlib.sha1(src).hexdigest()[:12]


def build(force=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'helios_{_key()}.npz')
    if os.path.exists(path) and not force:
        d = np.load(path, allow_pickle=False)
        return {k: d[k] for k in d.files}
    out = _build()
    np.savez_compressed(path, **out)
    return out


def _build():
    from scipy.spatial import cKDTree
    h = VOXEL / S
    lo, hi = (-0.4, -0.17, -0.04), (0.45, 0.27, 1.83)
    vol, org = SD.sample(prims(), lo, hi, h)
    V, F = SD.surface(vol, org, h)
    V = SD.taubin(V, F, iters=4)
    V = V * S
    # plates in horizontal courses: each course is cut into plates by Voronoi
    # cells of seeds spaced ~PLATE along it, so the horizontal joints run level
    # (as the work proceeded course by course) and the vertical ones stagger
    Fc = V[F].mean(axis=1)
    fb = np.floor(Fc[:, 2] / COURSE).astype(int)
    vb = np.floor(V[:, 2] / COURSE).astype(int)
    face_plate = np.zeros(len(F), np.int64)
    seam = np.full(len(V), 9.0)
    tone = np.zeros(len(V))
    seeds, plate_z = [], []
    for b in range(fb.min(), fb.max() + 1):
        fi = np.where(fb == b)[0]
        if len(fi) == 0:
            continue
        cand = fi[:: max(1, len(fi) // 4000)]
        pick = cand[SD.poisson_on_points(Fc[cand], PLATE, seed=100 + b, metric=(1.0, 1.0, 0.25))]
        sd = Fc[pick]
        tree = cKDTree(sd)
        _, j = tree.query(Fc[fi])
        # build order inside the course: round the figure from the seaward side
        ang = np.mod(np.arctan2(sd[:, 0], sd[:, 1] + 1e-9) + 2 * math.pi, 2 * math.pi)
        rank = np.argsort(np.argsort(ang))
        base = len(seeds)
        face_plate[fi] = base + j
        seeds += list(sd)
        plate_z += list(b * COURSE + COURSE * (rank + 0.5) / len(sd))
        vi = np.where(vb == b)[0]
        if len(sd) > 1:
            dv, iv = tree.query(V[vi], k=2)
            sv = 0.5 * (dv[:, 1] - dv[:, 0])
            tv = iv[:, 0]
        else:
            sv = np.full(len(vi), 9.0)
            tv = np.zeros(len(vi), int)
        zl = V[vi, 2] - b * COURSE
        seam[vi] = np.minimum(sv, np.minimum(zl, COURSE - zl))
        tone[vi] = [_hash('tone', base + int(k)) for k in tv]
    seeds = np.array(seeds)
    plate_z = np.array(plate_z)
    # armature and stone fill from the field itself
    bars = _armature(vol, org, h)
    fill = _fill(vol, org, h)
    crown_V, crown_F, crown_z = _crown()
    return dict(V=V.astype(np.float32), F=F.astype(np.int32), face_plate=face_plate.astype(np.int32),
                seam=seam.astype(np.float32), tone=tone.astype(np.float32), seeds=seeds.astype(np.float32),
                plate_z=plate_z.astype(np.float32), bars=bars.astype(np.float32), fill=fill.astype(np.float32),
                crown_V=crown_V.astype(np.float32), crown_F=crown_F.astype(np.int32),
                crown_z=crown_z.astype(np.float32))


RING_DZ = 1.2         # armature ring spacing (m)
INSET = 0.28          # rings sit this far inside the bronze (m)


def _armature(vol, org, h):
    """Iron frame: horizontal rings following the skin (inset), vertical bars
    between them every ~1.1 m, and a central bar in every limb.  Rows of
    (x0, y0, z0, x1, y1, z1, build_z)."""
    from scipy.spatial import cKDTree
    nz = vol.shape[2]
    levels = np.arange(0.6, HEIGHT - 0.4, RING_DZ)
    rings = []                         # per level: list of (N, 2) polylines (statue scale)
    for z in levels:
        k = int(round((z / S - org[2]) / h))
        if not 0 <= k < nz:
            rings.append([])
            continue
        cs = [c * S for c in SD.contours(vol, org, h, k, -INSET / S)]
        rings.append([c for c in cs if len(c) > 6 and np.sum(np.linalg.norm(np.diff(c, axis=0), axis=1)) > 1.6])
    segs = []
    step = 1.1
    for li, z in enumerate(levels):
        pts_here = []
        for c in rings[li]:
            L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
            n = max(int(L[-1] / 0.55), 3)
            s = np.linspace(0, L[-1], n + 1)
            poly = np.stack([np.interp(s, L, c[:, 0]), np.interp(s, L, c[:, 1])], 1)
            for a, b in zip(poly[:-1], poly[1:]):
                segs.append((a[0], a[1], z, b[0], b[1], z, z))
            m = max(int(L[-1] / step), 3)
            s = np.linspace(0, L[-1], m, endpoint=False)
            pts_here += list(np.stack([np.interp(s, L, c[:, 0]), np.interp(s, L, c[:, 1])], 1))
        if li + 1 < len(levels) and pts_here and rings[li + 1]:
            up = np.concatenate(rings[li + 1])
            tr = cKDTree(up)
            d, j = tr.query(np.array(pts_here))
            for p, dj, jj in zip(pts_here, d, j):
                if dj < 0.9:
                    q = up[jj]
                    segs.append((p[0], p[1], z, q[0], q[1], levels[li + 1], z))
    return np.array(segs, float)


def _fill(vol, org, h, course=0.9, grid=0.95, z_top=16.5, inner=0.55):
    """Stone blocks inside the legs and the drapery (Philon: weighted with stone)."""
    out = []
    for z in np.arange(0.2, z_top, course):
        k = int(round(((z + course / 2) / S - org[2]) / h))
        sl = vol[:, :, k]
        off = 0.5 * grid * (int(z / course) % 2)
        xs = np.arange(-7.0 + off, 8.0, grid)
        ys = np.arange(-3.5 + off, 4.5, grid)
        for x in xs:
            for y in ys:
                i = int(round((x / S - org[0]) / h))
                j = int(round((y / S - org[1]) / h))
                if 0 <= i < sl.shape[0] and 0 <= j < sl.shape[1] and sl[i, j] * S < -inner:
                    out.append((x, y, z, grid * 0.96, grid * 0.96, course * 0.97, z))
    return np.array(out, float)


CROWN_Z = 1.742                       # fillet height on the head (human scale)
CROWN_RAYS = 11


def _crown():
    """Radiate crown: a fillet round the head and 11 rays (flat, tapering)."""
    V, F, Z = [], [], []

    def add_prism(pts_bottom, pts_top, bz):
        b = len(V)
        n = len(pts_bottom)
        V.extend(pts_bottom)
        V.extend(pts_top)
        for i in range(n):
            j = (i + 1) % n
            F.append((b + i, b + j, b + n + j, b + n + i))
            Z.append(bz)
        F.append(tuple(b + n - 1 - i for i in range(n)) if n == 4 else (b, b + 2, b + 1, b + 1))
        Z.append(bz)
        F.append(tuple(b + n + i for i in range(n)) if n == 4 else (b + n, b + n + 1, b + n + 2, b + n + 2))
        Z.append(bz)
    ax, ay, cy = 0.081, 0.099, -0.012
    n = 48
    for i in range(n):                                   # fillet: a band round the hair
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        pts = []
        for a in (a0, a1):
            for r in (1.0, 1.06):
                pts.append((ax * r * math.cos(a), cy + ay * r * math.sin(a)))
        z0, z1 = CROWN_Z - 0.008, CROWN_Z + 0.008
        bot = [(pts[0][0], pts[0][1], z0), (pts[2][0], pts[2][1], z0), (pts[3][0], pts[3][1], z0), (pts[1][0], pts[1][1], z0)]
        top = [(x, y, z1) for x, y, _ in bot]
        add_prism(bot, top, CROWN_Z)
    for i in range(CROWN_RAYS):                          # rays, the front one straight ahead
        a = math.pi / 2 + 2 * math.pi * i / CROWN_RAYS
        c, s = math.cos(a), math.sin(a)
        base = np.array([ax * 1.03 * c, cy + ay * 1.03 * s, CROWN_Z])
        out_dir = np.array([c * 0.8, s * 0.8, 0.6])
        out_dir /= np.linalg.norm(out_dir)
        tip = base + out_dir * 0.105
        side = np.array([-s, c, 0.0])
        w0, w1, t = 0.016, 0.002, 0.004
        up = np.cross(side, out_dir)
        bot = [base - side * w0 - up * t, base + side * w0 - up * t, tip + side * w1 - up * t * 0.5, tip - side * w1 - up * t * 0.5]
        top = [p + up * 2 * t for p in bot]
        add_prism([tuple(p) for p in bot], [tuple(p) for p in top], CROWN_Z + 0.05)
    V = np.array(V) * S
    return V, np.array(F), np.array(Z) * S


if __name__ == '__main__':
    import time
    t0 = time.time()
    d = build(force=True)
    print({k: v.shape for k, v in d.items()}, f'{time.time() - t0:.1f}s')
