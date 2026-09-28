"""S1 of the lighthouse film (v6) without the fade-in, for AI video tools and compositing.

The game film fades in from black over 0.35 s (stylize.py --fade-in 0.35), so frame 0 of
the v6 reference package was black.  This takes S1 frames stylized again without the fade
(same stylize/stabilize settings as make_lighthouse20.sh) and writes into --out:
  S1_kai_ohne_blende.mp4            72 frames, 1280x720, 24 fps, no sound
  S1_kai_start/mitte/ende.png       frames 0, 36, 71
  S1_kai_tiefe.mp4                  depth (near = white), normalised once for the shot
  S1_kai_kanten.mp4                 edges (Canny) of the frames
  S1_kai_kranmaske.mp4, kranmaske/  white = crane pass: cranes, treadwheel, ropes, loads
  leuchtturm_v6_ohne_blende.mp4     the whole 20 s film with this S1 and the soundtrack

  python mache_s1_material.py --frames DIR_WITH_frame_NNNN.png --out DIR [--build build/l20v6]

Making the frames (from wonder_film/):
  python stylize.py --inp build/l20v6 --out X/png --look paint --no-titles --frames 0,1,...,71
  python stabilize.py --inp X/png --meta build/l20v6 --out X/png_stab --deflicker S2 --deflicker-frames 5
"""
import argparse
import os
import shutil
import subprocess

import cv2
import numpy as np
import OpenEXR

HERE = os.path.dirname(os.path.abspath(__file__))
F0, F1 = 0, 72


def enc(pattern, start, n, dst, crf=14):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '24', '-start_number', str(start),
                    '-i', pattern, '-frames:v', str(n), '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf),
                    '-pix_fmt', 'yuv420p', dst], check=True)


def channels(build, f):
    with OpenEXR.File(os.path.join(build, f'beauty_{f:04d}.exr'), separate_channels=True) as e:
        ch = e.channels()
        return (np.array(ch['ViewLayer.Depth.Z'].pixels, np.float32),
                np.array(ch['ViewLayer.IndexOB.X'].pixels, np.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', required=True, help='S1 frames frame_0000.png .. frame_0071.png without fade')
    ap.add_argument('--out', required=True)
    ap.add_argument('--build', default=os.path.join(HERE, '..', '..', 'wonder_film', 'build', 'l20v6'))
    args = ap.parse_args()
    n = F1 - F0
    tmp = os.path.join(args.out, '_tmp')
    os.makedirs(os.path.join(args.out, 'kranmaske'), exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    pat = os.path.join(args.frames, 'frame_%04d.png')

    enc(pat, F0, n, os.path.join(args.out, 'S1_kai_ohne_blende.mp4'))
    for lab, f in (('start', F0), ('mitte', (F0 + F1) // 2), ('ende', F1 - 1)):
        shutil.copy(os.path.join(args.frames, f'frame_{f:04d}.png'), os.path.join(args.out, f'S1_kai_{lab}.png'))

    data = [channels(args.build, f) for f in range(F0, F1)]
    fin = np.concatenate([z[np.isfinite(z) & (z < 1e8)][::97] for z, _ in data])
    lo, hi = np.percentile(np.log(fin), [1.0, 99.0])
    for i, (z, idx) in enumerate(data):
        z = np.where(np.isfinite(z) & (z < 1e8), z, np.exp(hi))
        d = 1.0 - np.clip((np.log(z) - lo) / (hi - lo), 0, 1)
        cv2.imwrite(os.path.join(tmp, f'd_{i:04d}.png'), (d * 255).astype(np.uint8))
        im = cv2.imread(os.path.join(args.frames, f'frame_{F0 + i:04d}.png'), cv2.IMREAD_GRAYSCALE)
        cv2.imwrite(os.path.join(tmp, f'e_{i:04d}.png'), cv2.Canny(cv2.GaussianBlur(im, (0, 0), 1.2), 40, 110))
        m = (np.abs(idx - 5.0) < 0.5).astype(np.uint8) * 255          # scene.PASS['crane'] == 5
        cv2.imwrite(os.path.join(args.out, 'kranmaske', f'maske_{F0 + i:04d}.png'), m)
    enc(os.path.join(tmp, 'd_%04d.png'), 0, n, os.path.join(args.out, 'S1_kai_tiefe.mp4'))
    enc(os.path.join(tmp, 'e_%04d.png'), 0, n, os.path.join(args.out, 'S1_kai_kanten.mp4'))
    enc(os.path.join(args.out, 'kranmaske', 'maske_%04d.png'), F0, n, os.path.join(args.out, 'S1_kai_kranmaske.mp4'), 8)

    # the whole film: this S1, then the v6 frames
    for f in range(480):
        src = os.path.join(args.frames, f'frame_{f:04d}.png') if f < F1 else \
            os.path.join(args.build, 'png_stab', f'frame_{f:04d}.png')
        os.symlink(os.path.abspath(src), os.path.join(tmp, f'v_{f:04d}.png'))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '24', '-i', os.path.join(tmp, 'v_%04d.png'),
                    '-i', os.path.join(args.build, 'soundtrack.wav'), '-c:v', 'libx264', '-preset', 'slow',
                    '-crf', '18', '-tune', 'film', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', '-shortest', os.path.join(args.out, 'leuchtturm_v6_ohne_blende.mp4')],
                   check=True)
    shutil.rmtree(tmp)
    print('written', args.out)


if __name__ == '__main__':
    main()
