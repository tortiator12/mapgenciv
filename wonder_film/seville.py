"""Seville in 1519 and the beach of Sanlucar de Barrameda, for the film
"Magellans Expedition" (wunderfilm_08_magellan).

Seville: the Guadalquivir runs north to south (+y north); the city lies on its
east bank (+x) behind crenellated walls, with the Arenal - the sandy river
beach where the ships are fitted out - between the walls and the water; the
Torre del Oro (the twelve-sided albarrana tower, two bodies, before its
eighteenth-century cupola) stands at the water's edge south of the Arenal,
tied to the walls by a curtain wall; the cathedral, a Gothic mass with
buttresses and pinnacles, and the Giralda (the Almohad minaret, 13.6 m square,
with a simple belfry: the Renaissance crown came only in 1568) rise behind;
Triana on the west bank; the bridge of boats upstream.

Sanlucar (S5), a world of its own far to the south-west: a sandy beach at the
river's mouth, the town on its hill with the tower of Nuestra Senora de la O.

Metres, the river at z = 0.
"""
import math

import bpy
import numpy as np

import geometry as G
import rhodes as RH
import scene as SC

LATITUDE_DEG = 37.38
BANK_X = 0.0                          # the east bank's waterline
WEST_X = -160.0                       # Triana's waterline
WALL_X = 92.0                         # the city wall along the Arenal
CITY_Z = 7.0
TORRE = (18.0, -150.0)                # the Torre del Oro
GIRALDA = (420.0, 40.0)
CATHEDRAL = (430.0, -30.0)            # centre of the cathedral (Giralda at its NE corner)
BRIDGE_Y = 330.0                      # the bridge of boats
SANLUCAR = (30000.0, -20000.0)        # the far beach, S5


def clamp(x, a=0.0, b=1.0):
    return min(max(x, a), b)


# ================================================================== ground
def height(X, Y):
    """The Arenal rising from the water to the walls, the city terrace, the river,
    Triana on the west bank; round Sanlucar a beach below a low hill."""
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    arenal = 0.08 * np.maximum(X - BANK_X, 0.0) + 0.9 * G.fbm(X / 40.0, Y / 40.0, 2, seed=2) * np.clip(X / 30.0, 0, 1)
    city = CITY_Z + 0.6 * G.fbm(X / 90.0, Y / 90.0, 3, seed=3)
    east = np.where(X < WALL_X, np.minimum(arenal, CITY_Z), city)
    riverbed = -4.0
    west = 0.06 * np.maximum(WEST_X - X, 0.0) + 0.5 * G.fbm(X / 50.0, Y / 50.0, 2, seed=4)
    west = np.minimum(west, 5.0)
    h = np.where(X >= BANK_X, east, np.where(X <= WEST_X, west, riverbed))
    # gentle banks into the water
    h = np.where((X > BANK_X - 12.0) & (X < BANK_X), -4.0 + 4.0 * ((X - (BANK_X - 12.0)) / 12.0) ** 1.5, h)
    h = np.where((X < WEST_X + 12.0) & (X > WEST_X), -4.0 + 4.0 * (((WEST_X + 12.0) - X) / 12.0) ** 1.5, h)
    # Sanlucar: the sea to the west of a north-south beach, the town hill behind
    dx = X - SANLUCAR[0]
    dy = Y - SANLUCAR[1]
    near = (np.abs(dx) < 6000) & (np.abs(dy) < 6000)
    beach = np.where(dx < 0.0, -3.0 + 3.0 * np.clip(1 + dx / 60.0, 0, 1) ** 2, 0.03 * dx)
    hill = 28.0 * np.exp(-((dx - 380.0) ** 2 + (dy - 120.0) ** 2) / (2 * 160.0 ** 2))
    san = np.maximum(beach, 0.0) + hill + np.minimum(beach, 0.0) + 0.3 * G.fbm(X / 60.0, Y / 60.0, 2, seed=6)
    return np.where(near, san, h)


def ground_z(x, y):
    return float(height(np.array([x]), np.array([y]))[0])


