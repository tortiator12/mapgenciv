"""Pure-numpy geometry generators for the lighthouse film (no bpy).

Almost everything that gets *built* in the film (ashlar blocks, scaffolding
poles, planks, ropes, props) is a hexahedron: 8 corners ordered
[b0, b1, b2, b3, t0, t1, t2, t3] (bottom quad, then the matching top quad).
HexBatch collects them together with the time they appear / disappear, so
the renderer can assemble exactly the elements that exist at any instant.
"""
import math

import numpy as np

HEX_FACES = np.array([[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
                      [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]], dtype=np.int64)

INF = 1e9


class HexBatch:
    """A bag of timed hexahedra sharing one mesh object in Blender."""

    def __init__(self, name):
        self.name = name
        self._c, self._on, self._off, self._mat, self._tone = [], [], [], [], []

    def add(self, corners, t_on=-INF, t_off=INF, mat=0, tone=None):
        self._c.append(np.asarray(corners, dtype=np.float64).reshape(8, 3))
        self._on.append(t_on)
        self._off.append(t_off)
        self._mat.append(mat)
        self._tone.append(np.random.random() if tone is None else tone)

    def extend(self, other):
        self._c += other._c
        self._on += other._on
        self._off += other._off
        self._mat += other._mat
        self._tone += other._tone

    def __len__(self):
        return len(self._c)

    def finalize(self):
        """Freeze into arrays; fixes face winding and computes per-corner UVs
        (in metres, per face) plus the face size used for mortar joints."""
        C = np.stack(self._c) if self._c else np.zeros((0, 8, 3))
        n = len(C)
        self.corners = C
        self.t_on = np.asarray(self._on, float)
        self.t_off = np.asarray(self._off, float)
        self.mat = np.asarray(self._mat, np.int32)
        self.tone = np.asarray(self._tone, np.float32)
        faces = np.broadcast_to(HEX_FACES, (n, 6, 4)).copy()
        if n:
            centre = C.mean(axis=1)                              # (n,3)
            P = C[np.arange(n)[:, None, None], faces]            # (n,6,4,3)
            fc = P.mean(axis=2)
            nrm = np.cross(P[:, :, 2] - P[:, :, 0], P[:, :, 3] - P[:, :, 1])
            flip = (np.einsum('nfk,nfk->nf', nrm, fc - centre[:, None, :]) < 0)
            faces[flip] = faces[flip][:, ::-1]
            P = C[np.arange(n)[:, None, None], faces]
            e_u = P[:, :, 1] - P[:, :, 0]
            e_v = P[:, :, 3] - P[:, :, 0]
            w = np.linalg.norm(e_u, axis=-1)
            h = np.linalg.norm(e_v, axis=-1)
            uv = np.zeros((n, 6, 4, 2), np.float32)
            uv[:, :, 1, 0] = w
            uv[:, :, 2, 0] = w
            uv[:, :, 2, 1] = h
            uv[:, :, 3, 1] = h
            self.uv = uv
            self.fsize = np.stack([w, h], axis=-1).astype(np.float32)
        else:
            self.uv = np.zeros((0, 6, 4, 2), np.float32)
            self.fsize = np.zeros((0, 6, 2), np.float32)
        self.faces = faces
        # keep things sorted by appearance time (cheap prefix selection)
        order = np.argsort(self.t_on, kind='stable')
        for k in ('corners', 't_on', 't_off', 'mat', 'tone', 'uv', 'fsize', 'faces'):
            setattr(self, k, getattr(self, k)[order])
        return self

    def select(self, t):
        return (self.t_on <= t) & (t < self.t_off)


# ---------------------------------------------------------------- polygons
def square_poly(a):
    return np.array([[-a, -a], [a, -a], [a, a], [-a, a]], float)


def oct_poly(ap):
    """Regular octagon with apothem ap, flats facing the axes and diagonals."""
    R = ap / math.cos(math.pi / 8)
    ang = -3 * math.pi / 8 + np.arange(8) * math.pi / 4
    return np.stack([R * np.cos(ang), R * np.sin(ang)], axis=1)


def circle_poly(r, n=20):
    ang = -math.pi / 2 + np.arange(n) * 2 * math.pi / n
    return np.stack([r * np.cos(ang), r * np.sin(ang)], axis=1)


def _hexa(b, t, zb, zt):
    """corners from 4 bottom (x,y) and 4 top (x,y) points at heights zb, zt."""
    out = np.zeros((8, 3))
    out[:4, :2] = b
    out[:4, 2] = zb
    out[4:, :2] = t
    out[4:, 2] = zt
    return out


def ring_course(poly_fn, a0, a1, thick, z0, z1, block_len, course, openings=None,
                min_piece=0.35):
    """One course of ashlar blocks for a (tapered) polygonal ring wall.

    poly_fn(a) -> CCW polygon for size parameter a (half-width / apothem / radius).
    a0, a1: outer size at the bottom / top of the course.
    openings: dict side_index -> list of (u0, u1) intervals (0..1 along the side)
              that are left open in this course (windows, doors).
    Returns a list of (corners(8,3), order) where order in [0,1) runs around the ring.
    """
    Po0, Po1 = poly_fn(a0), poly_fn(a1)
    Pi0, Pi1 = poly_fn(a0 - thick), poly_fn(a1 - thick)
    n = len(Po0)
    sides = [np.linalg.norm(Po0[(i + 1) % n] - Po0[i]) for i in range(n)]
    perim = sum(sides)
    out = []
    acc = 0.0
    for i in range(n):
        j = (i + 1) % n
        L = sides[i]
        nb = max(1, int(round(L / block_len)))
        if course % 2 and nb >= 2:
            cuts = [0.0] + [(k + 0.5) / nb for k in range(nb)] + [1.0]
        else:
            cuts = [k / nb for k in range(nb + 1)]
        holes = (openings or {}).get(i, [])
        if holes:
            for (h0, h1) in holes:
                cuts += [h0, h1]
            cuts = sorted(set(round(c, 6) for c in cuts))
            # drop regular cuts that would leave slivers next to an opening edge
            edges = {round(h, 6) for hh in holes for h in hh} | {0.0, 1.0}
            keep = []
            for c in cuts:
                if c in edges or all(abs(c - e) * L > min_piece for e in edges):
                    keep.append(c)
            cuts = keep
        for u0, u1 in zip(cuts[:-1], cuts[1:]):
            if (u1 - u0) * L < 1e-3:
                continue
            um = 0.5 * (u0 + u1)
            if any(h0 <= um <= h1 for (h0, h1) in holes):
                continue
            b = np.array([Po0[i] + (Po0[j] - Po0[i]) * u0, Po0[i] + (Po0[j] - Po0[i]) * u1,
                          Pi0[i] + (Pi0[j] - Pi0[i]) * u1, Pi0[i] + (Pi0[j] - Pi0[i]) * u0])
            t = np.array([Po1[i] + (Po1[j] - Po1[i]) * u0, Po1[i] + (Po1[j] - Po1[i]) * u1,
                          Pi1[i] + (Pi1[j] - Pi1[i]) * u1, Pi1[i] + (Pi1[j] - Pi1[i]) * u0])
            order = (acc + L * um) / perim
            out.append((_hexa(b, t, z0, z1), order))
        acc += L
    return out


def slab_blocks(x0, x1, y0, y1, z0, z1, bx, by, course=0, jitter=0.0, rng=None):
    """Rectangular area paved with staggered blocks (rows along x)."""
    out = []
    ny = max(1, int(round((y1 - y0) / by)))
    ys = np.linspace(y0, y1, ny + 1)
    for r in range(ny):
        L = x1 - x0
        nb = max(1, int(round(L / bx)))
        off = ((r + course) % 2) * 0.5
        cuts = [0.0] + [min(1.0, (k + off) / nb) for k in range(1, nb + (1 if off else 0))] + [1.0]
        cuts = sorted(set(cuts))
        for u0, u1 in zip(cuts[:-1], cuts[1:]):
            if (u1 - u0) * L < 0.2:
                continue
            xa, xb = x0 + L * u0, x0 + L * u1
            zt = z1 + (rng.uniform(-jitter, jitter) if rng is not None and jitter else 0.0)
            b = np.array([[xa, ys[r]], [xb, ys[r]], [xb, ys[r + 1]], [xa, ys[r + 1]]])
            out.append(_hexa(b, b, z0, zt))
    return out


def quad_slab(p, z0, z1):
    """Hexahedron from a 4-point (x,y) CCW footprint with flat bottom/top."""
    p = np.asarray(p, float)
    return _hexa(p, p, z0, z1)


def beam(p0, p1, w, h=None, up=(0, 0, 1)):
    """Rectangular timber / rope between two 3D points."""
    h = w if h is None else h
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    d = p1 - p0
    L = np.linalg.norm(d)
    d = d / max(L, 1e-9)
    u = np.asarray(up, float)
    if abs(np.dot(d, u)) > 0.95:
        u = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    s = np.cross(d, u)
    s /= np.linalg.norm(s)
    v = np.cross(s, d)
    hw, hh = 0.5 * w, 0.5 * h
    b = [p0 - s * hw - v * hh, p1 - s * hw - v * hh, p1 + s * hw - v * hh, p0 + s * hw - v * hh]
    t = [q + v * h for q in b]
    return np.array(b + t)


def box(cx, cy, cz, sx, sy, sz, rot=0.0):
    """Axis box centred at (cx,cy) with bottom at cz, rotated about Z."""
    c, s = math.cos(rot), math.sin(rot)
    pts = np.array([[-sx, -sy], [sx, -sy], [sx, sy], [-sx, sy]]) * 0.5
    pts = pts @ np.array([[c, s], [-s, c]]) + [cx, cy]
    return _hexa(pts, pts, cz, cz + sz)


def tent(cx, cy, cz, length, width, height, rot=0.0):
    """Ridge tent as a degenerate hexahedron (top quad collapsed to the ridge)."""
    c, s = math.cos(rot), math.sin(rot)
    R = np.array([[c, s], [-s, c]])
    b = np.array([[-length, -width], [length, -width], [length, width], [-length, width]]) * 0.5 @ R + [cx, cy]
    t = np.array([[-length, -0.02], [length, -0.02], [length, 0.02], [-length, 0.02]]) * 0.5 @ R + [cx, cy]
    return _hexa(b, t, cz, cz + height)


# ---------------------------------------------------------------- noise
def _hash2(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def value_noise(x, y, seed=0):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ix = np.floor(x).astype(np.int64)
    iy = np.floor(y).astype(np.int64)
    fx = x - ix
    fy = y - iy
    ux = fx * fx * (3 - 2 * fx)
    uy = fy * fy * (3 - 2 * fy)
    a = _hash2(ix, iy, seed)
    b = _hash2(ix + 1, iy, seed)
    c = _hash2(ix, iy + 1, seed)
    d = _hash2(ix + 1, iy + 1, seed)
    return (a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy) * 2 - 1


def fbm(x, y, octaves=5, seed=0, lac=2.03, gain=0.5):
    tot = np.zeros_like(np.asarray(x, float))
    amp, f = 1.0, 1.0
    for o in range(octaves):
        tot = tot + amp * value_noise(x * f, y * f, seed + o * 17)
        amp *= gain
        f *= lac
    return tot


def grid_mesh(x0, x1, y0, y1, nx, ny, hfun):
    """Regular heightfield grid -> (verts (N,3), quads (M,4))."""
    xs = np.linspace(x0, x1, nx)
    ys = np.linspace(y0, y1, ny)
    X, Y = np.meshgrid(xs, ys)
    Z = hfun(X, Y)
    V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    idx = np.arange(nx * ny).reshape(ny, nx)
    q = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(),
                  idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], axis=1)
    return V, q


def polar_mesh(r0, r_fine, dr_fine, r_max, growth, nseg):
    """Radial LOD grid for the sea: fine rings out to r_fine, then growing."""
    radii = [r0]
    r = r0
    while r < r_fine:
        r += dr_fine
        radii.append(r)
    step = dr_fine
    while r < r_max:
        step *= growth
        r += step
        radii.append(r)
    radii = np.array(radii)
    ang = np.linspace(0, 2 * np.pi, nseg, endpoint=False)
    R, A = np.meshgrid(radii, ang, indexing='ij')
    V = np.stack([(R * np.cos(A)).ravel(), (R * np.sin(A)).ravel(), np.zeros(R.size)], axis=1)
    nr = len(radii)
    idx = np.arange(nr * nseg).reshape(nr, nseg)
    nxt = np.roll(idx, -1, axis=1)
    q = np.stack([idx[:-1].ravel(), nxt[:-1].ravel(), nxt[1:].ravel(), idx[1:].ravel()], axis=1)
    # centre cap (hidden under the island anyway)
    return V, q
