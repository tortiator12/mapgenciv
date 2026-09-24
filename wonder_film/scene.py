"""Procedural Blender scene: the Pharos of Alexandria under construction.

build() creates everything once; pose(state, t) sets the scene to video time t
(which blocks exist, scaffolding, cranes, workers, ships, sun/moon/sky,
torches, the beacon and the camera).  Pure procedural geometry, no assets.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G  # noqa: E402
import timeline as TL  # noqa: E402

rng_global = np.random.default_rng(7)

# ----------------------------------------------------------------- dimensions
GROUND_Z = 3.0
PLAT_COURSES = 5
PLAT_H = 1.2
PLAT_A = [29.0, 28.4, 27.8, 27.2, 26.6]
PLAT_TOP = GROUND_Z + PLAT_COURSES * PLAT_H            # 9.0

T1_Z0, T1_H, T1_NC = PLAT_TOP, 56.0, 40                  # square tier
T1_A0, T1_A1, T1_THICK = 15.25, 13.6, 3.6
T1_CORE_A, T1_CORE_T = 3.4, 1.1
T1_TOP = T1_Z0 + T1_H                                    # 65.0
CORNICE1 = [(0.35, 0.45), (0.75, 0.45), (1.15, 0.45)]    # (projection, height)
T1_ROOF = T1_TOP + sum(h for _, h in CORNICE1)           # 66.35

T2_Z0, T2_H, T2_NC = T1_ROOF, 27.0, 20                   # octagonal tier
T2_A0, T2_A1, T2_THICK = 9.15, 8.3, 2.5
T2_CORE_R, T2_CORE_T = 2.3, 0.9
T2_TOP = T2_Z0 + T2_H                                    # 93.35
CORNICE2 = [(0.3, 0.4), (0.7, 0.4)]
T2_ROOF = T2_TOP + sum(h for _, h in CORNICE2)           # 94.15

T3_Z0 = T2_ROOF
DRUM_R, DRUM_T, DRUM_NC, DRUM_H = 4.4, 1.4, 2, 1.0
COL_Z0 = T3_Z0 + DRUM_NC * DRUM_H                        # 96.15
COL_H, COL_R, COL_RING = 4.0, 0.34, 3.75
ENT_Z0 = COL_Z0 + COL_H                                  # 100.15
ENT_H = 0.9
DOME = [(4.1, 0.55), (3.4, 0.55), (2.6, 0.55), (1.7, 0.5)]
DOME_TOP = ENT_Z0 + ENT_H + sum(h for _, h in DOME)       # 103.2
PED_H = 1.1
STATUE_Z = DOME_TOP + PED_H                              # 104.3
FIRE_POS = (0.0, 0.0, COL_Z0 + 1.6)

# material slots of the masonry mesh
M_STONE, M_STONE_DARK, M_FLOOR = 0, 1, 2
# material slots of the timber mesh
M_WOOD, M_PLANK, M_ROPE = 0, 1, 2

PASS = dict(water=1, terrain=2, masonry=3, timber=4, crane=5, worker=6, ship=7,
            city=8, props=9, statue=10, fire=11, torch=12, sky=0)


# ============================================================ bpy helpers
def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def mesh_from_arrays(name, V, Q, uv=None, face_attrs=None, mats=None, mat_idx=None, smooth=False):
    """Fast mesh creation from vertex (N,3) and polygon index arrays.

    Q is (M,k) for uniform polygons.  uv is per-loop (M*k,2)."""
    me = bpy.data.meshes.new(name)
    V = np.asarray(V, np.float32)
    Q = np.asarray(Q, np.int32)
    m, k = Q.shape
    me.vertices.add(len(V))
    me.vertices.foreach_set('co', V.ravel())
    me.loops.add(m * k)
    me.loops.foreach_set('vertex_index', Q.ravel())
    me.polygons.add(m)
    me.polygons.foreach_set('loop_start', (np.arange(m, dtype=np.int32) * k))
    me.update(calc_edges=True)
    if uv is not None:
        layer = me.uv_layers.new(name='UVMap')
        layer.data.foreach_set('uv', np.asarray(uv, np.float32).ravel())
    for aname, (dtype, data) in (face_attrs or {}).items():
        a = me.attributes.new(aname, dtype, 'FACE')
        key = 'value' if dtype == 'FLOAT' else 'vector'
        a.data.foreach_set(key, np.asarray(data, np.float32).ravel())
    for mt in (mats or []):
        me.materials.append(mt)
    if mat_idx is not None:
        me.polygons.foreach_set('material_index', np.asarray(mat_idx, np.int32))
    if smooth:
        me.shade_smooth()
    else:
        me.shade_flat()
    return me


def hex_mesh(name, batch, sel, mats):
    C = batch.corners[sel]
    n = len(C)
    if n == 0:
        V = np.zeros((0, 3))
        Q = np.zeros((0, 4), np.int32)
        return mesh_from_arrays(name, V, Q, mats=mats)
    V = C.reshape(-1, 3)
    Q = (batch.faces[sel] + (np.arange(n) * 8)[:, None, None]).reshape(-1, 4)
    fs = np.zeros((n, 6, 3), np.float32)
    fs[..., :2] = batch.fsize[sel]
    return mesh_from_arrays(
        name, V, Q, uv=batch.uv[sel].reshape(-1, 2),
        face_attrs={'tone': ('FLOAT', np.repeat(batch.tone[sel], 6)),
                    'fsize': ('FLOAT_VECTOR', fs.reshape(-1, 3))},
        mats=mats, mat_idx=np.repeat(batch.mat[sel], 6))


class NB:
    """Tiny node-tree builder."""

    def __init__(self, nt):
        self.nt = nt
        self.N = nt.nodes
        self.L = nt.links

    def new(self, typ, **props):
        n = self.N.new(typ)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def feed(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.L.new(v, sock)
        elif v is not None:
            sock.default_value = v

    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.new('ShaderNodeMath', operation=op, use_clamp=clamp)
        self.feed(n.inputs[0], a)
        if b is not None:
            self.feed(n.inputs[1], b)
        if c is not None:
            self.feed(n.inputs[2], c)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.new('ShaderNodeVectorMath', operation=op)
        self.feed(n.inputs[0], a)
        if b is not None:
            self.feed(n.inputs[1], b)
        if scale is not None:
            self.feed(n.inputs['Scale'], scale)
        out = n.outputs['Value'] if op in ('DOT_PRODUCT', 'LENGTH', 'DISTANCE') else n.outputs['Vector']
        return out

    def mix(self, fac, a, b, dtype='RGBA', blend='MIX'):
        n = self.new('ShaderNodeMix', data_type=dtype, blend_type=blend)
        sfx = {'RGBA': 'Color', 'FLOAT': 'Float', 'VECTOR': 'Vector'}[dtype]
        ins = {s.identifier: s for s in n.inputs}
        outs = {s.identifier: s for s in n.outputs}
        self.feed(ins['Factor_Float'], fac)
        self.feed(ins['A_' + sfx], a)
        self.feed(ins['B_' + sfx], b)
        return outs['Result_' + sfx]

    def sep(self, v):
        n = self.new('ShaderNodeSeparateXYZ')
        self.feed(n.inputs[0], v)
        return n.outputs

    def comb(self, x, y, z):
        n = self.new('ShaderNodeCombineXYZ')
        self.feed(n.inputs[0], x)
        self.feed(n.inputs[1], y)
        self.feed(n.inputs[2], z)
        return n.outputs[0]

    def rgb(self, col, name=None):
        n = self.new('ShaderNodeRGB')
        n.outputs[0].default_value = tuple(col) + (1.0,) if len(col) == 3 else col
        if name:
            n.name = name
        return n.outputs[0]

    def value(self, v, name=None):
        n = self.new('ShaderNodeValue')
        n.outputs[0].default_value = v
        if name:
            n.name = name
        return n.outputs[0]

    def attr(self, name, kind='GEOMETRY'):
        n = self.new('ShaderNodeAttribute', attribute_name=name, attribute_type=kind)
        return n

    def noise(self, vec, scale, detail=4.0, rough=0.5, w=None, dims='3D'):
        n = self.new('ShaderNodeTexNoise', noise_dimensions=dims)
        self.feed(n.inputs['Vector'], vec)
        n.inputs['Scale'].default_value = scale
        n.inputs['Detail'].default_value = detail
        n.inputs['Roughness'].default_value = rough
        if w is not None:
            self.feed(n.inputs['W'], w)
        return n

    def ramp(self, fac, stops):
        n = self.new('ShaderNodeValToRGB')
        self.feed(n.inputs[0], fac)
        el = n.color_ramp.elements
        el[0].position, el[0].color = stops[0][0], tuple(stops[0][1]) + (1,)
        el[1].position, el[1].color = stops[-1][0], tuple(stops[-1][1]) + (1,)
        for pos, col in stops[1:-1]:
            e = el.new(pos)
            e.color = tuple(col) + (1,)
        return n.outputs[0]

    def smooth(self, e0, e1, x):
        t = self.math('DIVIDE', self.math('SUBTRACT', x, e0), e1 - e0)
        n = self.new('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
        self.feed(n.inputs['Value'], t)
        return n.outputs[0]


def new_material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    nb = NB(m.node_tree)
    out = nb.new('ShaderNodeOutputMaterial')
    return m, nb, out


def principled(nb, base, rough=0.8, metal=0.0, spec=0.5, emit=None, emit_strength=0.0):
    b = nb.new('ShaderNodeBsdfPrincipled')
    nb.feed(b.inputs['Base Color'], base)
    nb.feed(b.inputs['Roughness'], rough)
    nb.feed(b.inputs['Metallic'], metal)
    nb.feed(b.inputs['Specular IOR Level'], spec)
    if emit is not None:
        nb.feed(b.inputs['Emission Color'], emit)
        nb.feed(b.inputs['Emission Strength'], emit_strength)
    return b


def joint_mask(nb, width=0.05):
    """1 on mortar joints (near the edges of each block face), 0 inside."""
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    fs = nb.attr('fsize').outputs['Vector']
    u, v, _ = nb.sep(uv)
    w, h, _ = nb.sep(fs)
    du = nb.math('MINIMUM', u, nb.math('SUBTRACT', w, u))
    dv = nb.math('MINIMUM', v, nb.math('SUBTRACT', h, v))
    d = nb.math('MINIMUM', du, dv)
    return nb.math('SUBTRACT', 1.0, nb.smooth(0.0, width, d))


def mat_masonry(name, base, joint_col, var=0.09, width=0.05, grime=0.22):
    m, nb, out = new_material(name)
    tone = nb.attr('tone').outputs['Fac']
    j = joint_mask(nb, width)
    obj = nb.new('ShaderNodeTexCoord').outputs['Object']
    n1 = nb.noise(obj, 0.35, 3.0, 0.6).outputs['Fac']
    n2 = nb.noise(obj, 3.0, 2.0, 0.5).outputs['Fac']
    # per-block tone variation, big weathering patches and fine grain
    k = nb.math('ADD', 1.0 - var, nb.math('MULTIPLY', tone, 2 * var))
    k = nb.math('MULTIPLY', k, nb.math('ADD', 1.0 - grime, nb.math('MULTIPLY', n1, grime * 1.6)))
    k = nb.math('MULTIPLY', k, nb.math('ADD', 0.92, nb.math('MULTIPLY', n2, 0.16)))
    col = nb.new('ShaderNodeMix', data_type='RGBA')
    ins = {s.identifier: s for s in col.inputs}
    col.blend_type = 'MULTIPLY'
    nb.feed(ins['Factor_Float'], 1.0)
    nb.feed(ins['A_Color'], tuple(base) + (1,))
    kc = nb.comb(k, k, k)
    nb.feed(ins['B_Color'], kc)
    colout = {s.identifier: s for s in col.outputs}['Result_Color']
    colj = nb.mix(j, colout, tuple(joint_col) + (1,))
    b = principled(nb, colj, rough=0.88, spec=0.35)
    bump = nb.new('ShaderNodeBump', invert=True)
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.05
    nb.feed(bump.inputs['Height'], nb.math('ADD', j, nb.math('MULTIPLY', n2, 0.3)))
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_wood(name, base, var=0.3, width=0.03):
    m, nb, out = new_material(name)
    tone = nb.attr('tone').outputs['Fac']
    j = joint_mask(nb, width)
    k = nb.math('ADD', 1.0 - var, nb.math('MULTIPLY', tone, 2 * var))
    kc = nb.comb(k, k, k)
    col = nb.new('ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY')
    ins = {s.identifier: s for s in col.inputs}
    nb.feed(ins['Factor_Float'], 1.0)
    nb.feed(ins['A_Color'], tuple(base) + (1,))
    nb.feed(ins['B_Color'], kc)
    colout = {s.identifier: s for s in col.outputs}['Result_Color']
    colj = nb.mix(nb.math('MULTIPLY', j, 0.6), colout, (0.03, 0.02, 0.012, 1))
    b = principled(nb, colj, rough=0.85, spec=0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_simple(name, base, rough=0.8, metal=0.0, spec=0.4, emit=None, emit_strength=0.0):
    m, nb, out = new_material(name)
    b = principled(nb, tuple(base) + (1,), rough, metal, spec,
                   None if emit is None else tuple(emit) + (1,), emit_strength)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_objcolor(name, rough=0.8):
    """Colour taken from Object > Color (workers, ships' sails...)."""
    m, nb, out = new_material(name)
    oi = nb.new('ShaderNodeObjectInfo')
    b = principled(nb, oi.outputs['Color'], rough, 0.0, 0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


# ============================================================ world / sky
def build_world():
    w = bpy.data.worlds.new('Sky')
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    nb = NB(nt)
    out = nb.new('ShaderNodeOutputWorld')
    bg = nb.new('ShaderNodeBackground')
    nb.feed(out.inputs['Surface'], bg.outputs[0])

    D = nb.vmath('NORMALIZE', nb.new('ShaderNodeTexCoord').outputs['Generated'])
    dx, dy, dz = nb.sep(D)
    zen = nb.rgb((0.1, 0.15, 0.3), 'zenith')
    hor = nb.rgb((0.5, 0.45, 0.4), 'horizon')
    glow = nb.rgb((1.0, 0.5, 0.2), 'sunglow')
    cl_lit = nb.rgb((0.8, 0.6, 0.5), 'cloud_lit')
    cl_dark = nb.rgb((0.1, 0.1, 0.12), 'cloud_dark')
    sun = nb.new('ShaderNodeCombineXYZ')
    sun.name = 'sun_dir'
    moon = nb.new('ShaderNodeCombineXYZ')
    moon.name = 'moon_dir'
    t_cloud = nb.value(0.0, 'cloud_time')
    moon_k = nb.value(0.0, 'moon')
    sun_k = nb.value(1.0, 'sun_disc')
    cover = nb.value(0.5, 'cover')

    up = nb.math('MAXIMUM', dz, 0.0)
    grad = nb.math('POWER', up, 0.3)
    sky = nb.mix(grad, hor, zen)
    # sun glow (forward scattering) - wide and tight lobes
    cs = nb.math('MAXIMUM', nb.vmath('DOT_PRODUCT', D, sun.outputs[0]), 0.0)
    g1 = nb.math('POWER', cs, 9.0)
    g2 = nb.math('POWER', cs, 60.0)
    horizon_boost = nb.math('SUBTRACT', 1.0, nb.math('POWER', up, 0.35))
    gl = nb.math('ADD', nb.math('MULTIPLY', g1, nb.math('MULTIPLY', horizon_boost, 0.75)),
                 nb.math('MULTIPLY', g2, 1.5))
    sky = nb.mix(gl, sky, glow, blend='ADD')

    # 2D cloud deck projected on a plane above the scene
    inv = nb.math('DIVIDE', 1.0, nb.math('ADD', up, 0.06))
    px = nb.math('MULTIPLY', dx, inv)
    py = nb.math('MULTIPLY', dy, inv)
    P = nb.comb(nb.math('ADD', px, nb.math('MULTIPLY', t_cloud, 0.55)),
                nb.math('ADD', py, nb.math('MULTIPLY', t_cloud, 0.18)), 0.0)
    sdx, sdy, _ = nb.sep(sun.outputs[0])
    P2 = nb.vmath('ADD', P, nb.comb(nb.math('MULTIPLY', sdx, 0.10), nb.math('MULTIPLY', sdy, 0.10), 0.0))
    tz = nb.math('MULTIPLY', t_cloud, 0.12)
    P = nb.vmath('ADD', P, nb.comb(0.0, 0.0, tz))
    P2 = nb.vmath('ADD', P2, nb.comb(0.0, 0.0, tz))
    nz1 = nb.noise(P, 0.28, 5.0, 0.55).outputs['Fac']
    nz2 = nb.noise(P2, 0.28, 5.0, 0.55).outputs['Fac']
    big = nb.noise(P, 0.07, 1.0, 0.5).outputs['Fac']
    cover = nb.math('ADD', cover, nb.math('MULTIPLY', nb.math('SUBTRACT', big, 0.5), 1.1))
    # coverage threshold
    lo = nb.math('SUBTRACT', 1.0, cover)
    dens = nb.math('MULTIPLY', nb.math('SUBTRACT', nz1, nb.math('MULTIPLY', lo, 0.55)), 3.2, clamp=True)
    dens = nb.math('MULTIPLY', dens, nb.math('SUBTRACT', 1.0, nb.math('POWER', nb.math('SUBTRACT', 1.0, up), 18.0)),
                   clamp=True)
    lit = nb.math('ADD', nb.math('MULTIPLY', nb.math('SUBTRACT', nz1, nz2), 9.0), 0.45, clamp=True)
    ccol = nb.mix(lit, cl_dark, cl_lit)
    # clouds near the sun catch the glow
    ccol = nb.mix(nb.math('MULTIPLY', g1, 0.7), ccol, glow, blend='ADD')
    # fade the deck into the horizon haze
    hfade = nb.math('POWER', nb.math('MINIMUM', nb.math('MULTIPLY', up, 5.0), 1.0), 0.7)
    sky = nb.mix(nb.math('MULTIPLY', dens, hfade), sky, ccol)
    aov = nb.new('ShaderNodeOutputAOV')
    aov.aov_name = 'clouds'
    nb.feed(aov.inputs['Value'], nb.math('MULTIPLY', dens, hfade))

    # stars (hidden by clouds) and a full moon
    cm = nb.vmath('DOT_PRODUCT', D, moon.outputs[0])
    disc = nb.smooth(0.99972, 0.99980, cm)
    halo = nb.math('MULTIPLY', nb.math('POWER', nb.math('MAXIMUM', cm, 0.0), 400.0), 0.08)
    mk = nb.math('MULTIPLY', moon_k, nb.math('ADD', nb.math('MULTIPLY', disc, nb.math('SUBTRACT', 1.0, nb.math('MULTIPLY', dens, 0.85))), halo))
    sky = nb.mix(mk, sky, (0.85, 0.9, 1.0, 1.0), blend='ADD')
    # sun disc
    sdisc = nb.math('MULTIPLY', nb.smooth(0.99990, 0.99995, cs), sun_k)
    sky = nb.mix(nb.math('MULTIPLY', sdisc, nb.math('SUBTRACT', 1.0, nb.math('MULTIPLY', dens, 0.9))), sky,
                 (1.0, 0.8, 0.55, 1.0), blend='ADD')
    # below the horizon: dark sea-coloured ground
    below = nb.smooth(0.0, -0.02, dz)
    sky = nb.mix(below, sky, (0.01, 0.015, 0.02, 1.0))
    nb.feed(bg.inputs['Color'], sky)
    bg.inputs['Strength'].default_value = 1.0
    bpy.context.scene.world = w
    return w


# sky palettes keyed by sun elevation (degrees); linear RGB
SKY_KEYS = [
    # el,   zenith,               horizon,             sunglow,             cloud_lit,          cloud_dark
    (-40, (0.0022, 0.0036, 0.0090), (0.0055, 0.0080, 0.0150), (0.000, 0.000, 0.000), (0.010, 0.013, 0.022), (0.0015, 0.002, 0.0035)),
    (-14, (0.0035, 0.0060, 0.0170), (0.012, 0.014, 0.030), (0.020, 0.010, 0.012), (0.016, 0.017, 0.028), (0.003, 0.0035, 0.006)),
    (-6, (0.008, 0.015, 0.045), (0.070, 0.050, 0.070), (0.260, 0.080, 0.035), (0.110, 0.060, 0.070), (0.010, 0.011, 0.022)),
    (0, (0.025, 0.048, 0.120), (0.360, 0.200, 0.120), (1.100, 0.360, 0.100), (0.800, 0.340, 0.170), (0.035, 0.032, 0.048)),
    (6, (0.055, 0.100, 0.215), (0.520, 0.390, 0.270), (0.850, 0.420, 0.150), (0.950, 0.620, 0.400), (0.075, 0.072, 0.088)),
    (18, (0.060, 0.105, 0.230), (0.340, 0.335, 0.330), (0.420, 0.300, 0.170), (0.820, 0.720, 0.610), (0.070, 0.075, 0.090)),
    (50, (0.055, 0.105, 0.235), (0.300, 0.325, 0.355), (0.230, 0.200, 0.160), (0.840, 0.790, 0.720), (0.080, 0.086, 0.100)),
]


def build_flat_world():
    w = bpy.data.worlds.new('Flat')
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.0
    return w


def sky_palette(el_deg):
    els = [k[0] for k in SKY_KEYS]
    out = []
    for c in range(1, 6):
        cols = np.array([k[c] for k in SKY_KEYS])
        out.append(tuple(float(np.interp(el_deg, els, cols[:, i])) for i in range(3)))
    return out


# ============================================================ terrain
def island_sd(X, Y):
    w = np.interp(X, [-2900, -2400, -1600, -600, -260, -40], [30, 120, 165, 175, 150, 92])
    yc = 16 * np.sin(X / 430.0) - 12
    d_side = np.abs(Y - yc) - w
    d_tip = np.hypot(np.maximum(X + 40, 0), Y - yc) - 92
    d = np.where(X > -40, d_tip, d_side)
    d = d + 13 * G.fbm(X / 70, Y / 70, 4, seed=3) + 4 * G.fbm(X / 14, Y / 14, 3, seed=9)
    return d


def island_height(X, Y):
    d = island_sd(X, Y)
    upl = np.clip((-X - 110) / 260.0, 0, 1)
    inland = (GROUND_Z + 0.4 + 1.6 * G.fbm(X / 110, Y / 110, 4, seed=21)
              + upl * (2.5 + 5.0 * np.maximum(G.fbm(X / 160, Y / 90, 4, seed=77) + 0.2, 0)))
    rocks = 2.6 * np.maximum(G.fbm(X / 7, Y / 7, 4, seed=5) + 0.15, 0) * np.exp(-(d / 11.0) ** 2)
    h = inland + (-7.5 - inland) * (np.clip((d + 22) / 42.0, 0, 1) ** 1.3) + rocks
    r = np.hypot(X, Y)
    yard = np.clip((78 - r) / 22.0, 0, 1)
    yard = yard * yard * (3 - 2 * yard)
    h = h * (1 - yard) + (GROUND_Z + 0.12 * G.fbm(X / 9, Y / 9, 2, seed=2)) * yard
    return h


def coast_y(X):
    return (-1320 + 110 * np.sin(X / 640.0) + 650 * np.exp(-((X - 1650) / 330.0) ** 2)
            + 25 * G.fbm(X / 90, 0.5, 3, seed=31))


def mainland_height(X, Y):
    d = coast_y(X) - Y   # >0 inland (south of the coast)
    h = 3.5 + 2.0 * G.fbm(X / 300, Y / 300, 3, seed=41)
    return np.where(d > 0, h * np.clip(d / 30.0, 0, 1) + (-6) * (1 - np.clip(d / 30.0, 0, 1)),
                    -6 + 0 * X)


def mat_terrain():
    m, nb, out = new_material('Terrain')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    nz = nb.sep(geo.outputs['Normal'])[2]
    z = nb.sep(pos)[2]
    n1 = nb.noise(pos, 0.08, 3.0, 0.6).outputs['Fac']
    n2 = nb.noise(pos, 0.9, 3.0, 0.6).outputs['Fac']
    rock = nb.mix(n2, (0.075, 0.068, 0.062, 1), (0.21, 0.19, 0.165, 1))
    sand = nb.mix(n1, (0.17, 0.15, 0.12, 1), (0.27, 0.235, 0.185, 1))
    flat = nb.smooth(0.78, 0.93, nz)
    col = nb.mix(nb.math('MULTIPLY', flat, nb.smooth(0.42, 0.72, nb.math('ADD', n1, 0.1))), rock, sand)
    # trampled, dusty construction yard around the podium
    x_, y_, _ = nb.sep(pos)
    rr = nb.vmath('LENGTH', nb.comb(x_, y_, 0.0))
    yardm = nb.math('MULTIPLY', nb.smooth(80.0, 58.0, rr), flat)
    dust = nb.mix(nb.noise(pos, 0.25, 4.0, 0.6).outputs['Fac'], (0.17, 0.155, 0.135, 1), (0.26, 0.24, 0.21, 1))
    col = nb.mix(yardm, col, dust)
    # sparse dry scrub
    scrub = nb.math('MULTIPLY', flat, nb.smooth(0.58, 0.66, nb.noise(pos, 0.35, 3.0, 0.6).outputs['Fac']))
    col = nb.mix(nb.math('MULTIPLY', scrub, 0.8), col, (0.14, 0.15, 0.07, 1))
    # wet, dark rock at the waterline
    wet = nb.smooth(1.6, 0.2, z)
    col = nb.mix(nb.math('MULTIPLY', wet, 0.75), col, (0.035, 0.035, 0.035, 1))
    b = principled(nb, col, rough=nb.math('SUBTRACT', 0.95, nb.math('MULTIPLY', wet, 0.5)), spec=0.3)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.6
    nb.feed(bump.inputs['Height'], nb.noise(pos, 1.6, 3.0, 0.6).outputs['Fac'])
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_terrain(coll):
    mt = mat_terrain()
    objs = []
    for name, (x0, x1, y0, y1, nx, ny) in {
        'IslandNear': (-700, 170, -270, 250, 436, 261),
        'IslandFar': (-3000, -700, -320, 300, 231, 63),
    }.items():
        V, Q = G.grid_mesh(x0, x1, y0, y1, nx, ny, island_height)
        me = mesh_from_arrays(name, V, Q, mats=[mt], smooth=True)
        o = link(bpy.data.objects.new(name, me), coll)
        o.pass_index = PASS['terrain']
        objs.append(o)
    V, Q = G.grid_mesh(-4500, 4500, -5200, -950, 301, 143, mainland_height)
    me = mesh_from_arrays('Mainland', V, Q, mats=[mt], smooth=True)
    o = link(bpy.data.objects.new('Mainland', me), coll)
    o.pass_index = PASS['terrain']
    objs.append(o)
    return objs


def shore_foam_image():
    """Distance-to-shore field around the island, used for surf foam."""
    from scipy.ndimage import distance_transform_edt
    x0, x1, y0, y1, res = -1100.0, 300.0, -450.0, 450.0, 1.0
    xs = np.arange(x0, x1, res)
    ys = np.arange(y0, y1, res)
    X, Y = np.meshgrid(xs, ys)
    land = island_height(X, Y) > 0.0
    d = distance_transform_edt(~land) * res
    foam = np.exp(-d / 6.0) * (~land)
    img = bpy.data.images.new('ShoreFoam', len(xs), len(ys), float_buffer=True)
    px = np.zeros((len(ys), len(xs), 4), np.float32)
    px[..., 0] = foam
    px[..., 1] = np.exp(-d / 25.0) * (~land)
    px[..., 3] = 1
    img.pixels.foreach_set(px.ravel())
    img.pack()
    return img, (x0, x1, y0, y1)


def mat_water(foam_img, extent):
    m, nb, out = new_material('Water')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    x, y, z = nb.sep(pos)
    x0, x1, y0, y1 = extent
    uvw = nb.comb(nb.math('DIVIDE', nb.math('SUBTRACT', x, x0), x1 - x0),
                  nb.math('DIVIDE', nb.math('SUBTRACT', y, y0), y1 - y0), 0.0)
    tex = nb.new('ShaderNodeTexImage', interpolation='Linear', extension='CLIP')
    tex.image = foam_img
    nb.feed(tex.inputs['Vector'], uvw)
    sep = nb.new('ShaderNodeSeparateColor')
    nb.feed(sep.inputs[0], tex.outputs['Color'])
    shore, shallow = sep.outputs[0], sep.outputs[1]
    tw = nb.value(0.0, 'water_time')
    fn = nb.noise(nb.vmath('ADD', pos, nb.comb(0.0, 0.0, nb.math('MULTIPLY', tw, 8.0))), 0.12, 3.0, 0.62).outputs['Fac']
    surf = nb.math('MULTIPLY', shore, nb.smooth(0.42, 0.62, nb.math('ADD', fn, nb.math('MULTIPLY', shore, 0.25))))
    foam_attr = nb.attr('foam').outputs['Fac']
    whitecap = nb.smooth(0.45, 0.95, foam_attr)
    foam = nb.math('MAXIMUM', surf, nb.math('MULTIPLY', whitecap, 0.55))
    base = nb.mix(shallow, (0.006, 0.020, 0.028, 1), (0.02, 0.07, 0.07, 1))
    col = nb.mix(foam, base, (0.55, 0.58, 0.58, 1))
    b = principled(nb, col, rough=nb.math('ADD', 0.05, nb.math('MULTIPLY', foam, 0.8)), spec=0.5)
    b.inputs['IOR'].default_value = 1.33
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.25
    nb.feed(bump.inputs['Height'], nb.noise(nb.vmath('ADD', pos, nb.comb(0.0, 0.0, nb.math('MULTIPLY', tw, 5.0))), 0.6, 2.0, 0.5).outputs['Fac'])
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_sea(coll):
    img, extent = shore_foam_image()
    V, Q = G.polar_mesh(30.0, 520.0, 2.2, 16000.0, 1.05, 1150)
    me = mesh_from_arrays('Sea', V, Q, mats=[mat_water(img, extent)], smooth=True)
    sea = link(bpy.data.objects.new('Sea', me), coll)
    sea.pass_index = PASS['water']
    mod = sea.modifiers.new('Ocean', 'OCEAN')
    mod.geometry_mode = 'DISPLACE'
    mod.spatial_size = 160
    mod.resolution = 12
    mod.wave_scale = 1.1
    mod.choppiness = 1.15
    mod.wind_velocity = 13.0
    mod.wave_alignment = 0.35
    mod.wave_direction = math.radians(200)
    mod.use_normals = False
    mod.use_foam = True
    mod.foam_layer_name = 'foam'
    mod.foam_coverage = 0.05
    mod.random_seed = 11
    return sea, mod


def mat_rock():
    m, nb, out = new_material('Rock')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    z = nb.sep(pos)[2]
    n2 = nb.noise(pos, 0.7, 4.0, 0.6).outputs['Fac']
    col = nb.mix(n2, (0.06, 0.055, 0.05, 1), (0.2, 0.18, 0.155, 1))
    wet = nb.smooth(1.4, 0.0, z)
    col = nb.mix(nb.math('MULTIPLY', wet, 0.8), col, (0.025, 0.025, 0.028, 1))
    b = principled(nb, col, rough=nb.math('SUBTRACT', 0.9, nb.math('MULTIPLY', wet, 0.55)), spec=0.35)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.5
    nb.feed(bump.inputs['Height'], nb.noise(pos, 2.5, 4.0, 0.6).outputs['Fac'])
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_boulders(coll):
    """Faceted boulders (convex hulls) strewn along the headland's waterline."""
    from scipy.spatial import ConvexHull
    rng = np.random.default_rng(23)
    xs = rng.uniform(-620, 160, 60000)
    ys = rng.uniform(-260, 240, 60000)
    d = island_sd(xs, ys)
    cand = np.where((d > -6) & (d < 12))[0]
    pick = cand[:: max(1, len(cand) // 420)][:420]
    V, F = [], []
    for k in pick:
        x, y = xs[k], ys[k]
        r = rng.uniform(1.2, 4.2) * (1.4 if rng.random() < 0.12 else 1.0)
        pts = rng.normal(size=(16, 3))
        pts /= np.linalg.norm(pts, axis=1, keepdims=True)
        pts *= rng.uniform(0.75, 1.0, (16, 1))
        pts *= [r * rng.uniform(0.9, 1.4), r * rng.uniform(0.8, 1.2), r * rng.uniform(0.5, 0.85)]
        hull = ConvexHull(pts)
        zc = min(float(island_height(np.array([x]), np.array([y]))[0]), 1.0) - r * 0.25
        base = len(V)
        rot = rng.uniform(0, 2 * np.pi)
        c, s_ = math.cos(rot), math.sin(rot)
        for p in pts:
            V.append([x + c * p[0] - s_ * p[1], y + s_ * p[0] + c * p[1], zc + p[2]])
        for simp in hull.simplices:
            a, b_, cc = simp
            # outward winding
            n = np.cross(pts[b_] - pts[a], pts[cc] - pts[a])
            if np.dot(n, pts[a]) < 0:
                b_, cc = cc, b_
            F.append([base + a, base + b_, base + cc])
    me = mesh_from_arrays('Boulders', np.array(V), np.array(F), mats=[mat_rock()])
    o = link(bpy.data.objects.new('Boulders', me), coll)
    o.pass_index = PASS['terrain']
    return o


def build_cloud_shadows(coll):
    """Invisible deck high above the site that only blocks shadow rays:
    cloud shadows racing over land and sea, the classic time-lapse cue."""
    m, nb, out = new_material('CloudShadow')
    geo = nb.new('ShaderNodeNewGeometry')
    x, y, _ = nb.sep(geo.outputs['Position'])
    tt = nb.value(0.0, 'shadow_time')
    cover = nb.value(0.5, 'shadow_cover')
    P = nb.comb(nb.math('ADD', x, nb.math('MULTIPLY', tt, 1.0)), nb.math('ADD', y, nb.math('MULTIPLY', tt, 0.33)), 0.0)
    n = nb.noise(nb.vmath('ADD', P, nb.comb(0.0, 0.0, nb.math('MULTIPLY', tt, 0.25))), 0.0016, 3.0, 0.6).outputs['Fac']
    dens = nb.smooth(0.0, 0.14, nb.math('SUBTRACT', n, nb.math('SUBTRACT', 1.0, cover)))
    tr = nb.math('SUBTRACT', 1.0, nb.math('MULTIPLY', dens, 0.82))
    shadow_bsdf = nb.new('ShaderNodeBsdfTransparent')
    nb.feed(shadow_bsdf.inputs['Color'], nb.comb(tr, tr, tr))
    clear = nb.new('ShaderNodeBsdfTransparent')
    lp = nb.new('ShaderNodeLightPath')
    mix = nb.new('ShaderNodeMixShader')
    nb.feed(mix.inputs[0], lp.outputs['Is Shadow Ray'])
    nb.feed(mix.inputs[1], clear.outputs[0])
    nb.feed(mix.inputs[2], shadow_bsdf.outputs[0])
    nb.feed(out.inputs['Surface'], mix.outputs[0])
    V = np.array([[-30000, -30000, 1400], [30000, -30000, 1400], [30000, 30000, 1400], [-30000, 30000, 1400]])
    me = mesh_from_arrays('CloudShadow', V, np.array([[0, 1, 2, 3]]), mats=[m])
    o = link(bpy.data.objects.new('CloudShadow', me), coll)
    o.visible_camera = False
    o.visible_glossy = False
    o.visible_diffuse = False
    o.visible_transmission = False
    o.visible_volume_scatter = False
    return o, m


# ============================================================ masonry
class Schedule:
    """Maps masonry top height <-> video time (filled while building courses)."""

    def __init__(self):
        self.pts = [(GROUND_Z, 0.9)]

    def add(self, z, t):
        self.pts.append((z, t))

    def finalize(self):
        self.pts.sort(key=lambda p: p[1])
        self.t = np.array([p[1] for p in self.pts])
        self.z = np.maximum.accumulate(np.array([p[0] for p in self.pts]))

    def height(self, t):
        return float(np.interp(t, self.t, self.z))

    def time_at(self, z):
        i = np.searchsorted(self.z, z)
        if i >= len(self.z):
            return 1e9
        return float(np.interp(z, self.z, self.t))


def course_times(phase, k, nc, order, spread=1.25):
    """Appearance time of a block with ring order `order` in course k of nc."""
    p = (k + min(order * spread, 1.0) * 0.999) / nc
    return TL.phase_time(phase, min(p, 1.0))


def build_masonry(sched):
    mb = G.HexBatch('masonry')
    rng = np.random.default_rng(3)

    # --- survey stage has no masonry; platform: 5 stepped courses of big blocks
    for k in range(PLAT_COURSES):
        a = PLAT_A[k]
        z0 = GROUND_Z + k * PLAT_H
        blocks = G.slab_blocks(-a, a, -a, a, z0, z0 + PLAT_H, 2.6, 1.9, course=k)
        for c in blocks:
            cx, cy = c[:, 0].mean(), c[:, 1].mean()
            order = np.clip((cx * 0.8 - cy * 0.6) / (2 * a) + 0.5 + rng.uniform(-0.06, 0.06), 0, 1)
            t_on = course_times('platform', k, PLAT_COURSES, order, 1.0)
            mb.add(c, t_on, mat=M_STONE_DARK)
        sched.add(z0 + PLAT_H, TL.phase_time('platform', (k + 1) / PLAT_COURSES))

    # --- tier 1: square, battered walls, windows, door, core shaft, floors
    ch = T1_H / T1_NC
    for k in range(T1_NC):
        z0, z1 = T1_Z0 + k * ch, T1_Z0 + (k + 1) * ch
        a0 = T1_A0 + (T1_A1 - T1_A0) * (k / T1_NC)
        a1 = T1_A0 + (T1_A1 - T1_A0) * ((k + 1) / T1_NC)
        openings = {}
        if k < 5:   # great door on the north face (side index 2 runs +x..-x at y=+a)
            openings.setdefault(2, []).append((0.44, 0.56))
        if 6 <= k < T1_NC - 2 and (k - 6) % 5 in (0, 1):
            for s in range(4):
                for u in (0.26, 0.5, 0.74):
                    if s == 2 and u == 0.5 and k < 9:
                        continue
                    openings.setdefault(s, []).append((u - 0.025, u + 0.025))
        for c, order in G.ring_course(G.square_poly, a0, a1, T1_THICK, z0, z1, 2.1, k, openings):
            o = (order * 2 + 0.37 * k) % 1.0
            mb.add(c, course_times('tier1', k, T1_NC, o + rng.uniform(0, 0.05)), mat=M_STONE)
        for c, order in G.ring_course(G.square_poly, T1_CORE_A, T1_CORE_A, T1_CORE_T, z0, z1, 1.8, k):
            mb.add(c, course_times('tier1', k, T1_NC, rng.uniform(0, 1)), mat=M_STONE)
        if k % 4 == 3 and k < T1_NC - 1:   # timber-and-slab floors inside
            ai = a1 - T1_THICK + 0.02
            ac = T1_CORE_A
            t_f = course_times('tier1', k, T1_NC, 1.0)
            for s in range(4):
                P = G.square_poly(ai)
                Q = G.square_poly(ac)
                j = (s + 1) % 4
                for u0 in np.linspace(0, 1, 6)[:-1]:
                    u1 = u0 + 0.2
                    quad = [P[s] + (P[j] - P[s]) * u0, P[s] + (P[j] - P[s]) * u1,
                            Q[s] + (Q[j] - Q[s]) * u1, Q[s] + (Q[j] - Q[s]) * u0]
                    mb.add(G.quad_slab(quad, z1 - 0.45, z1 - 0.02), t_f + rng.uniform(0, 0.08), mat=M_FLOOR)
        sched.add(z1, TL.phase_time('tier1', (k + 1) / T1_NC))

    # --- tier 1 cap: stepped cornice, roof slab, parapet with merlons
    z = T1_TOP
    for i, (proj, h) in enumerate(CORNICE1):
        p0 = i / len(CORNICE1) * 0.45
        for c, order in G.ring_course(G.square_poly, T1_A1 + proj, T1_A1 + proj, T1_THICK + proj, z, z + h, 2.4, i):
            mb.add(c, TL.phase_time('tier1cap', p0 + order * 0.15), mat=M_STONE)
        z += h
    ai = T1_A1 - T1_THICK + 0.02
    for c in G.slab_blocks(-ai, ai, -ai, ai, T1_ROOF - 0.5, T1_ROOF - 0.01, 3.2, 2.6, course=1):
        cx, cy = c[:, 0].mean(), c[:, 1].mean()
        mb.add(c, TL.phase_time('tier1cap', 0.25 + 0.35 * ((cx + ai) / (2 * ai))), mat=M_FLOOR)
    ap = T1_A1 + CORNICE1[-1][0]
    for c, order in G.ring_course(G.square_poly, ap, ap, 0.8, T1_ROOF, T1_ROOF + 1.0, 2.4, 0):
        mb.add(c, TL.phase_time('tier1cap', 0.45 + order * 0.25), mat=M_STONE)
    merl = []
    P = G.square_poly(ap)
    for s in range(4):
        j = (s + 1) % 4
        L = np.linalg.norm(P[j] - P[s])
        n = int(L // 1.7)
        for m_ in range(n):
            u0 = (m_ * 1.7 + 0.35) / L
            u1 = u0 + 1.0 / L
            merl.append((s, u0, u1))
    for (s, u0, u1) in merl:
        c = [x for x in G.ring_course(G.square_poly, ap, ap, 0.8, T1_ROOF + 1.0, T1_ROOF + 1.9, 99, 0,
                                      openings={q: ([(0, u0), (u1, 1)] if q == s else [(0, 1)]) for q in range(4)})]
        for cc, order in c:
            mb.add(cc, TL.phase_time('tier1cap', 0.62 + 0.28 * ((s + u0) / 4)), mat=M_STONE)
    sched.add(T1_ROOF, TL.phase_time('tier1cap', 0.6))

    # --- tier 2: octagon
    ch = T2_H / T2_NC
    for k in range(T2_NC):
        z0, z1 = T2_Z0 + k * ch, T2_Z0 + (k + 1) * ch
        a0 = T2_A0 + (T2_A1 - T2_A0) * (k / T2_NC)
        a1 = T2_A0 + (T2_A1 - T2_A0) * ((k + 1) / T2_NC)
        openings = {}
        if 2 <= k < T2_NC - 2 and (k - 2) % 5 in (0, 1):
            for s in (1, 3, 5, 7) if (k // 5) % 2 == 0 else (0, 2, 4, 6):
                openings.setdefault(s, []).append((0.42, 0.58))
        for c, order in G.ring_course(G.oct_poly, a0, a1, T2_THICK, z0, z1, 2.0, k, openings):
            o = (order * 2 + 0.29 * k) % 1.0
            mb.add(c, course_times('tier2', k, T2_NC, o + rng.uniform(0, 0.05)), mat=M_STONE)
        for c, order in G.ring_course(lambda r: G.circle_poly(r, 12), T2_CORE_R, T2_CORE_R, T2_CORE_T, z0, z1, 1.6, k):
            mb.add(c, course_times('tier2', k, T2_NC, rng.uniform(0, 1)), mat=M_STONE)
        if k % 5 == 4 and k < T2_NC - 1:
            ai = a1 - T2_THICK + 0.02
            P = G.oct_poly(ai)
            Q = G.circle_poly(T2_CORE_R, 8)
            Q = np.roll(Q, 0, axis=0)
            t_f = course_times('tier2', k, T2_NC, 1.0)
            ang_p = np.arctan2(P[:, 1], P[:, 0])
            for s in range(8):
                j = (s + 1) % 8
                qa = np.array([math.cos(ang_p[s]), math.sin(ang_p[s])]) * T2_CORE_R
                qb = np.array([math.cos(ang_p[j]), math.sin(ang_p[j])]) * T2_CORE_R
                mb.add(G.quad_slab([P[s], P[j], qb, qa], z1 - 0.4, z1 - 0.02), t_f, mat=M_FLOOR)
        sched.add(z1, TL.phase_time('tier2', (k + 1) / T2_NC))

    # --- tier 2 cap
    z = T2_TOP
    for i, (proj, h) in enumerate(CORNICE2):
        for c, order in G.ring_course(G.oct_poly, T2_A1 + proj, T2_A1 + proj, T2_THICK + proj, z, z + h, 2.2, i):
            mb.add(c, TL.phase_time('tier2cap', i * 0.2 + order * 0.2), mat=M_STONE)
        z += h
    ai = T2_A1 - T2_THICK + 0.02
    P = G.oct_poly(ai)
    for s in range(8):
        j = (s + 1) % 8
        mb.add(G.quad_slab([P[s], P[j], [0, 0], [0, 0]], T2_ROOF - 0.45, T2_ROOF - 0.01),
               TL.phase_time('tier2cap', 0.3 + s * 0.03), mat=M_FLOOR)
    ap = T2_A1 + CORNICE2[-1][0]
    for c, order in G.ring_course(G.oct_poly, ap, ap, 0.7, T2_ROOF, T2_ROOF + 0.8, 2.2, 0):
        mb.add(c, TL.phase_time('tier2cap', 0.5 + order * 0.2), mat=M_STONE)
    P = G.oct_poly(ap)
    for s in range(8):
        for u0 in (0.12, 0.44, 0.76):
            op = {q: ([(0, u0), (u0 + 0.14, 1)] if q == s else [(0, 1)]) for q in range(8)}
            for cc, order in G.ring_course(G.oct_poly, ap, ap, 0.7, T2_ROOF + 0.8, T2_ROOF + 1.5, 99, 0, op):
                mb.add(cc, TL.phase_time('tier2cap', 0.7 + 0.25 * s / 8), mat=M_STONE)
    sched.add(T2_ROOF, TL.phase_time('tier2cap', 0.6))

    # --- tier 3: drum of the lantern (columns/dome are separate objects)
    circ = lambda r: G.circle_poly(r, 16)  # noqa: E731
    for k in range(DRUM_NC):
        z0 = T3_Z0 + k * DRUM_H
        for c, order in G.ring_course(circ, DRUM_R, DRUM_R, DRUM_T, z0, z0 + DRUM_H, 1.8, k):
            mb.add(c, TL.phase_time('tier3', (k + order) / DRUM_NC * 0.28), mat=M_STONE)
    P = circ(DRUM_R - DRUM_T + 0.02)
    for s in range(16):
        j = (s + 1) % 16
        mb.add(G.quad_slab([P[s], P[j], [0, 0], [0, 0]], COL_Z0 - 0.5, COL_Z0 - 0.02),
               TL.phase_time('tier3', 0.28), mat=M_FLOOR)
    sched.add(COL_Z0, TL.phase_time('tier3', 0.3))
    sched.add(ENT_Z0 + ENT_H, TL.phase_time('tier3', 0.65))
    sched.add(DOME_TOP, TL.phase_time('tier3', 1.0))
    sched.add(STATUE_Z + 6.2, TL.PHASES['statue'][1])
    return mb.finalize()


# ============================================================ lantern pieces
def prism(name, radius, z0, z1, n=12, r_top=None, center=(0, 0), mats=None):
    r_top = radius if r_top is None else r_top
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cx, cy = center
    bot = np.stack([cx + radius * np.cos(ang), cy + radius * np.sin(ang), np.full(n, z0)], 1)
    top = np.stack([cx + r_top * np.cos(ang), cy + r_top * np.sin(ang), np.full(n, z1)], 1)
    V = np.concatenate([bot, top, [[cx, cy, z0], [cx, cy, z1]]])
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    tris_b = [[2 * n, j, i, i] for i, j in ((i, (i + 1) % n) for i in range(n))]
    tris_t = [[2 * n + 1, n + i, n + (i + 1) % n, n + (i + 1) % n] for i in range(n)]
    Q = np.array(faces + tris_b + tris_t)
    return mesh_from_arrays(name, V, Q, mats=mats, smooth=False)


def build_lantern(coll, mat_stone, mat_bronze):
    """Columns, entablature, dome and statue pedestal: appear piece by piece."""
    parts = []
    for i in range(8):
        a = i * math.pi / 4 + math.pi / 8
        cx, cy = COL_RING * math.cos(a), COL_RING * math.sin(a)
        me = prism(f'Column{i}', COL_R, COL_Z0, COL_Z0 + COL_H, 10, COL_R * 0.88, (cx, cy), [mat_stone])
        o = link(bpy.data.objects.new(f'Column{i}', me), coll)
        o.pass_index = PASS['masonry']
        parts.append((o, TL.phase_time('tier3', 0.30 + 0.035 * i)))
        me = prism(f'Capital{i}', COL_R * 1.5, COL_Z0 + COL_H - 0.35, COL_Z0 + COL_H, 8, COL_R * 1.6, (cx, cy), [mat_stone])
        o = link(bpy.data.objects.new(f'Capital{i}', me), coll)
        o.pass_index = PASS['masonry']
        parts.append((o, TL.phase_time('tier3', 0.40 + 0.03 * i)))
    for i in range(8):
        a0 = i * math.pi / 4
        # entablature segments: annular sectors
        ang = np.linspace(a0, a0 + math.pi / 4, 4)
        ro, ri = DRUM_R + 0.05, 2.9
        V, Q = [], []
        for zz in (ENT_Z0, ENT_Z0 + ENT_H):
            for r in (ro, ri):
                for a in ang:
                    V.append([r * math.cos(a), r * math.sin(a), zz])
        # indices: z-level l, ring r (0 outer,1 inner), angle k -> l*8 + r*4 + k
        idx = lambda l, r, k: l * 8 + r * 4 + k  # noqa: E731
        for k in range(3):
            Q.append([idx(0, 0, k), idx(0, 0, k + 1), idx(1, 0, k + 1), idx(1, 0, k)])  # outer
            Q.append([idx(0, 1, k + 1), idx(0, 1, k), idx(1, 1, k), idx(1, 1, k + 1)])  # inner
            Q.append([idx(1, 0, k), idx(1, 0, k + 1), idx(1, 1, k + 1), idx(1, 1, k)])  # top
            Q.append([idx(0, 0, k + 1), idx(0, 0, k), idx(0, 1, k), idx(0, 1, k + 1)])  # bottom
        Q.append([idx(0, 0, 0), idx(1, 0, 0), idx(1, 1, 0), idx(0, 1, 0)])
        Q.append([idx(0, 0, 3), idx(0, 1, 3), idx(1, 1, 3), idx(1, 0, 3)])
        me = mesh_from_arrays(f'Entab{i}', np.array(V), np.array(Q), mats=[mat_stone])
        o = link(bpy.data.objects.new(f'Entab{i}', me), coll)
        o.pass_index = PASS['masonry']
        parts.append((o, TL.phase_time('tier3', 0.50 + 0.02 * i)))
    z = ENT_Z0 + ENT_H
    for i, (r, h) in enumerate(DOME):
        r_next = DOME[i + 1][0] if i + 1 < len(DOME) else 0.9
        me = prism(f'Dome{i}', r, z, z + h, 20, r_next + 0.1, (0, 0), [mat_stone])
        o = link(bpy.data.objects.new(f'Dome{i}', me), coll)
        o.pass_index = PASS['masonry']
        parts.append((o, TL.phase_time('tier3', 0.68 + 0.08 * i)))
        z += h
    me = prism('Pedestal', 1.0, DOME_TOP - 0.05, STATUE_Z, 12, 0.85, (0, 0), [mat_stone])
    o = link(bpy.data.objects.new('Pedestal', me), coll)
    o.pass_index = PASS['masonry']
    parts.append((o, TL.phase_time('tier3', 0.99)))
    return parts


# ============================================================ figures
def skin_figure(name, joints, edges, radii, mat, subsurf=2):
    me = bpy.data.meshes.new(name)
    me.from_pydata(joints, edges, [])
    o = bpy.data.objects.new(name, me)
    sk = o.modifiers.new('Skin', 'SKIN')
    sk.use_smooth_shade = True
    sv = me.skin_vertices[0].data
    for i, r in enumerate(radii):
        sv[i].radius = (r, r) if np.isscalar(r) else r
    sv[0].use_root = True
    ss = o.modifiers.new('Sub', 'SUBSURF')
    ss.levels = subsurf
    ss.render_levels = subsurf
    me.materials.append(mat)
    return o


def statue_zeus(mat):
    """Standing Zeus Soter: himation-draped body, raised sceptre arm (6.2 m)."""
    s = 6.2 / 1.9
    J = [(0, 0, 0.95), (0, 0, 1.25), (0, 0, 1.52), (0, 0, 1.68), (0, 0, 1.82),        # 0 pelvis..4 head
         (-0.12, 0, 0.5), (-0.13, 0.02, 0.06), (0.12, 0, 0.5), (0.14, -0.05, 0.06),     # 5-8 legs
         (-0.2, 0, 1.52), (-0.32, 0.05, 1.3), (-0.34, 0.12, 1.08),                       # 9-11 left arm down
         (0.2, 0, 1.52), (0.36, 0.02, 1.72), (0.42, 0.0, 1.98),                          # 12-14 right arm up
         (0.0, 0, 0.3)]                                                                   # 15 robe hem
    E = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (0, 7), (7, 8), (2, 9), (9, 10), (10, 11),
         (2, 12), (12, 13), (13, 14), (0, 15)]
    R = [0.19, 0.17, 0.2, 0.07, 0.1, 0.1, 0.06, 0.1, 0.06, 0.07, 0.055, 0.05, 0.07, 0.055, 0.05, 0.24]
    J = [(x * s, y * s, z * s) for x, y, z in J]
    R = [r * s for r in R]
    o = skin_figure('Statue', J, E, R, mat)
    # sceptre / spear
    sp = prism('Sceptre', 0.07, 0.0, 7.4, 6, 0.05, (0.42 * s, 0.0), [mat])
    so = bpy.data.objects.new('Sceptre', sp)
    so.location = (0, 0, -0.6)
    return o, so


def triton(mat, name):
    """Kneeling Triton blowing a conch (about 3 m)."""
    J = [(0, 0, 0.6), (0, 0, 1.0), (0, 0.05, 1.3), (0, 0.08, 1.48), (0, 0.1, 1.62),
         (-0.18, 0.1, 0.35), (-0.2, 0.35, 0.1), (0.18, -0.2, 0.35), (0.2, -0.45, 0.05),
         (-0.18, 0.1, 1.3), (-0.2, 0.3, 1.45), (-0.08, 0.35, 1.6),
         (0.18, 0.1, 1.3), (0.2, 0.3, 1.45), (0.08, 0.35, 1.6),
         (0, 0.45, 1.66), (0, 0.8, 1.78)]
    E = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (0, 7), (7, 8), (2, 9), (9, 10), (10, 11),
         (2, 12), (12, 13), (13, 14), (4, 15), (15, 16)]
    R = [0.2, 0.18, 0.2, 0.07, 0.11, 0.1, 0.08, 0.1, 0.08, 0.07, 0.06, 0.05, 0.07, 0.06, 0.05, 0.05, 0.13]
    s = 1.75
    return skin_figure(name, [(x * s, y * s, z * s) for x, y, z in J], E, [r * s for r in R], mat)


def worker_mesh(mat):
    J = [(0, 0, 0.9), (0, 0, 1.2), (0, 0, 1.45), (0, 0, 1.62), (-0.1, 0, 0.45), (-0.1, 0, 0.02),
         (0.1, 0, 0.45), (0.12, 0.05, 0.02), (-0.22, 0.05, 1.1), (0.22, 0.08, 1.05)]
    E = [(0, 1), (1, 2), (2, 3), (0, 4), (4, 5), (0, 6), (6, 7), (2, 8), (2, 9)]
    R = [0.17, 0.17, 0.07, 0.11, 0.08, 0.06, 0.08, 0.06, 0.05, 0.05]
    o = skin_figure('WorkerProto', J, E, R, mat, subsurf=1)
    # bake the modifiers into a plain mesh for cheap instancing
    dg = bpy.context.evaluated_depsgraph_get()
    link(o)
    dg.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    bpy.data.objects.remove(o)
    return me


# ============================================================ timber: scaffolds, props
def scaffold_tier(tb, poly_fn, size_at, z_base, height, sched, t_down, rng, lift=2.3, off=1.5,
                  spacing=3.6, extra_top=1.6, collar=11.0):
    """Putlog scaffolding that climbs with the work: each lift appears when the
    masonry reaches it and is struck again once the walls are `collar` metres
    higher, so the finished ashlar below stays visible (top lifts stay until
    the final dismantling phase t_down)."""
    n_lifts = int(math.ceil((height + extra_top) / lift))
    d0, d1 = t_down
    for L in range(n_lifts):
        z0 = z_base + L * lift
        z1 = z0 + lift
        t_on = sched.time_at(z0 - 0.6)
        if t_on > 1e8:
            continue
        t_off = d0 + (1.0 - L / max(n_lifts - 1, 1)) * (d1 - d0) * 0.85
        t_off = min(t_off, sched.time_at(z1 + collar))
        if t_off <= t_on:
            continue
        P0 = poly_fn(size_at(min(z0, z_base + height)) + off)
        P1 = poly_fn(size_at(min(z1, z_base + height)) + off)
        W1 = poly_fn(size_at(min(z1, z_base + height)) + 0.08)
        n = len(P0)
        for i in range(n):
            j = (i + 1) % n
            side = np.linalg.norm(P1[j] - P1[i])
            npol = max(1, int(round(side / spacing)))
            for kk in range(npol):
                u = kk / npol
                p0 = np.append(P0[i] + (P0[j] - P0[i]) * u, z0)
                p1 = np.append(P1[i] + (P1[j] - P1[i]) * u, z1 + 0.05)
                jit = rng.normal(0, 0.03, 3)
                jit[2] = 0
                tb.add(G.beam(p0 + jit, p1 + jit, 0.16), t_on, t_off, M_WOOD)
                w1 = np.append(W1[i] + (W1[j] - W1[i]) * u, z1 - 0.1)
                tb.add(G.beam(w1, p1 - [0, 0, 0.1], 0.12), t_on + 0.04, t_off, M_WOOD)
                if (kk + 2 * L) % 5 == 0 and kk + 1 <= npol:
                    u2 = (kk + 1) / npol
                    q0 = np.append(P0[i] + (P0[j] - P0[i]) * u, z0 + 0.1)
                    q1 = np.append(P1[i] + (P1[j] - P1[i]) * u2, z1 - 0.1)
                    nrm = np.append(np.array([P0[j][1] - P0[i][1], -(P0[j][0] - P0[i][0])]) / max(side, 1e-6), 0)
                    tb.add(G.beam(q0 + nrm * 0.16, q1 + nrm * 0.16, 0.1), t_on + 0.06, t_off, M_WOOD)
            a = np.append(P1[i], z1 - 0.1)
            b = np.append(P1[j], z1 - 0.1)
            tb.add(G.beam(a, b, 0.12), t_on + 0.05, t_off, M_WOOD)
            nb_ = max(1, int(round(side / 3.0)))
            for kk in range(nb_):
                u0, u1 = kk / nb_, (kk + 1) / nb_
                quad = [W1[i] + (W1[j] - W1[i]) * u0, W1[i] + (W1[j] - W1[i]) * u1,
                        P1[i] + (P1[j] - P1[i]) * u1, P1[i] + (P1[j] - P1[i]) * u0]
                tb.add(G.quad_slab(quad, z1 - 0.03, z1 + 0.04), t_on + 0.1 + 0.02 * kk, t_off, M_PLANK)


def build_timber(sched):
    tb = G.HexBatch('timber')
    rng = np.random.default_rng(11)
    s1 = lambda z: T1_A0 + (T1_A1 - T1_A0) * np.clip((z - T1_Z0) / T1_H, 0, 1)  # noqa: E731
    s2 = lambda z: T2_A0 + (T2_A1 - T2_A0) * np.clip((z - T2_Z0) / T2_H, 0, 1)  # noqa: E731
    scaffold_tier(tb, G.square_poly, s1, T1_Z0, T1_H, sched, TL.PHASES['scaf1_down'], rng, extra_top=1.2)
    scaffold_tier(tb, G.oct_poly, s2, T2_Z0, T2_H, sched, TL.PHASES['scaf2_down'], rng, off=1.3, extra_top=1.0)
    # lantern scaffold: a simple tower of poles around the drum
    d0, d1 = TL.PHASES['scaf2_down']
    t3a, t3b = TL.PHASES['tier3']
    for L in range(5):
        z0 = T3_Z0 + L * 2.0
        P = G.circle_poly(DRUM_R + 1.5, 10)
        for i in range(10):
            j = (i + 1) % 10
            t_on = t3a + (t3b - t3a) * L / 5
            tb.add(G.beam(np.append(P[i], z0), np.append(P[i], z0 + 2.05), 0.15), t_on, d0 + 0.2, M_WOOD)
            tb.add(G.beam(np.append(P[i], z0 + 1.95), np.append(P[j], z0 + 1.95), 0.12), t_on, d0 + 0.2, M_WOOD)
            Wi = G.circle_poly(DRUM_R + 0.1, 10)
            tb.add(G.quad_slab([Wi[i], Wi[j], P[j], P[i]], z0 + 1.95, z0 + 2.02), t_on, d0 + 0.2, M_PLANK)

    # survey stakes and ropes marking out the podium
    a = PLAT_A[0] + 0.5
    t_s0, t_s1 = TL.PHASES['survey']
    corners = [(-a, -a), (a, -a), (a, a), (-a, a)]
    stakes = []
    for i in range(4):
        p, q = np.array(corners[i]), np.array(corners[(i + 1) % 4])
        for u in np.linspace(0, 1, 7)[:-1]:
            stakes.append(p + (q - p) * u)
    for k, s in enumerate(stakes):
        t_on = t_s0 + 0.5 * k / len(stakes)
        tb.add(G.beam(np.append(s, GROUND_Z - 0.2), np.append(s, GROUND_Z + 1.1), 0.12), t_on, t_s1 + 0.3, M_WOOD)
    for k in range(len(stakes)):
        s, s2 = stakes[k], stakes[(k + 1) % len(stakes)]
        tb.add(G.beam(np.append(s, GROUND_Z + 0.9), np.append(s2, GROUND_Z + 0.9), 0.04),
               t_s0 + 0.55 + 0.3 * k / len(stakes), t_s1 + 0.3, M_ROPE)
    for d in (np.array([[-a, 0], [a, 0]]), np.array([[0, -a], [0, a]])):
        tb.add(G.beam(np.append(d[0], GROUND_Z + 0.9), np.append(d[1], GROUND_Z + 0.9), 0.04),
               t_s0 + 0.95, t_s1 + 0.3, M_ROPE)
    return tb.finalize()


def build_props(coll, mats):
    """Static site props: tents, huts, quay, timber piles, the Heptastadion."""
    pb = G.HexBatch('props')
    rng = np.random.default_rng(5)
    # workers' camp (west of the podium)
    for i in range(9):
        cx = -62 - (i % 3) * 9 + rng.uniform(-2, 2)
        cy = -26 + (i // 3) * 12 + rng.uniform(-2, 2)
        pb.add(G.tent(cx, cy, GROUND_Z - 0.1, 6.0, 4.0, 2.6, rng.uniform(-0.3, 0.3)), mat=2)
    for i in range(3):
        cx, cy = -64 + i * 10, 26 + rng.uniform(-2, 2)
        pb.add(G.box(cx, cy, GROUND_Z - 0.2, 7.0, 5.0, 3.0, 0.1), mat=0)
        pb.add(G.tent(cx, cy, GROUND_Z + 2.8, 7.6, 5.6, 1.3, 0.1), mat=1)
    # quay on the south shore where the stone barges dock
    pb.add(G.box(36, -84, -3.0, 12.0, 40.0, 5.8, 0.0), mat=0)
    pb.add(G.box(36, -104, -3.0, 22.0, 8.0, 5.8, 0.0), mat=0)
    # timber piles
    for i in range(3):
        cx, cy = 48 + i * 5, 30 - i * 6
        for L in range(4):
            for k in range(5 - L):
                y = cy + (k - (4 - L) / 2) * 0.45
                pb.add(G.beam([cx - 4, y, GROUND_Z + 0.2 + L * 0.4], [cx + 4, y, GROUND_Z + 0.2 + L * 0.4], 0.4), mat=1)
    # the Heptastadion causeway to the mainland
    pb.add(G.box(-950, -720, -4.0, 26.0, 1150.0, 7.2), mat=3)
    pb.add(G.box(-950, -720, 3.2, 3.0, 1150.0, 1.2), mat=3)
    pb = pb.finalize()
    me = hex_mesh('Props', pb, np.ones(len(pb.t_on), bool), mats)
    o = link(bpy.data.objects.new('Props', me), coll)
    o.pass_index = PASS['props']
    return o


def build_island_life(coll, mats):
    """Scrub, date palms, a fishing village and a small temple on Pharos island."""
    from scipy.spatial import ConvexHull
    rng = np.random.default_rng(31)
    m_bush, m_trunk, m_frond, m_house, m_temple = mats
    # --- scrub bushes (faceted blobs)
    V, F = [], []
    xs = rng.uniform(-900, 120, 9000)
    ys = rng.uniform(-260, 240, 9000)
    d = island_sd(xs, ys)
    r = np.hypot(xs, ys)
    clump = G.fbm(xs / 45.0, ys / 45.0, 3, seed=12)
    ok = (d < -14) & (r > 88) & ~((xs < -40) & (xs > -100) & (np.abs(ys) < 45)) & (clump > 0.18)
    for x, y in list(zip(xs[ok], ys[ok]))[:380]:
        rad = rng.uniform(0.6, 1.7)
        pts = rng.normal(size=(12, 3))
        pts /= np.linalg.norm(pts, axis=1, keepdims=True)
        pts *= [rad, rad, rad * 0.7]
        hull = ConvexHull(pts)
        z = float(island_height(np.array([x]), np.array([y]))[0])
        base = len(V)
        for q in pts:
            V.append([x + q[0], y + q[1], z + q[2] + rad * 0.35])
        for a, b, c in hull.simplices:
            if np.dot(np.cross(pts[b] - pts[a], pts[c] - pts[a]), pts[a]) < 0:
                b, c = c, b
            F.append([base + a, base + b, base + c])
    me = mesh_from_arrays('Scrub', np.array(V), np.array(F), mats=[m_bush])
    o = link(bpy.data.objects.new('Scrub', me), coll)
    o.pass_index = PASS['props']

    # --- date palms: segmented leaning trunks + drooping fronds
    pb = G.HexBatch('palms')
    spots = []
    while len(spots) < 34:
        x, y = rng.uniform(-700, 60), rng.uniform(-200, 200)
        if island_sd(np.array([x]), np.array([y]))[0] < -18 and math.hypot(x, y) > 95:
            spots.append((x, y))
    for (x, y) in spots:
        z = float(island_height(np.array([x]), np.array([y]))[0]) - 0.3
        h = rng.uniform(9, 15)
        lean = rng.uniform(0.05, 0.25)
        la = rng.uniform(0, 2 * math.pi)
        prev = np.array([x, y, z])
        segs = 7
        for k in range(1, segs + 1):
            f = k / segs
            p = np.array([x + math.cos(la) * lean * h * f * f, y + math.sin(la) * lean * h * f * f, z + h * f])
            pb.add(G.beam(prev, p, 0.45 - 0.12 * f), mat=0)
            prev = p
        top = prev
        for j in range(13):
            a = j * 2 * math.pi / 13 + rng.uniform(-0.2, 0.2)
            L = rng.uniform(3.5, 5.0)
            droop = rng.uniform(0.25, 0.7)
            q0 = top
            for k in range(1, 4):
                f = k / 3
                q1 = top + np.array([math.cos(a) * L * f, math.sin(a) * L * f, 0.9 * f - droop * L * f * f])
                pb.add(G.beam(q0, q1, 0.55 * (1 - 0.5 * f), 0.05), mat=1)
                q0 = q1
    pb.finalize()
    me = hex_mesh('Palms', pb, np.ones(len(pb.t_on), bool), [m_trunk, m_frond])
    o = link(bpy.data.objects.new('Palms', me), coll)
    o.pass_index = PASS['props']

    # --- fishing village on the western island + temple of Isis Pharia
    vb = G.HexBatch('village')
    n = 0
    while n < 90:
        x, y = rng.uniform(-1500, -380), rng.uniform(-170, 170)
        if island_sd(np.array([x]), np.array([y]))[0] > -20:
            continue
        z = float(island_height(np.array([x]), np.array([y]))[0]) - 0.5
        w, dd, hh = rng.uniform(6, 12), rng.uniform(6, 12), rng.uniform(3.5, 6.5)
        vb.add(G.box(x, y, z, w, dd, hh, rng.uniform(-0.3, 0.3)), mat=0, tone=rng.random())
        n += 1
    tx, ty = -330.0, 58.0
    tz = float(island_height(np.array([tx]), np.array([ty]))[0]) - 0.3
    vb.add(G.box(tx, ty, tz, 22, 36, 2.2), mat=1, tone=0.5)
    for i in range(6):
        for j in range(10):
            if 0 < i < 5 and 0 < j < 9:
                continue
            vb.add(G.box(tx - 9 + i * 3.6, ty - 16 + j * 3.55, tz + 2.2, 1.1, 1.1, 7.5), mat=1, tone=0.5)
    vb.add(G.box(tx, ty, tz + 2.2, 11, 22, 7.5), mat=1, tone=0.4)
    vb.add(G.box(tx, ty, tz + 9.7, 21, 35, 1.4), mat=1, tone=0.55)
    vb.add(G.tent(tx, ty, tz + 11.1, 35.2, 21.2, 3.2, math.pi / 2), mat=1, tone=0.55)
    vb.finalize()
    me = hex_mesh('Village', vb, np.ones(len(vb.t_on), bool), [m_house, m_temple])
    o = link(bpy.data.objects.new('Village', me), coll)
    o.pass_index = PASS['props']


def build_city(coll, mat_city):
    """Alexandria across the Great Harbour: whitewashed blocks, temples, palaces."""
    cb = G.HexBatch('city')
    rng = np.random.default_rng(17)
    n = 0
    tries = 0
    while n < 1300 and tries < 20000:
        tries += 1
        x = rng.uniform(-3600, 3200)
        yc = float(coast_y(np.array([x]))[0])
        depth = rng.exponential(420)
        y = yc - 35 - depth
        if y < -4200:
            continue
        if abs(x + 950) < 30 and y > yc - 60:
            continue
        w = rng.uniform(9, 26)
        d = rng.uniform(9, 26)
        h = rng.uniform(5, 13) * (1.3 if rng.random() < 0.15 else 1.0)
        rot = rng.normal(0, 0.05) + (0.0 if rng.random() < 0.8 else math.pi / 4)
        cb.add(G.box(x, y, 2.0, w, d, h + 1.5, rot), mat=0, tone=rng.random())
        if rng.random() < 0.3:
            cb.add(G.box(x + rng.uniform(-2, 2), y + rng.uniform(-2, 2), 3.5 + h, w * 0.5, d * 0.5, 3.0, rot), mat=0)
        n += 1
    # monumental buildings: temples with pitched roofs, palace blocks on Lochias
    for (x, y, w, d, h) in [(-300, -1480, 50, 90, 18), (400, -1560, 70, 40, 16), (1650, -820, 120, 70, 20),
                            (1500, -950, 60, 60, 24), (-1400, -1500, 45, 80, 17), (900, -1420, 55, 55, 22)]:
        cb.add(G.box(x, y, 2.0, w, d, h), mat=1, tone=0.5)
        cb.add(G.tent(x, y, 2.0 + h, d * 1.02, w * 1.02, h * 0.35, math.pi / 2), mat=1, tone=0.5)
    cb = cb.finalize()
    me = hex_mesh('City', cb, np.ones(len(cb.t_on), bool), [mat_city, mat_city])
    o = link(bpy.data.objects.new('City', me), coll)
    o.pass_index = PASS['city']
    return o


def mat_city_mat():
    m, nb, out = new_material('City')
    tone = nb.attr('tone').outputs['Fac']
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    fs = nb.attr('fsize').outputs['Vector']
    u, v, _ = nb.sep(uv)
    w, h, _ = nb.sep(fs)
    base = nb.mix(tone, (0.42, 0.38, 0.31, 1), (0.62, 0.58, 0.5, 1))
    # windows: grid cells, randomly lit at night
    cu = nb.math('FLOOR', nb.math('DIVIDE', u, 3.2))
    cv = nb.math('FLOOR', nb.math('DIVIDE', v, 3.4))
    fu = nb.math('FRACT', nb.math('DIVIDE', u, 3.2))
    fv = nb.math('FRACT', nb.math('DIVIDE', v, 3.4))
    win = nb.math('MULTIPLY', nb.math('MULTIPLY', nb.smooth(0.3, 0.36, fu), nb.smooth(0.7, 0.64, fu)),
                  nb.math('MULTIPLY', nb.smooth(0.3, 0.36, fv), nb.smooth(0.72, 0.66, fv)))
    wn = nb.new('ShaderNodeTexWhiteNoise', noise_dimensions='3D')
    nb.feed(wn.inputs['Vector'], nb.comb(cu, cv, nb.math('MULTIPLY', tone, 97.0)))
    lit = nb.math('GREATER_THAN', wn.outputs['Value'], 0.72)
    # only on vertical faces that are big enough
    geo = nb.new('ShaderNodeNewGeometry')
    nz = nb.math('ABSOLUTE', nb.sep(geo.outputs['Normal'])[2])
    vert = nb.math('LESS_THAN', nz, 0.3)
    k = nb.value(0.0, 'city_lights')
    e = nb.math('MULTIPLY', nb.math('MULTIPLY', win, lit), nb.math('MULTIPLY', vert, k))
    b = principled(nb, base, 0.9, 0.0, 0.3, (1.0, 0.55, 0.22, 1), e)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_fire():
    m, nb, out = new_material('Fire')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    tw = nb.value(0.0, 'fire_time')
    n = nb.noise(pos, 2.2, 4.0, 0.6, w=tw, dims='4D').outputs['Fac']
    z = nb.sep(pos)[2]
    hz = nb.math('SUBTRACT', z, FIRE_POS[2] - 1.4)
    col = nb.ramp(nb.math('ADD', nb.math('MULTIPLY', hz, -0.22), nb.math('MULTIPLY', n, 0.9)),
                  [(0.0, (0.9, 0.12, 0.01)), (0.45, (1.0, 0.42, 0.05)), (0.75, (1.0, 0.78, 0.35)), (1.0, (1.0, 0.95, 0.8))])
    em = nb.new('ShaderNodeEmission')
    nb.feed(em.inputs['Color'], col)
    k = nb.value(0.0, 'fire_k')
    nb.feed(em.inputs['Strength'], nb.math('MULTIPLY', k, nb.math('ADD', 1.5, nb.math('MULTIPLY', n, 5.0))))
    nb.feed(out.inputs['Surface'], em.outputs[0])
    return m


def mat_torch():
    m, nb, out = new_material('TorchFlame')
    em = nb.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (1.0, 0.45, 0.1, 1)
    k = nb.value(0.0, 'torch_k')
    nb.feed(em.inputs['Strength'], nb.math('MULTIPLY', k, 40.0))
    nb.feed(out.inputs['Surface'], em.outputs[0])
    return m


# ============================================================ cranes / ships
def crane_mesh(mats, mast_h=9.0, boom_len=13.0, boom_el=55.0):
    cb = G.HexBatch('crane')
    be = math.radians(boom_el)
    tip = np.array([boom_len * math.cos(be), 0.0, 1.0 + boom_len * math.sin(be)])
    cb.add(G.beam([0, 0, 0], [0, 0, mast_h], 0.36), mat=0)
    cb.add(G.beam([0, 0, 1.0], tip, 0.3), mat=0)
    cb.add(G.beam([0, 0, mast_h], tip, 0.06), mat=1)            # stay
    cb.add(G.beam([0, 0, mast_h], [-6.0, 0, 0.2], 0.06), mat=1)   # back stays
    cb.add(G.beam([-6.0, -2.5, 0.0], [-6.0, 2.5, 0.0], 0.25), mat=0)
    cb.add(G.beam([0, 0, mast_h], [-5.0, -3.5, 0.2], 0.05), mat=1)
    cb.add(G.beam([0, 0, mast_h], [-5.0, 3.5, 0.2], 0.05), mat=1)
    cb.add(G.beam([-1.2, -1.0, 0.2], [-1.2, 1.0, 0.2], 0.25), mat=0)  # winch drum frame
    cb.add(G.box(-1.2, 0.0, 0.0, 1.0, 1.6, 1.2), mat=0)
    cb.add(G.beam([-1.5, -1.5, 0.0], [1.5, 1.5, 0.0], 0.3), mat=0)     # base cross
    cb.add(G.beam([-1.5, 1.5, 0.0], [1.5, -1.5, 0.0], 0.3), mat=0)
    cb = cb.finalize()
    return hex_mesh('CraneMesh', cb, np.ones(len(cb.t_on), bool), mats), tip


def ship_mesh(mats, length=22.0, beam_w=6.0, sail=True):
    """Hellenistic merchantman: lofted hull, stern post, mast, yard, square sail."""
    ns, nt = 16, 9
    V = []
    for i in range(ns):
        s = i / (ns - 1)
        x = (s - 0.5) * length
        wdt = beam_w * 0.5 * (math.sin(math.pi * s) ** 0.55)
        dep = 2.2 * (0.35 + 0.65 * math.sin(math.pi * s) ** 0.8)
        sheer = 1.4 + 1.8 * abs(2 * s - 1) ** 3
        for k in range(nt):
            th = -math.pi / 2 + math.pi * k / (nt - 1)
            y = wdt * math.sin(th)
            z = -dep * math.cos(th) * 0.9 if abs(th) < math.pi / 2 - 1e-6 else 0.0
            if k in (0, nt - 1):
                z = sheer
            V.append([x, y, z])
    Q = []
    for i in range(ns - 1):
        for k in range(nt - 1):
            a = i * nt + k
            Q.append([a, a + nt, a + nt + 1, a + 1])
    hull = mesh_from_arrays('Hull', np.array(V), np.array(Q), mats=[mats[0]], smooth=True)
    sb = G.HexBatch('rig')
    sb.add(G.box(0, 0, 0.9, length * 0.8, beam_w * 0.75, 0.25), mat=0)                # deck
    sb.add(G.beam([-length * 0.5, 0, 3.0], [-length * 0.62, 0, 5.2], 0.5), mat=0)       # stern post
    sb.add(G.beam([length * 0.05, 0, 1.0], [length * 0.05, 0, 15.0], 0.4), mat=0)       # mast
    sb.add(G.beam([length * 0.05, -6.5, 14.2], [length * 0.05, 6.5, 14.2], 0.3), mat=0)  # yard
    if sail:
        sb.add(G.quad_slab([[length * 0.05 - 0.1, -6.2], [length * 0.05 + 0.1, -6.2],
                            [length * 0.05 + 0.1, 6.2], [length * 0.05 - 0.1, 6.2]], 5.0, 14.1), mat=1)
    sb.add(G.box(-length * 0.3, 0, 1.1, 4.0, 3.2, 2.0), mat=0)                           # deck house
    sb = sb.finalize()
    rig = hex_mesh('Rig', sb, np.ones(len(sb.t_on), bool), mats)
    return hull, rig


def barge_cargo_mesh(mat):
    bb = G.HexBatch('cargo')
    for i in range(3):
        for j in range(2):
            bb.add(G.box(-4 + i * 3.2, -1.2 + j * 2.4, 1.1, 3.0, 2.2, 1.2), mat=0)
    bb.add(G.box(-2.4, 0, 2.3, 3.0, 2.2, 1.1), mat=0)
    bb = bb.finalize()
    return hex_mesh('Cargo', bb, np.ones(len(bb.t_on), bool), [mat])


# ============================================================ build
class State:
    pass


def build(res=(1280, 720)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = TL.FPS
    sc.frame_start, sc.frame_end = 0, TL.NFRAMES - 1
    S = State()
    S.sched = Schedule()
    coll = sc.collection

    # materials
    S.m_stone = mat_masonry('Limestone', (0.74, 0.66, 0.53), (0.30, 0.26, 0.21))
    S.m_stone_dark = mat_masonry('Podium', (0.58, 0.53, 0.45), (0.22, 0.20, 0.17), var=0.12)
    S.m_floor = mat_masonry('Paving', (0.55, 0.49, 0.40), (0.20, 0.17, 0.14), width=0.04)
    S.m_wood = mat_wood('Timber', (0.42, 0.30, 0.18))
    S.m_plank = mat_wood('Planks', (0.52, 0.40, 0.26), width=0.04)
    S.m_rope = mat_simple('Rope', (0.12, 0.09, 0.06), 0.9)
    S.m_bronze = mat_simple('Bronze', (0.62, 0.42, 0.20), 0.32, 1.0)
    S.m_cloth = mat_simple('Canvas', (0.55, 0.49, 0.40), 0.9)
    S.m_cloth2 = mat_simple('CanvasDark', (0.38, 0.22, 0.14), 0.9)
    S.m_hull = mat_wood('Hull', (0.16, 0.10, 0.06))
    S.m_sail = mat_simple('Sail', (0.62, 0.55, 0.44), 0.9)
    S.m_worker = mat_objcolor('Worker')
    S.m_fire = mat_fire()
    S.m_torch = mat_torch()
    S.m_city = mat_city_mat()

    S.world = build_world()
    S.flat_world = build_flat_world()
    S.terrain = build_terrain(coll)
    S.sea, S.ocean = build_sea(coll)
    S.boulders = build_boulders(coll)
    S.cloud_shadow, S.m_cshadow = build_cloud_shadows(coll)

    # masonry (dynamic mesh rebuilt per frame)
    S.masonry = build_masonry(S.sched)
    S.sched.finalize()
    S.mas_obj = link(bpy.data.objects.new('Masonry', bpy.data.meshes.new('Masonry')), coll)
    S.mas_obj.pass_index = PASS['masonry']
    S.mas_mats = [S.m_stone, S.m_stone_dark, S.m_floor]
    S.timber = build_timber(S.sched)
    S.tim_obj = link(bpy.data.objects.new('Timber', bpy.data.meshes.new('Timber')), coll)
    S.tim_obj.pass_index = PASS['timber']
    S.tim_mats = [S.m_wood, S.m_plank, S.m_rope]
    S.lantern = build_lantern(coll, S.m_stone, S.m_bronze)

    # statue + sceptre, tritons
    S.statue, S.sceptre = statue_zeus(S.m_bronze)
    link(S.statue, coll)
    link(S.sceptre, coll)
    S.sceptre.parent = S.statue
    S.statue.pass_index = S.sceptre.pass_index = PASS['statue']
    S.tritons = []
    ap = T1_A1 + CORNICE1[-1][0] - 1.4
    for i, (sx, sy) in enumerate([(1, 1), (-1, 1), (-1, -1), (1, -1)]):
        tr = link(triton(S.m_bronze, f'Triton{i}'), coll)
        tr.location = (sx * ap, sy * ap, T1_ROOF + 1.2)
        tr.rotation_euler = (0, 0, math.atan2(sy, sx) - math.pi / 2)
        tr.pass_index = PASS['statue']
        me = prism(f'TritonBase{i}', 1.0, T1_ROOF - 0.05, T1_ROOF + 1.2, 4, 0.95, (sx * ap, sy * ap), [S.m_stone])
        base = link(bpy.data.objects.new(f'TritonBase{i}', me), coll)
        base.pass_index = PASS['masonry']
        t_on = TL.phase_time('tier1cap', 0.86 + 0.03 * i)
        S.tritons += [(tr, t_on), (base, t_on - 0.1)]

    # props, city
    S.props = build_props(coll, [S.m_stone_dark, S.m_wood, S.m_cloth, S.m_stone_dark])
    S.city = build_city(coll, S.m_city)
    build_island_life(coll, [mat_simple('Scrub', (0.11, 0.13, 0.065), 0.95),
                             mat_wood('PalmTrunk', (0.2, 0.15, 0.1)),
                             mat_simple('Frond', (0.07, 0.1, 0.04), 0.8),
                             S.m_city, S.m_stone])
    S.stack_obj = link(bpy.data.objects.new('Stacks', bpy.data.meshes.new('Stacks')), coll)
    S.stack_obj.pass_index = PASS['props']

    # fire: flame tongues + point light
    S.flames = []
    for i in range(7):
        a = i * 2 * math.pi / 7
        r = 0.0 if i == 0 else 1.15
        me = prism(f'Flame{i}', 1.25 if i == 0 else 0.75, 0.0, 4.6 if i == 0 else 3.0, 8, 0.02,
                   (0, 0), [S.m_fire])
        fo = link(bpy.data.objects.new(f'Flame{i}', me), coll)
        fo.location = (r * math.cos(a), r * math.sin(a), COL_Z0 + 0.05)
        fo.pass_index = PASS['fire']
        fo.visible_shadow = False
        S.flames.append(fo)
    me = prism('Brazier', 1.6, COL_Z0 - 0.02, COL_Z0 + 0.5, 12, 1.9, (0, 0), [S.m_bronze])
    S.brazier = link(bpy.data.objects.new('Brazier', me), coll)
    S.brazier.pass_index = PASS['statue']
    ld = bpy.data.lights.new('Beacon', 'POINT')
    ld.shadow_soft_size = 1.2
    ld.color = (1.0, 0.52, 0.18)
    S.beacon = link(bpy.data.objects.new('Beacon', ld), coll)
    S.beacon.location = FIRE_POS
    S.embers = []
    em_me = prism('Ember', 0.08, 0, 0.16, 4, 0.08, (0, 0), [S.m_fire])
    for i in range(26):
        eo = link(bpy.data.objects.new(f'Ember{i}', em_me), coll)
        eo.pass_index = PASS['fire']
        eo.visible_shadow = False
        S.embers.append(eo)

    # torches / braziers / campfires (point lights + small flames)
    S.torches = []
    t_me = prism('TorchFlame', 0.28, 0.0, 0.9, 6, 0.02, (0, 0), [S.m_torch])
    for i in range(16):
        ld = bpy.data.lights.new(f'Torch{i}', 'POINT')
        ld.color = (1.0, 0.5, 0.2)
        ld.shadow_soft_size = 0.4
        lo = link(bpy.data.objects.new(f'Torch{i}', ld), coll)
        fo = link(bpy.data.objects.new(f'TorchFlame{i}', t_me), coll)
        fo.pass_index = PASS['torch']
        fo.visible_shadow = False
        S.torches.append((lo, fo))

    # sun + moon
    ld = bpy.data.lights.new('Sun', 'SUN')
    ld.angle = math.radians(1.0)
    S.sun = link(bpy.data.objects.new('Sun', ld), coll)
    ld = bpy.data.lights.new('Moon', 'SUN')
    ld.angle = math.radians(1.5)
    ld.color = (0.55, 0.68, 1.0)
    S.moon = link(bpy.data.objects.new('Moon', ld), coll)

    # cranes
    cm, S.crane_tip = crane_mesh([S.m_wood, S.m_rope])
    S.cranes = []
    rope_me = G.HexBatch('rope')
    rope_me.add(G.beam([0, 0, -1.0], [0, 0, 0.0], 0.09), mat=0)
    rope_me.finalize()
    rope_mesh = hex_mesh('RopeUnit', rope_me, np.ones(1, bool), [S.m_rope])
    load_b = G.HexBatch('load')
    load_b.add(G.box(0, 0, -1.0, 1.8, 1.1, 1.0), mat=0)
    load_b.add(G.beam([-0.9, 0, 0.0], [0.9, 0, 0.0], 0.08), mat=1)
    load_b.finalize()
    load_mesh = hex_mesh('LoadBlock', load_b, np.ones(2, bool), [S.m_stone, S.m_rope])
    cm_tall, S.crane_tip_tall = crane_mesh([S.m_wood, S.m_rope], mast_h=12.0, boom_len=20.0, boom_el=65.0)
    for i in range(6):
        c = link(bpy.data.objects.new(f'Crane{i}', cm_tall if i == 4 else cm), coll)
        r = link(bpy.data.objects.new(f'Rope{i}', rope_mesh), coll)
        ld_ = link(bpy.data.objects.new(f'Load{i}', load_mesh), coll)
        for o in (c, r, ld_):
            o.pass_index = PASS['crane']
        S.cranes.append((c, r, ld_))
    # statue hoist rope
    S.hoist = link(bpy.data.objects.new('HoistRope', rope_mesh), coll)
    S.hoist.pass_index = PASS['crane']

    # workers
    wm = worker_mesh(S.m_worker)
    S.workers = []
    palette = [(0.62, 0.58, 0.5), (0.55, 0.45, 0.32), (0.45, 0.2, 0.12), (0.7, 0.66, 0.58),
               (0.35, 0.3, 0.25), (0.5, 0.36, 0.2)]
    for i in range(70):
        o = link(bpy.data.objects.new(f'Worker{i}', wm), coll)
        o.color = palette[i % len(palette)] + (1.0,)
        o.pass_index = PASS['worker']
        S.workers.append(o)

    # ships and barges
    S.ships = []
    for i in range(5):
        hull, rig = ship_mesh([S.m_hull, S.m_sail], length=rng_global.uniform(18, 28))
        h = link(bpy.data.objects.new(f'Ship{i}', hull), coll)
        r = link(bpy.data.objects.new(f'ShipRig{i}', rig), coll)
        r.parent = h
        h.pass_index = r.pass_index = PASS['ship']
        S.ships.append((h, r))
    S.barges = []
    cargo = barge_cargo_mesh(S.m_stone)
    for i in range(3):
        hull, rig = ship_mesh([S.m_hull, S.m_sail], length=16.0, beam_w=6.5, sail=False)
        h = link(bpy.data.objects.new(f'Barge{i}', hull), coll)
        r = link(bpy.data.objects.new(f'BargeRig{i}', rig), coll)
        cg = link(bpy.data.objects.new(f'BargeCargo{i}', cargo), coll)
        r.parent = h
        cg.parent = h
        for o in (h, r, cg):
            o.pass_index = PASS['ship']
        S.barges.append((h, r, cg))

    # camera
    cd = bpy.data.cameras.new('Cam')
    cd.lens = CAM_LENS
    cd.sensor_width = 36
    cd.clip_start = 1.0
    cd.clip_end = 40000
    S.cam = link(bpy.data.objects.new('Cam', cd), coll)
    sc.camera = S.cam
    S.cam_track = camera_track(S.sched)
    return S


# ============================================================ camera
# camera keys: (t, distance, camera height, target height, azimuth deg)
CAM_KEYS = [
    (0.0, 118, 21, 4.0, 44), (2.0, 122, 23, 5.0, 47), (4.6, 136, 26, 9.0, 52),
    (8.0, 168, 30, 20.0, 60), (12.0, 205, 33, 31.0, 69), (15.5, 245, 35, 41.0, 78),
    (19.0, 285, 36, 50.0, 88), (22.5, 318, 34, 56.0, 98), (25.0, 330, 29, 52.0, 106),
    (26.6, 354, 22, 33.0, 111), (30.0, 376, 19, 24.0, 118),
]
CAM_LENS = 38.0


def camera_track(sched):
    """Smooth, slowly orbiting crane move; pulls back and rises with the tower."""
    track = []
    ks = CAM_KEYS
    for i in range(TL.NFRAMES):
        t = i / TL.FPS
        d, cz, tz, az = (TL._pchip([k[0] for k in ks], [k[j] for k in ks], t) for j in (1, 2, 3, 4))
        a = math.radians(az)
        track.append(((d * math.cos(a), d * math.sin(a), cz), (0.0, 0.0, tz)))
    return track


def look_at(obj, loc, target):
    loc = Vector(loc)
    d = Vector(target) - loc
    obj.location = loc
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


# ============================================================ per-frame pose
def set_dynamic_mesh(obj, name, batch, sel, mats):
    old = obj.data
    obj.data = hex_mesh(name, batch, sel, mats)
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)


def smooth_rand(seed, t, rate):
    """Deterministic piecewise-eased random value in [0,1) changing `rate` times per second."""
    x = t * rate
    i = math.floor(x)
    f = TL.ease(x - i)
    a = G._hash2(np.int64(i), np.int64(seed), 5)
    b = G._hash2(np.int64(i + 1), np.int64(seed), 5)
    return float(a + (b - a) * f)


def hop(seed, t, rate):
    """Random value held constant for 1/rate seconds (time-lapse 'jumps')."""
    return float(G._hash2(np.int64(math.floor(t * rate)), np.int64(seed), 9))


def tier_size(z):
    if z < T1_Z0:
        return PLAT_A[0]
    if z <= T1_TOP:
        return T1_A0 + (T1_A1 - T1_A0) * (z - T1_Z0) / T1_H
    if z <= T2_Z0:
        return T1_A1
    return T2_A0 + (T2_A1 - T2_A0) * min((z - T2_Z0) / T2_H, 1.0)


def top_ring_point(z, u, inset):
    """A point on top of the walls of the tier being built (u in [0,1) around)."""
    if z <= T1_ROOF + 0.2:
        P = G.square_poly(tier_size(z) - inset)
    else:
        P = G.oct_poly(tier_size(z) - inset)
    n = len(P)
    s = u * n
    i = int(s) % n
    f = s - int(s)
    p = P[i] + (P[(i + 1) % n] - P[i]) * f
    return float(p[0]), float(p[1])


def pose(S, t):
    sc = bpy.context.scene
    hour = TL.clock(t)
    el, az = TL.sun_angles(hour)
    el_deg = math.degrees(el)
    day = TL.daylight(t)
    night = 1.0 - day
    H = S.sched.height(t)

    # --- masonry & timber
    set_dynamic_mesh(S.mas_obj, 'Masonry', S.masonry, S.masonry.select(t), S.mas_mats)
    set_dynamic_mesh(S.tim_obj, 'Timber', S.timber, S.timber.select(t), S.tim_mats)
    for o, t_on in S.lantern + S.tritons:
        o.hide_render = t < t_on
    S.brazier.hide_render = t < TL.phase_time('tier3', 0.29)

    # --- stone stacks on the yard (depleted and re-stocked)
    sb = G.HexBatch('stacks')
    t_end = TL.PHASES['tier3'][1]
    for k, (cx, cy) in enumerate([(-38, -40), (-44, 8), (40, -46), (22, -54), (-20, -52), (46, 40)]):
        if t > t_end + 0.8:
            layers = 0 if k % 2 else 1
        else:
            layers = 1 + int(3.99 * smooth_rand(k + 50, t, 0.8))
        for L in range(layers):
            for i in range(4 - (L > 1)):
                for j in range(3):
                    sb.add(G.box(cx + (i - 1.5) * 2.0, cy + (j - 1) * 1.3, GROUND_Z + L * 1.0, 1.9, 1.2, 0.98),
                           mat=0, tone=G._hash2(np.int64(k * 100 + i * 10 + j), np.int64(L), 3))
    sb.finalize()
    set_dynamic_mesh(S.stack_obj, 'Stacks', sb, np.ones(len(sb.t_on), bool), [S.m_stone])

    # --- cranes: two on the rising walls, one per terrace later, two at the quay
    tip = S.crane_tip
    t1a, t1b = TL.PHASES['tier1']
    t2a, t2b = TL.PHASES['tier2']
    t3a, t3b = TL.PHASES['tier3']
    st0, st1 = TL.PHASES['statue']
    removal = TL.PHASES['scaf2_down'][0] + 0.4
    specs = []
    zt = max(H, PLAT_TOP)
    if t1a - 0.6 < t < TL.PHASES['tier1cap'][1]:
        zc = min(zt, T1_TOP)
        a = tier_size(zc) - T1_THICK * 0.5
        specs += [((a, a, zc), 0), ((-a, -a, zc), 1)]
    if TL.PHASES['tier1cap'][1] - 0.3 < t < t2b + 0.4:
        zc = T1_ROOF
        specs += [((10.6, -10.6, zc), 2), ((-10.6, 10.6, zc), 3)]
    if t2b - 0.2 < t < removal:
        specs += [((6.0, 6.0, T2_ROOF), 4)]
    if TL.PHASES['platform'][0] - 0.5 < t < removal + 0.5:
        specs += [((34.0, -70.0, 2.8), 5)]
    used = set()
    for (loc, idx) in specs:
        c, r, ld_ = S.cranes[idx]
        used.add(idx)
        tip = S.crane_tip_tall if idx == 4 else S.crane_tip
        slew = 2 * math.pi * smooth_rand(idx * 7 + 1, t, 1.6) + idx
        hoisting_statue = idx == 4 and st0 - 0.4 < t < st1 + 0.3
        if hoisting_statue:
            slew = math.atan2(-loc[1], -loc[0])
        c.hide_render = r.hide_render = False
        c.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(slew, 4, 'Z')
        tip_w = c.matrix_world @ Vector(tip)
        if hoisting_statue:
            r.hide_render = True
            ld_.hide_render = True
            continue
        base_z = GROUND_Z if idx in (0, 1, 5) else loc[2]
        frac = hop(idx * 13 + 3, t, 3.0)
        load_z = base_z + 1.0 + frac * (tip_w.z - base_z - 3.0)
        length = max(tip_w.z - load_z, 0.5)
        r.matrix_world = Matrix.Translation(tip_w) @ Matrix.Diagonal((1, 1, length, 1))
        ld_.hide_render = hop(idx * 5 + 1, t, 3.0) < 0.3
        ld_.matrix_world = Matrix.Translation((tip_w.x, tip_w.y, load_z)) @ Matrix.Rotation(slew, 4, 'Z')
    for idx, (c, r, ld_) in enumerate(S.cranes):
        if idx not in used:
            c.hide_render = r.hide_render = ld_.hide_render = True

    # --- statue: waits on the terrace, hoisted, set on the pedestal
    park = Vector((0.5, -7.6, T2_ROOF + 0.05))
    final = Vector((0.0, 0.0, STATUE_Z))
    S.hoist.hide_render = True
    if t < st0 - 0.5:
        S.statue.hide_render = S.sceptre.hide_render = True
    else:
        S.statue.hide_render = S.sceptre.hide_render = False
        p = TL.ease_io((t - st0) / (st1 - st0))
        if p <= 0:
            pos = park
        else:
            lift = Vector((final.x, final.y, final.z + 1.2))
            if p < 0.6:
                q = p / 0.6
                pos = park.lerp(Vector((park.x * 0.3, park.y * 0.3, lift.z)), TL.ease_io(q))
            else:
                q = (p - 0.6) / 0.4
                pos = Vector((park.x * 0.3, park.y * 0.3, lift.z)).lerp(final, TL.ease_io(q))
        S.statue.location = pos
        S.statue.rotation_euler = (0, 0, math.radians(-100) + (0.4 * math.sin(t * 9) if 0 < p < 1 else 0))
        if 0 < p < 1 and 4 in used:
            c, _, _ = S.cranes[4]
            tip_w = c.matrix_world @ Vector(S.crane_tip_tall)
            top = pos + Vector((0, 0, 6.4))
            length = max(tip_w.z - top.z, 0.3)
            S.hoist.hide_render = False
            S.hoist.matrix_world = Matrix.Translation((top.x, top.y, tip_w.z)) @ Matrix.Diagonal((1, 1, length, 1))

    # --- workers (time-lapse: they jump around a bit every few frames)
    rngw = np.random.default_rng(int(t * TL.FPS / 3) + 1000)
    building = t1a - 0.5 < t < removal
    n_top = 16 if building else 0
    active = 0.35 + 0.65 * day
    wi = 0
    for i in range(n_top):
        o = S.workers[wi]
        wi += 1
        vis = building and hop(i + 300, t, 2.5) < active and H > PLAT_TOP + 0.5
        o.hide_render = not vis
        if vis:
            zz = S.sched.height(t - 0.05)
            if zz > T2_TOP:
                zz = T2_ROOF
            th = T1_THICK if zz <= T1_TOP else T2_THICK
            x, y = top_ring_point(zz, hop(i + 900, t, 3.0), th * 0.5)
            o.location = (x, y, zz)
            o.rotation_euler = (0, 0, rngw.uniform(0, 6.3))
    for i in range(14):   # on the scaffold planks just below the top
        o = S.workers[wi]
        wi += 1
        vis = building and hop(i + 400, t, 2.0) < active and H > PLAT_TOP + 4
        o.hide_render = not vis
        if vis:
            zz = PLAT_TOP + 2.0 * (math.floor((H - PLAT_TOP) / 2.0) - hop(i + 77, t, 2.0) * 2)
            zz = max(PLAT_TOP + 2.0, min(zz, T2_TOP - 1))
            if zz > T1_TOP + 1 and t > TL.PHASES['scaf1_down'][0]:
                zz = max(zz, T2_Z0 + 2)
            size = tier_size(zz)
            P = G.square_poly(size + 0.8) if zz <= T1_TOP else G.oct_poly(size + 0.75)
            n = len(P)
            s = hop(i + 555, t, 2.0) * n
            k = int(s) % n
            p = P[k] + (P[(k + 1) % n] - P[k]) * (s - int(s))
            o.location = (p[0], p[1], zz + 0.05)
    for i in range(40):   # on the ground: stacks, quay, camp
        o = S.workers[wi]
        wi += 1
        vis = hop(i + 500, t, 1.5) < (0.25 + 0.75 * day) * (1.0 if t < removal + 1 else 0.3)
        o.hide_render = not vis
        if vis:
            ang = 2 * math.pi * G._hash2(np.int64(i), np.int64(1), 1) + smooth_rand(i, t, 0.7) * 1.5
            rad = 34 + 30 * G._hash2(np.int64(i), np.int64(2), 1) + 6 * smooth_rand(i + 40, t, 1.1)
            x, y = rad * math.cos(ang), rad * math.sin(ang)
            o.location = (x, y, float(island_height(np.array([x]), np.array([y]))[0]))
            o.rotation_euler = (0, 0, ang + 1.6)

    # --- ships (daylight traffic in the harbour) and stone barges
    for i, (h, r) in enumerate(S.ships):
        speed = 90 + 60 * i
        y = -520 - 170 * i
        x = ((t * speed + 900 * i) % 5200) - 2600
        dirn = 1 if i % 2 == 0 else -1
        h.location = (x * dirn, y, 0.3)
        h.rotation_euler = (0, 0, 0 if dirn > 0 else math.pi)
        h.hide_render = r.hide_render = day < 0.25
    for i, (h, r, cg) in enumerate(S.barges):
        cyc = 3.2
        ph = ((t + i * cyc / 3) % cyc) / cyc
        dock = Vector((36 + (i - 1) * 9, -118 - 6 * i, 0.4))
        far = Vector((360 + 80 * i, -700, 0.4))
        if ph < 0.35:
            p = dock.lerp(far, 1 - TL.ease_io(ph / 0.35))
            loaded = True
        elif ph < 0.6:
            p = dock
            loaded = (ph - 0.35) / 0.25 < 0.5
        else:
            p = dock.lerp(far, TL.ease_io((ph - 0.6) / 0.4))
            loaded = False
        active_b = TL.PHASES['platform'][0] < t < TL.PHASES['tier3'][1]
        h.location = p
        h.rotation_euler = (0, 0, math.atan2(far.y - dock.y, far.x - dock.x))
        h.hide_render = r.hide_render = not active_b
        cg.hide_render = not (active_b and loaded)

    # --- sun, moon, sky
    sdir = TL.sun_dir(hour)
    mdir = TL.moon_dir(hour)
    S.sun.rotation_euler = Vector(sdir).to_track_quat('Z', 'Y').to_euler()
    S.moon.rotation_euler = Vector(mdir).to_track_quat('Z', 'Y').to_euler()
    sun_k = TL.smoothstep(-1.5, 10.0, el_deg)
    warm = TL.smoothstep(2.0, 24.0, el_deg)
    S.sun.data.energy = 6.5 * sun_k
    S.sun.data.color = (1.0, 0.52 + 0.4 * warm, 0.28 + 0.6 * warm)
    S.sun.hide_render = sun_k <= 0.0
    moon_up = max(0.0, mdir[2])
    S.moon.data.energy = 0.42 * night * TL.smoothstep(0.0, 0.25, moon_up)
    S.moon.hide_render = S.moon.data.energy <= 1e-4
    zen, hor, glow, cl_lit, cl_dark = sky_palette(el_deg)
    nt = S.world.node_tree.nodes
    for nm, col in (('zenith', zen), ('horizon', hor), ('sunglow', glow), ('cloud_lit', cl_lit),
                    ('cloud_dark', cl_dark)):
        nt[nm].outputs[0].default_value = col + (1.0,)
    for i, v in enumerate(sdir):
        nt['sun_dir'].inputs[i].default_value = float(v)
    for i, v in enumerate(mdir):
        nt['moon_dir'].inputs[i].default_value = float(v)
    nt['cloud_time'].outputs[0].default_value = t * 1.6
    nt['moon'].outputs[0].default_value = 6.0 * night
    nt['sun_disc'].outputs[0].default_value = 30.0 * TL.smoothstep(-1.0, 1.0, el_deg)
    nt['cover'].outputs[0].default_value = 0.6 + 0.1 * math.sin(t * 0.37) - 0.16 * TL.smoothstep(24.0, 27.0, t)

    S.m_cshadow.node_tree.nodes['shadow_time'].outputs[0].default_value = t * 260.0
    S.m_cshadow.node_tree.nodes['shadow_cover'].outputs[0].default_value = 0.40 + 0.08 * math.sin(t * 0.37)
    # --- water, city lights, ocean
    S.ocean.time = t * 2.2
    S.sea.data.materials[0].node_tree.nodes['water_time'].outputs[0].default_value = t * 0.9
    S.m_city.node_tree.nodes['city_lights'].outputs[0].default_value = 6.0 * night

    # --- the beacon
    f0, f1 = TL.PHASES['fire']
    fire_k = TL.ease((t - f0) / (f1 - f0))
    flick = 0.85 + 0.15 * math.sin(t * 31.0) * math.sin(t * 17.3 + 1.0)
    S.m_fire.node_tree.nodes['fire_k'].outputs[0].default_value = fire_k * (1.0 + 0.6 * max(0.0, 1 - (t - f0) / 0.5) * (t > f0))
    S.m_fire.node_tree.nodes['fire_time'].outputs[0].default_value = t * 3.0
    S.beacon.data.energy = 26000.0 * fire_k * flick
    S.beacon.hide_render = fire_k <= 0
    for i, fo in enumerate(S.flames):
        fo.hide_render = fire_k <= 0.01
        sz = fire_k * (0.8 + 0.35 * smooth_rand(i + 70, t, 9.0))
        fo.scale = (sz, sz, sz * (0.8 + 0.5 * smooth_rand(i + 90, t, 11.0)))
        fo.rotation_euler = (0.18 * (smooth_rand(i + 20, t, 6.0) - 0.5), 0.18 * (smooth_rand(i + 30, t, 6.0) - 0.5), 0)
    for i, eo in enumerate(S.embers):
        life = (t * 0.9 + i / len(S.embers)) % 1.0
        ang = i * 2.4 + t * 1.3
        rr = 0.6 + 2.5 * life
        eo.hide_render = fire_k < 0.3
        eo.location = (rr * math.cos(ang), rr * math.sin(ang), COL_Z0 + 1.0 + life * 9.0)
        eo.scale = (1 - life,) * 3

    # --- torches: top-of-work lights, podium braziers, camp fires, quay
    tk = TL.smoothstep(0.55, 0.1, day)
    S.m_torch.node_tree.nodes['torch_k'].outputs[0].default_value = tk
    spots = []
    if building:
        for i in range(6):
            zz = min(H, T2_ROOF) + 1.6
            th = T1_THICK if zz <= T1_ROOF else T2_THICK
            x, y = top_ring_point(max(zz - 1.6, PLAT_TOP), i / 6 + 0.08, th * 0.5)
            spots.append((x, y, zz, 1.0))
    if t > TL.PHASES['platform'][1]:
        a = PLAT_A[-1] - 1.0
        for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            spots.append((sx * a, sy * a, PLAT_TOP + 1.0, 1.3))
    for (x, y) in ((-58, -8), (-70, 12), (-52, 30)):
        spots.append((x, y, GROUND_Z + 0.6, 1.6))
    for (x, y) in ((30, -104), (42, -104)):
        spots.append((x, y, 3.4, 0.9))
    for i, (lo, fo) in enumerate(S.torches):
        if i < len(spots) and tk > 0.01:
            x, y, z, s = spots[i]
            fl = 0.8 + 0.2 * smooth_rand(i + 200, t, 8.0)
            lo.location = (x, y, z + 0.6)
            fo.location = (x, y, z)
            fo.scale = (s * fl,) * 3
            lo.data.energy = 900.0 * tk * s * fl
            lo.hide_render = fo.hide_render = False
        else:
            lo.hide_render = fo.hide_render = True

    # --- camera
    fi = min(int(round(t * TL.FPS)), TL.NFRAMES - 1)
    loc, tgt = S.cam_track[fi]
    look_at(S.cam, loc, tgt)
    return dict(t=t, hour=hour, sun_el=el_deg, day=day, height=H, fire=fire_k,
                horizon=hor, zenith=zen)