def mat_ground():
    """Sand and trodden mud on the Arenal and the beach, dusty earth in the city,
    grass and reeds on the far bank."""
    m, nb, out = SC.new_material('SevilleGround')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    x_, y_, z = nb.sep(pos)
    n1 = nb.noise(pos, 0.07, 4.0, 0.6).outputs['Fac']
    n2 = nb.noise(pos, 0.8, 3.0, 0.6).outputs['Fac']
    sand = nb.mix(n1, (0.42, 0.35, 0.25, 1), (0.52, 0.44, 0.31, 1))
    tracks = nb.smooth(0.55, 0.7, nb.noise(nb.comb(nb.math('MULTIPLY', x_, 0.6), nb.math('MULTIPLY', y_, 0.08), 0.0), 3.0, 3.0, 0.6).outputs['Fac'])
    sand = nb.mix(nb.math('MULTIPLY', tracks, 0.5), sand, (0.30, 0.25, 0.18, 1))
    mud = nb.mix(n2, (0.36, 0.30, 0.22, 1), (0.46, 0.38, 0.27, 1))
    wet = nb.smooth(0.9, 0.1, z)
    col = nb.mix(wet, sand, mud)
    earth = nb.mix(n2, (0.56, 0.44, 0.30, 1), (0.66, 0.52, 0.36, 1))
    col = nb.mix(nb.smooth(CITY_Z - 1.5, CITY_Z - 0.5, z), col, earth)
    grass = nb.mix(n1, (0.30, 0.32, 0.14, 1), (0.44, 0.42, 0.20, 1))
    west = nb.math('MULTIPLY', nb.smooth(-150.0, -175.0, x_), nb.smooth(0.3, 0.6, n2))
    col = nb.mix(nb.math('MULTIPLY', west, nb.smooth(1.0, 2.0, z)), col, grass)
    b = SC.principled(nb, col, rough=0.95, spec=0.25)
    bump = nb.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.3
    nb.feed(bump.inputs['Height'], n2)
    nb.feed(b.inputs['Normal'], bump.outputs['Normal'])
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_ground(coll):
    objs = []
    for (cx, cy, span) in ((0.0, 0.0, 700.0), (SANLUCAR[0], SANLUCAR[1], 700.0)):
        xs = RH._graded(cx - 5000.0, cx + 5000.0, cx - span, cx + span, 1.8, growth=1.1)
        ys = RH._graded(cy - 5000.0, cy + 5000.0, cy - span, cy + span, 1.8, growth=1.1)
        X, Y = np.meshgrid(xs, ys)
        Z = height(X, Y)
        V = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
        nx = len(xs)
        idx = np.arange(len(ys) * nx).reshape(len(ys), nx)
        Q = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
        me = SC.mesh_from_arrays('SevilleGround', V, Q, mats=[mat_ground()] if not objs else [objs[0].data.materials[0]], smooth=True)
        o = SC.link(bpy.data.objects.new('SevilleGround', me), coll)
        o.pass_index = SC.PASS['terrain']
        objs.append(o)
    return objs


# ================================================================== buildings
def mat_whitewash():
    """Lime-washed walls in white, cream and ochre (tone per house); windows lit at night."""
    m = RH.mat_houses()
    m.name = 'SevilleHouses'
    ramp = [n for n in m.node_tree.nodes if n.type == 'VALTORGB'][0]
    els = ramp.color_ramp.elements
    cols = [(0.0, (0.92, 0.90, 0.84)), (0.4, (0.88, 0.84, 0.74)), (0.65, (0.84, 0.72, 0.50)),
            (0.85, (0.80, 0.62, 0.44)), (1.0, (0.90, 0.86, 0.78))]
    while len(els) < len(cols):
        els.new(0.5)
    for e, (p, c) in zip(els, cols):
        e.position = p
        e.color = c + (1.0,)
    return m


def dodeca(r):
    """Twelve-sided polygon (apothem r) for ring_course."""
    R = r / math.cos(math.pi / 12)
    ang = np.arange(12) * 2 * math.pi / 12 + math.pi / 12
    return np.stack([R * np.cos(ang), R * np.sin(ang)], 1)


