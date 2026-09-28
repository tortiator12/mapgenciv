"""Quay crane of the lighthouse film (wunderfilm_04_lighthouse, v6) as a template for
correction work: per-frame crane data of the whole film, and shot S1 as a .blend in which
one value drives the whole hoist.

Writes into --out (default: the folder of this script):
  kran5_daten.csv          the quay crane (crane 5, with the treadwheel), frames 0-479
  alle_kraene.csv          all six cranes, frames 0-479
  kran_geometrie.json      dimensions of crane, wheel and drum, shot table, formulas
  leuchtturm_S1_kran.blend S1 (0-3 s).  Scene frozen as in frame 0; animated are only the
                           camera, the sun and the quay crane.  The crane is a rig: the custom
                           property hub_m on 'Kran5_Steuerung' (rope wound onto the drum since
                           frame 0, in metres) turns the wheel (hub_m / drum radius), lifts the
                           load, shortens the rope and sets the steps of the two men in the
                           wheel; schwenk_grad slews the crane, pendel_m swings the load.
                           Keyed with the film's values it reproduces S1.

  leuchtturm_S1_kran_gepackt.blend (--pack) the same with textures and sky packed in

  /path/to/venv/bin/python export_kran.py [--out DIR] [--no-blend] [--pack]
"""
import argparse
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.normpath(os.path.join(HERE, '..', '..', 'wonder_film'))
sys.path.insert(0, WF)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import film_lighthouse20 as FM  # noqa: E402
import geometry as G  # noqa: E402
import render as R  # noqa: E402
import scene as SC  # noqa: E402

S1_END = 72                      # S1 = frames 0-71
N_WALK = 12                      # walk-cycle meshes (film_lighthouse20.build_people)
STRIDE = 1.45                    # metres per walk cycle (pose_treadwheel)
RIM = FM.WHEEL_R - 0.06          # radius the men walk on
SHEAVE = (-0.25, 0.0, 0.9)       # rope from the drum runs to this sheave at the mast foot
TAG_HAND = (41.0, -95.2, FM.QUAY_Z + 1.2)   # the man steadying the load holds the tag line here
TAG_LOAD = (0.9, 0.0, -1.0)      # ... tied to the load here (load frame)


def yaw(M):
    return math.atan2(M[1][0], M[0][0])


def wheel_angle(S):
    """Treadwheel angle about its axle (local y of crane 5), -pi..pi."""
    rel = S.cranes[5][0].matrix_world.inverted() @ S.tread.matrix_world
    return math.atan2(rel[0][2], rel[0][0])


BLEND_README = '''Leuchtturm v6, Einstellung S1 (Bild 0-71, 24 fps), Kran am Kai als gekoppeltes Rig.

Steuerung: Objekt 'Kran5_Steuerung' -> Objekteigenschaften -> Custom Properties
  hub_m         Seil, das seit Bild 0 auf die Trommel gewickelt wurde (m)
                Rad: Winkel = hub_m / 0.25 (Trommelradius); Last: z = z0 + hub_m;
                Seil: haengt gespannt von der Auslegerspitze zur Last (Stretch To);
                Maenner im Rad: Gehphase folgt dem Rad (1,54 m Laufradius, 1,45 m je Gehzyklus)
  schwenk_grad  Schwenk des Krans um den Mast
  pendel_m      Auslenkung der Last in Welt-x
Die drei Werte sind mit den Filmwerten verkeyt (hub 0 -> 0,49 m, Schwenk 15 -> 60 Grad).
Nur die hub_m-Kurve aendern: Rad, Seil, Last und Schritte bleiben mechanisch gekoppelt.
Treiber sind einfache Ausdruecke (kein 'Auto Run Python Scripts' noetig).

Animiert sind nur Kran, Kamera und Sonne. Leute, Boote, Moewen, Rauch und Wasser sind
auf dem Stand von Bild 0 eingefroren.
Render: Cycles, 6 Samples + OIDN, 1280x720, Mehrschicht-EXR (mit Tiefe und Objekt-Index).
Den gemalten Look des Films machen erst wonder_film/stylize.py und stabilize.py.
'''


def r4(x):
    return round(float(x), 4)


