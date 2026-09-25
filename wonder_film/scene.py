"""Procedural Blender scene: the Pharos of Alexandria under construction.

build() creates everything once; pose(state, t) sets the scene to video time t
(which blocks exist, scaffolding, cranes, workers, ships, sun/moon/sky,
torches, the beacon and the camera).  Pure procedural geometry, no assets.
"""
import json
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

# ----------------------------------------------------------------- looks
# 'dark': the moody graphic-novel film.  'bright': the sunny, painterly look of
# the Civ1 wonder films.  build(look=...) selects one before anything is made.
PALETTES = {
    'dark': dict(
        stone=((0.74, 0.66, 0.53), (0.30, 0.26, 0.21)), podium=((0.58, 0.53, 0.45), (0.22, 0.20, 0.17)),
        paving=((0.55, 0.49, 0.40), (0.20, 0.17, 0.14)), grime=0.22,
        wood=(0.42, 0.30, 0.18), plank=(0.52, 0.40, 0.26), rope=(0.12, 0.09, 0.06),
        cloth=(0.55, 0.49, 0.40), cloth2=(0.38, 0.22, 0.14), hull=(0.16, 0.10, 0.06), sail=(0.62, 0.55, 0.44),
        rock=((0.075, 0.068, 0.062), (0.21, 0.19, 0.165)), sand=((0.17, 0.15, 0.12), (0.27, 0.235, 0.185)),
        dust=((0.17, 0.155, 0.135), (0.26, 0.24, 0.21)), scrub_ground=(0.14, 0.15, 0.07), wet=(0.035, 0.035, 0.035),
        boulder=((0.06, 0.055, 0.05), (0.2, 0.18, 0.155)), boulder_wet=(0.025, 0.025, 0.028),
        water=((0.006, 0.020, 0.028), (0.02, 0.07, 0.07)), foam=(0.55, 0.58, 0.58),
        city=((0.42, 0.38, 0.31), (0.62, 0.58, 0.5)),
        scrub=(0.11, 0.13, 0.065), trunk=(0.2, 0.15, 0.1), frond=(0.07, 0.1, 0.04),
        workers=[(0.62, 0.58, 0.5), (0.55, 0.45, 0.32), (0.45, 0.2, 0.12), (0.7, 0.66, 0.58),
                 (0.35, 0.3, 0.25), (0.5, 0.36, 0.2)]),
    'bright': dict(
        stone=((0.68, 0.55, 0.38), (0.42, 0.33, 0.22)), podium=((0.60, 0.49, 0.35), (0.35, 0.28, 0.19)),
        paving=((0.52, 0.42, 0.30), (0.31, 0.25, 0.17)), grime=0.18,
        wood=(0.50, 0.36, 0.22), plank=(0.60, 0.47, 0.31), rope=(0.34, 0.27, 0.17),
        cloth=(0.80, 0.74, 0.62), cloth2=(0.62, 0.30, 0.16), hull=(0.26, 0.17, 0.10), sail=(0.86, 0.79, 0.65),
        rock=((0.20, 0.16, 0.12), (0.40, 0.33, 0.24)), sand=((0.44, 0.29, 0.14), (0.60, 0.41, 0.21)),
        dust=((0.45, 0.34, 0.21), (0.57, 0.44, 0.27)), scrub_ground=(0.30, 0.29, 0.13), scrub_k=0.45, cumulus=True, stone_detail=True, textures=True, filtered_joints=True, worksite=True, wakes=True,
        wave_dir=-67.6,   # wind waves run with the Etesian NNW (towards SSE), like smoke, pennants and sails
        hop_desync=True,  # time-lapse jumps staggered per object
        hdri=True,        # photographed day sky (fetch_hdri.py), when downloaded
        wet=(0.10, 0.09, 0.08),
        boulder=((0.18, 0.15, 0.12), (0.42, 0.36, 0.28)), boulder_wet=(0.08, 0.07, 0.06),
        water=((0.004, 0.040, 0.070), (0.025, 0.19, 0.18)), foam=(0.80, 0.83, 0.82),
        city=((0.58, 0.50, 0.38), (0.80, 0.72, 0.58)),
        scrub=(0.20, 0.25, 0.10), trunk=(0.36, 0.27, 0.18), frond=(0.13, 0.22, 0.06),
        workers=[(0.80, 0.76, 0.66), (0.62, 0.26, 0.14), (0.28, 0.35, 0.50), (0.72, 0.56, 0.30),
                 (0.42, 0.29, 0.18), (0.84, 0.80, 0.70), (0.50, 0.18, 0.12), (0.58, 0.52, 0.36)]),
}
P = PALETTES['dark']


# ============================================================ photo textures (CC0)
TEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'textures')
_TEX = None


def tex_manifest():
    """Textures fetched by fetch_textures.py (Poly Haven, CC0); {} if absent."""
    global _TEX
    if _TEX is None:
        path = os.path.join(TEX_DIR, 'manifest.json')
        _TEX = json.load(open(path)) if os.path.exists(path) else {}
    return _TEX


def use_textures():
    return bool(P.get('textures')) and bool(tex_manifest())


PIX_ANGLE = 36.0 / (33.0 * 1280.0)   # radians per pixel (≈ a 33 mm lens at 1280 px)


def pixel_footprint(nb):
    """Size of one pixel on the surface (metres): used to filter fine detail."""
    cam = nb.new('ShaderNodeCameraData')
    return nb.math('MULTIPLY', cam.outputs['View Distance'], PIX_ANGLE)


def tex_sample(nb, role, vec_m, detail=0.8, gray=False, normal_uv=None, normal_strength=0.8):
    """Sample photo texture `role` at its real-world size (vec_m in metres).
    Cycles has no mip-mapping, so the shader picks pre-filtered levels
    (1k / 256 / 64 px) by the pixel footprint and fades to the mean colour
    far away: no shimmering on moving shots.  Returns (colour multiplier,
    tangent normal or None, roughness, height); the multiplier is the texture
    divided by its mean colour, so the palette keeps the hue."""
    e = tex_manifest()[role]
    sx, sy = e['size_m']
    v = nb.vmath('MULTIPLY', vec_m, (1.0 / sx, 1.0 / sy, 1.0))
    mips = e.get('mips') or {k: [p] for k, p in e['maps'].items()}
    texel0 = max(sx, sy) / 1024.0
    lvl = nb.math('LOGARITHM', nb.math('MAXIMUM', nb.math('DIVIDE', pixel_footprint(nb), texel0), 1e-3), 2.0)
    # weights: 1k up to 2 texels per pixel, 256 up to 8, 64 up to 32, then the mean
    w1 = nb.smooth(1.0, 2.0, lvl)
    w2 = nb.smooth(3.0, 4.0, lvl)
    w3 = nb.smooth(5.0, 6.0, lvl)

    def img(key, level, noncolor):
        lv = min(level, len(mips[key]) - 1)
        n = nb.new('ShaderNodeTexImage', interpolation='Linear', extension='REPEAT')
        im = bpy.data.images.load(os.path.join(TEX_DIR, mips[key][lv]), check_existing=True)
        if noncolor:
            im.colorspace_settings.name = 'Non-Color'
        n.image = im
        nb.feed(n.inputs['Vector'], v)
        return n.outputs['Color']

    def mip(key, noncolor, constant):
        c = nb.mix(w1, img(key, 0, noncolor), img(key, 1, noncolor))
        c = nb.mix(w2, c, img(key, 2, noncolor))
        return nb.mix(w3, c, constant)
    mr, mg, mb = e['mean_rgb']
    diff = mip('diff', False, (mr, mg, mb, 1.0))
    if gray:
        bw = nb.new('ShaderNodeRGBToBW')
        nb.feed(bw.inputs[0], diff)
        k = nb.math('DIVIDE', bw.outputs[0], 0.2126 * mr + 0.7152 * mg + 0.0722 * mb)
        ratio = nb.comb(k, k, k)
    else:
        ratio = nb.vmath('DIVIDE', diff, (mr, mg, mb))
    mult = nb.mix(detail, (1.0, 1.0, 1.0, 1.0), ratio)
    rough = nb.sep(img('rough', 1, True))[0]
    height = nb.sep(mip('disp', True, (0.5, 0.5, 0.5, 1.0)))[0]
    nrm = None
    if normal_uv is not None:
        nm = nb.new('ShaderNodeNormalMap', space='TANGENT', uv_map=normal_uv)
        nb.feed(nm.inputs['Color'], nb.mix(w1, img('nor_gl', 0, True), img('nor_gl', 1, True)))
        nb.feed(nm.inputs['Strength'], nb.math('MULTIPLY', normal_strength, nb.math('SUBTRACT', 1.0, w2)))
        nrm = nm.outputs['Normal']
    return mult, nrm, rough, height