def build_torre(coll, m_stone):
    """The Torre del Oro: a twelve-sided body of 16 m with merlons, a second, smaller
    twelve-sided body with merlons above it; a curtain wall to the city walls."""
    tb = G.HexBatch('torre')
    tx, ty = TORRE
    z0 = ground_z(tx, ty) - 2.0
    for k in range(int((16.0 - z0) / 0.7)):
        za = z0 + k * 0.7
        holes = {s: [(0.4, 0.6)] for s in (1, 5, 9)} if 8.0 < za < 10.0 else None
        for corners, order in G.ring_course(lambda r: dodeca(r) + [tx, ty], 7.8, 7.8, 7.8, za, za + 0.7, 2.2, k, openings=holes):
            tb.add(corners, mat=0)
    for s_ in range(12):                                                  # merlons, stepped
        P = dodeca(7.8)
        a, b = P[s_], P[(s_ + 1) % 12]
        for u in (0.25, 0.75):
            p = a + (b - a) * u + [tx, ty]
            rot = math.atan2(b[1] - a[1], b[0] - a[0])
            tb.add(G.box(p[0], p[1], 16.0, 1.1, 0.7, 1.4, rot), mat=0)
    for k in range(int(8.0 / 0.7)):
        za = 16.0 + k * 0.7
        for corners, order in G.ring_course(lambda r: dodeca(r) + [tx, ty], 4.4, 4.4, 1.1, za, za + 0.7, 1.6, k):
            tb.add(corners, mat=0)
    for s_ in range(12):
        P = dodeca(4.4)
        a, b = P[s_], P[(s_ + 1) % 12]
        p = 0.5 * (a + b) + [tx, ty]
        tb.add(G.box(p[0], p[1], 24.0, 0.9, 0.6, 1.2, math.atan2(b[1] - a[1], b[0] - a[0])), mat=0)
    # the curtain wall east to the city walls
    x = tx + 7.0
    while x < WALL_X:
        z = ground_z(x, ty)
        tb.add(G.box(x + 3.0, ty, z - 1.0, 6.0, 3.0, 10.0), mat=0)
        tb.add(G.box(x + 3.0, ty, z + 9.0, 1.0, 3.2, 1.2), mat=0)
        x += 6.0
    tb.finalize()
    o = SC.link(bpy.data.objects.new('TorreDelOro', SC.hex_mesh('TorreDelOro', tb, np.ones(len(tb.t_on), bool), [m_stone])), coll)
    o.pass_index = SC.PASS['masonry']
    return o


def build_walls(coll, m_stone):
    """The city walls along the Arenal: crenellated, square towers every 40 m, two gates."""
    wb = G.HexBatch('walls')
    y = -140.0
    while y < 420.0:
        z = CITY_Z
        gate = abs(y - 60.0) < 5.0 or abs(y - 250.0) < 5.0
        if not gate:
            wb.add(G.box(WALL_X, y + 3.0, z - 3.0, 2.6, 6.0, 12.0), mat=0)
            for dy in (0.8, 3.8):
                wb.add(G.box(WALL_X - 0.8, y + dy, z + 9.0, 1.0, 1.2, 1.3), mat=0)
        if abs((y + 140.0) % 40.0) < 1e-6:
            wb.add(G.box(WALL_X - 1.5, y, z - 3.0, 7.0, 7.0, 16.0), mat=0)
            wb.add(G.tent(WALL_X - 1.5, y, z + 13.0, 7.4, 7.4, 3.0, 0.0), mat=1)
        y += 6.0
    for gy in (60.0, 250.0):                                              # gatehouses
        wb.add(G.box(WALL_X - 1.0, gy - 7.0, CITY_Z - 3.0, 8.0, 4.0, 17.0), mat=0)
        wb.add(G.box(WALL_X - 1.0, gy + 7.0, CITY_Z - 3.0, 8.0, 4.0, 17.0), mat=0)
        wb.add(G.box(WALL_X - 1.0, gy, CITY_Z + 7.0, 8.0, 10.0, 7.0), mat=0)
    wb.finalize()
    o = SC.link(bpy.data.objects.new('CityWalls', SC.hex_mesh('CityWalls', wb, np.ones(len(wb.t_on), bool), [m_stone, RH.mat_roof()])), coll)
    o.pass_index = SC.PASS['masonry']
    return o