# ------------------------------------------------------------------ pass 1: the whole film
def collect(S, want_s1):
    c5, rope5, load5 = S.cranes[5]
    rows5, rows_all, s1 = [], [], []
    for f in range(FM.NFRAMES):
        meta = FM.pose(S, f)
        t = f / FM.FPS
        M = c5.matrix_world
        tip = M @ Vector(S.crane_tip)
        wc = M @ Vector(FM.WHEEL_C)
        vis = not c5.hide_render
        rows5.append(dict(
            bild=f, zeit_s=r4(t), einstellung=meta['shot'], kran_sichtbar=int(vis),
            rad_sichtbar=int(not S.tread.hide_render), schwenk_grad=math.degrees(yaw(M)),
            spitze=tuple(tip), seil_sichtbar=int(not rope5.hide_render),
            seil_laenge_m=rope5.matrix_world.to_scale().z, last_sichtbar=int(not load5.hide_render),
            last=tuple(load5.matrix_world.translation), rad_roh=wheel_angle(S),
            laeufer=sum(1 for o in S.people if not o.hide_render and (o.location - wc).length < 2.0) if vis else 0))
        for i, (c, r, ld) in enumerate(S.cranes):
            tp = c.matrix_world @ Vector(S.crane_tip_tall if i == 4 else S.crane_tip)
            lp = ld.matrix_world.translation
            rows_all.append(dict(
                bild=f, zeit_s=r4(t), einstellung=meta['shot'], kran=i, sichtbar=int(not c.hide_render),
                schwenk_grad=r4(math.degrees(yaw(c.matrix_world))), spitze_x=r4(tp.x), spitze_y=r4(tp.y),
                spitze_z=r4(tp.z), seil_sichtbar=int(not r.hide_render),
                seil_laenge_m=r4(r.matrix_world.to_scale().z), last_sichtbar=int(not ld.hide_render),
                last_x=r4(lp.x), last_y=r4(lp.y), last_z=r4(lp.z)))
        if want_s1 and f < S1_END:
            s1.append(dict(
                cam=S.cam.matrix_basis.copy(), sun_m=S.sun.matrix_basis.copy(),
                sun=(S.sun.data.energy, tuple(S.sun.data.color)), lens=S.cam.data.lens,
                slew=math.degrees(yaw(M)), rope=rope5.matrix_world.to_scale().z,
                pendel=load5.matrix_world.translation.x - tip.x))
        if f % 40 == 0:
            print(f'[data] frame {f} {meta["shot"]}', flush=True)
    return rows5, rows_all, s1


def finish_crane5(rows5):
    """Unwrap the wheel angle and compare it with the angle a drum on the same rope would
    have: theta(f) = theta(f0) + (L(f0) - L(f)) / DRUM_R, f0 = first frame of the shot."""
    out, prev, first = [], None, {}
    for r in rows5:
        a = r['rad_roh']
        if prev is not None and r['rad_sichtbar']:
            a = prev + (a - prev + math.pi) % (2 * math.pi) - math.pi
        if r['rad_sichtbar']:
            prev = a
        if r['rad_sichtbar']:
            first.setdefault(r['einstellung'], (a, r['seil_laenge_m']))
        f0 = first.get(r['einstellung'], (a, r['seil_laenge_m']))
        coupled = f0[0] + (f0[1] - r['seil_laenge_m']) / FM.DRUM_R
        seen = r['rad_sichtbar']
        tip, ld = r['spitze'], r['last']
        out.append(dict(
            bild=r['bild'], zeit_s=r['zeit_s'], einstellung=r['einstellung'], kran_sichtbar=r['kran_sichtbar'],
            rad_sichtbar=r['rad_sichtbar'], laeufer_im_rad=r['laeufer'], schwenk_grad=r4(r['schwenk_grad']),
            spitze_x=r4(tip[0]), spitze_y=r4(tip[1]), spitze_z=r4(tip[2]), seil_sichtbar=r['seil_sichtbar'],
            seil_laenge_m=r4(r['seil_laenge_m']),
            seil_aufgewickelt_m=r4(f0[1] - r['seil_laenge_m']),
            last_sichtbar=r['last_sichtbar'], last_x=r4(ld[0]), last_y=r4(ld[1]), last_z=r4(ld[2]),
            rad_winkel_rad=r4(a) if seen else '', rad_winkel_gekoppelt_rad=r4(coupled) if seen else '',
            abweichung_grad=r4(math.degrees(a - coupled)) if seen else ''))
    return out


def write_csv(path, rows):
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=';')
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ pass 2: S1 as a rig
def unit_rope(name, S, width):
    """Rope mesh from (0,0,0) to (0,1,0); a Stretch To constraint aims and stretches it."""
    b = G.HexBatch(name)
    b.add(G.beam([0, 0, 0], [0, 1.0, 0], width), mat=0)
    b.finalize()
    return SC.hex_mesh(name, b, np.ones(1, bool), [S.m_rope])