def mul_col(nb, col, mult):
    return nb.mix(1.0, col, mult, blend='MULTIPLY')


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
    """1 on mortar joints (near the edges of each block face), 0 inside.
    In the bright look the joint is filtered by the pixel footprint: far away
    it widens and fades to its average darkness instead of aliasing."""
    uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
    fs = nb.attr('fsize').outputs['Vector']
    u, v, _ = nb.sep(uv)
    w, h, _ = nb.sep(fs)
    du = nb.math('MINIMUM', u, nb.math('SUBTRACT', w, u))
    dv = nb.math('MINIMUM', v, nb.math('SUBTRACT', h, v))
    d = nb.math('MINIMUM', du, dv)
    if not P.get('filtered_joints'):
        return nb.math('SUBTRACT', 1.0, nb.smooth(0.0, width, d))
    w_eff = nb.math('MAXIMUM', width, nb.math('MULTIPLY', pixel_footprint(nb), 1.5))
    t = nb.math('DIVIDE', d, w_eff)
    n = nb.new('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
    nb.feed(n.inputs['Value'], t)
    return nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, n.outputs[0]), nb.math('DIVIDE', width, w_eff))


def mat_masonry(name, base, joint_col, var=0.09, width=0.05, grime=None):
    grime = P['grime'] if grime is None else grime
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
    tex = None
    if use_textures():
        uvs = nb.sep(nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0])
        vec = nb.comb(nb.math('ADD', uvs[0], nb.math('MULTIPLY', tone, 5.17)),
                      nb.math('ADD', uvs[1], nb.math('MULTIPLY', tone, 3.31)), 0.0)
        tex = tex_sample(nb, 'stone', vec, detail=0.85, normal_uv='UVMap', normal_strength=0.9)
        colout = mul_col(nb, colout, tex[0])
    colj = nb.mix(j, colout, tuple(joint_col) + (1,))
    b = principled(nb, colj, rough=0.88, spec=0.35)
    if tex is not None:
        nb.feed(b.inputs['Roughness'], nb.math('ADD', 0.35, nb.math('MULTIPLY', tex[2], 0.6)))
    bump = nb.new('ShaderNodeBump', invert=True)
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.05
    height = nb.math('ADD', j, nb.math('MULTIPLY', n2, 0.3))
    if tex is not None:
        nb.feed(bump.inputs['Normal'], tex[1])            # photo relief under the mortar joints
    elif P.get('stone_detail'):
        # dressed stone for close shots: claw-chisel tooling across each face,
        # small pits, and softly worn arrises next to the joints
        uv = nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0]
        u, v, _ = nb.sep(uv)
        wv = nb.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X')
        nb.feed(wv.inputs['Vector'], nb.comb(nb.math('ADD', u, nb.math('MULTIPLY', v, 0.35)), v,
                                             nb.math('MULTIPLY', tone, 13.0)))
        wv.inputs['Scale'].default_value = 5.5
        wv.inputs['Distortion'].default_value = 3.0
        wv.inputs['Detail'].default_value = 2.0
        pits = nb.noise(obj, 14.0, 2.0, 0.6).outputs['Fac']
        tool = nb.math('MULTIPLY', wv.outputs['Fac'], 0.16)
        height = nb.math('ADD', height, nb.math('ADD', tool, nb.math('MULTIPLY', nb.smooth(0.62, 0.72, pits), -0.5)))
        bump.inputs['Strength'].default_value = 0.45
    nb.feed(bump.inputs['Height'], height)
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_wood(name, base, var=0.3, width=0.03, textured=True):
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
    tex = None
    if textured and use_textures():
        uvs = nb.sep(nb.new('ShaderNodeUVMap', uv_map='UVMap').outputs[0])
        fs = nb.sep(nb.attr('fsize').outputs['Vector'])
        along_u = nb.math('GREATER_THAN', fs[0], fs[1])       # grain runs along the longer side
        a = nb.comb(uvs[0], nb.math('ADD', uvs[1], nb.math('MULTIPLY', tone, 7.0)), 0.0)
        bvec = nb.comb(uvs[1], nb.math('ADD', uvs[0], nb.math('MULTIPLY', tone, 7.0)), 0.0)
        vec = nb.mix(along_u, a, bvec, dtype='VECTOR')
        tex = tex_sample(nb, 'timber', vec, detail=0.75, gray=True, normal_uv='UVMap', normal_strength=0.7)
        colout = mul_col(nb, colout, tex[0])
    colj = nb.mix(nb.math('MULTIPLY', j, 0.6), colout, (0.03, 0.02, 0.012, 1))
    b = principled(nb, colj, rough=0.85, spec=0.3)
    if tex is not None:
        nb.feed(b.inputs['Normal'], tex[1])
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
def PAL_CUMULUS():
    return bool(P.get('cumulus'))


HDRI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'hdri')


def hdri_available():
    return bool(P.get('hdri')) and os.path.exists(os.path.join(HDRI_DIR, 'manifest.json'))


def hdri_sky(nb, D, dz, sky, sun_glow):
    """Blend in the photographed day sky (fetch_hdri.py: sun removed).  Our own
    sun disc and glow stay on top, so light and shadows keep following the
    film's clock; 'hdri_rot' turns the sky (drifting clouds), 'hdri_k' fades it
    in by day and out towards dusk, 'hdri_tint' warms it when the sun is low."""
    man = json.load(open(os.path.join(HDRI_DIR, 'manifest.json')))['day']
    env = nb.new('ShaderNodeTexEnvironment', interpolation='Linear')
    env.image = bpy.data.images.load(os.path.join(HDRI_DIR, man['file']))
    rot = nb.value(0.0, 'hdri_rot')
    c, s_ = nb.math('COSINE', rot), nb.math('SINE', rot)
    dx, dy, dz2 = nb.sep(D)
    rx = nb.math('SUBTRACT', nb.math('MULTIPLY', dx, c), nb.math('MULTIPLY', dy, s_))
    ry = nb.math('ADD', nb.math('MULTIPLY', dx, s_), nb.math('MULTIPLY', dy, c))
    nb.feed(env.inputs['Vector'], nb.comb(rx, ry, dz2))
    # light of the hour: the photographed day sky is re-lit by the ratio of our sky's
    # colours now to its colours at midday (zenith and horizon), so the same clouds
    # turn golden at sunset and dark at night instead of being swapped
    tz = nb.rgb((1.0, 1.0, 1.0), 'hdri_tint')
    th = nb.rgb((1.0, 1.0, 1.0), 'hdri_tint_h')
    up = nb.math('POWER', nb.math('MAXIMUM', dz2, 0.0), 0.3)
    tint = nb.mix(up, th, tz)
    hcol = nb.mix(1.0, env.outputs['Color'], tint, blend='MULTIPLY')
    hcol = nb.mix(1.0, hcol, (0.36 / man['median_sky'],) * 3 + (1.0,), blend='MULTIPLY')
    hcol = nb.mix(1.0, hcol, sun_glow, blend='ADD')
    hk = nb.value(0.0, 'hdri_k')
    return nb.mix(nb.math('MULTIPLY', hk, nb.smooth(-0.01, 0.03, dz)), sky, hcol)


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
    gain = nb.value(3.2, 'cloud_gain')

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
    Pc = nb.comb(nb.math('ADD', px, nb.math('MULTIPLY', t_cloud, 0.55)),
                nb.math('ADD', py, nb.math('MULTIPLY', t_cloud, 0.18)), 0.0)
    sdx, sdy, _ = nb.sep(sun.outputs[0])
    so = 0.35 if PAL_CUMULUS() else 0.10
    P2 = nb.vmath('ADD', Pc, nb.comb(nb.math('MULTIPLY', sdx, so), nb.math('MULTIPLY', sdy, so), 0.0))
    tz = nb.math('MULTIPLY', t_cloud, 0.12)
    Pc = nb.vmath('ADD', Pc, nb.comb(0.0, 0.0, tz))
    P2 = nb.vmath('ADD', P2, nb.comb(0.0, 0.0, tz))
    if PAL_CUMULUS():
        # fair-weather cumulus: domain-warped Voronoi puffs with billowy edges
        def puffs(Q):
            wv = nb.noise(Q, 0.55, 4.0, 0.6).outputs['Color']
            Qw = nb.vmath('ADD', Q, nb.vmath('SCALE', nb.vmath('SUBTRACT', wv, (0.5, 0.5, 0.5)), scale=1.3))
            vo = nb.new('ShaderNodeTexVoronoi', voronoi_dimensions='3D', feature='F1')
            nb.feed(vo.inputs['Vector'], Qw)
            vo.inputs['Scale'].default_value = 0.36
            vo.inputs['Randomness'].default_value = 0.9
            lo_ = nb.math('SUBTRACT', 0.62, nb.math('MULTIPLY', cover, 0.55))     # more cells carry a cloud
            present = nb.smooth(0.0, 0.05, nb.math('SUBTRACT', nb.sep(vo.outputs['Color'])[0], lo_))
            puff = nb.math('MULTIPLY', nb.smooth(0.62, 0.18, vo.outputs['Distance']), present)
            fine = nb.noise(Q, 1.6, 6.0, 0.62).outputs['Fac']
            return nb.smooth(0.25, 0.55, nb.math('MULTIPLY', puff, nb.math('ADD', -0.1, nb.math('MULTIPLY', fine, 1.7))))
        nz1 = puffs(Pc)
        nz2 = puffs(P2)
        dens = nb.math('MULTIPLY', nz1, nb.math('ADD', 0.5, nb.math('MULTIPLY', cover, 2.0)), clamp=True)
    else:
        nz1 = nb.noise(Pc, 0.28, 5.0, 0.55).outputs['Fac']
        nz2 = nb.noise(P2, 0.28, 5.0, 0.55).outputs['Fac']
        big = nb.noise(Pc, 0.07, 1.0, 0.5).outputs['Fac']
        cover = nb.math('ADD', cover, nb.math('MULTIPLY', nb.math('SUBTRACT', big, 0.5), 1.1))
        # coverage threshold
        lo = nb.math('SUBTRACT', 1.0, cover)
        dens = nb.math('MULTIPLY', nb.math('SUBTRACT', nz1, nb.math('MULTIPLY', lo, 0.55)), gain, clamp=True)
    dens = nb.math('MULTIPLY', dens, nb.math('SUBTRACT', 1.0, nb.math('POWER', nb.math('SUBTRACT', 1.0, up), 18.0)),
                   clamp=True)
    lit = nb.math('ADD', nb.math('MULTIPLY', nb.math('SUBTRACT', nz1, nz2), 1.3 if PAL_CUMULUS() else 9.0), 0.5 if PAL_CUMULUS() else 0.45, clamp=True)
    ccol = nb.mix(lit, cl_dark, cl_lit)
    # clouds near the sun catch the glow
    ccol = nb.mix(nb.math('MULTIPLY', g1, 0.7), ccol, glow, blend='ADD')
    # fade the deck into the horizon haze
    hfade = nb.math('POWER', nb.math('MINIMUM', nb.math('MULTIPLY', up, 5.0), 1.0), 0.7)
    sky = nb.mix(nb.math('MULTIPLY', dens, hfade), sky, ccol)
    if hdri_available():
        sky = hdri_sky(nb, D, dz, sky, nb.mix(gl, (0.0, 0.0, 0.0, 1.0), glow))
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