def build_city(coll, m_houses, m_roof, m_stone):
    """Low lime-washed houses with tiled roofs in the walls and in Triana; the
    cathedral with its buttresses and pinnacles; the Giralda."""
    hb = G.HexBatch('seville_city')
    rng = np.random.default_rng(1519)
    for (x0, x1, y0, y1, n) in ((WALL_X + 8.0, 700.0, -400.0, 500.0, 1300), (-900.0, WEST_X - 25.0, -400.0, 500.0, 700)):
        k = 0
        while k < n:
            x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
            if abs(x - CATHEDRAL[0]) < 95 and abs(y - CATHEDRAL[1]) < 70:
                continue
            k += 1
            z = ground_z(x, y)
            w, d, h = rng.uniform(8, 14), rng.uniform(8, 14), rng.uniform(6.0, 10.5)
            rot = rng.choice([0.0, math.pi / 2]) + rng.uniform(-0.05, 0.05)
            hb.add(G.box(x, y, z - 1.0, w, d, h + 1.0, rot), mat=0, tone=float(rng.random()))
            if rng.random() < 0.7:
                hb.add(G.tent(x, y, z + h, w + 0.4, d + 0.4, rng.uniform(1.8, 2.8), rot), mat=1, tone=float(rng.random()))
    # the cathedral: nave, aisles, chapels, buttresses with pinnacles
    cx, cy = CATHEDRAL
    zc = ground_z(cx, cy)
    hb.add(G.box(cx, cy, zc - 1.0, 116.0, 76.0, 27.0), mat=2)
    hb.add(G.box(cx, cy, zc + 26.0, 116.0, 18.0, 11.0), mat=2)             # the high nave
    hb.add(G.box(cx, cy, zc + 26.0, 22.0, 70.0, 11.0), mat=2)              # the transept
    hb.add(G.box(cx, cy, zc + 36.0, 14.0, 14.0, 6.0), mat=2)              # the crossing
    for i in range(-5, 6):
        for sg in (-1, 1):
            x = cx + i * 10.5
            hb.add(G.box(x, cy + sg * 39.0, zc - 1.0, 2.0, 3.0, 30.0), mat=2)
            hb.add(G._hexa(G.square_poly(0.7) + [x, cy + sg * 39.0], G.square_poly(0.05) + [x, cy + sg * 39.0], zc + 29.0, zc + 34.0), mat=2)
            hb.add(G.beam([x, cy + sg * 38.0, zc + 24.0], [x, cy + sg * 9.5, zc + 33.0], 1.2, 1.6), mat=2)   # flying buttresses
    # the Giralda: the Almohad minaret, sebka panels in the shader, a simple belfry
    gx, gy = GIRALDA
    zg = ground_z(gx, gy)
    hb.add(G.box(gx, gy, zg - 1.0, 13.6, 13.6, 51.5), mat=3)
    hb.add(G.box(gx, gy, zg + 50.5, 14.4, 14.4, 1.0), mat=2)
    for sg_x in (-1, 1):
        for sg_y in (-1, 1):
            hb.add(G.box(gx + sg_x * 6.2, gy + sg_y * 6.2, zg + 51.5, 1.2, 1.2, 1.4), mat=3)
    hb.add(G.box(gx, gy, zg + 51.5, 8.0, 8.0, 8.0), mat=3)
    hb.add(G._hexa(G.square_poly(4.3) + [gx, gy], G.square_poly(0.2) + [gx, gy], zg + 59.5, zg + 64.5), mat=1)
    hb.add(G.box(gx, gy, zg + 64.5, 0.3, 0.3, 3.0), mat=4)
    hb.add(G.box(gx, gy, zg + 66.3, 1.4, 0.3, 0.3), mat=4)
    hb.finalize()
    m_sebka = mat_sebka()
    o = SC.link(bpy.data.objects.new('SevilleCity', SC.hex_mesh('SevilleCity', hb, np.ones(len(hb.t_on), bool),
                                                                 [m_houses, m_roof, m_stone, m_sebka, SC.mat_simple('Iron', (0.1, 0.09, 0.08), 0.5)])), coll)
    o.pass_index = SC.PASS['city']
    return o