def stretch(obj, target):
    con = obj.constraints.new('STRETCH_TO')
    con.target = target
    con.rest_length = 1.0
    con.volume = 'NO_VOLUME'
    con.keep_axis = 'SWING_Y'


def driver(obj, path, index, expr, ctrl, props):
    fc = obj.driver_add(path, index) if index is not None else obj.driver_add(path)
    d = fc.driver
    d.type = 'SCRIPTED'
    for name, prop in props:
        v = d.variables.new()
        v.name = name
        v.type = 'SINGLE_PROP'
        v.targets[0].id_type = 'OBJECT'
        v.targets[0].id = ctrl
        v.targets[0].data_path = f'["{prop}"]'
    d.expression = expr
    assert d.is_simple_expression, expr      # evaluates without 'Auto Run Python Scripts'
    return fc


def build_rig(S, s1, out_path, pack):
    sc = bpy.context.scene
    c5, rope5, load5 = S.cranes[5]
    Q = Vector(FM.QUAY_CRANE)
    tipL = Vector(S.crane_tip)
    M0 = c5.matrix_world.copy()
    wheel_w = M0 @ Vector(FM.WHEEL_C)

    # the two men in the wheel (frame 0), ordered along the axle
    men = sorted((o for o in S.people if not o.hide_render and (o.location - wheel_w).length < 2.0),
                 key=lambda o: (M0.inverted() @ o.location).y)
    assert len(men) == 2, len(men)

    # control object: the three values the whole crane follows
    ctrl = SC.link(bpy.data.objects.new('Kran5_Steuerung', None))
    ctrl.empty_display_type = 'ARROWS'
    ctrl.empty_display_size = 2.0
    ctrl.location = Q + Vector((0, 0, 14.0))
    ctrl.hide_render = True
    for key, val, desc, lo, hi in (
            ('hub_m', 0.0, 'Seil, das seit Bild 0 auf die Trommel gewickelt wurde (m). Dreht das Rad um '
                           'hub_m / Trommelradius, hebt die Last um hub_m, kuerzt das Seil um hub_m und '
                           'setzt die Schritte der Maenner im Rad', -10.0, 10.0),
            ('schwenk_grad', 15.0, 'Schwenkwinkel des Krans um die Mastachse (Grad)', -360.0, 360.0),
            ('pendel_m', 0.0, 'Auslenkung der Last in Welt-x (m), wie im Film', -2.0, 2.0)):
        ctrl[key] = val
        ctrl.id_properties_ui(key).update(description=desc, min=lo, max=hi, soft_min=lo, soft_max=hi)

    # crane: stands at the quay, slews about z
    c5.matrix_world = Matrix.Identity(4)
    c5.location = Q
    driver(c5, 'rotation_euler', 2, 'radians(s)', ctrl, [('s', 'schwenk_grad')])

    # wheel and drum: angle = wound rope / drum radius
    S.tread.parent = c5
    S.tread.matrix_parent_inverse = Matrix.Identity(4)
    S.tread.location = FM.WHEEL_C
    S.tread.rotation_euler = (0, 0, 0)
    S.tread.hide_render = False
    driver(S.tread, 'rotation_euler', 1, f'h / {FM.DRUM_R!r}', ctrl, [('h', 'hub_m')])

    # load: hangs below the jib tip, rises by the wound length; pendel_m swings it in world x
    z0 = s1[0]['last_z0'] - Q.z
    load5.parent = c5
    load5.matrix_parent_inverse = Matrix.Identity(4)
    load5.rotation_euler = (0, 0, 0)
    load5.hide_render = False
    driver(load5, 'location', 0, f'{tipL.x!r} + cos(radians(s)) * p', ctrl, [('s', 'schwenk_grad'), ('p', 'pendel_m')])
    driver(load5, 'location', 1, f'{tipL.y!r} - sin(radians(s)) * p', ctrl, [('s', 'schwenk_grad'), ('p', 'pendel_m')])
    driver(load5, 'location', 2, f'{z0!r} + h', ctrl, [('h', 'hub_m')])

    # hoist rope: from the jib tip to the load's lifting bar, always straight and taut
    rope = SC.link(bpy.data.objects.new('Kran5_Seil', unit_rope('Kran5_Seil', S, 0.09)))
    rope.parent = c5
    rope.location = tipL
    rope.pass_index = SC.PASS['crane']
    stretch(rope, load5)
    rope5.hide_render = rope5.hide_viewport = True

    # tag line: from the load to the man steadying it
    knot = SC.link(bpy.data.objects.new('Kran5_Leinenknoten', None))
    knot.parent = load5
    knot.location = TAG_LOAD
    knot.empty_display_size = 0.2
    tag = SC.link(bpy.data.objects.new('Kran5_Fuehrungsleine', unit_rope('Kran5_Fuehrungsleine', S, 0.035)))
    tag.location = TAG_HAND
    tag.pass_index = SC.PASS['crane']
    stretch(tag, knot)

    # pennant on the jib tip (film: life.pose_pennants, mount 1 in S1): rides with the tip and
    # keeps streaming downwind; its flutter is frozen as in frame 0
    pen = S.pennants[1]
    mount = M0 @ tipL + Vector((0, 0, 0.2))
    assert all(abs(a - b) < 1e-6 for ra, rb in zip(pen.matrix_world, Matrix.Identity(4)) for a, b in zip(ra, rb))
    assert min((v.co - mount).length for v in pen.data.vertices) < 0.5
    pen.data.transform(Matrix.Translation(-mount))
    holder = SC.link(bpy.data.objects.new('Kran5_Wimpelhalter', None))
    holder.parent = c5
    holder.location = tipL + Vector((0, 0, 0.2))
    holder.empty_display_size = 0.3
    pen.location = (0, 0, 0)
    pen.constraints.new('COPY_LOCATION').target = holder

    # the two men in the wheel: 12 walk-cycle meshes each, the visible one follows the wheel's rim
    k = RIM / (FM.DRUM_R * STRIDE)                  # walk cycles per metre of wound rope
    for j, man in enumerate(men):
        ph = j * 1.7 / (2 * math.pi)
        for i, me in enumerate(S.pose_meshes['walk']):
            o = SC.link(bpy.data.objects.new(f'Kran5_Laeufer{j}_{i:02d}', me))
            o.parent = c5
            o.location = (FM.WHEEL_C[0] + 0.3, (j - 0.5) * 0.46, FM.WHEEL_C[2] - FM.WHEEL_R + 0.1)
            o.rotation_euler = (0, 0, -math.pi / 2)
            o.scale = (man.get('size', 1.0),) * 3
            o.color = man.color
            o.pass_index = man.pass_index
            u = f'(h * {k!r} + {ph!r})'
            expr = f'floor({u} * {N_WALK}) - {N_WALK} * floor({u}) != {i}'
            driver(o, 'hide_render', None, expr, ctrl, [('h', 'hub_m')])
            driver(o, 'hide_viewport', None, expr, ctrl, [('h', 'hub_m')])
        man.hide_render = man.hide_viewport = True

    # keyframes: control values from the film, and every other object that moves in S1
    L0 = s1[0]['rope']
    for f, st in enumerate(s1):
        ctrl['hub_m'] = L0 - st['rope']
        ctrl['schwenk_grad'] = st['slew']
        ctrl['pendel_m'] = st['pendel']
        for key in ('hub_m', 'schwenk_grad', 'pendel_m'):
            ctrl.keyframe_insert(f'["{key}"]', frame=f)
    for o, key in ((S.cam, 'cam'), (S.sun, 'sun_m')):
        prev = None
        for f, st in enumerate(s1):
            loc, rot, sca = st[key].decompose()
            prev = rot.to_euler('XYZ', prev) if prev is not None else rot.to_euler('XYZ')
            o.location, o.rotation_euler, o.scale = loc, prev, sca
            for p in ('location', 'rotation_euler', 'scale'):
                o.keyframe_insert(p, frame=f)
    for f, st in enumerate(s1):
        S.sun.data.energy, S.sun.data.color = st['sun'][0], st['sun'][1]
        S.sun.data.keyframe_insert('energy', frame=f)
        S.sun.data.keyframe_insert('color', frame=f)
        S.cam.data.lens = st['lens']
        S.cam.data.keyframe_insert('lens', frame=f)
    # hidden-for-render objects out of the viewport, too (the pools keep old positions)
    for o in bpy.context.scene.objects:
        if o.animation_data is None or not o.animation_data.drivers:
            o.hide_viewport = o.hide_render
    ctrl.hide_viewport = False

    txt = bpy.data.texts.new('LIES_MICH')
    txt.write(BLEND_README)

    sc.frame_start, sc.frame_end = 0, S1_END - 1
    sc.render.fps = FM.FPS
    R.configure_beauty(sc, 6, (1280, 720))
    sc.world.cycles.sampling_method = 'MANUAL'
    sc.world.cycles.sample_map_resolution = 256
    sc.render.filepath = '//render/S1_'
    sc.camera = S.cam
    sc.frame_set(0)

    bpy.ops.wm.save_as_mainfile(filepath=out_path, compress=True)
    bpy.ops.file.make_paths_relative()            # textures from ../../wonder_film/assets
    bpy.ops.wm.save_as_mainfile(filepath=out_path, compress=True)
    if pack:
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=out_path.replace('.blend', '_gepackt.blend'), compress=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=HERE)
    ap.add_argument('--no-blend', action='store_true')
    ap.add_argument('--pack', action='store_true', help='pack textures and sky into the .blend')
    ap.add_argument('--name', default='leuchtturm_S1_kran.blend')
    args, _ = ap.parse_known_args()
    os.makedirs(args.out, exist_ok=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
    bpy.context.preferences.filepaths.save_version = 0

    S = FM.build((1280, 720))
    rows5, rows_all, s1 = collect(S, not args.no_blend)
    write_csv(os.path.join(args.out, 'kran5_daten.csv'), finish_crane5(rows5))
    write_csv(os.path.join(args.out, 'alle_kraene.csv'), rows_all)
    geo = dict(
        einheiten='Meter, Radiant/Grad wie angegeben; Blender-Koordinaten, z nach oben',
        fps=FM.FPS, bilder=FM.NFRAMES,
        einstellungen=[dict(name=n, von_s=a, bis_s=b, von_bild=int(round(a * FM.FPS)),
                            bis_bild=int(round(b * FM.FPS)) - 1) for n, a, b in FM.SHOTS],
        kran5=dict(
            standort=list(FM.QUAY_CRANE), kai_hoehe=FM.QUAY_Z, mast_hoehe_lokal=9.0,
            auslegerspitze_lokal=[float(v) for v in S.crane_tip],
            radachse_lokal=list(FM.WHEEL_C), rad_radius=FM.WHEEL_R, lauf_radius=RIM,
            trommel_radius=FM.DRUM_R, schrittlaenge_pro_zyklus=STRIDE, gehzyklus_meshes=N_WALK,
            umlenkrolle_mastfuss_lokal=list(SHEAVE), seil_am_ausleger_lokal=[[0.2, 0.0, 1.25], 'spitze - (0,0,0.3)'],
            lokal='im drehbaren Kranrahmen: x zeigt zum Ausleger, Drehung um z = Schwenk'),
        formeln={
            'radwinkel': 'theta = theta0 + hub / trommel_radius',
            'seillaenge': 'L = L0 - hub',
            'lasthoehe': 'z_last = z_last0 + hub',
            'randgeschwindigkeit': 'v_rand = lauf_radius * dtheta/dt  (Maenner gehen genau so schnell)',
            'schrittphase': 'zyklen = hub * lauf_radius / (trommel_radius * schrittlaenge_pro_zyklus)',
            'film_S1': 'hub = 0.5 m * t / 3 s, schwenk = 15 + 45 * ease(t / 3 s) Grad, pendel = 0.075 m * sin(2.1 t)',
            'film_S2_bis_S5': 'theta = 0.8 rad/s * t, unabhaengig vom Seil (nicht gekoppelt)'})
    with open(os.path.join(args.out, 'kran_geometrie.json'), 'w') as fh:
        json.dump(geo, fh, indent=2, ensure_ascii=False)
    print('[data] written', flush=True)
    if args.no_blend:
        return

    # back to frame 0; keep the tag line out of the shared rope mesh (the rig draws its own)
    lines = {}
    orig = FM.set_lines

    def capture(S_, segs):
        lines['segs'] = list(segs)
        orig(S_, segs)
    FM.set_lines = capture
    FM.pose(S, 0)
    FM.set_lines = orig
    lb = S.cranes[5][2].matrix_world @ Vector(TAG_LOAD)
    rest = [sg for sg in lines['segs'] if (Vector(sg[0]) - lb).length > 1e-4]
    assert len(rest) == len(lines['segs']) - 1
    orig(S, rest)
    s1[0]['last_z0'] = S.cranes[5][2].matrix_world.translation.z
    build_rig(S, s1, os.path.join(args.out, args.name), args.pack)
    print('[blend] written', os.path.join(args.out, args.name), flush=True)


if __name__ == '__main__':
    main()