# the sunny look: saturated blue sky, white cumulus, warm golden hour, blue dusk
SKY_KEYS_BRIGHT = [
    # el,   zenith,               horizon,             sunglow,             cloud_lit,          cloud_dark
    (-40, (0.0022, 0.0040, 0.0110), (0.0050, 0.0080, 0.0160), (0.000, 0.000, 0.000), (0.008, 0.011, 0.020), (0.002, 0.003, 0.005)),
    (-14, (0.0040, 0.0095, 0.0320), (0.016, 0.020, 0.040), (0.030, 0.014, 0.008), (0.016, 0.020, 0.036), (0.004, 0.005, 0.010)),
    (-6, (0.014, 0.036, 0.120), (0.200, 0.120, 0.090), (0.460, 0.160, 0.050), (0.240, 0.140, 0.130), (0.028, 0.034, 0.064)),
    (0, (0.045, 0.095, 0.250), (0.700, 0.420, 0.250), (1.500, 0.560, 0.160), (1.300, 0.660, 0.340), (0.110, 0.095, 0.130)),
    (6, (0.075, 0.165, 0.420), (0.900, 0.680, 0.450), (1.250, 0.620, 0.240), (1.450, 1.020, 0.680), (0.290, 0.270, 0.320)),
    (18, (0.060, 0.190, 0.580), (0.500, 0.600, 0.750), (0.550, 0.420, 0.260), (1.500, 1.440, 1.340), (0.420, 0.470, 0.580)),
    (50, (0.050, 0.180, 0.620), (0.450, 0.580, 0.760), (0.330, 0.290, 0.230), (1.600, 1.560, 1.500), (0.450, 0.500, 0.620)),
]


def sky_palette(el_deg, look='dark', log=False):
    """Sky colours for a sun elevation.  log=True interpolates below -6 deg in
    log space: dusk then darkens by a steady ratio per degree (as it does in
    nature), with no kink at the keys - a fast time-lapse shows every kink."""
    keys = SKY_KEYS_BRIGHT if look == 'bright' else SKY_KEYS
    els = [k[0] for k in keys]
    out = []
    for c in range(1, 6):
        cols = np.array([k[c] for k in keys])
        lin = [float(np.interp(el_deg, els, cols[:, i])) for i in range(3)]
        if log and el_deg < -6.0:
            lin = [float(np.exp(np.interp(el_deg, els, np.log(cols[:, i] + 1e-4)))) - 1e-4 for i in range(3)]
        out.append(tuple(lin))
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


# ------------------------------------------------------------ worked ground
WS_X0, WS_Y0, WS_SPAN, WS_N = -130.0, -130.0, 240.0, 1536
WS_TRACKS = [  # (polyline, width m, ruts): beaten tracks between the quay, the stacks, the camp and the podium
    ([(38, -64), (30, -54), (16, -40), (6, -31)], 4.5, True),
    ([(38, -64), (42, -50), (36, -36), (30, -30)], 3.6, True),
    ([(-58, -8), (-44, -10), (-31, -6)], 3.6, False),
    ([(-38, -40), (-30, -30)], 3.0, False), ([(-44, 8), (-31, 6)], 3.0, False), ([(46, 40), (31, 27)], 3.0, False),
    ([(22, -54), (14, -36)], 3.0, False), ([(-20, -52), (-12, -31)], 3.0, False), ([(-28, -50), (-22, -40)], 2.5, False),
    ([(-62, -26), (-58, -8), (-64, 26)], 2.6, False),
]
WS_STACKS = [(-38, -40), (-44, 8), (40, -46), (22, -54), (-20, -52), (46, 40)]


