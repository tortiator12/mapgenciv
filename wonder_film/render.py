"""Render the lighthouse film frames with Cycles (CPU).

For every frame two renders are made:
  1. beauty  - path traced + OIDN denoised, scene-linear EXR (colour, depth, object id)
  2. data    - 2x resolution, 1 sample, flat override material: depth/normal/id
               passes that are turned into anti-aliased ink lines (PNG)

Usage (inside the venv that has `bpy`):
  python wonder_film/render.py --out build/frames --frames 0-719
  python wonder_film/render.py --out build/preview --frames 60,240,480 --res 640x360 --spp 4
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
import OpenEXR  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

import lines as LN  # noqa: E402
import scene as SC  # noqa: E402
import timeline as TL  # noqa: E402


def parse_frames(spec):
    out = []
    for part in spec.split(','):
        if '-' in part:
            a, b = part.split('-')
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def read_exr(path):
    with OpenEXR.File(path, separate_channels=True) as f:
        return {k: np.array(v.pixels) for k, v in f.channels().items()}


def configure_beauty(sc, spp, res):
    cy = sc.cycles
    sc.render.resolution_x, sc.render.resolution_y = res
    cy.samples = spp
    cy.use_adaptive_sampling = False
    cy.use_denoising = True
    cy.denoiser = 'OPENIMAGEDENOISE'
    cy.denoising_quality = 'BALANCED'
    cy.denoising_prefilter = 'FAST'
    cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    cy.max_bounces = 4
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 1
    cy.transmission_bounces = 0
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 2
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.sample_clamp_indirect = 4.0
    cy.filter_width = 1.5
    sc.render.film_transparent = False
    vl = sc.view_layers[0]
    vl.use_pass_z = True
    vl.use_pass_normal = False
    vl.use_pass_object_index = True
    vl.material_override = None
    if 'clouds' not in vl.aovs:
        a = vl.aovs.add()
        a.name = 'clouds'
        a.type = 'VALUE'
    im = sc.render.image_settings
    im.file_format = 'OPEN_EXR_MULTILAYER'
    im.color_depth = '16'
    im.exr_codec = 'DWAA'


DATA_SCALE = 1.5


def configure_data(sc, res, override):
    cy = sc.cycles
    sc.render.resolution_x, sc.render.resolution_y = int(res[0] * DATA_SCALE), int(res[1] * DATA_SCALE)
    cy.samples = 1
    cy.use_denoising = False
    cy.max_bounces = 0
    cy.filter_width = 0.01
    vl = sc.view_layers[0]
    vl.use_pass_z = True
    vl.use_pass_normal = True
    vl.use_pass_object_index = True
    vl.material_override = override
    im = sc.render.image_settings
    im.file_format = 'OPEN_EXR_MULTILAYER'
    im.color_depth = '16'
    im.exr_codec = 'NONE'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--frames', default=f'0-{TL.NFRAMES - 1}')
    ap.add_argument('--res', default='1280x720')
    ap.add_argument('--spp', type=int, default=6)
    ap.add_argument('--no-lines', action='store_true')
    ap.add_argument('--skip-existing', action='store_true')
    ap.add_argument('--threads', type=int, default=0)
    ap.add_argument('--film', default=None, help='edit module film_<name>.py (e.g. lighthouse20)')
    args = ap.parse_args()
    FM = None
    if args.film:
        import importlib
        FM = importlib.import_module(f'film_{args.film}')
        if args.frames == f'0-{TL.NFRAMES - 1}':
            args.frames = f'0-{FM.NFRAMES - 1}'
    res = tuple(int(v) for v in args.res.split('x'))
    os.makedirs(args.out, exist_ok=True)

    t0 = time.time()
    S = FM.build(res) if FM else SC.build(res)
    sc = bpy.context.scene
    if args.threads:
        sc.render.threads_mode = 'FIXED'
        sc.render.threads = args.threads
    sc.render.use_persistent_data = True
    sc.world.cycles.sampling_method = 'MANUAL'
    sc.world.cycles.sample_map_resolution = 256
    override = SC.mat_simple('DataOverride', (0.5, 0.5, 0.5), 1.0)
    print(f'[build] {time.time() - t0:.1f}s', flush=True)

    lights = [o for o in sc.objects if o.type == 'LIGHT']
    for f in parse_frames(args.frames):
        beauty = os.path.join(args.out, f'beauty_{f:04d}.exr')
        linep = os.path.join(args.out, f'lines_{f:04d}.png')
        meta_p = os.path.join(args.out, f'meta_{f:04d}.json')
        if args.skip_existing and os.path.exists(meta_p):
            continue
        tf = time.time()
        if FM:
            meta = FM.pose(S, f)
            t = meta['t']
        else:
            t = f / TL.FPS
            meta = SC.pose(S, t)
        sc.frame_current = f
        sc.cycles.seed = 17   # fixed: static residual noise reads calmer than boiling noise

        configure_beauty(sc, args.spp, res)
        sc.render.filepath = beauty
        bpy.ops.render.render(write_still=True)
        tb = time.time() - tf

        if not args.no_lines:
            hidden = [(o, o.hide_render) for o in lights]
            for o in lights:
                o.hide_render = True
            sky_world = sc.world
            sc.world = S.flat_world
            configure_data(sc, res, override)
            tmp = os.path.join(args.out, f'_data_{f:04d}.exr')
            sc.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            for o, h in hidden:
                o.hide_render = h
            sc.world = sky_world
            ch = read_exr(tmp)
            Z = ch['ViewLayer.Depth.Z']
            N = np.stack([ch['ViewLayer.Normal.X'], ch['ViewLayer.Normal.Y'], ch['ViewLayer.Normal.Z']], -1)
            ID = ch['ViewLayer.IndexOB.X']
            LN.save_lines(linep, Z, N, ID, out_size=res)
            os.remove(tmp)

        # screen-space positions used by the stylizer (god rays, glow)
        cam = S.cam
        fire_s = world_to_camera_view(sc, cam, Vector(SC.FIRE_POS))
        sun_s = world_to_camera_view(sc, cam, cam.location + Vector(TL.sun_dir(meta['hour'])) * 10000)
        meta.update(cam_matrix=[list(r) for r in cam.matrix_world], lens=cam.data.lens,
                    sensor=cam.data.sensor_width)
        meta.update(frame=f, fire_screen=list(fire_s), sun_screen=list(sun_s),
                    cam=list(cam.location), horizon=list(meta['horizon']), zenith=list(meta['zenith']))
        with open(meta_p, 'w') as fh:
            json.dump(meta, fh)
        print(f'[frame {f}] t={t:.2f}s beauty {tb:.1f}s total {time.time() - tf:.1f}s '
              f'H={meta["height"]:.1f} sun={meta["sun_el"]:.1f}', flush=True)


if __name__ == '__main__':
    main()
