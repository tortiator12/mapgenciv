"""Copernicus' instruments (De revolutionibus, 1543), as he describes them.

  triquetrum  Ptolemy's parallactic rulers: a vertical post; the sighting rule
              hinged at its top, the eye end C resting on the lower rule that is
              hinged at the post's foot.  Post AB and rule AC are equal (2.2 m),
              so the length BC read on the lower rule is the chord of the
              zenith distance z: BC = 2 AB sin(z / 2).
  quadrant    a wooden quarter circle standing in the meridian, a brass limb,
              a peg at the centre whose shadow gives the sun's altitude
  armillary   brass rings on a turned wooden stand: meridian and horizon
              fixed, the pole axis at the latitude, equator, ecliptic (23.5 deg)
              and the colures turning with it

All in local frames (instrument foot at the origin); pose_* sets the moving
parts.  No text; plain meshes with wood and brass.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import geometry as G
import scene as SC

TQ_AB = 2.2          # post, hinge to hinge
TQ_A = 2.45          # the upper hinge above the foot
TQ_B = TQ_A - TQ_AB  # the lower hinge


def mat_brass():
    m, nb, out = SC.new_material('Brass')
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    n = nb.noise(pos, 6.0, 3.0, 0.6).outputs['Fac']
    col = nb.mix(n, (0.72, 0.52, 0.22, 1), (0.86, 0.66, 0.32, 1))
    b = SC.principled(nb, col, rough=nb.math('ADD', 0.2, nb.math('MULTIPLY', n, 0.15)), metal=1.0, spec=0.5)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def _obj(name, batch, mats, coll):
    batch.finalize()
    me = SC.hex_mesh(name, batch, np.ones(len(batch.t_on), bool), mats)
    o = SC.link(bpy.data.objects.new(name, me), coll)
    o.pass_index = SC.PASS['props']
    return o


def build_triquetrum(name, m_wood, m_brass, coll=None):
    """Returns dict(root, post, sight, lower): sight pivots at A, lower at B (local x = towards the target)."""
    coll = coll or bpy.context.scene.collection
    pb = G.HexBatch(name + 'post')
    pb.add(G.beam([0, 0, 0.0], [0, 0, TQ_A + 0.15], 0.13), mat=0)
    for a in (0.0, math.pi / 2):                                   # cross feet with braces
        d = np.array([math.cos(a), math.sin(a), 0.0])
        pb.add(G.beam(-0.7 * d, 0.7 * d, 0.12, 0.1), mat=0)
        for s in (-1, 1):
            pb.add(G.beam(s * 0.55 * d + [0, 0, 0.05], [0, 0, 0.75], 0.06), mat=0)
    pb.add(G.box(0, 0, TQ_A - 0.08, 0.22, 0.22, 0.16), mat=1)       # brass hinge plates
    pb.add(G.box(0, 0, TQ_B - 0.08, 0.22, 0.22, 0.16), mat=1)
    post = _obj(name + 'Post', pb, [m_wood, m_brass], coll)
    sb = G.HexBatch(name + 'sight')                               # sighting rule, along -x from A (eye end at C)
    sb.add(G.beam([0.15, 0.1, 0], [-TQ_AB - 0.2, 0.1, 0], 0.08, 0.1), mat=0)
    for x in (-0.25, -TQ_AB + 0.15):                                 # the two sights
        sb.add(G.box(x, 0.1, 0.05, 0.03, 0.12, 0.16), mat=1)
    sight = _obj(name + 'Sight', sb, [m_wood, m_brass], coll)
    lb = G.HexBatch(name + 'lower')                               # the graduated lower rule, along -x from B
    lb.add(G.beam([0.1, -0.1, 0], [-3.3, -0.1, 0], 0.07, 0.09), mat=0)
    for k in range(15):                                              # brass scale marks
        x = -0.4 - 0.2 * k
        lb.add(G.box(x, -0.1, 0.045, 0.015 if k % 5 else 0.03, 0.07, 0.012), mat=1)
    lower = _obj(name + 'Lower', lb, [m_wood, m_brass], coll)
    root = SC.link(bpy.data.objects.new(name, None), coll)
    for o in (post, sight, lower):
        o.parent = root
    return dict(root=root, post=post, sight=sight, lower=lower)


def pose_triquetrum(tq, M, zenith, visible=True):
    """M: world matrix of the foot (local +x towards the target's azimuth); zenith distance (rad)."""
    tq['root'].matrix_world = M
    z = min(max(zenith, math.radians(3)), math.radians(89))
    A = Vector((0, 0, TQ_A))
    B = Vector((0, 0, TQ_B))
    C = A - TQ_AB * Vector((math.sin(z), 0.0, math.cos(z)))           # the eye end, below and behind A
    # the sight rule lies along C -> A (pointing at the target); its local -x runs A -> C
    ang_s = math.atan2(-(C.z - A.z), -(C.x - A.x))
    tq['sight'].matrix_world = M @ Matrix.Translation(A) @ Matrix.Rotation(-ang_s, 4, 'Y')
    ang_l = math.atan2(-(C.z - B.z), -(C.x - B.x))
    tq['lower'].matrix_world = M @ Matrix.Translation(B) @ Matrix.Rotation(-ang_l, 4, 'Y')
    tq['post'].matrix_world = M
    for o in (tq['post'], tq['sight'], tq['lower']):
        o.hide_render = not visible
    return M @ C


def build_quadrant(name, m_wood, m_brass, coll=None):
    """A quarter circle of 1.6 m on a trestle, its limb brass, in the local xz-plane."""
    coll = coll or bpy.context.scene.collection
    qb = G.HexBatch(name)
    R = 1.6
    z0 = 0.55
    qb.add(G.beam([0, 0, z0], [R, 0, z0], 0.1), mat=0)
    qb.add(G.beam([0, 0, z0], [0, 0, z0 + R], 0.1), mat=0)
    qb.add(G.beam([0, 0, z0], [R * 0.7071, 0, z0 + R * 0.7071], 0.07), mat=0)
    n = 18
    for k in range(n):
        a0, a1 = math.pi / 2 * k / n, math.pi / 2 * (k + 1) / n
        p0 = [R * math.cos(a0), 0, z0 + R * math.sin(a0)]
        p1 = [R * math.cos(a1), 0, z0 + R * math.sin(a1)]
        qb.add(G.beam(p0, p1, 0.1, 0.12, up=(0, 1, 0)), mat=0)
        q0 = [(R + 0.06) * math.cos(a0), 0.0, z0 + (R + 0.06) * math.sin(a0)]
        q1 = [(R + 0.06) * math.cos(a1), 0.0, z0 + (R + 0.06) * math.sin(a1)]
        qb.add(G.beam(q0, q1, 0.03, 0.13, up=(0, 1, 0)), mat=1)
    for s in (-1, 1):                                                # the trestle
        qb.add(G.beam([0.8, s * 0.5, 0], [0.8, 0, z0], 0.08), mat=0)
        qb.add(G.beam([-0.1, s * 0.5, 0], [0.0, 0, z0], 0.08), mat=0)
    qb.add(G.beam([0.0, 0.0, z0 + 0.02], [0.0, 0.12, z0 + 0.02], 0.03), mat=1)   # the peg
    return _obj(name, qb, [m_wood, m_brass], coll)


def _ring(R, r, n=48, m=6):
    V, F = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        c = np.array([R * math.cos(a), R * math.sin(a), 0.0])
        u = np.array([math.cos(a), math.sin(a), 0.0])
        for j in range(m):
            b = 2 * math.pi * j / m
            V.append(c + r * (math.cos(b) * u + math.sin(b) * np.array([0, 0, 1.0])))
    for i in range(n):
        for j in range(m):
            i2, j2 = (i + 1) % n, (j + 1) % m
            F.append([i * m + j, i2 * m + j, i2 * m + j2, i * m + j2])
    return np.array(V), np.array(F)


def build_armillary(name, m_wood, m_brass, latitude, coll=None):
    """Brass rings (R = 0.55 m) on a stand.  Returns dict(root, fixed, moving)."""
    coll = coll or bpy.context.scene.collection
    R = 0.55
    zc = 1.35
    parts_f, parts_m = [], []

    def ring(Rr, rr, M, into):
        V, F = _ring(Rr, rr)
        A = np.array(M)
        into.append((V @ A[:3, :3].T + A[:3, 3], F))
    ring(R * 1.08, 0.025, Matrix.Translation((0, 0, zc)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'), parts_f)   # meridian (N-S plane)
    ring(R * 1.16, 0.02, Matrix.Translation((0, 0, zc)), parts_f)                                       # horizon
    tilt = Matrix.Translation((0, 0, zc)) @ Matrix.Rotation(-(math.pi / 2 - latitude), 4, 'X')            # equatorial frame
    ring(R, 0.02, tilt, parts_m)                                                                         # equator
    ring(R * 0.97, 0.018, tilt @ Matrix.Rotation(math.radians(23.44), 4, 'X'), parts_m)                  # ecliptic
    ring(R * 0.94, 0.016, tilt @ Matrix.Rotation(math.pi / 2, 4, 'Y'), parts_m)                          # colures
    ring(R * 0.94, 0.016, tilt @ Matrix.Rotation(math.pi / 2, 4, 'Y') @ Matrix.Rotation(math.pi / 2, 4, 'X'), parts_m)

    def merge(parts):
        Vs, Fs, n = [], [], 0
        for V, F in parts:
            Vs.append(V)
            Fs.append(F + n)
            n += len(V)
        return np.concatenate(Vs), np.concatenate(Fs)
    V, F = merge(parts_f)
    fixed = SC.link(bpy.data.objects.new(name + 'Fixed', SC.mesh_from_arrays(name + 'Fixed', V, F, mats=[m_brass], smooth=True)), coll)
    V, F = merge(parts_m)
    moving = SC.link(bpy.data.objects.new(name + 'Rings', SC.mesh_from_arrays(name + 'Rings', V, F, mats=[m_brass], smooth=True)), coll)
    sb = G.HexBatch(name + 'stand')                                  # turned stand, four feet, the pole axis
    sb.add(G.beam([0, 0, 0.05], [0, 0, zc - R * 1.1], 0.12), mat=0)
    for a in np.linspace(0, 2 * math.pi, 4, endpoint=False):
        d = np.array([math.cos(a), math.sin(a), 0.0])
        sb.add(G.beam([0, 0, 0.35], d * 0.45 + [0, 0, 0.02], 0.07), mat=0)
    axis = np.array([0.0, math.cos(latitude), math.sin(latitude)])
    sb.add(G.beam(np.array([0, 0, zc]) - axis * R * 1.15, np.array([0, 0, zc]) + axis * R * 1.15, 0.02), mat=1)
    for a in np.linspace(0, 2 * math.pi, 4, endpoint=False):         # posts holding the horizon ring
        d = np.array([math.cos(a + 0.785), math.sin(a + 0.785), 0.0])
        sb.add(G.beam(d * 0.3 + [0, 0, 0.3], d * R * 1.16 + [0, 0, zc], 0.04), mat=0)
    stand = _obj(name + 'Stand', sb, [m_wood, m_brass], coll)
    for o in (fixed, moving):
        o.pass_index = SC.PASS['props']
    root = SC.link(bpy.data.objects.new(name, None), coll)
    for o in (fixed, moving, stand):
        o.parent = root
    return dict(root=root, fixed=fixed, moving=moving, stand=stand, zc=zc, axis=axis)


def pose_armillary(am, M, spin=0.0, visible=True):
    """M: world matrix of the foot (local +y = north).  spin turns the rings about the pole."""
    am['root'].matrix_world = M
    zc = am['zc']
    ax = Vector(tuple(am['axis']))
    am['moving'].matrix_world = M @ Matrix.Translation((0, 0, zc)) @ Matrix.Rotation(spin, 4, ax) @ Matrix.Translation((0, 0, -zc))
    am['fixed'].matrix_world = M
    am['stand'].matrix_world = M
    for o in (am['fixed'], am['moving'], am['stand']):
        o.hide_render = not visible