def _seg_dist(X, Y, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
    return np.hypot(X - (ax + t * dx), Y - (ay + t * dy))


def worksite_image():
    """R: beaten tracks, G: stone chips and dust from the masons, B: cart ruts."""
    n = WS_N
    c = WS_X0 + (np.arange(n) + 0.5) * WS_SPAN / n
    X, Y = np.meshgrid(c, WS_Y0 + (np.arange(n) + 0.5) * WS_SPAN / n)      # row 0 = south
    path = np.zeros((n, n), np.float32)
    ruts = np.zeros((n, n), np.float32)
    wob = 0.8 * G.fbm(X / 9.0, Y / 9.0, 3, seed=61)
    for pts, w, has_ruts in WS_TRACKS:
        d = np.full((n, n), 1e9, np.float32)
        for a, b in zip(pts[:-1], pts[1:]):
            d = np.minimum(d, _seg_dist(X, Y, a, b))
        path = np.maximum(path, np.clip(1.0 - (d + wob - 0.5 * w) / 1.6, 0, 1))
        if has_ruts:                                   # two wheel ruts 1.6 m apart (the carts' track)
            ruts = np.maximum(ruts, np.clip(1.0 - np.abs(d - 0.8) / 0.22, 0, 1))
    dp = np.maximum(np.abs(X), np.abs(Y)) - PLAT_A[0]
    chips = np.where(dp > 0, np.exp(-(dp / 6.0) ** 2), 0.0)
    for (sx, sy) in WS_STACKS:
        chips = np.maximum(chips, np.exp(-((np.hypot(X - sx, Y - sy)) / 6.5) ** 2))
    chips = chips * np.clip(0.6 + 0.8 * G.fbm(X / 6.0, Y / 6.0, 3, seed=62), 0, 1)
    img = bpy.data.images.new('Worksite', n, n, alpha=True, float_buffer=False)
    img.colorspace_settings.name = 'Non-Color'
    px = np.stack([path, chips, ruts, np.ones_like(path)], -1).astype(np.float32)
    img.pixels.foreach_set(px.ravel())
    return img


def mat_terrain():
    m, nb, out = new_material('Terrain')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    nz = nb.sep(geo.outputs['Normal'])[2]
    z = nb.sep(pos)[2]
    n1 = nb.noise(pos, 0.08, 3.0, 0.6).outputs['Fac']
    n2 = nb.noise(pos, 0.9, 3.0, 0.6).outputs['Fac']
    rock = nb.mix(n2, P['rock'][0] + (1,), P['rock'][1] + (1,))
    sand = nb.mix(n1, P['sand'][0] + (1,), P['sand'][1] + (1,))
    flat = nb.smooth(0.78, 0.93, nz)
    col = nb.mix(nb.math('MULTIPLY', flat, nb.smooth(0.42, 0.72, nb.math('ADD', n1, 0.1))), rock, sand)
    # trampled, dusty construction yard around the podium
    x_, y_, _ = nb.sep(pos)
    rr = nb.vmath('LENGTH', nb.comb(x_, y_, 0.0))
    yardm = nb.math('MULTIPLY', nb.smooth(80.0, 58.0, rr), flat)
    dust = nb.mix(nb.noise(pos, 0.25, 4.0, 0.6).outputs['Fac'], P['dust'][0] + (1,), P['dust'][1] + (1,))
    col = nb.mix(yardm, col, dust)
    # sparse dry scrub
    scrub = nb.math('MULTIPLY', flat, nb.smooth(0.58, 0.66, nb.noise(pos, 0.35, 3.0, 0.6).outputs['Fac']))
    col = nb.mix(nb.math('MULTIPLY', scrub, P.get('scrub_k', 0.8)), col, P['scrub_ground'] + (1,))
    # wet, dark rock at the waterline
    wet = nb.smooth(1.6, 0.2, z)
    col = nb.mix(nb.math('MULTIPLY', wet, 0.75), col, P['wet'] + (1,))
    relief = nb.noise(pos, 1.6, 3.0, 0.6).outputs['Fac']
    if P.get('worksite'):          # beaten tracks, cart ruts, stone chips round the podium and the stacks
        tex = nb.new('ShaderNodeTexImage')
        tex.image = worksite_image()
        tex.extension = 'CLIP'
        tex.interpolation = 'Linear'
        nb.feed(tex.inputs['Vector'], nb.comb(nb.math('DIVIDE', nb.math('SUBTRACT', x_, WS_X0), WS_SPAN),
                                              nb.math('DIVIDE', nb.math('SUBTRACT', y_, WS_Y0), WS_SPAN), 0.0))
        tr, ch, ru = nb.sep(tex.outputs['Color'])
        brk = nb.noise(pos, 0.45, 3.0, 0.6).outputs['Fac']
        pm = nb.math('MULTIPLY', nb.smooth(0.2, 0.8, nb.math('ADD', tr, nb.math('MULTIPLY', nb.math('SUBTRACT', brk, 0.5), 0.5))), flat)
        col = nb.mix(nb.math('MULTIPLY', pm, 0.72), col, (0.33, 0.26, 0.18, 1))
        ru = nb.math('MULTIPLY', ru, nb.smooth(0.25, 0.08, pixel_footprint(nb)))     # thin ruts fade out far away
        col = nb.mix(nb.math('MULTIPLY', nb.math('MULTIPLY', ru, flat), 0.35), col, (0.26, 0.20, 0.13, 1))
        # chips: fine bright flecks that fade to their mean tone once a pixel covers them
        fl = nb.noise(pos, 7.0, 2.0, 0.5).outputs['Fac']
        fine = nb.smooth(0.5, 0.66, fl)
        far = nb.smooth(0.03, 0.12, pixel_footprint(nb))
        fleck = nb.mix(far, fine, 0.35, dtype='FLOAT')
        cm = nb.math('MULTIPLY', nb.math('MULTIPLY', ch, flat), nb.math('ADD', 0.25, nb.math('MULTIPLY', fleck, 0.75)))
        col = nb.mix(nb.math('MULTIPLY', cm, 0.8), col, (0.70, 0.64, 0.53, 1))
        relief = nb.math('ADD', relief, nb.math('MULTIPLY', nb.math('SUBTRACT', ru, pm), 0.25))
    if use_textures():
        t1 = tex_sample(nb, 'sand', pos, detail=0.7)
        pos2 = nb.vmath('ADD', nb.comb(nb.math('MULTIPLY', y_, 0.37), nb.math('MULTIPLY', x_, -0.37), 0.0), (13.1, 7.7, 0.0))
        t2 = tex_sample(nb, 'sand', pos2, detail=0.5)
        sandy = nb.math('MULTIPLY', flat, nb.math('SUBTRACT', 1.0, wet))
        col = mul_col(nb, col, nb.mix(sandy, (1.0, 1.0, 1.0, 1.0), nb.mix(0.5, t1[0], t2[0])))
        relief = nb.math('ADD', nb.math('MULTIPLY', relief, 0.4), nb.math('MULTIPLY', t1[3], 0.9))
    b = principled(nb, col, rough=nb.math('SUBTRACT', 0.95, nb.math('MULTIPLY', wet, 0.5)), spec=0.3)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.6
    nb.feed(bump.inputs['Height'], relief)
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
    return img, (x0, x1, y0, y1)


N_WAKES = 6
KELVIN = math.tan(math.radians(19.47))


def wake_foam(nb, x, y, pos, tw):
    """Foam behind moving boats, drawn on the displaced sea: the two arms of a
    Kelvin wedge (19.5 deg half-angle, from the bow) and the churned water
    behind the stern, both fading astern.  Boats are value nodes wake{i}_*
    (x, y, heading, strength, length) set per frame; strength 0 = no wake."""
    total = None
    brk = nb.noise(nb.vmath('ADD', pos, nb.comb(0.0, 0.0, nb.math('MULTIPLY', tw, 3.0))), 0.9, 3.0, 0.6).outputs['Fac']
    for i in range(N_WAKES):
        bx, by = nb.value(0.0, f'wake{i}_x'), nb.value(0.0, f'wake{i}_y')
        hd, st, bl = nb.value(0.0, f'wake{i}_h'), nb.value(0.0, f'wake{i}_s'), nb.value(7.0, f'wake{i}_L')
        dx, dy = nb.math('SUBTRACT', x, bx), nb.math('SUBTRACT', y, by)
        ch, sh = nb.math('COSINE', hd), nb.math('SINE', hd)
        u = nb.math('MULTIPLY', nb.math('ADD', nb.math('MULTIPLY', dx, ch), nb.math('MULTIPLY', dy, sh)), -1.0)
        v = nb.math('ABSOLUTE', nb.math('SUBTRACT', nb.math('MULTIPLY', dy, ch), nb.math('MULTIPLY', dx, sh)))
        half = nb.math('MULTIPLY', bl, 0.5)
        ub = nb.math('ADD', u, half)                                   # astern of the bow
        us = nb.math('SUBTRACT', u, half)                              # astern of the stern
        fade = nb.math('EXPONENT', nb.math('DIVIDE', nb.math('MULTIPLY', ub, -1.0), nb.math('MULTIPLY', bl, 3.0)))
        wid = nb.math('ADD', 0.3, nb.math('MULTIPLY', ub, 0.04))
        off = nb.math('DIVIDE', nb.math('SUBTRACT', v, nb.math('MULTIPLY', ub, KELVIN)), wid)
        arm = nb.math('MULTIPLY', nb.math('EXPONENT', nb.math('MULTIPLY', nb.math('MULTIPLY', off, off), -1.0)),
                      nb.math('GREATER_THAN', ub, 0.0))
        cw = nb.math('ADD', 0.35, nb.math('MULTIPLY', us, 0.05))
        oc = nb.math('DIVIDE', v, cw)
        core = nb.math('MULTIPLY', nb.math('EXPONENT', nb.math('MULTIPLY', nb.math('MULTIPLY', oc, oc), -1.0)),
                       nb.math('GREATER_THAN', us, 0.0))
        core = nb.math('MULTIPLY', core, nb.math('EXPONENT', nb.math('DIVIDE', nb.math('MULTIPLY', us, -1.0), bl)))
        w = nb.math('MULTIPLY', nb.math('MAXIMUM', nb.math('MULTIPLY', arm, 0.7), core), nb.math('MULTIPLY', fade, st))
        total = w if total is None else nb.math('MAXIMUM', total, w)
    return nb.math('MULTIPLY', total, nb.smooth(0.3, 0.6, brk), clamp=True)


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
    if P.get('wakes'):
        foam = nb.math('MAXIMUM', foam, wake_foam(nb, x, y, pos, tw))
    base = nb.mix(shallow, P['water'][0] + (1,), P['water'][1] + (1,))
    col = nb.mix(foam, base, P['foam'] + (1,))
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
    mod.wave_direction = math.radians(P.get('wave_dir', 200.0))
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
    col = nb.mix(n2, P['boulder'][0] + (1,), P['boulder'][1] + (1,))
    wet = nb.smooth(1.4, 0.0, z)
    col = nb.mix(nb.math('MULTIPLY', wet, 0.8), col, P['boulder_wet'] + (1,))
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
def quad_uvs(V, Q, tone=0.5):
    """Per-face UVs in metres (u along the first edge) plus the face size, as
    HexBatch gives the blocks: needed by the mortar joints and photo textures."""
    V = np.asarray(V, float)
    Q = np.asarray(Q)
    A, B, D = V[Q[:, 0]], V[Q[:, 1]], V[Q[:, 3]]
    w = np.linalg.norm(B - A, axis=1)
    h = np.linalg.norm(D - A, axis=1)
    uv = np.zeros((len(Q), 4, 2), np.float32)
    uv[:, 1, 0] = w
    uv[:, 2, 0] = w
    uv[:, 2, 1] = h
    uv[:, 3, 1] = h
    fs = np.zeros((len(Q), 3), np.float32)
    fs[:, 0], fs[:, 1] = w, h
    return uv.reshape(-1, 2), {'fsize': ('FLOAT_VECTOR', fs), 'tone': ('FLOAT', np.full(len(Q), tone, np.float32))}


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
    uv, attrs = quad_uvs(V, Q, tone=float(G._hash2(np.int64(len(name)), np.int64(n), 4)))
    return mesh_from_arrays(name, V, Q, uv=uv, face_attrs=attrs, mats=mats, smooth=False)


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
        uv, attrs = quad_uvs(V, Q, tone=0.3 + 0.05 * i)
        me = mesh_from_arrays(f'Entab{i}', np.array(V), np.array(Q), uv=uv, face_attrs=attrs, mats=[mat_stone])
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


def _evaluated_arrays(o):
    link(o)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    bpy.data.objects.remove(o)
    V = np.array([v.co[:] for v in me.vertices])
    F = [list(p.vertices) for p in me.polygons]
    bpy.data.meshes.remove(me)
    F = np.array([f if len(f) == 4 else f + [f[-1]] * (4 - len(f)) for f in F])
    return V, F


def statue_zeus_fine(mat):
    """Zeus Soter for close-ups (6.2 m): bearded head, raised right arm with a
    long sceptre, the left forearm held forward, a himation wrapped round the
    hips and legs and thrown over the left shoulder.  Faces +y."""
    s = 6.2 / 1.9
    J = [(0, 0, 0.98), (0, 0.01, 1.18), (0, 0.0, 1.38), (0, 0.0, 1.55), (0, 0.02, 1.665), (0, 0.0, 1.8),
         (0, 0.085, 1.6),
         (-0.2, 0, 1.5), (-0.27, 0.1, 1.3), (-0.24, 0.32, 1.22),
         (0.2, 0, 1.5), (0.33, 0.02, 1.72), (0.39, 0.04, 1.94),
         (-0.1, 0, 0.92), (-0.11, 0.03, 0.5), (-0.11, 0.02, 0.07),
         (0.1, 0, 0.92), (0.14, -0.03, 0.5), (0.16, -0.07, 0.07)]
    E = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (4, 6), (2, 7), (7, 8), (8, 9), (2, 10), (10, 11), (11, 12),
         (0, 13), (13, 14), (14, 15), (0, 16), (16, 17), (17, 18)]
    R = [0.165, 0.15, 0.185, 0.068, 0.1, 0.095, 0.065, 0.085, 0.06, 0.05, 0.085, 0.06, 0.05,
         0.1, 0.075, 0.055, 0.1, 0.075, 0.055]
    J = [(x * s, y * s, z * s) for x, y, z in J]
    body = skin_figure('Statue', J, E, [r * s for r in R], mat, subsurf=2)
    # accessories mesh: himation skirt (lofted, folded), shoulder sash, sceptre, base
    parts_V, parts_F = [], []

    def add(V, F):
        off = sum(len(v) for v in parts_V)
        parts_V.append(np.asarray(V, float))
        parts_F.append(np.asarray(F) + off)
    nr, nz = 28, 9
    V, F = [], []
    for k in range(nz):
        f = k / (nz - 1)
        z = (1.05 - 0.95 * f) * s
        rx, ry = (0.25 + 0.1 * f) * s, (0.19 + 0.09 * f) * s
        for i in range(nr):
            a = 2 * math.pi * i / nr
            fold = 1 + (0.03 + 0.07 * f) * math.sin(9 * a + 2.5 * f) + 0.03 * math.sin(4 * a - 1.3)
            hem = 0.05 * s * f ** 4 * math.sin(3 * a + 0.8)
            V.append((rx * fold * math.cos(a), ry * fold * math.sin(a) - 0.02 * s, z + hem))
    for k in range(nz - 1):
        for i in range(nr):
            j = (i + 1) % nr
            F.append((k * nr + i, k * nr + j, (k + 1) * nr + j, (k + 1) * nr + i))
    add(V, F)
    sash = skin_figure('Sash', [(x * s, y * s, z * s) for x, y, z in
                                ((0.2, 0.06, 1.0), (0.05, 0.12, 1.22), (-0.14, 0.08, 1.45), (-0.2, -0.04, 1.52),
                                 (-0.24, -0.12, 1.3), (-0.25, -0.1, 0.95))],
                       [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)], [0.1 * s, 0.09 * s, 0.085 * s, 0.09 * s, 0.1 * s, 0.09 * s],
                       mat, subsurf=1)
    add(*_evaluated_arrays(sash))
    n = 8
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    for (cx, cy, z0, z1, r0, r1) in ((0.39 * s, 0.05 * s, -0.15, 2.45 * s, 0.065, 0.05),   # sceptre
                                     (0.39 * s, 0.05 * s, 2.45 * s, 2.45 * s + 0.35, 0.14, 0.02),
                                     (0.0, 0.0, -0.2, 0.05, 0.62, 0.58)):                  # bronze base
        bot = np.stack([cx + r0 * np.cos(ang), cy + r0 * np.sin(ang), np.full(n, z0)], 1)
        top = np.stack([cx + r1 * np.cos(ang), cy + r1 * np.sin(ang), np.full(n, z1)], 1)
        FF = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        FF += [(2 * n, (i + 1) % n, i, i) for i in range(n)] + [(2 * n + 1, n + i, n + (i + 1) % n, n + (i + 1) % n) for i in range(n)]
        add(np.concatenate([bot, top, [[cx, cy, z0], [cx, cy, z1]]]), FF)
    me = mesh_from_arrays('StatueDrapery', np.concatenate(parts_V), np.concatenate(parts_F), mats=[mat], smooth=True)
    so = bpy.data.objects.new('Sceptre', me)
    return body, so


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