def mat_sebka():
    """The Giralda's brick: warm ochre with raised lozenge panels (sebka) on each face."""
    m, nb, out = SC.new_material('Sebka')
    geo = nb.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    nrm = geo.outputs['Normal']
    x_, y_, z_ = nb.sep(pos)
    nx, ny, nz = nb.sep(nrm)
    u = nb.math('ADD', nb.math('MULTIPLY', x_, nb.math('ABSOLUTE', ny)), nb.math('MULTIPLY', y_, nb.math('ABSOLUTE', nx)))
    du = nb.math('ABSOLUTE', nb.math('SUBTRACT', nb.math('FRACT', nb.math('DIVIDE', u, 13.6)), 0.5))
    panel = nb.math('MULTIPLY', nb.smooth(0.34, 0.3, du), nb.math('MULTIPLY', nb.smooth(22.0, 24.0, z_), nb.smooth(48.0, 46.0, z_)))
    lu = nb.math('FRACT', nb.math('DIVIDE', nb.math('ADD', u, nb.math('MULTIPLY', z_, 0.5)), 1.4))
    lv = nb.math('FRACT', nb.math('DIVIDE', nb.math('SUBTRACT', u, nb.math('MULTIPLY', z_, 0.5)), 1.4))
    lattice = nb.math('MAXIMUM', nb.smooth(0.12, 0.05, nb.math('ABSOLUTE', nb.math('SUBTRACT', lu, 0.5))),
                      nb.smooth(0.12, 0.05, nb.math('ABSOLUTE', nb.math('SUBTRACT', lv, 0.5))))
    n = nb.noise(pos, 1.5, 3.0, 0.6).outputs['Fac']
    base = nb.mix(n, (0.66, 0.46, 0.30, 1), (0.74, 0.54, 0.36, 1))
    col = nb.mix(nb.math('MULTIPLY', panel, lattice), base, (0.46, 0.30, 0.19, 1))
    b = SC.principled(nb, col, rough=0.9, spec=0.3)
    nb.feed(out.inputs['Surface'], b.outputs[0])
    return m


def build_bridge_of_boats(coll, m_wood, m_hull):
    """The Puente de Barcas to Triana: thirteen moored boats under a plank deck."""
    bb = G.HexBatch('barcas')
    n = 13
    for k in range(n):
        x = BANK_X - 8.0 - k * (BANK_X - WEST_X - 16.0) / (n - 1)
        bb.add(G.box(x, BRIDGE_Y, -0.9, 4.0, 11.0, 1.6), mat=1)
        bb.add(G.tent(x, BRIDGE_Y + 5.5, -0.9, 4.0, 2.0, 0.0, math.pi / 2), mat=1)
    bb.add(G.box(0.5 * (BANK_X + WEST_X), BRIDGE_Y, 0.7, BANK_X - WEST_X, 4.0, 0.25), mat=0)
    for sg in (-1, 1):
        bb.add(G.box(0.5 * (BANK_X + WEST_X), BRIDGE_Y + sg * 1.9, 0.95, BANK_X - WEST_X, 0.12, 1.0), mat=0)
    bb.finalize()
    o = SC.link(bpy.data.objects.new('BridgeOfBoats', SC.hex_mesh('BridgeOfBoats', bb, np.ones(len(bb.t_on), bool), [m_wood, m_hull])), coll)
    o.pass_index = SC.PASS['props']
    return o


