"""Dresden about 1730, for the film "J. S. Bachs Kathedrale" (wunderfilm_13_bach).

The wonder is George Baehr's Frauenkirche (1726-1743) on the Neumarkt, here
reconstructed from its published dimensions and built in Elbe sandstone,
course by course:

  body      a square of 40 m with its corners cut back, three tiers of arched
            windows, portals on the north, west and south, pilasters, string
            courses and the main cornice at 24 m; the choir (apse) on the east
  towers    four stair towers on the cut corners, rising above the cornice
            to little stone cupolas
  bell      the "Glockenfuss": a concave stone skirt from the square to the
            round drum, then the stone dome, bell-shaped, 28 m across, closed
            at 60 m by a crown ring; the lantern with eight arched openings,
            its cupola, the spire, the orb and the cross at 88 m
  inside    eight piers under the dome, three tiers of galleries round the
            central space, the altar in the choir and the Silbermann organ
            above it (case, pipe towers, console on the organ gallery), pews

The dome is laid over a timber centering (sixteen ribs and their lagging)
that stays until the crown ring is closed; the walls rise in a putlog
scaffold that climbs with the work, the dome in a scaffold of its own.

Around it: the Neumarkt with baroque houses (plastered, mansard roofs), the
city in blocks, the fortress wall along the Elbe with a gate and a landing
below it (a stone quay, a wooden pier, sandstone blocks), the Elbe with the
long stone bridge, the Neustadt on the far bank.  Coordinates: metres, +x
east, +y north, the Neumarkt at z = 0, the Elbe at z = -7.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix

import geometry as G
import rhodes as RH
import scene as SC

LATITUDE_DEG = 51.05
WATER_Z = -7.0
BANK_Y = 250.0                        # the Elbe's south bank (water from here)
FAR_Y = 360.0                         # its north bank
WALL_Y = 205.0                        # the fortress wall along the river
STRAND_Z = -5.6
LANDING_X = -75.0                     # the gate in the fortress wall and the landing below it
BRIDGE_X = -260.0

# ---- the church (origin at the centre of the square body, east = +x)
HALF = 20.0                           # half-width of the square body (outer face)
CHAMF = 6.5                           # the corners cut back for the stair towers
WALL_T = 1.8
COURSE = 0.6                          # ashlar courses of the walls
Z_CORNICE = 24.0
TOWER_R = 4.2                         # the stair towers (octagons)
TOWER_Z = 32.0                        # their bodies end here, the cupolas above
APSE_R = 10.5
APSE_Z = 21.0
PIER_R = 12.0                         # the eight piers under the dome
SKIRT = (24.0, 31.0)                  # the bell's foot, from the square to the drum
DOME_PROFILE = [(24.0, 14.2), (31.0, 14.2), (34.0, 13.8), (38.0, 13.4), (42.0, 12.9), (46.0, 12.1), (50.0, 10.9),
                (53.0, 9.5), (56.0, 7.6), (58.0, 5.9), (60.0, 4.3)]
DOME_TOP = 60.0
LANTERN = (60.0, 69.0)
CROSS_TOP = 88.0
GALLERIES = (7.0, 12.0, 17.0)
ORGAN_Z = 13.5                        # the organ gallery in the choir

# ---- construction clock (tc)
TC_WALLS = (0.2, 3.2)                 # walls, piers and towers to the cornice
TC_TOWERS = (3.2, 4.0)                # the stair towers above the cornice and their cupolas
TC_SKIRT = (3.3, 4.0)
TC_CENTER = (3.8, 4.2)                # the centering is raised
TC_DOME = (4.2, 7.0)
TC_LANTERN = (7.0, 7.8)
TC_CENTER_OFF = (7.8, 8.1)            # struck once the crown ring carries the lantern
TC_SCAF_DOWN = (8.0, 8.8)
TC_INSIDE = (8.8, 9.2)                # altar and organ (the galleries go in with the walls)


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


# ================================================================== ground and river
def height(X, Y):
    """The Neumarkt and the city at 0, the strand below the fortress wall, the
    Elbe, the far bank rising gently to the Neustadt."""
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    city = 0.15 * G.fbm(X / 60.0, Y / 60.0, 2, seed=3)
    strand = STRAND_Z - 1.9 * np.clip((Y - (WALL_Y + 12.0)) / (BANK_Y - WALL_Y - 12.0), 0, 1) ** 1.5
    river = WATER_Z - 2.5
    far = -1.2 + 0.004 * np.maximum(Y - FAR_Y - 20.0, 0.0) + 0.2 * G.fbm(X / 80.0, Y / 80.0, 2, seed=4)
    h = np.where(Y < WALL_Y + 6.0, city, strand)
    h = np.where(Y > BANK_Y + 4.0, river, h)
    up = np.clip((Y - (FAR_Y - 14.0)) / 14.0, 0, 1)
    h = np.where(Y > FAR_Y - 14.0, river + (far - river) * up, h)
    return h


def ground_z(x, y):
    return float(height(np.array([x]), np.array([y]))[0])


def mat_ground():
    """Cobbles on the squares and streets, trodden earth and sand on the strand
    and the building site, grass on the far bank."""
    m, nb, out = SC.new_material('DresdenGround')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    x_, y_, z = nb.sep(pos)
    n1 = nb.noise(pos, 0.08, 4.0, 0.6).outputs['Fac']
    n2 = nb.noise(pos, 0.9, 3.0, 0.6).outputs['Fac']
    cob = nb.mix(n2, (0.36, 0.33, 0.29, 1), (0.47, 0.43, 0.37, 1))
    vx = nb.new('ShaderNodeTexVoronoi')
    vx.inputs['Scale'].default_value = 5.0
    nb.feed(vx.inputs['Vector'], pos)
    stones = nb.smooth(0.0, 0.08, vx.outputs['Distance'])
    far = nb.smooth(0.02, 0.08, SC.pixel_footprint(nb))
    cob = nb.mix(nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, stones), nb.math('SUBTRACT', 1.0, far)), cob, (0.22, 0.20, 0.17, 1))
    earth = nb.mix(n1, (0.42, 0.36, 0.27, 1), (0.52, 0.45, 0.34, 1))
    site = nb.math('MULTIPLY', nb.smooth(62.0, 40.0, nb.math('MAXIMUM', nb.math('ABSOLUTE', x_), nb.math('ABSOLUTE', y_))),
                   nb.smooth(0.3, 0.6, nb.noise(pos, 0.05, 3.0, 0.6).outputs['Fac']))
    col = nb.mix(nb.math('MULTIPLY', site, 0.8), cob, earth)
    strand = nb.smooth(-1.0, -3.0, z)
    sand = nb.mix(n1, (0.50, 0.44, 0.33, 1), (0.40, 0.35, 0.26, 1))
    col = nb.mix(strand, col, sand)
    grass = nb.mix(n1, (0.18, 0.24, 0.09, 1), (0.30, 0.33, 0.14, 1))
    farbank = nb.smooth(FAR_Y - 5.0, FAR_Y + 15.0, y_)
    col = nb.mix(nb.math('MULTIPLY', farbank, nb.smooth(0.3, 0.6, n2)), col, grass)
    b = SC.principled(nb, col, rough=0.93, spec=0.25)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.3
    nb.feed(bump.inputs['Height'], nb.math('ADD', stones, nb.math('MULTIPLY', n2, 0.5)))
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_ground(coll):
    xs = RH._graded(-5000.0, 5000.0, -320.0, 320.0, 1.5, growth=1.1)
    ys = RH._graded(-5000.0, 5000.0, -200.0, 420.0, 1.5, growth=1.1)
    X, Y = np.meshgrid(xs, ys)
    Z = height(X, Y)
    V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    nx = len(xs)
    idx = np.arange(len(ys) * nx).reshape(len(ys), nx)
    Q = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
    me = SC.mesh_from_arrays('DresdenGround', V, Q, mats=[mat_ground()], smooth=True)
    o = SC.link(bpy.data.objects.new('DresdenGround', me), coll)
    o.pass_index = SC.PASS['terrain']
    return o


# ================================================================== materials
def mat_sandstone(name='Sandstone', base=(0.80, 0.71, 0.55)):
    """Elbe sandstone, freshly dressed: warm light ochre, a tone per block."""
    return SC.mat_masonry(name, base, (0.62, 0.58, 0.50), var=0.08, width=0.025, grime=0.12)


def mat_church_stone():
    """The church's stones: Elbe sandstone outside; inside, the walls and piers are
    plastered cream and the dome is painted (warm, softly mottled), decided per face
    from where a point just off the face lies."""
    m = mat_sandstone('ChurchStone')
    nt = m.node_tree
    bsdf = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    src = bsdf.inputs['Base Color'].links[0].from_socket
    geo = nt.nodes.new('ShaderNodeNewGeometry')

    def math(op, a, b=None):
        n = nt.nodes.new('ShaderNodeMath')
        n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = float(v)
            else:
                nt.links.new(v, n.inputs[i])
        return n.outputs[0]
    sepP = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(geo.outputs['Position'], sepP.inputs[0])
    sepN = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(geo.outputs['Normal'], sepN.inputs[0])
    px, py, pz = sepP.outputs
    nx, ny, nz = sepN.outputs
    qx = math('ADD', px, math('MULTIPLY', nx, 0.4))
    qy = math('ADD', py, math('MULTIPLY', ny, 0.4))
    qz = math('ADD', pz, math('MULTIPLY', nz, 0.4))
    body = math('MULTIPLY', math('LESS_THAN', math('MAXIMUM', math('ABSOLUTE', qx), math('ABSOLUTE', qy)), HALF - WALL_T + 0.1),
                math('LESS_THAN', qz, Z_CORNICE + 0.2))
    r = math('SQRT', math('ADD', math('MULTIPLY', px, px), math('MULTIPLY', py, py)))
    inward = math('LESS_THAN', math('ADD', math('MULTIPLY', nx, px), math('MULTIPLY', ny, py)), 0.0)
    dome = math('MULTIPLY', math('MULTIPLY', math('GREATER_THAN', qz, Z_CORNICE + 0.2), math('LESS_THAN', r, 15.0)), inward)
    ax = HALF - 0.9
    dx = math('SUBTRACT', qx, ax)
    apse = math('MULTIPLY', math('MULTIPLY', math('LESS_THAN', math('ADD', math('MULTIPLY', dx, dx), math('MULTIPLY', qy, qy)),
                                                  (APSE_R - 1.4) ** 2), math('GREATER_THAN', qx, ax - 0.5)),
                math('LESS_THAN', qz, APSE_Z + 6.0))
    inside = math('MINIMUM', math('ADD', math('ADD', body, dome), apse), 1.0)
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 0.35
    noise.inputs['Detail'].default_value = 3.0
    nt.links.new(geo.outputs['Position'], noise.inputs['Vector'])
    fresco = nt.nodes.new('ShaderNodeValToRGB')
    fresco.color_ramp.elements[0].color = (0.80, 0.66, 0.48, 1)
    fresco.color_ramp.elements[1].color = (0.58, 0.62, 0.72, 1)
    fresco.color_ramp.elements.new(0.5).color = (0.86, 0.78, 0.62, 1)
    nt.links.new(noise.outputs['Fac'], fresco.inputs['Fac'])
    painted = math('MULTIPLY', dome, math('GREATER_THAN', qz, 31.5))
    mixd = nt.nodes.new('ShaderNodeMix')
    mixd.data_type = 'RGBA'
    nt.links.new(painted, mixd.inputs['Factor'])
    mixd.inputs[6].default_value = (0.88, 0.85, 0.77, 1)                  # plaster
    nt.links.new(fresco.outputs['Color'], mixd.inputs[7])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    nt.links.new(inside, mix.inputs['Factor'])
    nt.links.new(src, mix.inputs[6])
    nt.links.new(mixd.outputs[2], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])
    return m


def mat_houses():
    """Baroque Dresden: plaster in cream, pale yellow, sandstone, pink and pale
    green (tone per house), window rows lit at night."""
    m = RH.mat_houses()
    m.name = 'DresdenHouses'
    ramp = [n for n in m.node_tree.nodes if n.type == 'VALTORGB'][0]
    els = ramp.color_ramp.elements
    cols = [(0.0, (0.88, 0.84, 0.72)), (0.3, (0.86, 0.78, 0.56)), (0.5, (0.78, 0.72, 0.60)),
            (0.7, (0.84, 0.70, 0.62)), (1.0, (0.72, 0.76, 0.64))]
    while len(els) < len(cols):
        els.new(0.5)
    for e, (p, c) in zip(els, cols):
        e.position = p
        e.color = c + (1.0,)
    return m


def mat_slate():
    m, nb, out = SC.new_material('SlateRoof')
    pos = nb.new('ShaderNodeNewGeometry').outputs['Position']
    tone = nb.attr('tone').outputs['Fac']
    base = nb.mix(tone, (0.20, 0.21, 0.23, 1), (0.46, 0.22, 0.14, 1))       # slate or red tile, per house
    n = nb.noise(pos, 0.7, 3.0, 0.6).outputs['Fac']
    col = SC.mul_col(nb, base, nb.comb(nb.math('ADD', 0.8, nb.math('MULTIPLY', n, 0.4)),
                                       nb.math('ADD', 0.8, nb.math('MULTIPLY', n, 0.4)),
                                       nb.math('ADD', 0.8, nb.math('MULTIPLY', n, 0.4))))
    b = SC.principled(nb, col, 0.7, 0.0, 0.4)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def mat_gold():
    return SC.mat_simple('Gilt', (0.83, 0.62, 0.26), 0.3, metal=1.0)


def mat_tin():
    return SC.mat_simple('OrganTin', (0.78, 0.78, 0.76), 0.22, metal=1.0)


# ================================================================== the city
def mansard_house(hb, x, y, w, d, h, rot, tone, wall_mat=0, roof_mat=1):
    """A baroque town house: plastered block and a mansard roof (steep lower
    slopes, a low hipped top)."""
    c, s = math.cos(rot), math.sin(rot)
    z0 = ground_z(x, y)
    hb.add(G.box(x, y, z0 - 1.0, w, d, h + 1.0, rot), mat=wall_mat, tone=tone)
    R = np.array([[c, s], [-s, c]])

    def quad(hw, hd):
        return np.array([[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]]) @ R + [x, y]
    inset = min(1.3, 0.2 * min(w, d))
    hb.add(G._hexa(quad(w / 2 + 0.3, d / 2 + 0.3), quad(w / 2 - inset, d / 2 - inset), z0 + h, z0 + h + 3.4), mat=roof_mat, tone=tone)
    top = np.array([[-(w / 2 - inset), 0.0], [w / 2 - inset, 0.0], [w / 2 - inset, 0.0], [-(w / 2 - inset), 0.0]])
    top[:, 0] *= 0.6
    hb.add(G._hexa(quad(w / 2 - inset, d / 2 - inset), top @ R + [x, y], z0 + h + 3.4, z0 + h + 5.2), mat=roof_mat, tone=tone)
    for k in range(2):                                                   # chimneys
        cx_, cy_ = np.array([(k - 0.5) * w * 0.5, 0.0]) @ R + [x, y]
        hb.add(G.box(cx_, cy_, z0 + h + 3.0, 0.7, 0.7, 3.4, rot), mat=wall_mat, tone=0.5)


def block_of_houses(hb, rng, x0, x1, y0, y1, depth=14.0, h_rng=(13.0, 19.0), skip=None):
    """Houses along the four edges of a city block, facing the streets."""
    for side in range(4):
        if side in (0, 2):                                               # south / north edges, facades along x
            y = y0 + depth / 2 if side == 0 else y1 - depth / 2
            rot = 0.0 if side == 0 else math.pi
            x = x0 + 1.0
            while x < x1 - 4.0:
                w = min(rng.uniform(10.0, 16.0), x1 - x)
                cx_ = x + w / 2
                if not (skip and skip(cx_, y)):
                    mansard_house(hb, cx_, y, w - 0.3, depth, rng.uniform(*h_rng), rot, float(rng.random()))
                x += w
        else:                                                            # east / west edges
            x = x1 - depth / 2 if side == 1 else x0 + depth / 2
            rot = math.pi / 2 if side == 1 else -math.pi / 2
            y = y0 + depth + 0.5
            while y < y1 - depth - 4.0:
                w = min(rng.uniform(10.0, 16.0), y1 - depth - y)
                cy_ = y + w / 2
                if not (skip and skip(x, cy_)):
                    mansard_house(hb, x, cy_, w - 0.3, depth, rng.uniform(*h_rng), rot, float(rng.random()))
                y += w


NEUMARKT = (-60.0, 50.0, -58.0, 52.0)            # the open square round the church (x0, x1, y0, y1)


def build_city(coll, m_houses, m_roof):
    """Blocks of houses on a street grid round the Neumarkt, up to the fortress
    wall; the Neustadt on the far bank."""
    hb = G.HexBatch('city')
    rng = np.random.default_rng(1733)
    pitch_x, pitch_y, street = 72.0, 64.0, 11.0
    for i in range(-7, 7):
        for j in range(-6, 3):
            x0 = NEUMARKT[0] + i * pitch_x
            y0 = NEUMARKT[2] + j * pitch_y
            x1, y1 = x0 + pitch_x - street, y0 + pitch_y - street
            if y1 > WALL_Y - 12.0:
                y1 = WALL_Y - 12.0
            if y1 - y0 < 30.0:
                continue
            if x1 > NEUMARKT[0] - 2 and x0 < NEUMARKT[1] + 2 and y1 > NEUMARKT[2] - 2 and y0 < NEUMARKT[3] + 2:
                continue                                                 # the square itself
            block_of_houses(hb, rng, x0, x1, y0, y1)
    for i in range(-8, 8):                                               # the Neustadt
        for j in range(0, 5):
            x0 = -300.0 + i * 80.0
            y0 = FAR_Y + 40.0 + j * 70.0
            block_of_houses(hb, rng, x0, x0 + 68.0, y0, y0 + 58.0, h_rng=(10.0, 16.0))
    hb.finalize()
    me = SC.hex_mesh('City', hb, np.ones(len(hb.t_on), bool), [m_houses, m_roof])
    o = SC.link(bpy.data.objects.new('City', me), coll)
    o.pass_index = SC.PASS['city']
    return o


def build_fortress(coll, m_stone, m_wood):
    """The fortress wall along the Elbe with a parapet, a bastion, the gate to the
    landing and a ramp down to the strand; the landing: a stone quay, a pier."""
    fb = G.HexBatch('fortress')
    x = -420.0
    while x < 420.0:
        L = 6.0
        if abs(x + L / 2 - LANDING_X) < 5.5:
            x += L
            continue
        fb.add(G.box(x + L / 2, WALL_Y + 3.5, STRAND_Z - 1.0, L - 0.02, 7.0, -STRAND_Z + 1.0 + 1.2), mat=0)
        fb.add(G.box(x + L / 2, WALL_Y + 6.6, 1.2, L - 0.02, 0.8, 1.1), mat=0)          # parapet
        x += L
    for k in range(10):                                                  # a bastion towards the river
        a0 = math.pi * k / 10
        cx_, cy_ = 120.0 + 26.0 * math.cos(a0 + math.pi), WALL_Y + 7.0 + 22.0 * math.sin(a0)
        fb.add(G.box(cx_, cy_, STRAND_Z - 1.5, 9.0, 9.0, -STRAND_Z + 2.4, a0), mat=0)
    fb.add(G.box(LANDING_X - 7.0, WALL_Y + 3.5, STRAND_Z - 1.0, 3.0, 8.0, -STRAND_Z + 7.5), mat=0)   # the gate's piers
    fb.add(G.box(LANDING_X + 7.0, WALL_Y + 3.5, STRAND_Z - 1.0, 3.0, 8.0, -STRAND_Z + 7.5), mat=0)
    fb.add(G.box(LANDING_X, WALL_Y + 3.5, 3.4, 11.0, 8.0, 2.8), mat=0)                          # the arch's lintel
    fb.add(G.tent(LANDING_X, WALL_Y + 3.5, 6.2, 12.0, 9.0, 3.2, 0.0), mat=2)
    for k in range(10):                                                  # the ramp down to the strand
        y = WALL_Y + 1.0 + k * 1.2
        z = -0.3 - (STRAND_Z + 0.3) * (-k / 10.0)
        fb.add(G.box(LANDING_X, y + 0.6, STRAND_Z - 1.0, 9.0, 1.25, z - STRAND_Z + 1.0), mat=0)
    fb.add(G.box(LANDING_X, WALL_Y + 26.0, STRAND_Z - 3.0, 26.0, 22.0, 3.0 - 0.2), mat=0)        # the quay
    for k in range(12):                                                  # the pier on posts
        y = WALL_Y + 37.0 + k * 2.5
        for dx in (-1.6, 1.6):
            fb.add(G.box(LANDING_X + 6.0 + dx, y, WATER_Z - 3.0, 0.35, 0.35, 3.0 + (STRAND_Z - WATER_Z) + 0.4), mat=1)
        fb.add(G.box(LANDING_X + 6.0, y, STRAND_Z + 0.2, 4.0, 2.4, 0.22), mat=1)
    fb.finalize()
    o = SC.link(bpy.data.objects.new('Fortress', SC.hex_mesh('Fortress', fb, np.ones(len(fb.t_on), bool),
                                                              [m_stone, m_wood, SC.mat_simple('GateRoof', (0.22, 0.22, 0.24), 0.7)])), coll)
    o.pass_index = SC.PASS['masonry']
    return o


def build_bridge(coll, m_stone):
    """The long stone bridge over the Elbe: segmental arches on piers with cutwaters."""
    bb = G.HexBatch('bridge')
    y0, y1 = WALL_Y - 10.0, FAR_Y + 30.0
    n = 12
    span = (y1 - y0) / n
    deck = 1.5
    for k in range(n + 1):
        y = y0 + k * span
        bb.add(G.box(BRIDGE_X, y, WATER_Z - 3.0, 12.0, 4.2, deck - WATER_Z + 1.5), mat=0)            # pier
        if 0 < k < n:
            bb.add(G.tent(BRIDGE_X, y, deck + 0.2, 12.4, 4.6, 0.0, 0.0), mat=0)
            for sgn in (-1, 1):                                                                        # cutwaters
                bb.add(G.box(BRIDGE_X + sgn * 7.0, y, WATER_Z - 3.0, 3.0, 3.0, 5.0, math.pi / 4), mat=0)
        if k < n:
            for j in range(8):                                                                         # the arch, in slabs
                u0, u1 = j / 8, (j + 1) / 8
                yy0 = y + 2.1 + (span - 4.2) * u0
                yy1 = y + 2.1 + (span - 4.2) * u1
                zb = WATER_Z + 1.0 + 5.2 * (1.0 - (2 * (0.5 * (u0 + u1)) - 1) ** 2)
                bb.add(G.box(BRIDGE_X, 0.5 * (yy0 + yy1), zb, 12.0, yy1 - yy0 + 0.02, deck - zb), mat=0)
    bb.add(G.box(BRIDGE_X, 0.5 * (y0 + y1), deck, 12.0, y1 - y0, 0.4), mat=0)
    for sgn in (-1, 1):
        bb.add(G.box(BRIDGE_X + sgn * 5.8, 0.5 * (y0 + y1), deck + 0.4, 0.5, y1 - y0, 1.0), mat=0)
    bb.finalize()
    o = SC.link(bpy.data.objects.new('Bridge', SC.hex_mesh('Bridge', bb, np.ones(len(bb.t_on), bool), [m_stone])), coll)
    o.pass_index = SC.PASS['masonry']
    return o


# ================================================================== the church
def body_poly(a):
    """The square body with its corners cut back (CCW from the east side's south end).
    Sides: 0 east, 1 NE, 2 north, 3 NW, 4 west, 5 SW, 6 south, 7 SE."""
    c = CHAMF
    return np.array([[a, -a + c], [a, a - c], [a - c, a], [-a + c, a], [-a, a - c], [-a, -a + c], [-a + c, -a], [a - c, -a]], float)


def _ray_body(a, th):
    ct, st = abs(math.cos(th)), abs(math.sin(th))
    return min(a / max(ct, 1e-6), a / max(st, 1e-6), (2 * a - CHAMF) / max(ct + st, 1e-6))


def skirt_poly(a, n=64):
    """From the cut square (a = 20) to the round drum (a = 14.2), by angle."""
    s = clamp((a - 14.2) / (HALF - 14.2))
    ang = -math.pi / 2 + np.arange(n) * 2 * math.pi / n
    r = np.array([s * _ray_body(a, t) + (1 - s) * a for t in ang])
    return np.stack([r * np.cos(ang), r * np.sin(ang)], 1)


def dome_r(z):
    zs, rs = zip(*DOME_PROFILE)
    return float(np.interp(z, zs, rs))


def dome_t(z):
    return 2.0 if z < 31.0 else 1.5 - 0.6 * clamp((z - 31.0) / (DOME_TOP - 31.0))


TOWERS = [(17.4 * sx, 17.4 * sy) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]


def oct_prism(cb, cx, cy, r0, r1, z0, z1, **kw):
    """An octagonal prism (or frustum) as three hexahedra."""
    B = G.oct_poly(r0) + [cx, cy]
    T = G.oct_poly(r1) + [cx, cy]
    for q in ((0, 1, 2, 3), (0, 3, 4, 7), (4, 5, 6, 7)):
        cb.add(G._hexa(B[list(q)], T[list(q)], z0, z1), **kw)


def tc_at(z, span, z0, z1):
    return span[0] + (span[1] - span[0]) * clamp((z - z0) / (z1 - z0))


def build_church():
    """All the stones of the church, each with the tc at which it is set;
    mats: 0 sandstone, 1 dark joints/voids (glass), 2 timber (galleries, centering),
    3 gilt, 4 organ tin, 5 white case paint, 6 pews."""
    cb = G.HexBatch('church')
    # -- foundation plate
    cb.add(G.box(0, 0, -1.4, 2 * HALF + 2.0, 2 * HALF + 2.0, 0.8), t_on=TC_WALLS[0] - 0.15, mat=0)
    n_c = int(round(Z_CORNICE / COURSE))
    for k in range(n_c):
        z0, z1 = k * COURSE - 0.6, (k + 1) * COURSE - 0.6
        zc = 0.5 * (z0 + z1)
        tk = tc_at(z0, TC_WALLS, -0.6, Z_CORNICE)
        tk1 = tc_at(z1, TC_WALLS, -0.6, Z_CORNICE)
        openings = {}
        for side in (2, 4, 6):                                           # north, west, south facades
            holes = []
            for u in (0.12, 0.31, 0.5, 0.69, 0.88):
                if side != 6 or True:
                    if abs(u - 0.5) < 0.01 and zc < 6.0:
                        holes.append((u - 0.06, u + 0.06))                # the portals
                    elif 1.5 < zc < 7.5 or 9.5 < zc < 15.5 or 17.6 < zc < 22.2:
                        holes.append((u - 0.033, u + 0.033))              # three tiers of windows
            openings[side] = holes
        if zc < 20.0:
            openings[0] = [(0.14, 0.86)]                                  # the choir arch
        pieces = G.ring_course(body_poly, HALF, HALF, WALL_T, z0, z1, 1.7, k, openings=openings)
        for corners, order in pieces:
            cb.add(corners, t_on=tk + (tk1 - tk) * order, mat=0)
        # string courses and the main cornice
        if abs(z1 - 8.4) < 0.31 or abs(z1 - 16.8) < 0.31:
            for corners, order in G.ring_course(body_poly, HALF + 0.3, HALF + 0.3, 0.6, z1 - 0.3, z1, 2.5, k):
                cb.add(corners, t_on=tk1, mat=0)
        # the piers inside
        for p in range(8):
            a = math.radians(22.5 + 45 * p)
            cb.add(G.box(PIER_R * math.cos(a), PIER_R * math.sin(a), z0, 2.4, 2.4, COURSE, a), t_on=tk + 0.02, mat=0)
        # the stair towers (octagons) with the walls
        for tx, ty in TOWERS:
            for corners, order in G.ring_course(lambda r: G.oct_poly(r) + [tx, ty], TOWER_R, TOWER_R, 0.9, z0, z1, 1.6, k):
                cb.add(corners, t_on=tk + (tk1 - tk) * order, mat=0)
    # pilasters on the facades (between the bays) and at the corners
    for side in (2, 4, 6):
        P = body_poly(HALF)
        a, b = P[side], P[(side + 1) % 8]
        d = (b - a) / np.linalg.norm(b - a)
        nrm = np.array([d[1], -d[0]])
        for u in (0.02, 0.215, 0.405, 0.595, 0.785, 0.98):
            p = a + (b - a) * u + nrm * 0.2
            rot = math.atan2(d[1], d[0])
            for kz in range(0, n_c, 4):
                z0 = kz * COURSE - 0.6
                cb.add(G.box(p[0], p[1], z0, 1.2, 0.4, 4 * COURSE, rot), t_on=tc_at(z0 + 2.4, TC_WALLS, -0.6, Z_CORNICE), mat=0)
    # the main cornice
    for corners, order in G.ring_course(body_poly, HALF + 0.9, HALF + 0.9, 2.4, Z_CORNICE - 0.6, Z_CORNICE, 2.5, 0):
        cb.add(corners, t_on=TC_WALLS[1] - 0.05 + 0.1 * order, mat=0)
    # -- the choir (apse) on the east: a half ring with three windows and a half dome
    ax = HALF - 0.9
    for k in range(int(APSE_Z / COURSE)):
        z0, z1 = k * COURSE - 0.6, (k + 1) * COURSE - 0.6
        zc = 0.5 * (z0 + z1)
        tk = tc_at(z0, TC_WALLS, -0.6, Z_CORNICE)
        n = 22
        win = 3.0 < zc < 13.0
        for j in range(n):
            a0 = -math.pi / 2 + math.pi * (j + (0.0 if win else 0.5 * (k % 2))) / n
            a1 = min(a0 + math.pi / n, math.pi / 2)
            am = 0.5 * (a0 + a1)
            if win and any(abs(am - w) < 0.09 for w in (-0.75, 0.0, 0.75)):
                continue
            ro, ri = APSE_R, APSE_R - 1.5
            bq = np.array([[ax + ro * math.cos(a0), ro * math.sin(a0)], [ax + ro * math.cos(a1), ro * math.sin(a1)],
                           [ax + ri * math.cos(a1), ri * math.sin(a1)], [ax + ri * math.cos(a0), ri * math.sin(a0)]])
            cb.add(G._hexa(bq, bq, z0, z1), t_on=tk + 0.03 * j / n, mat=0)
    for k in range(8):                                                   # the half dome over the choir
        z0 = APSE_Z - 0.6 + k * 0.8
        f0 = math.cos(math.pi / 2 * k / 8)
        f1 = math.cos(math.pi / 2 * (k + 1) / 8)
        n = 16
        for j in range(n):
            a0 = -math.pi / 2 + math.pi * j / n
            a1 = a0 + math.pi / n
            ro0, ro1 = APSE_R * f0 + 0.3, APSE_R * f1 + 0.3
            ri0, ri1 = max(ro0 - 1.2, 0.05), max(ro1 - 1.2, 0.05)
            bq = np.array([[ax + ro0 * math.cos(a0), ro0 * math.sin(a0)], [ax + ro0 * math.cos(a1), ro0 * math.sin(a1)],
                           [ax + ri0 * math.cos(a1), ri0 * math.sin(a1)], [ax + ri0 * math.cos(a0), ri0 * math.sin(a0)]])
            tq = np.array([[ax + ro1 * math.cos(a0), ro1 * math.sin(a0)], [ax + ro1 * math.cos(a1), ro1 * math.sin(a1)],
                           [ax + ri1 * math.cos(a1), ri1 * math.sin(a1)], [ax + ri1 * math.cos(a0), ri1 * math.sin(a0)]])
            cb.add(G._hexa(bq, tq, z0, z0 + 0.8), t_on=TC_WALLS[1] - 0.2 + 0.03 * k, mat=0)
    # -- the stair towers above the cornice, their cupolas and finials
    for i, (tx, ty) in enumerate(TOWERS):
        nk = int((TOWER_Z - Z_CORNICE) / COURSE)
        for k in range(nk):
            z0 = Z_CORNICE + k * COURSE
            t0 = TC_TOWERS[0] + (TC_TOWERS[1] - TC_TOWERS[0]) * 0.7 * k / nk
            holes = {s: [(0.35, 0.65)] for s in range(8)} if 2 <= k <= 7 else None
            for corners, order in G.ring_course(lambda r: G.oct_poly(r) + [tx, ty], TOWER_R - 0.3, TOWER_R - 0.3, 0.8, z0, z0 + COURSE, 1.6, k,
                                                openings=holes):
                cb.add(corners, t_on=t0, mat=0)
        for k in range(8):                                               # the cupola: an ogee of stone rings
            z0 = TOWER_Z + k * 0.9
            u0, u1 = k / 8, (k + 1) / 8
            r0 = 0.3 + (TOWER_R - 0.1) * math.cos(math.pi / 2 * u0) ** 1.4
            r1 = 0.3 + (TOWER_R - 0.1) * math.cos(math.pi / 2 * u1) ** 1.4
            t0 = TC_TOWERS[0] + (TC_TOWERS[1] - TC_TOWERS[0]) * (0.7 + 0.3 * k / 8)
            for corners, order in G.ring_course(lambda r: G.oct_poly(r) + [tx, ty], r0, r1, min(0.8, r1), z0, z0 + 0.9, 1.6, k):
                cb.add(corners, t_on=t0, mat=0)
        cb.add(G.box(tx, ty, TOWER_Z + 7.2, 0.5, 0.5, 3.0, 0.0), t_on=TC_TOWERS[1], mat=0)
    # -- the bell's foot: concave courses from the cut square to the drum
    nk = 10
    for k in range(nk):
        z0 = SKIRT[0] + (SKIRT[1] - SKIRT[0]) * k / nk
        z1 = SKIRT[0] + (SKIRT[1] - SKIRT[0]) * (k + 1) / nk
        a0 = 14.2 + (HALF - 0.4 - 14.2) * (1 - k / nk) ** 1.7
        a1 = 14.2 + (HALF - 0.4 - 14.2) * (1 - (k + 1) / nk) ** 1.7
        t0 = TC_SKIRT[0] + (TC_SKIRT[1] - TC_SKIRT[0]) * k / nk
        for corners, order in G.ring_course(skirt_poly, a0, a1, 1.4, z0, z1, 1.9, k):
            cb.add(corners, t_on=t0 + 0.06 * order, mat=0)
    # -- the drum and the dome, ring by ring
    z = SKIRT[0]
    k = 0
    while z < DOME_TOP - 1e-6:
        dz = 0.7 if z < 31.0 else 0.8
        z1 = min(z + dz, DOME_TOP)
        r0, r1 = dome_r(z), dome_r(z1)
        n = max(12, int(round(2 * math.pi * r0 / 1.7)))
        if z < 31.0:
            t0 = TC_SKIRT[0] + (TC_SKIRT[1] - TC_SKIRT[0]) * (z - SKIRT[0]) / (31.0 - SKIRT[0])
            t1 = t0 + 0.05
        else:
            t0 = tc_at(z, TC_DOME, 31.0, DOME_TOP)
            t1 = tc_at(z1, TC_DOME, 31.0, DOME_TOP)
        for corners, order in G.ring_course(lambda a, n=n: G.circle_poly(a, n), r0, r1, dome_t(z), z, z1, 99.0, k):
            cb.add(corners, t_on=t0 + (t1 - t0) * order, mat=0)
        z = z1
        k += 1
    # -- the lantern: an octagon with eight arched openings, cornice, cupola, spire, orb, cross
    z = LANTERN[0]
    k = 0
    while z < LANTERN[1] - 1e-6:
        holes = {s: [(0.28, 0.72)] for s in range(8)} if 61.5 < z < 67.0 else None
        t0 = tc_at(z, (TC_LANTERN[0], TC_LANTERN[0] + 0.55 * (TC_LANTERN[1] - TC_LANTERN[0])), LANTERN[0], LANTERN[1])
        for corners, order in G.ring_course(G.oct_poly, 4.0, 4.0, 0.8, z, z + 0.75, 1.6, k, openings=holes):
            cb.add(corners, t_on=t0, mat=0)
        z += 0.75
        k += 1
    tl = TC_LANTERN[0] + 0.55 * (TC_LANTERN[1] - TC_LANTERN[0])
    for corners, order in G.ring_course(G.oct_poly, 4.6, 4.6, 1.6, LANTERN[1], LANTERN[1] + 0.6, 2.0, 0):
        cb.add(corners, t_on=tl, mat=0)
    for k in range(7):
        z0 = LANTERN[1] + 0.6 + k * 0.9
        r0 = 0.25 + 3.8 * math.cos(math.pi / 2 * k / 7) ** 1.2
        r1 = 0.25 + 3.8 * math.cos(math.pi / 2 * (k + 1) / 7) ** 1.2
        t0 = tl + (TC_LANTERN[1] - tl) * 0.7 * k / 7
        for corners, order in G.ring_course(G.oct_poly, r0, r1, min(0.7, r1), z0, z0 + 0.9, 1.4, k):
            cb.add(corners, t_on=t0, mat=0)
    zs = LANTERN[1] + 0.6 + 6.3
    oct_prism(cb, 0, 0, 0.6, 0.08, zs, zs + 8.5, t_on=TC_LANTERN[1] - 0.12, mat=0)                              # the spire
    oct_prism(cb, 0, 0, 0.55, 0.55, zs + 8.0, zs + 9.1, t_on=TC_LANTERN[1] - 0.06, mat=3)                        # the orb
    cb.add(G.box(0, 0, zs + 9.1, 0.25, 0.25, CROSS_TOP - zs - 9.1), t_on=TC_LANTERN[1] - 0.02, mat=3)          # the cross
    cb.add(G.box(0, 0, CROSS_TOP - 2.2, 1.6, 0.25, 0.25), t_on=TC_LANTERN[1] - 0.02, mat=3)
    # -- inside: the galleries (three tiers, open towards the choir), with their parapets
    for gi, zg in enumerate(GALLERIES):
        t0 = tc_at(zg + 1.0, TC_WALLS, -0.6, Z_CORNICE) + 0.1
        n = 56
        for j in range(n):
            a0 = math.radians(38.0) + (2 * math.pi - math.radians(76.0)) * j / n
            a1 = math.radians(38.0) + (2 * math.pi - math.radians(76.0)) * (j + 1) / n
            ro = 18.0 - 0.6 * abs(math.sin(2 * (a0 + a1) / 2)) ** 3
            ri = PIER_R + 1.4
            q = np.array([[ro * math.cos(a0), ro * math.sin(a0)], [ro * math.cos(a1), ro * math.sin(a1)],
                          [ri * math.cos(a1), ri * math.sin(a1)], [ri * math.cos(a0), ri * math.sin(a0)]])
            cb.add(G._hexa(q, q, zg - 0.35, zg), t_on=t0, mat=2)
            pq = np.array([[ri * math.cos(a0), ri * math.sin(a0)], [ri * math.cos(a1), ri * math.sin(a1)],
                           [(ri - 0.25) * math.cos(a1), (ri - 0.25) * math.sin(a1)], [(ri - 0.25) * math.cos(a0), (ri - 0.25) * math.sin(a0)]])
            cb.add(G._hexa(pq, pq, zg - 0.9, zg + 1.0), t_on=t0 + 0.02, mat=5)
            cb.add(G._hexa(pq, pq, zg + 1.0, zg + 1.1), t_on=t0 + 0.02, mat=3)          # gilt rail
            cb.add(G._hexa(pq, pq, zg - 0.95, zg - 0.85), t_on=t0 + 0.02, mat=3)
    # pews in the nave
    for row in range(9):
        x = -9.0 + row * 1.9
        for sgn in (-1, 1):
            half_w = math.sqrt(max(PIER_R ** 2 - x ** 2, 0.0)) - 2.2
            if half_w < 1.5:
                continue
            cb.add(G.box(x, sgn * (1.4 + half_w / 2), 0.0, 0.5, half_w, 0.9), t_on=TC_INSIDE[0], mat=6)
    # the altar in the choir: mensa, columns, entablature, the glory above
    ax_ = HALF + APSE_R - 3.0
    cb.add(G.box(ax_ - 1.5, 0, 0.0, 1.6, 3.4, 1.2), t_on=TC_INSIDE[0], mat=5)
    cb.add(G.box(ax_, 0, 0.0, 1.2, 7.0, 1.6), t_on=TC_INSIDE[0], mat=0)
    for dy in (-2.8, -1.6, 1.6, 2.8):
        oct_prism(cb, ax_, dy, 0.28, 0.24, 1.6, 8.0, t_on=TC_INSIDE[0] + 0.05, mat=3)
    cb.add(G.box(ax_, 0, 8.0, 1.3, 7.4, 0.8), t_on=TC_INSIDE[0] + 0.08, mat=5)
    cb.add(G.box(ax_ + 0.3, 0, 1.8, 0.2, 2.6, 5.8), t_on=TC_INSIDE[0] + 0.08, mat=3)             # the relief panel
    for j in range(12):                                                                              # the glory's rays
        a = math.pi * (j + 0.5) / 12
        cb.add(G.beam([ax_, 0, 10.2], [ax_, 2.4 * math.cos(a), 10.2 + 2.4 * math.sin(a)], 0.12, 0.05, up=(1, 0, 0)),
               t_on=TC_INSIDE[0] + 0.1, mat=3)
    # the organ gallery and the organ above the altar: case, towers of pipes, flats, the console
    ox = HALF + 2.0
    cb.add(G.box(ox + 0.5, 0, ORGAN_Z - 0.5, 6.0, 11.0, 0.5), t_on=TC_INSIDE[0] + 0.05, mat=2)
    cb.add(G.box(ox - 3.0, 0, ORGAN_Z, 0.3, 11.0, 0.85), t_on=TC_INSIDE[0] + 0.07, mat=5)            # the gallery's parapet
    cb.add(G.box(ox - 3.0, 0, ORGAN_Z + 0.85, 0.36, 11.0, 0.1), t_on=TC_INSIDE[0] + 0.07, mat=3)
    cb.add(G.box(ox + 3.2, 0, ORGAN_Z, 2.2, 7.5, 8.0), t_on=TC_INSIDE[0] + 0.08, mat=5)              # the case
    cb.add(G.box(ox + 2.2, 0, ORGAN_Z + 8.0, 2.6, 8.0, 0.5), t_on=TC_INSIDE[0] + 0.08, mat=3)
    towers = ((0.0, 1.8, 6.6), (-2.6, 1.4, 5.4), (2.6, 1.4, 5.4), (-1.35, 0.7, 4.2), (1.35, 0.7, 4.2))
    pipes = []
    for ty_, w_, h_ in towers:
        nps = int(w_ / 0.24)
        for j in range(nps):
            y = ty_ - w_ / 2 + (j + 0.5) * w_ / nps
            hh = h_ * (0.72 + 0.28 * math.cos(math.pi * (j + 0.5) / nps - math.pi / 2))
            pipes.append((y, hh))
    order = np.random.default_rng(1736).permutation(len(pipes))              # set one by one, in no strict order
    for rank, i in enumerate(order):
        y, hh = pipes[i]
        oct_prism(cb, ox + 2.0, y, 0.1, 0.1, ORGAN_Z + 1.1, ORGAN_Z + 1.1 + hh,
                  t_on=TC_INSIDE[0] + 0.12 + 0.2 * rank / len(pipes), mat=4)
    cb.add(G.box(ox + 1.55, 0, ORGAN_Z, 0.9, 1.9, 1.15), t_on=TC_INSIDE[1] - 0.1, mat=5)            # the console, built into the case
    cb.add(G.box(ox + 0.75, 0, ORGAN_Z, 0.45, 1.3, 0.5), t_on=TC_INSIDE[1] - 0.1, mat=2)            # the bench
    cb.finalize()
    return cb


class Sched:
    """Wall-top height <-> tc for the putlog scaffold of the walls."""

    def __init__(self, span, z0, z1):
        self.t = np.array([span[0], span[1]])
        self.z = np.array([z0, z1])

    def height(self, t):
        return float(np.interp(t, self.t, self.z))

    def time_at(self, z):
        if z > self.z[-1]:
            return 1e9
        return float(np.interp(z, self.z, self.t))


def build_scaffolds():
    """The walls' putlog scaffold (it climbs with the courses and is struck from the
    top), the dome's scaffold rings, and the centering: sixteen timber ribs under
    the dome with lagging rings, raised before the first dome course and struck
    once the crown ring carries the lantern."""
    tb = G.HexBatch('church_scaffold')
    rng = np.random.default_rng(29)
    sched = Sched(TC_WALLS, -0.6, Z_CORNICE)
    SC.scaffold_tier(tb, body_poly, lambda z: HALF, 0.0, Z_CORNICE, sched, TC_SCAF_DOWN, rng,
                     lift=2.2, off=1.6, spacing=3.4, extra_top=1.8, collar=40.0)
    dsched = Sched(TC_DOME, 31.0, DOME_TOP)
    SC.scaffold_tier(tb, lambda r: G.circle_poly(r, 24), lambda z: dome_r(z), 31.0, DOME_TOP - 31.0, dsched,
                     TC_SCAF_DOWN, rng, lift=2.4, off=1.4, spacing=3.4, extra_top=1.2, collar=40.0)
    # the centering
    n = 16
    zs = np.linspace(31.0, DOME_TOP - 0.3, 14)
    t_on0, t_off = TC_CENTER[0], TC_CENTER_OFF
    for i in range(n):
        a = 2 * math.pi * (i + 0.5) / n
        ca, sa = math.cos(a), math.sin(a)
        for k in range(len(zs) - 1):
            r0 = dome_r(zs[k]) - dome_t(zs[k]) - 0.25
            r1 = dome_r(zs[k + 1]) - dome_t(zs[k + 1]) - 0.25
            p0 = [r0 * ca, r0 * sa, zs[k]]
            p1 = [r1 * ca, r1 * sa, zs[k + 1]]
            ton = t_on0 + (TC_CENTER[1] - t_on0) * k / len(zs)
            tof = t_off[0] + (t_off[1] - t_off[0]) * (1 - k / len(zs))
            tb.add(G.beam(p0, p1, 0.35), ton, tof, SC.M_WOOD)
            if k % 3 == 0:                                                    # struts down to the ring below
                q = [PIER_R * 0.8 * ca, PIER_R * 0.8 * sa, 24.5]
                tb.add(G.beam(q, p0, 0.22), ton, tof, SC.M_WOOD)
    for k in range(0, len(zs) - 1, 2):                                        # lagging rings
        r = dome_r(zs[k]) - dome_t(zs[k]) - 0.5
        P = G.circle_poly(r, n)
        ton = t_on0 + (TC_CENTER[1] - t_on0) * k / len(zs)
        tof = t_off[0] + (t_off[1] - t_off[0]) * (1 - k / len(zs))
        for i in range(n):
            tb.add(G.beam(np.append(P[i], zs[k]), np.append(P[(i + 1) % n], zs[k]), 0.25), ton, tof, SC.M_WOOD)
    tb.add(G.box(0, 0, 24.0, 2 * PIER_R - 3.0, 2 * PIER_R - 3.0, 0.6), t_on0, t_off[1], SC.M_PLANK)
    tb.finalize()
    return tb, sched, dsched


# ================================================================== river craft
def build_barge_mesh(S, name='Barge', load=True):
    """An Elbe barge: a long flat hull with raked ends, a deck house aft, a mast
    with the square sail furled on its yard; sandstone blocks amidships."""
    bb = G.HexBatch(name)
    L, W, D = 28.0, 4.6, 1.6
    bb.add(G.box(0, 0, -0.9, L - 5.0, W, D), mat=0)
    for sgn in (-1, 1):                                                  # raked ends
        x0 = sgn * (L - 5.0) / 2
        bq = np.array([[x0, -W / 2], [x0 + sgn * 2.5, -W / 2 + 0.8], [x0 + sgn * 2.5, W / 2 - 0.8], [x0, W / 2]])
        if sgn < 0:
            bq = bq[[3, 2, 1, 0]]
        tq = np.array([[x0, -W / 2], [x0 + sgn * 3.0, -W / 2 + 0.6], [x0 + sgn * 3.0, W / 2 - 0.6], [x0, W / 2]])
        if sgn < 0:
            tq = tq[[3, 2, 1, 0]]
        bb.add(G._hexa(bq, tq, -0.4, D - 0.9), mat=0)
    bb.add(G.box(-9.0, 0, D - 0.9, 3.0, 3.4, 1.9), mat=0)               # deck house
    bb.add(G.tent(-9.0, 0, D + 1.0, 3.4, 3.8, 0.8, 0.0), mat=3)
    bb.add(G.beam([2.0, 0, D - 0.9], [2.0, 0, D + 12.0], 0.3), mat=1)   # mast
    bb.add(G.beam([2.0, -4.0, D + 10.5], [2.0, 4.0, D + 10.5], 0.16), mat=1)
    bb.add(G.beam([2.2, -3.8, D + 10.1], [2.2, 3.8, D + 10.1], 0.45, 0.35), mat=2)   # the furled sail
    bb.add(G.beam([2.0, 0, D + 12.0], [13.0, 0, D - 0.7], 0.05), mat=1)              # stays
    bb.add(G.beam([2.0, 0, D + 12.0], [-11.0, 0, D - 0.7], 0.05), mat=1)
    if load:
        for i in range(6):
            for j in range(2):
                bb.add(G.box(-5.0 + 2.0 * i + (0.5 if j else 0), (j - 0.5) * 1.7, D - 0.9, 1.7, 1.4, 1.0 + 0.1 * (i % 2)), mat=4)
    bb.finalize()
    return SC.hex_mesh(name, bb, np.ones(len(bb.t_on), bool), [S.m_hull, S.m_wood, S.m_sail, S.m_roof, S.m_stone])


# ================================================================== build / pose
class State:
    pass


def build(res=(1280, 720)):
    SC.P = SC.PALETTES['bright']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    S = State()
    S.look = 'bright'
    coll = sc.collection
    P = SC.P
    S.m_stone = mat_sandstone()
    S.m_church = mat_church_stone()
    S.m_houses = mat_houses()
    S.m_roof = mat_slate()
    S.m_wood = SC.mat_wood('Timber', P['wood'])
    S.m_plank = SC.mat_wood('Planks', P['plank'], width=0.04)
    S.m_rope = SC.mat_simple('Rope', P['rope'], 0.9)
    S.m_cloth = SC.mat_simple('Canvas', P['cloth'], 0.9)
    S.m_cloth2 = SC.mat_simple('CanvasDark', P['cloth2'], 0.9)
    S.m_hull = SC.mat_wood('Hull', P['hull'], textured=False)
    S.m_sail = SC.mat_simple('Sail', P['sail'], 0.9)
    S.m_torch = SC.mat_torch()
    S.m_city = S.m_houses
    S.m_gold = mat_gold()
    S.m_tin = mat_tin()
    S.m_white = SC.mat_simple('CasePaint', (0.86, 0.84, 0.78), 0.5)
    S.m_pew = SC.mat_wood('Pews', (0.30, 0.19, 0.11))
    S.m_glass = SC.mat_simple('ChurchGlass', (0.10, 0.11, 0.12), 0.15, spec=0.6)
    S.world = SC.build_world()
    S.flat_world = SC.build_flat_world()
    S.ground = build_ground(coll)
    S.sea, S.ocean = SC.build_sea(coll, height_fn=lambda X, Y: height(X, Y) - WATER_Z,
                                  extent=(-2500.0, 2500.0, BANK_Y - 10.0, FAR_Y + 10.0),
                                  center=(0.0, 0.5 * (BANK_Y + FAR_Y)), r0=2.0)
    S.sea.location.z = WATER_Z
    S.ocean.wave_scale = 0.2                     # a river: short, low ripples
    S.ocean.wind_velocity = 5.0
    S.ocean.foam_coverage = 0.0
    S.cloud_shadow, S.m_cshadow = SC.build_cloud_shadows(coll)
    S.city = build_city(coll, S.m_houses, S.m_roof)
    S.fortress = build_fortress(coll, S.m_stone, S.m_wood)
    S.bridge = build_bridge(coll, S.m_stone)
    S.church_batch = build_church()
    S.church_obj = SC.link(bpy.data.objects.new('Frauenkirche', bpy.data.meshes.new('Frauenkirche')), coll)
    S.church_obj.pass_index = SC.PASS['masonry']
    S.church_mats = [S.m_church, S.m_glass, S.m_plank, S.m_gold, S.m_tin, S.m_white, S.m_pew]
    S.scaf_batch, S.sched, S.dsched = build_scaffolds()
    S.scaf_obj = SC.link(bpy.data.objects.new('ChurchScaffold', bpy.data.meshes.new('ChurchScaffold')), coll)
    S.scaf_obj.pass_index = SC.PASS['timber']
    S.site_tc = None
    S.barge_me = build_barge_mesh(S)
    S.barge_empty = build_barge_mesh(S, 'BargeEmpty', load=False)
    ld = bpy.data.lights.new('Sun', 'SUN')
    ld.angle = math.radians(1.0)
    S.sun = SC.link(bpy.data.objects.new('Sun', ld), coll)
    ld = bpy.data.lights.new('Moon', 'SUN')
    ld.angle = math.radians(1.5)
    ld.color = (0.55, 0.68, 1.0)
    S.moon = SC.link(bpy.data.objects.new('Moon', ld), coll)
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 35.0
    cd.sensor_width = 36
    cd.clip_start = 0.2
    cd.clip_end = 60000
    S.cam = SC.link(bpy.data.objects.new('Cam', cd), coll)
    sc.camera = S.cam
    return S


def pose_site(S, tc):
    key = round(tc, 4)
    if key != S.site_tc:
        S.site_tc = key
        SC.set_dynamic_mesh(S.church_obj, 'Frauenkirche', S.church_batch, S.church_batch.select(tc), S.church_mats)
        SC.set_dynamic_mesh(S.scaf_obj, 'ChurchScaffold', S.scaf_batch, S.scaf_batch.select(tc), [S.m_wood, S.m_plank])
    return dict(level=S.sched.height(tc))


def pose(S, t, **kw):
    hour = kw.get('hour', 9.0)
    zen, hor = SC.pose_environment(S, t, **dict(kw, hour=hour))
    site = pose_site(S, kw.get('tc', 0.0))
    if 'cam' in kw:
        loc, tgt, lens = kw['cam']
        S.cam.data.lens = lens
        SC.look_at(S.cam, loc, tgt)
    import timeline as TL
    el, _ = TL.sun_angles(hour)
    return dict(t=t, hour=hour, sun_el=math.degrees(el), day=TL.smoothstep(math.radians(-7), math.radians(5), el),
                height=site['level'], fire=0.0, horizon=hor, zenith=zen, **site)