def build_quay_blocks(pb, rng):
    """The jetty and its T-head built of ashlar courses, paved on top, with
    stone bollards along the berths (for close shots)."""
    rects = [(30.0, 42.0, -100.0, -64.0), (25.0, 47.0, -108.0, -100.0)]
    for (x0, x1, y0, y1) in rects:
        pb.add(G.box((x0 + x1) / 2, (y0 + y1) / 2, -3.0, x1 - x0 - 1.6, y1 - y0 - 1.6, 5.7), mat=0, tone=0.5)
    for c in range(3):
        z0 = -0.2 + c * 1.0
        for (x0, x1, y0, y1) in rects:
            edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
            for (ax, ay), (bx, by) in edges:
                L = math.hypot(bx - ax, by - ay)
                ux, uy = (bx - ax) / L, (by - ay) / L
                nx, ny = uy, -ux                      # outward normal (CCW rectangle)
                s = 1.2 - 1.1 * (c % 2)
                while s < L:
                    bl = rng.uniform(1.8, 2.6)
                    a, b = max(s, 1.2), min(s + bl, L)
                    if b - a > 0.3:
                        p = [(ax + ux * a, ay + uy * a), (ax + ux * b, ay + uy * b),
                             (ax + ux * b - nx * 1.2, ay + uy * b - ny * 1.2), (ax + ux * a - nx * 1.2, ay + uy * a - ny * 1.2)]
                        pb.add(G.quad_slab(p, z0, z0 + 0.98), mat=0, tone=rng.random())
                    s += bl
    # paving
    for (x0, x1, y0, y1) in rects:
        y = y0
        row = 0
        while y < y1 - 0.01:
            h = min(1.5, y1 - y)
            x = x0 - (0.9 if row % 2 else 0.0)
            while x < x1 - 0.01:
                w = rng.uniform(1.6, 2.4)
                a, b = max(x, x0), min(x + w, x1)
                if b - a > 0.2:
                    pb.add(G.quad_slab([(a, y), (b, y), (b, y + h), (a, y + h)], 2.78, 2.95), mat=3,
                           tone=rng.random())
                x += w
            y += h
            row += 1
    for yb in np.arange(-98.0, -64.0, 7.0):
        pb.add(G.box(41.4, yb, 2.95, 0.45, 0.45, 0.65), mat=0, tone=0.3)
    for (cx, cy, n_l) in ((33.2, -79.0, 2), (33.4, -71.0, 3), (29.5, -104.5, 2)):
        for L in range(n_l):
            for i in range(3 - L):
                for j in range(2):
                    pb.add(G.box(cx + (j - 0.5) * 1.25, cy + (i - (2 - L) / 2) * 2.0, 2.95 + L * 0.9, 1.15, 1.9, 0.88,
                                 rng.uniform(-0.03, 0.03)), mat=4, tone=rng.random())
    for xb in (27.0, 33.0, 39.0, 45.0):
        pb.add(G.box(xb, -107.4, 2.95, 0.45, 0.45, 0.65), mat=0, tone=0.3)


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
    if P is PALETTES['bright']:
        build_quay_blocks(pb, rng)
    else:
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
    base = nb.mix(tone, P['city'][0] + (1,), P['city'][1] + (1,))
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
    wl = nb.math('MULTIPLY', win, lit)
    if P.get('filtered_joints'):
        # far away a window is smaller than a pixel: use the lit fraction of the
        # facade instead of sub-pixel dots that twinkle as the camera moves
        far = nb.smooth(0.8, 3.0, pixel_footprint(nb))
        wl = nb.mix(far, wl, 0.09, dtype='FLOAT')
    e = nb.math('MULTIPLY', wl, nb.math('MULTIPLY', vert, k))
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


def ship_mesh(mats, length=22.0, beam_w=6.0, sail=True, mast=True):
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
    if mast:
        sb.add(G.beam([-length * 0.5, 0, 3.0], [-length * 0.62, 0, 5.2], 0.5), mat=0)   # stern post
    else:
        sb.add(G.beam([-length * 0.5, 0, 2.2], [-length * 0.55, 0, 3.4], 0.3), mat=0)
    if mast:
        sb.add(G.beam([length * 0.05, 0, 1.0], [length * 0.05, 0, 15.0], 0.4), mat=0)       # mast
        sb.add(G.beam([length * 0.05, -6.5, 14.2], [length * 0.05, 6.5, 14.2], 0.3), mat=0)  # yard
    if sail:
        sb.add(G.quad_slab([[length * 0.05 - 0.1, -6.2], [length * 0.05 + 0.1, -6.2],
                            [length * 0.05 + 0.1, 6.2], [length * 0.05 - 0.1, 6.2]], 5.0, 14.1), mat=1)
    if mast:
        sb.add(G.box(-length * 0.3, 0, 1.1, 4.0, 3.2, 2.0), mat=0)                       # deck house
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