def build_sanlucar(coll, m_houses, m_roof, m_stone):
    """The town on its hill above the beach, the tower of Nuestra Senora de la O."""
    hb = G.HexBatch('sanlucar')
    rng = np.random.default_rng(1522)
    sx, sy = SANLUCAR
    for k in range(260):
        x = sx + rng.uniform(150.0, 700.0)
        y = sy + rng.uniform(-350.0, 500.0)
        z = ground_z(x, y)
        w, d, h = rng.uniform(7, 12), rng.uniform(7, 12), rng.uniform(5.0, 8.5)
        rot = rng.uniform(-0.2, 0.2)
        hb.add(G.box(x, y, z - 1.0, w, d, h + 1.0, rot), mat=0, tone=float(rng.random()))
        if rng.random() < 0.6:
            hb.add(G.tent(x, y, z + h, w + 0.4, d + 0.4, 1.8, rot), mat=1, tone=float(rng.random()))
    cx, cy = sx + 380.0, sy + 120.0                                    # the church on the hilltop
    zc = ground_z(cx, cy)
    hb.add(G.box(cx, cy, zc - 1.0, 36.0, 16.0, 15.0), mat=2)
    hb.add(G.tent(cx, cy, zc + 14.0, 36.4, 16.4, 5.0, 0.0), mat=1)
    hb.add(G.box(cx - 20.0, cy, zc - 1.0, 7.0, 7.0, 32.0), mat=2)       # the tower
    hb.add(G._hexa(G.square_poly(3.6) + [cx - 20.0, cy], G.square_poly(0.2) + [cx - 20.0, cy], zc + 31.0, zc + 36.0), mat=1)
    hb.finalize()
    o = SC.link(bpy.data.objects.new('Sanlucar', SC.hex_mesh('Sanlucar', hb, np.ones(len(hb.t_on), bool), [m_houses, m_roof, m_stone])), coll)
    o.pass_index = SC.PASS['city']
    return o


# ================================================================== build / pose
class State:
    pass


def build(res=(1280, 720)):
    SC.P = dict(SC.PALETTES['bright'], water=((0.012, 0.040, 0.045), (0.08, 0.16, 0.13)))
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
    S.m_stone = SC.mat_masonry('SevilleStone', (0.64, 0.50, 0.34), (0.50, 0.42, 0.32), var=0.12, width=0.03, grime=0.3)
    S.m_houses = mat_whitewash()
    S.m_roof = RH.mat_roof()
    S.m_wood = SC.mat_wood('Timber', P['wood'])
    S.m_plank = SC.mat_wood('Planks', P['plank'], width=0.04)
    S.m_rope = SC.mat_simple('Rope', P['rope'], 0.9)
    S.m_cloth = SC.mat_simple('Canvas', P['cloth'], 0.9)
    S.m_cloth2 = SC.mat_simple('CanvasDark', P['cloth2'], 0.9)
    S.m_hull = SC.mat_wood('Hull', P['hull'], textured=False)
    S.m_sail = SC.mat_simple('Sail', P['sail'], 0.9)
    S.m_torch = SC.mat_torch()
    S.m_city = S.m_houses
    S.world = SC.build_world()
    S.flat_world = SC.build_flat_world()
    S.grounds = build_ground(coll)
    S.sea, S.ocean = SC.build_sea(coll, height_fn=height, extent=(-400.0, 200.0, -600.0, 700.0), center=(-80.0, 0.0), r0=2.0)
    S.ocean.wave_scale = 0.25
    S.ocean.wind_velocity = 6.0
    S.ocean.foam_coverage = 0.0
    sx, sy = SANLUCAR                                                     # the sea off Sanlucar (S5): a water of its own
    S.sea2, S.ocean2 = SC.build_sea(coll, height_fn=height, extent=(sx - 700.0, sx + 60.0, sy - 700.0, sy + 700.0),
                                    center=(sx - 300.0, sy), r0=2.0)
    S.ocean2.wave_scale = 0.6
    S.ocean2.wind_velocity = 9.0
    S.sea2.hide_render = True
    S.cloud_shadow, S.m_cshadow = SC.build_cloud_shadows(coll)
    S.torre = build_torre(coll, S.m_stone)
    S.walls = build_walls(coll, S.m_stone)
    S.city = build_city(coll, S.m_houses, S.m_roof, S.m_stone)
    S.barcas = build_bridge_of_boats(coll, S.m_wood, S.m_hull)
    S.sanlucar = build_sanlucar(coll, S.m_houses, S.m_roof, S.m_stone)
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


def pose(S, t, **kw):
    hour = kw.get('hour', 9.0)
    zen, hor = SC.pose_environment(S, t, **dict(kw, hour=hour))
    if 'cam' in kw:
        loc, tgt, lens = kw['cam']
        S.cam.data.lens = lens
        SC.look_at(S.cam, loc, tgt)
    import timeline as TL
    el, _ = TL.sun_angles(hour)
    return dict(t=t, hour=hour, sun_el=math.degrees(el), day=TL.smoothstep(math.radians(-7), math.radians(5), el),
                height=0.0, fire=0.0, horizon=hor, zenith=zen)
