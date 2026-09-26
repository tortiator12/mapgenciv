"""Signed-distance sculpting: smooth-blended primitives -> marching cubes -> mesh.

A figure is written as a list of primitives (round cones for limbs, ellipsoids
for muscle masses, ...), each blended into the body with a smooth minimum or
carved out with a smooth maximum.  sample() evaluates the field on a regular
grid slab by slab (each primitive only inside its padded bounding box), and
surface() extracts the zero level set.  No bpy here: the result is plain
arrays that the scene modules cache and turn into meshes.
"""
import numpy as np


def smin(a, b, k):
    """Polynomial smooth minimum (blend radius k)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def rot_from_axes(fwd, up=(0.0, 0.0, 1.0)):
    """Rows = local x, y, z axes with local y along fwd."""
    y = np.asarray(fwd, float)
    y = y / np.linalg.norm(y)
    x = np.cross(y, up)
    if np.linalg.norm(x) < 1e-6:
        x = np.cross(y, (1.0, 0.0, 0.0))
    x /= np.linalg.norm(x)
    z = np.cross(x, y)
    return np.stack([x, y, z])


class Prim:
    """One primitive: kind 'cone' (round cone a->b, radii ra->rb), 'ell'
    (ellipsoid centre c, radii r, optional rotation rows R), 'box' (rounded
    box).  op 'add' blends with k, 'sub' carves with k.  disp(P, d) may
    modify the distance (folds, curls)."""

    def __init__(self, kind, op='add', k=0.0, disp=None, tag=0, **g):
        self.kind, self.op, self.k, self.disp, self.tag = kind, op, k, disp, tag
        self.g = {n: (np.asarray(v, float) if not np.isscalar(v) else float(v)) for n, v in g.items()}
        self.lo, self.hi = self._bounds()

    def _bounds(self):
        g = self.g
        pad = self.k + 0.02
        if self.kind == 'cone':
            r = max(g['ra'], g['rb']) + pad
            lo = np.minimum(g['a'], g['b']) - r
            hi = np.maximum(g['a'], g['b']) + r
        elif self.kind == 'ell':
            r = np.max(g['r']) + pad
            lo, hi = g['c'] - r, g['c'] + r
        else:
            r = np.linalg.norm(g['h']) + g.get('rr', 0.0) + pad
            lo, hi = g['c'] - r, g['c'] + r
        return lo, hi

    def dist(self, P):
        g = self.g
        if self.kind == 'cone':
            d = sd_round_cone(P, g['a'], g['b'], g['ra'], g['rb'])
        elif self.kind == 'ell':
            q = P - g['c']
            if 'R' in g:
                q = q @ g['R'].T
            d = sd_ellipsoid(q, g['r'])
        else:
            q = P - g['c']
            if 'R' in g:
                q = q @ g['R'].T
            rr = g.get('rr', 0.0)
            qq = np.abs(q) - (g['h'] - rr)
            d = np.linalg.norm(np.maximum(qq, 0.0), axis=1) + np.minimum(np.max(qq, axis=1), 0.0) - rr
        if self.disp is not None:
            d = self.disp(P, d)
        return d


def sd_round_cone(P, a, b, ra, rb):
    """Exact distance to a round cone (Inigo Quilez)."""
    ba = b - a
    l2 = float(ba @ ba)
    rr = ra - rb
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = P - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - y[:, None] * ba
    x2 = np.einsum('ij,ij->i', xv, xv)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d_b = np.sqrt(x2 + z2) * il2 - rb
    d_a = np.sqrt(x2 + y2) * il2 - ra
    d_m = (np.sqrt(np.maximum(x2 * a2 * il2, 0.0)) + y * rr) * il2 - ra
    return np.where(np.sign(z) * a2 * z2 > k, d_b, np.where(np.sign(y) * a2 * y2 < k, d_a, d_m))


def sd_ellipsoid(q, r):
    """Bound-correct ellipsoid approximation (Inigo Quilez)."""
    k0 = np.linalg.norm(q / r, axis=1)
    k1 = np.linalg.norm(q / (r * r), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sample(prims, lo, hi, h, slab=24, far=1.0):
    """Field on the grid lo + h*(i, j, k); returns (vol[i, j, k], origin)."""
    lo = np.asarray(lo, float)
    n = np.ceil((np.asarray(hi, float) - lo) / h).astype(int) + 1
    xs = lo[0] + h * np.arange(n[0])
    ys = lo[1] + h * np.arange(n[1])
    zs = lo[2] + h * np.arange(n[2])
    vol = np.full(tuple(n), far, np.float32)
    for k0 in range(0, n[2], slab):
        k1 = min(k0 + slab, n[2])
        z0, z1 = zs[k0], zs[k1 - 1]
        X, Y, Z = np.meshgrid(xs, ys, zs[k0:k1], indexing='ij')
        P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
        d = np.full(len(P), far)
        for pr in prims:
            if pr.hi[2] < z0 or pr.lo[2] > z1:
                continue
            m = np.all((P >= pr.lo) & (P <= pr.hi), axis=1)
            if not m.any():
                continue
            idx = np.where(m)[0]
            dp = pr.dist(P[idx])
            if pr.op == 'add':
                d[idx] = smin(d[idx], dp, pr.k)
            elif pr.op == 'sub':
                d[idx] = smax(d[idx], -dp, pr.k)
            else:                       # 'int'
                d[idx] = smax(d[idx], dp, pr.k)
        vol[:, :, k0:k1] = d.reshape(len(xs), len(ys), k1 - k0)
    return vol, lo


def surface(vol, origin, h, level=0.0):
    """Marching cubes -> (V, F) with outward winding."""
    from skimage.measure import marching_cubes
    V, F, N, _ = marching_cubes(vol, level=level, spacing=(h, h, h), gradient_direction='ascent',
                                allow_degenerate=False)
    V = V + origin
    # outward = direction of increasing distance: flip faces whose normal points inward
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = N[F].mean(axis=1)
    flip = np.einsum('ij,ij->i', fn, vn) < 0
    F[flip] = F[flip][:, ::-1]
    return V, F


def taubin(V, F, iters=6, lam=0.5, mu=-0.53):
    """Shrink-free smoothing of the voxel ripples marching cubes leaves."""
    import scipy.sparse as sp
    n = len(V)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(axis=1)).ravel()
    deg[deg == 0] = 1
    W = sp.diags(1.0 / deg) @ A
    V = V.copy()
    for _ in range(iters):
        V = V + lam * (W @ V - V)
        V = V + mu * (W @ V - V)
    return V


def contours(vol, origin, h, k, level):
    """Closed iso-lines of the horizontal slice k (world xy polylines)."""
    from skimage.measure import find_contours
    out = []
    for c in find_contours(vol[:, :, k], level):
        out.append(origin[:2] + c * h)
    return out


def poisson_on_points(P, r, seed=0, metric=(1.0, 1.0, 1.0)):
    """Greedy Poisson-disk subset of points P (dart throwing on a hash grid)."""
    rng = np.random.default_rng(seed)
    Q = P * np.asarray(metric)
    order = rng.permutation(len(Q))
    cell = r / np.sqrt(3.0)
    grid = {}
    keep = []
    for i in order:
        c = tuple((Q[i] // cell).astype(int))
        ok = True
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for dz in (-2, -1, 0, 1, 2):
                    j = grid.get((c[0] + dx, c[1] + dy, c[2] + dz))
                    if j is not None and np.sum((Q[j] - Q[i]) ** 2) < r * r:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            grid[c] = i
            keep.append(i)
    return np.array(sorted(keep))