# ============================================================ guy derrick
# A guyed derrick on the octagon roof for the lantern and the statue: a fixed
# mast held by three guys (one down to the first terrace), a boom hinged on
# the mast that slews and whose tip reaches exactly over the axis of the tower.
DERRICK_PHI = math.radians(135.0)
DERRICK_R = 8.24                                      # boom reach = mast distance from the axis
DERRICK_C = (DERRICK_R * math.cos(DERRICK_PHI), DERRICK_R * math.sin(DERRICK_PHI))
DERRICK_HEEL = 6.0                                    # boom heel above the roof: clears the lantern scaffold
DERRICK_EL = math.radians(65.0)
DERRICK_BOOM = DERRICK_R / math.cos(DERRICK_EL)
DERRICK_MAST = 25.0
DERRICK_TIP = (DERRICK_R, 0.0, DERRICK_HEEL + DERRICK_BOOM * math.sin(DERRICK_EL))   # boom frame
THETA_CENTER = DERRICK_PHI + math.pi                  # boom slew that puts the tip over the axis
THETA_PARK = THETA_CENTER - math.radians(55.0)        # tip over the statue's parking spot
STATUE_PARK = (DERRICK_C[0] + DERRICK_R * math.cos(THETA_PARK), DERRICK_C[1] + DERRICK_R * math.sin(THETA_PARK))
STATUE_LIFT_Z = 105.6                                 # clears scaffold, dome and pedestal while slewing
STATUE_HOOK = 6.0                                     # sling point above the statue's base
DERRICK_WINCH = (DERRICK_C[0] + 1.5 * math.cos(DERRICK_PHI - math.pi / 2),
                 DERRICK_C[1] + 1.5 * math.sin(DERRICK_PHI - math.pi / 2))


def build_derrick(S, coll):
    cx, cy = DERRICK_C
    z0 = T2_ROOF
    out = np.array([math.cos(DERRICK_PHI), math.sin(DERRICK_PHI)])
    tan = np.array([-out[1], out[0]])
    C2 = np.array([cx, cy])
    mb = G.HexBatch('derrick_mast')
    mb.add(G.beam([cx, cy, z0], [cx, cy, z0 + DERRICK_MAST], 0.42), mat=0)
    for a, b in ((C2 - 2.0 * tan, C2 + 2.0 * tan), (C2 - 2.2 * out, C2 + 0.55 * out)):
        mb.add(G.beam(np.append(a, z0 + 0.18), np.append(b, z0 + 0.18), 0.36), mat=0)
    head = np.array([cx, cy, z0 + DERRICK_MAST - 0.4])
    anchors = [np.array([-11.5, 11.5, T1_ROOF + 0.15]), np.array([-1.5, 8.7, z0 + 0.25]),
               np.array([-8.7, 1.5, z0 + 0.25])]
    for A in anchors:
        mb.add(G.beam(head, A, 0.06), mat=1)
        mb.add(G.box(A[0], A[1], A[2] - 0.2, 0.7, 0.7, 0.45), mat=2)
    # windlass beside the mast foot: two trestles and a drum
    wx, wy = DERRICK_WINCH
    for s in (-0.8, 0.8):
        p = np.array([wx, wy]) + s * out
        mb.add(G.beam(np.append(p - 0.45 * tan, z0), np.append(p, z0 + 1.2), 0.16), mat=0)
        mb.add(G.beam(np.append(p + 0.45 * tan, z0), np.append(p, z0 + 1.2), 0.16), mat=0)
    # hoist rope from the heel sheave down to the drum
    mb.add(G.beam([cx, cy, z0 + DERRICK_HEEL], [wx, wy, z0 + 1.25], 0.07), mat=1)
    mb.finalize()
    S.dmast = link(bpy.data.objects.new('DerrickMast', hex_mesh('DerrickMast', mb, np.ones(len(mb.t_on), bool),
                                                                [S.m_wood, S.m_rope, S.m_stone])), coll)
    S.dmast.pass_index = PASS['crane']
    # windlass drum (turns while hoisting) with its handspikes
    wb = G.HexBatch('winch')
    wb.add(G.beam([-0.95, 0, 0], [0.95, 0, 0], 0.42), mat=0)
    for k in range(4):
        a = k * math.pi / 2
        for s in (-0.75, 0.75):
            wb.add(G.beam([s, 0.2 * math.cos(a), 0.2 * math.sin(a)], [s, 0.95 * math.cos(a), 0.95 * math.sin(a)], 0.07), mat=0)
    wb.finalize()
    S.dwinch = link(bpy.data.objects.new('DerrickWinch', hex_mesh('DerrickWinch', wb, np.ones(len(wb.t_on), bool),
                                                                  [S.m_wood])), coll)
    S.dwinch.pass_index = PASS['crane']
    S.dwinch.matrix_world = (Matrix.Translation((wx, wy, z0 + 1.2)) @ Matrix.Rotation(DERRICK_PHI, 4, 'Z'))
    S.dwinch_base = S.dwinch.matrix_world.copy()
    # the boom (origin on the mast axis at roof level, +x along the boom)
    bb = G.HexBatch('derrick_boom')
    tip = np.array(DERRICK_TIP)
    heel = np.array([0.0, 0.0, DERRICK_HEEL])
    bb.add(G.beam(heel + [0.35, 0, 0], tip, 0.4, 0.3), mat=0)
    bb.add(G.box(tip[0], 0, tip[2] - 0.45, 0.5, 0.45, 0.6), mat=0)                   # tip block
    mh = np.array([0.0, 0.0, DERRICK_MAST - 0.5])
    for dy in (-0.12, 0.12):                                                         # luffing tackle
        bb.add(G.beam(mh + [0.3, dy, 0], tip + [0, dy, 0.1], 0.05), mat=1)
    bb.add(G.beam(tip + [0, 0, -0.35], heel + [0.4, 0, -0.35], 0.06), mat=1)         # hoist fall
    bb.finalize()
    return hex_mesh('DerrickBoom', bb, np.ones(len(bb.t_on), bool), [S.m_wood, S.m_rope])


# ============================================================ build
class State:
    pass


def build(res=(1280, 720), look='dark', derrick=False, n_workers=70):
    global P
    P = PALETTES[look]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = TL.FPS
    sc.frame_start, sc.frame_end = 0, TL.NFRAMES - 1
    S = State()
    S.look = look
    S.sched = Schedule()
    coll = sc.collection

    # materials
    S.m_stone = mat_masonry('Limestone', *P['stone'])
    S.m_stone_dark = mat_masonry('Podium', *P['podium'], var=0.12)
    S.m_floor = mat_masonry('Paving', *P['paving'], width=0.04)
    S.m_wood = mat_wood('Timber', P['wood'])
    S.m_plank = mat_wood('Planks', P['plank'], width=0.04)
    S.m_rope = mat_simple('Rope', P['rope'], 0.9)
    S.m_bronze = mat_simple('Bronze', (0.62, 0.42, 0.20), 0.32, 1.0)
    S.m_cloth = mat_simple('Canvas', P['cloth'], 0.9)
    S.m_cloth2 = mat_simple('CanvasDark', P['cloth2'], 0.9)
    S.m_hull = mat_wood('Hull', P['hull'], textured=False)
    S.m_sail = mat_simple('Sail', P['sail'], 0.9)
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
    S.statue, S.sceptre = (statue_zeus_fine if look == 'bright' else statue_zeus)(S.m_bronze)
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
    S.props = build_props(coll, [S.m_stone_dark, S.m_wood, S.m_cloth, S.m_stone_dark, S.m_stone])
    S.city = build_city(coll, S.m_city)
    build_island_life(coll, [mat_simple('Scrub', P['scrub'], 0.95),
                             mat_wood('PalmTrunk', P['trunk']),
                             mat_simple('Frond', P['frond'], 0.8),
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
    S.derrick = derrick
    if derrick:
        cm_tall = build_derrick(S, coll)
        S.crane_tip_tall = np.array(DERRICK_TIP)
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
    palette = P['workers']
    for i in range(n_workers):
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
        hull, rig = ship_mesh([S.m_hull, S.m_sail], length=16.0, beam_w=6.5, sail=False, mast=look != 'bright')
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
    """Random value held constant for 1/rate seconds (time-lapse 'jumps').  With
    the palette's hop_desync every seed jumps at its own moment, so a crowd
    changes continuously instead of all at once (no pulsing)."""
    off = (seed * 0.6180339887) % 1.0 if P.get('hop_desync') else 0.0
    return float(G._hash2(np.int64(math.floor(t * rate + off)), np.int64(seed), 9))


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


def lantern_top(tc):
    """Top of the lantern work (drum..pedestal) at construction time tc."""
    p = TL.phase_progress('tier3', tc)
    return T3_Z0 + p * (STATUE_Z - T3_Z0) if p > 0 else T2_ROOF


def statue_track(p):
    """Statue base position and derrick slew for hoist progress p (0..1).
    Lift at the parking spot, slew with the load under the boom tip, lower."""
    park = Vector((STATUE_PARK[0], STATUE_PARK[1], T2_ROOF + 0.05))
    lift_z = STATUE_LIFT_Z
    if p <= 0.3:
        q = TL.ease_io(p / 0.3)
        return Vector((park.x, park.y, park.z + (lift_z - park.z) * q)), THETA_PARK
    if p <= 0.75:
        q = TL.ease_io((p - 0.3) / 0.45)
        th = THETA_PARK + (THETA_CENTER - THETA_PARK) * q
        x = DERRICK_C[0] + DERRICK_R * math.cos(th)
        y = DERRICK_C[1] + DERRICK_R * math.sin(th)
        return Vector((x, y, lift_z)), th
    q = TL.ease_io((p - 0.75) / 0.25)
    return Vector((0.0, 0.0, lift_z + (STATUE_Z - lift_z) * q)), THETA_CENTER


def pose(S, t, **kw):
    """Set the scene for video time t of the 30-s film.

    Keyword overrides decouple the clocks for other edits of the same scene:
      tc        construction time (which blocks, scaffolds, cranes exist)
      hour      time of day (sun, moon, sky)
      life      continuous animation clock (flames, embers, torches, barges, ships)
      hop_t     time-lapse clock for the 'jumping' workers, crane loads, stacks
      sea_t, water_t, cloud_t, shadow_t, cover, shadow_cover
      fire      beacon intensity 0..1, statue_p hoist progress 0..1
      cam       (location, target, lens); traffic=False hides ships and barges
      torch_t   clock of the torches' flicker (a time-lapse exposure averages it out)
      sky_log   dusk sky interpolated in log space (smooth ramps in a time-lapse)
    """
    sc = bpy.context.scene
    tc = kw.get('tc', t)
    hour = kw.get('hour', TL.clock(t))
    life = kw.get('life', t)
    hop_t = kw.get('hop_t', life)
    el, az = TL.sun_angles(hour)
    el_deg = math.degrees(el)
    day = TL.smoothstep(math.radians(-7), math.radians(5), el)
    night = 1.0 - day
    H = S.sched.height(tc)

    # --- masonry & timber
    set_dynamic_mesh(S.mas_obj, 'Masonry', S.masonry, S.masonry.select(tc), S.mas_mats)
    set_dynamic_mesh(S.tim_obj, 'Timber', S.timber, S.timber.select(tc), S.tim_mats)
    for o, t_on in S.lantern + S.tritons:
        o.hide_render = tc < t_on
    S.brazier.hide_render = tc < TL.phase_time('tier3', 0.29)

    # --- stone stacks on the yard (depleted and re-stocked)
    sb = G.HexBatch('stacks')
    t_end = TL.PHASES['tier3'][1]
    for k, (cx, cy) in enumerate([(-38, -40), (-44, 8), (40, -46), (22, -54), (-20, -52), (46, 40)]):
        if tc > t_end + 0.8:
            layers = 0 if k % 2 else 1
        else:
            layers = 1 + int(3.99 * smooth_rand(k + 50, hop_t, 0.8))
        for L in range(layers):
            for i in range(4 - (L > 1)):
                for j in range(3):
                    sb.add(G.box(cx + (i - 1.5) * 2.0, cy + (j - 1) * 1.3, GROUND_Z + L * 1.0, 1.9, 1.2, 0.98),
                           mat=0, tone=G._hash2(np.int64(k * 100 + i * 10 + j), np.int64(L), 3))
    sb.finalize()
    set_dynamic_mesh(S.stack_obj, 'Stacks', sb, np.ones(len(sb.t_on), bool), [S.m_stone])

    # --- cranes: two on the rising walls, one per terrace later, two at the quay
    t1a, t1b = TL.PHASES['tier1']
    t2a, t2b = TL.PHASES['tier2']
    st0, st1 = TL.PHASES['statue']
    removal = TL.PHASES['scaf2_down'][0] + 0.4
    statue_p = kw.get('statue_p')
    if statue_p is None:
        statue_p = TL.ease_io((tc - st0) / (st1 - st0))
    specs = []
    zt = max(H, PLAT_TOP)
    if t1a - 0.6 < tc < TL.PHASES['tier1cap'][1]:
        zc = min(zt, T1_TOP)
        a = tier_size(zc) - T1_THICK * 0.5
        specs += [((a, a, zc), 0), ((-a, -a, zc), 1)]
    if TL.PHASES['tier1cap'][1] - 0.3 < tc < t2b + 0.4:
        zc = T1_ROOF
        specs += [((10.6, -10.6, zc), 2), ((-10.6, 10.6, zc), 3)]
    if t2b - 0.2 < tc < removal:
        specs += [(((DERRICK_C[0], DERRICK_C[1], T2_ROOF) if S.derrick else (6.0, 6.0, T2_ROOF)), 4)]
    if TL.PHASES['platform'][0] - 0.5 < tc < removal + 0.5:
        specs += [(kw.get('crane5_loc', (34.0, -70.0, 2.8)), 5)]
    used = set()
    hoisting_window = st0 - 0.4 < tc < st1 + 0.3 or 'statue_p' in kw
    for (loc, idx) in specs:
        c, r, ld_ = S.cranes[idx]
        used.add(idx)
        tip = S.crane_tip_tall if idx == 4 else S.crane_tip
        slew = 2 * math.pi * smooth_rand(idx * 7 + 1, hop_t, 1.6) + idx
        if idx == 4 and S.derrick:
            slew = THETA_PARK + (THETA_CENTER - THETA_PARK) * smooth_rand(idx * 7 + 1, hop_t, 1.6)
        hoisting_statue = idx == 4 and hoisting_window
        if hoisting_statue:
            slew = statue_track(statue_p)[1] if S.derrick else math.atan2(-loc[1], -loc[0])
        c.hide_render = r.hide_render = False
        c.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(slew, 4, 'Z')
        tip_w = c.matrix_world @ Vector(tip)
        if hoisting_statue:
            r.hide_render = True
            ld_.hide_render = True
            continue
        base_z = GROUND_Z if idx in (0, 1, 5) else loc[2]
        frac = hop(idx * 13 + 3, hop_t, 3.0)
        load_z = base_z + 1.0 + frac * (tip_w.z - base_z - 3.0)
        if idx == 4 and S.derrick and math.hypot(tip_w.x, tip_w.y) < 7.0:
            load_z = max(load_z, lantern_top(tc) + 1.2)     # never hang a load inside the lantern
        length = max(tip_w.z - load_z, 0.5)
        r.matrix_world = Matrix.Translation(tip_w) @ Matrix.Diagonal((1, 1, length, 1))
        ld_.hide_render = hop(idx * 5 + 1, hop_t, 3.0) < 0.3
        ld_.matrix_world = Matrix.Translation((tip_w.x, tip_w.y, load_z)) @ Matrix.Rotation(slew, 4, 'Z')
    for idx, (c, r, ld_) in enumerate(S.cranes):
        if idx not in used:
            c.hide_render = r.hide_render = ld_.hide_render = True
    if S.derrick:
        S.dmast.hide_render = S.dwinch.hide_render = 4 not in used

    # --- statue: waits on the terrace, hoisted, set on the pedestal
    S.hoist.hide_render = True
    if tc < st0 - 0.5 and 'statue_p' not in kw:
        S.statue.hide_render = S.sceptre.hide_render = True
    else:
        S.statue.hide_render = S.sceptre.hide_render = False
        p = statue_p
        sway = 0.0
        if S.derrick:
            pos, _ = statue_track(p)
            if 0 < p < 1:
                sway = 0.04 * math.sin(life * 1.3)
            yaw = kw.get('statue_yaw', math.radians(-100))
        else:
            park = Vector((0.5, -7.6, T2_ROOF + 0.05))
            final = Vector((0.0, 0.0, STATUE_Z))
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
            if 0 < p < 1:
                sway = 0.4 * math.sin(life * 9)
            yaw = math.radians(-100)
        S.statue.location = pos
        S.statue.rotation_euler = (0, 0, yaw + sway)
        if 0 < p < 1 and 4 in used:
            c, _, _ = S.cranes[4]
            tip_w = c.matrix_world @ Vector(S.crane_tip_tall)
            top = pos + Vector((0, 0, STATUE_HOOK if S.derrick else 6.4))
            length = max(tip_w.z - top.z, 0.3)
            S.hoist.hide_render = False
            x, y = (tip_w.x, tip_w.y) if S.derrick else (top.x, top.y)
            S.hoist.matrix_world = Matrix.Translation((x, y, tip_w.z)) @ Matrix.Diagonal((1, 1, length, 1))
        if S.derrick and 4 in used:
            ang = -statue_p * 9.0 if hoisting_window else -hop_t * 2.0
            S.dwinch.matrix_world = S.dwinch_base @ Matrix.Rotation(ang, 4, 'X')

    # --- workers (time-lapse: they jump around a bit every few frames)
    rngw = np.random.default_rng(int(hop_t * TL.FPS / 3) + 1000)
    building = t1a - 0.5 < tc < removal
    crowd = kw.get('crowd', 1.0)
    n_top = int(16 * crowd) if building else 0
    active = 0.35 + 0.65 * day
    wi = 0
    for i in range(n_top):
        o = S.workers[wi]
        wi += 1
        vis = building and hop(i + 300, hop_t, 2.5) < active and H > PLAT_TOP + 0.5
        o.hide_render = not vis
        if vis:
            zz = S.sched.height(tc - 0.05)
            if zz > T2_TOP:
                zz = T2_ROOF
            th = T1_THICK if zz <= T1_TOP else T2_THICK
            x, y = top_ring_point(zz, hop(i + 900, hop_t, 3.0), th * 0.5)
            o.location = (x, y, zz)
            o.rotation_euler = (0, 0, rngw.uniform(0, 6.3))
    for i in range(int(14 * crowd)):   # on the scaffold planks just below the top
        o = S.workers[wi]
        wi += 1
        vis = building and hop(i + 400, hop_t, 2.0) < active and H > PLAT_TOP + 4
        o.hide_render = not vis
        if vis:
            zz = PLAT_TOP + 2.0 * (math.floor((H - PLAT_TOP) / 2.0) - hop(i + 77, hop_t, 2.0) * 2)
            zz = max(PLAT_TOP + 2.0, min(zz, T2_TOP - 1))
            if zz > T1_TOP + 1 and tc > TL.PHASES['scaf1_down'][0]:
                zz = max(zz, T2_Z0 + 2)
            size = tier_size(zz)
            Pl = G.square_poly(size + 0.8) if zz <= T1_TOP else G.oct_poly(size + 0.75)
            n = len(Pl)
            s = hop(i + 555, hop_t, 2.0) * n
            k = int(s) % n
            p = Pl[k] + (Pl[(k + 1) % n] - Pl[k]) * (s - int(s))
            o.location = (p[0], p[1], zz + 0.05)
    for i in range(int(40 * crowd)):   # on the ground: stacks, quay, camp
        o = S.workers[wi]
        wi += 1
        vis = hop(i + 500, hop_t, 1.5) < (0.25 + 0.75 * day) * (1.0 if tc < removal + 1 else 0.3)
        o.hide_render = not vis
        if vis:
            ang = 2 * math.pi * G._hash2(np.int64(i), np.int64(1), 1) + smooth_rand(i, hop_t, 0.7) * 1.5
            rad = 34 + 30 * G._hash2(np.int64(i), np.int64(2), 1) + 6 * smooth_rand(i + 40, hop_t, 1.1)
            x, y = rad * math.cos(ang), rad * math.sin(ang)
            o.location = (x, y, float(island_height(np.array([x]), np.array([y]))[0]))
            o.rotation_euler = (0, 0, ang + 1.6)
    for o in S.workers[wi:]:
        o.hide_render = True
    S.n_workers_used = wi

    # --- ships (daylight traffic in the harbour) and stone barges
    traffic = kw.get('traffic', True)
    for i, (h, r) in enumerate(S.ships):
        speed = 90 + 60 * i
        y = -520 - 170 * i
        x = ((life * speed + 900 * i) % 5200) - 2600
        dirn = 1 if i % 2 == 0 else -1
        h.location = (x * dirn, y, 0.3)
        h.rotation_euler = (0, 0, 0 if dirn > 0 else math.pi)
        h.hide_render = r.hide_render = day < 0.25 or not traffic
    for i, (h, r, cg) in enumerate(S.barges):
        cyc = 3.2
        ph = ((life + i * cyc / 3) % cyc) / cyc
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
        active_b = TL.PHASES['platform'][0] < tc < TL.PHASES['tier3'][1] and traffic
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
    S.sun.data.energy = kw.get('sun_energy', 6.5) * sun_k
    S.sun.data.color = (1.0, 0.52 + 0.4 * warm, 0.28 + 0.6 * warm)
    S.sun.hide_render = sun_k <= 0.0
    moon_up = max(0.0, mdir[2])
    moon_k = kw.get('moon', 1.0)
    S.moon.data.energy = 0.42 * night * TL.smoothstep(0.0, 0.25, moon_up) * kw.get('moon_light', moon_k)
    S.moon.hide_render = S.moon.data.energy <= 1e-4
    zen, hor, glow, cl_lit, cl_dark = sky_palette(el_deg, S.look, log=kw.get('sky_log', False))
    nt = S.world.node_tree.nodes
    for nm, col in (('zenith', zen), ('horizon', hor), ('sunglow', glow), ('cloud_lit', cl_lit),
                    ('cloud_dark', cl_dark)):
        nt[nm].outputs[0].default_value = col + (1.0,)
    for i, v in enumerate(sdir):
        nt['sun_dir'].inputs[i].default_value = float(v)
    for i, v in enumerate(mdir):
        nt['moon_dir'].inputs[i].default_value = float(v)
    nt['cloud_time'].outputs[0].default_value = kw.get('cloud_t', t * 1.6)
    nt['cloud_gain'].outputs[0].default_value = kw.get('cloud_gain', 3.2)
    nt['moon'].outputs[0].default_value = 6.0 * night * moon_k
    nt['sun_disc'].outputs[0].default_value = 30.0 * TL.smoothstep(-1.0, 1.0, el_deg)
    if 'hdri_k' in nt:
        nt['hdri_k'].outputs[0].default_value = kw.get('hdri', 0.0)
        nt['hdri_rot'].outputs[0].default_value = kw.get('hdri_rot', 0.0)
        zd, hd = sky_palette(45.0, S.look)[:2]
        w = 0.5 + 0.5 * TL.smoothstep(3.0, -3.0, el_deg)       # half the warmth by day, all of the dark by night
        for name, now, day_ in (('hdri_tint', zen, zd), ('hdri_tint_h', hor, hd)):
            nt[name].outputs[0].default_value = tuple((n / d) ** w for n, d in zip(now, day_)) + (1.0,)
    nt['cover'].outputs[0].default_value = kw.get(
        'cover', 0.6 + 0.1 * math.sin(t * 0.37) - 0.16 * TL.smoothstep(24.0, 27.0, t))

    S.m_cshadow.node_tree.nodes['shadow_time'].outputs[0].default_value = kw.get('shadow_t', t * 260.0)
    S.m_cshadow.node_tree.nodes['shadow_cover'].outputs[0].default_value = kw.get(
        'shadow_cover', 0.40 + 0.08 * math.sin(t * 0.37))
    # --- water, city lights, ocean
    S.ocean.time = kw.get('sea_t', t * 2.2)
    S.sea.data.materials[0].node_tree.nodes['water_time'].outputs[0].default_value = kw.get('water_t', t * 0.9)
    S.m_city.node_tree.nodes['city_lights'].outputs[0].default_value = 6.0 * night

    # --- the beacon
    f0, f1 = TL.PHASES['fire']
    if 'fire' in kw:
        fire_k = kw['fire']
        surge = kw.get('fire_surge', 0.0)
    else:
        fire_k = TL.ease((tc - f0) / (f1 - f0))
        surge = 0.6 * max(0.0, 1 - (tc - f0) / 0.5) * (tc > f0)
    flick = 0.85 + 0.15 * math.sin(life * 31.0) * math.sin(life * 17.3 + 1.0)
    S.m_fire.node_tree.nodes['fire_k'].outputs[0].default_value = fire_k * (1.0 + surge)
    S.m_fire.node_tree.nodes['fire_time'].outputs[0].default_value = life * 3.0
    S.beacon.data.energy = 26000.0 * fire_k * flick
    S.beacon.hide_render = fire_k <= 0
    for i, fo in enumerate(S.flames):
        fo.hide_render = fire_k <= 0.01
        sz = fire_k * (0.8 + 0.35 * smooth_rand(i + 70, life, 9.0))
        fo.scale = (sz, sz, sz * (0.8 + 0.5 * smooth_rand(i + 90, life, 11.0)))
        fo.rotation_euler = (0.18 * (smooth_rand(i + 20, life, 6.0) - 0.5), 0.18 * (smooth_rand(i + 30, life, 6.0) - 0.5), 0)
    for i, eo in enumerate(S.embers):
        lf = (life * 0.9 + i / len(S.embers)) % 1.0
        ang = i * 2.4 + life * 1.3
        rr = 0.6 + 2.5 * lf
        eo.hide_render = fire_k < 0.3
        eo.location = (rr * math.cos(ang), rr * math.sin(ang), COL_Z0 + 1.0 + lf * 9.0)
        eo.scale = (1 - lf,) * 3

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
    if tc > TL.PHASES['platform'][1]:
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
            fl = 0.8 + 0.2 * smooth_rand(i + 200, kw.get('torch_t', life), 8.0)
            lo.location = (x, y, z + 0.6)
            fo.location = (x, y, z)
            fo.scale = (s * fl,) * 3
            lo.data.energy = 900.0 * tk * s * fl
            lo.hide_render = fo.hide_render = False
        else:
            lo.hide_render = fo.hide_render = True

    # --- camera
    if 'cam' in kw:
        loc, tgt, lens = kw['cam']
        S.cam.data.lens = lens
    else:
        fi = min(int(round(t * TL.FPS)), TL.NFRAMES - 1)
        loc, tgt = S.cam_track[fi]
    look_at(S.cam, loc, tgt)
    return dict(t=t, hour=hour, sun_el=el_deg, day=day, height=H, fire=fire_k,
                horizon=hor, zenith=zen)
