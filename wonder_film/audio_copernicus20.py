"""Soundtrack for the game film "Kopernikus' Observatorium" (numpy/scipy only).

Follows the five shots of film_copernicus20.py:
  S1 0-3 s      morning at the brick kilns: larks, the kilns' fire, an ox cart creaking up
                the road, bricks stacked, a far bell; a lute prelude alone (D Dorian)
  S2 3-9 s      time-lapse of the tower: a galliard on recorder, lute and tabor; sped-up
                trowels on brick, the treadwheel crane, the hours struck by the bell
  S3 9-12.5 s   the workshop: the carpenter's plane on its stroke, a quill, the lute alone
  S4 12.5-15.5 s sunset on the platform: the Angelus from the cathedral on the cut, the
                cadence in D major (choir, recorder, lute), mallets setting the instruments,
                swifts, the wind at height
  S5 15.5-20 s  night: stillness, the cold wind, an owl; a quiet choir, G to D (Amen)

Loudness matches the other wonder films (mean volume about -24 dB).

  python wonder_film/audio_copernicus20.py --out build/copernicus20.wav
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio as A  # noqa: E402
import audio_lighthouse20 as AL  # noqa: E402
from audio import SR, bandpass, highpass, lowpass, midi_hz, place  # noqa: E402

DUR = 20.0
N = int(SR * DUR)
RNG = np.random.default_rng(1043)
A.RNG = RNG
AL.RNG = RNG
Q = 0.4                          # a quarter of the galliard (150 BPM, 3/4)
BAR = 3 * Q
T_S2, T_S3, T_DONE, T_S5 = 3.0, 9.0, 12.5, 15.5


# ------------------------------------------------------------------ instruments
def lute(m, dur=1.6, gain=1.0):
    """A lute course: two strings plucked together, one a hair sharp; soft and short-lived."""
    x = A.pluck(m, dur, bright=0.5, damp=0.995)
    x += 0.7 * A.pluck(m + 0.04, dur, bright=0.45, damp=0.995)[:len(x)]
    return lowpass(x, 3800) * gain * 0.8


def recorder(m, dur, gain=1.0):
    """A recorder: nearly a sine, a little second harmonic, breath and a soft chiff."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(m)
    vib = 0.003 * np.sin(2 * np.pi * 4.8 * t) * np.clip((t - 0.25) / 0.3, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * (1 + vib)) / SR
    x = np.sin(ph) + 0.12 * np.sin(2 * ph) + 0.05 * np.sin(3 * ph)
    breath = bandpass(RNG.normal(0, 1, n), f * 0.8, f * 3.0) * 0.06
    chiff = highpass(RNG.normal(0, 1, n), 1500) * np.exp(-t * 60) * 0.25
    return (x + breath + chiff) * A.env_adsr(n, 0.03, 0.08, 0.85, 0.08) * gain * 0.35


def tabor(gain=1.0):
    """The pipe-and-tabor drum: a small snared drum."""
    n = int(0.25 * SR)
    k = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * k * (1 - 0.3 * k)) * np.exp(-k * 28)
    snare = bandpass(RNG.normal(0, 1, n), 1500, 6000) * np.exp(-k * 22) * 0.6
    return (body + snare) * gain * 0.5


def bell(f0, dur=6.0, gain=1.0):
    """A church bell: hum, prime, minor tierce, quint, nominal and above, each with its
    own decay; a metallic strike at the start."""
    n = int(dur * SR)
    k = np.arange(n) / SR
    x = np.zeros(n)
    for r, a, d in ((0.5, 0.5, 0.35), (1.0, 0.6, 0.6), (1.19, 0.45, 0.8), (1.5, 0.25, 1.0), (2.0, 0.55, 1.2),
                    (2.51, 0.2, 1.8), (2.66, 0.18, 2.0), (3.01, 0.15, 2.4), (4.16, 0.1, 3.5)):
        beat = 1 + 0.15 * np.sin(2 * np.pi * RNG.uniform(0.6, 1.8) * k)
        x += a * np.sin(2 * np.pi * f0 * r * k + RNG.uniform(0, 6)) * np.exp(-k * d) * beat
    x += 0.5 * bandpass(RNG.normal(0, 1, n), 1500, 6000) * np.exp(-k * 60)
    return x * gain * 0.3


# ------------------------------------------------------------------ music
CH = {'Dm': [38, 50, 57, 62, 65], 'C': [36, 48, 55, 60, 64], 'F': [41, 53, 57, 60, 65], 'Gm': [43, 50, 55, 58, 62],
      'A': [45, 52, 57, 61, 64], 'Bb': [46, 53, 58, 62, 65], 'D': [38, 50, 57, 62, 66], 'G': [43, 50, 55, 59, 62]}


def music():
    mus = np.zeros((N, 2))
    # S1: the lute prelude, free and unhurried
    for k, (m, dt) in enumerate(((50, 0.08), (57, 0.34), (62, 0.6), (65, 0.86), (64, 1.18), (62, 1.46), (60, 1.76),
                                 (62, 2.06), (57, 2.36), (55, 2.62), (57, 2.86))):
        place(mus, lute(m, 1.8), dt, pan=-0.15 + 0.03 * k, gain=0.85)
    place(mus, lute(38, 2.6), 0.08, pan=-0.2, gain=0.55)
    # S2: the galliard, five bars; the recorder over lute chords and the tabor
    chords = ['Dm', 'C', 'F', 'Gm', 'Dm']
    tune = [[(69, 0, 1), (65, 1, 0.5), (67, 1.5, 0.5), (69, 2, 1)],
            [(67, 0, 1), (64, 1, 0.5), (65, 1.5, 0.5), (67, 2, 1)],
            [(69, 0, 0.5), (70, 0.5, 0.5), (72, 1, 1), (69, 2, 1)],
            [(70, 0, 1), (67, 1, 1), (69, 2, 1)],
            [(65, 0, 1), (64, 1, 0.5), (62, 1.5, 1.5)]]
    for b, ch in enumerate(chords):
        tb = T_S2 + b * BAR
        notes = CH['A'] if (b == 3) else CH[ch]
        place(mus, lute(notes[0], 1.4), tb, pan=-0.3, gain=0.5)
        for beat in (1, 2):
            for i, m in enumerate(CH[ch][2:] if not (b == 3 and beat == 2) else CH['A'][2:]):
                place(mus, lute(m, 0.9), tb + beat * Q + 0.012 * i, pan=-0.25 + 0.1 * i, gain=0.28)
        for m, st, du in tune[b]:
            place(mus, recorder(m, du * Q + 0.05), tb + st * Q, pan=0.2, gain=0.55)
        for pos, g in ((0, 0.55), (1.5, 0.3), (2, 0.4)):
            place(mus, tabor(g), tb + pos * Q, pan=0.3)
    # S3: the lute alone in the workshop, broken chords leading to the cadence
    for c, ch in enumerate(('Dm', 'Bb', 'C')):
        tc = T_S3 + c * 1.18
        for i, m in enumerate(CH[ch][1:] + [CH[ch][3]]):
            place(mus, lute(m + (12 if i == 3 and c == 2 else 0), 1.6), tc + i * 0.29, pan=-0.1 + 0.05 * i, gain=0.45)
    place(mus, lute(45, 1.2), T_S3 + 3.3, pan=-0.2, gain=0.4)                    # A under the cut: the dominant
    place(mus, lute(57, 1.2), T_S3 + 3.3, pan=0.0, gain=0.35)
    for m, st, du in ((69, 9.6, 1.0), (67, 10.9, 0.8), (64, 11.8, 0.6)):
        place(mus, recorder(m, du), st, pan=0.25, gain=0.3)
    # S4: the cadence on the cut: D major with choir, recorder and lute, the Angelus above it
    for i, m in enumerate(CH['D']):
        place(mus, A.pad_note(m, T_S5 - T_DONE + 1.2, bright=1600, a=0.2, r=1.2), T_DONE, pan=(i / 4 - 0.5) * 0.8, gain=0.22)
    for i, m in enumerate((50, 57, 62, 66)):
        place(mus, A.choir_note(m, T_S5 - T_DONE + 0.8, a=0.4, r=1.2), T_DONE, pan=(i - 1.5) * 0.3, gain=0.16)
    for k, (m, du) in enumerate(((74, 0.5), (73, 0.3), (74, 0.3), (76, 0.5), (78, 0.8), (76, 0.4), (74, 0.9))):
        st = T_DONE + 0.3 + sum(d for _, d in ((74, 0.5), (73, 0.3), (74, 0.3), (76, 0.5), (78, 0.8), (76, 0.4), (74, 0.9))[:k])
        place(mus, recorder(m, du + 0.05), st, pan=0.2, gain=0.45)
    for k in range(8):
        m = CH['D'][1 + k % 4] + (12 if k >= 4 else 0)
        place(mus, lute(m, 1.2), T_DONE + 0.1 + k * 0.36, pan=-0.2, gain=0.3)
    place(mus, A.boom(3.0, 36.7, 0.35), T_DONE)
    # S5: night, the choir alone and quiet: G major to D major, an Amen
    for i, m in enumerate((43, 55, 59, 62)):
        place(mus, A.choir_note(m, 2.4, a=0.9, r=1.0), T_S5, pan=(i - 1.5) * 0.35, gain=0.32)
    for i, m in enumerate((38, 50, 57, 62, 66)):
        place(mus, A.choir_note(m, DUR - T_S5 - 1.9, a=1.1, r=2.2), T_S5 + 2.0, pan=(i - 2) * 0.3, gain=0.28)
    for i, m in enumerate((38, 45, 50)):
        place(mus, A.pad_note(m, DUR - T_S5, bright=900, a=1.5, r=2.5), T_S5, pan=(i - 1) * 0.4, gain=0.22)
    return mus


# ------------------------------------------------------------------ sound effects
def songbird(dur=1.2, seed=0):
    """A lark's run: fast chirps sweeping 2.5-6 kHz."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    out = np.zeros(n)
    t = 0.0
    while t < dur - 0.08:
        m = int(rng.uniform(0.02, 0.06) * SR)
        k = np.arange(m) / SR
        f0, f1 = rng.uniform(2500, 5000), rng.uniform(3000, 6200)
        ph = 2 * np.pi * np.cumsum(np.linspace(f0, f1, m)) / SR
        i0 = int(t * SR)
        out[i0:i0 + m] += np.sin(ph) * np.sin(np.pi * k / k[-1]) ** 2
        t += rng.uniform(0.03, 0.09)
    return out * 0.3


def swift(dur=0.6, seed=0):
    """Swifts screaming past at dusk: a shrill buzzy trill."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    k = np.arange(n) / SR
    f = rng.uniform(5500, 7000) * (1 - 0.1 * k / dur)
    buzz = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 70 * k))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * lowpass(buzz, 900) * np.sin(np.pi * k / dur)
    return x * 0.25


def owl():
    """A tawny owl: hoo ... hoo-hoo-hoo."""
    out = np.zeros(int(1.6 * SR))
    for st, du, f in ((0.0, 0.35, 420), (0.75, 0.12, 440), (0.95, 0.12, 440), (1.15, 0.3, 430)):
        n = int(du * SR)
        k = np.arange(n) / SR
        x = np.sin(2 * np.pi * f * k * (1 - 0.05 * k / du)) * np.sin(np.pi * k / du) ** 1.5
        out[int(st * SR):int(st * SR) + n] += x
    return out * 0.2


def clink():
    """A fired brick set on another: a short ceramic clack."""
    n = int(0.18 * SR)
    k = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * RNG.uniform(1100, 2600) * k) * np.exp(-k * RNG.uniform(40, 70)) for _ in range(3))
    x += bandpass(RNG.normal(0, 1, n), 1500, 5000) * np.exp(-k * 120)
    return x * 0.35


def trowel():
    """A mason's trowel: a scrape through the mortar, then the handle tapping the brick home."""
    n = int(0.45 * SR)
    k = np.arange(n) / SR
    scrape = bandpass(RNG.normal(0, 1, n), 2000, 7000) * np.exp(-((k - 0.1) / 0.06) ** 2) * 0.5
    tap = (np.sin(2 * np.pi * RNG.uniform(800, 1300) * k) * np.exp(-(k - 0.3).clip(0) * 60)
           * (k > 0.3) + lowpass(RNG.normal(0, 1, n), 1500) * np.exp(-((k - 0.3) / 0.006) ** 2) * 2)
    return (scrape + tap * 0.5) * 0.4


def plane_stroke(dur=0.6):
    """A plane along a rule: a rising swish of shavings."""
    n = int(dur * SR)
    k = np.arange(n) / SR
    env = np.sin(np.pi * np.clip(k / dur, 0, 1)) ** 0.8
    x = bandpass(RNG.normal(0, 1, n), 900, 5500) * env * (0.7 + 0.3 * np.sin(2 * np.pi * 37 * k))
    return x * 0.3


def knock():
    """Wood on wood: a mallet setting a joint."""
    n = int(0.2 * SR)
    k = np.arange(n) / SR
    x = np.sin(2 * np.pi * RNG.uniform(260, 420) * k) * np.exp(-k * 45)
    x += lowpass(RNG.normal(0, 1, n), 2500) * np.exp(-k * 150) * 0.8
    return x * 0.5


def fire(dur, seed):
    """A kiln or a hearth: a low roar and crackle."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    roar = lowpass(rng.normal(0, 1, n), 260) * (0.7 + 0.3 * AL.smooth_noise(n, 1.5, seed))
    crack = np.zeros(n)
    t = 0.0
    while t < dur - 0.02:
        t += rng.exponential(0.07)
        m = int(0.01 * SR)
        i0 = int(t * SR)
        if i0 + m < n:
            crack[i0:i0 + m] += bandpass(rng.normal(0, 1, m), 1500, 7000) * np.exp(-np.arange(m) / SR * 400) * rng.uniform(0.2, 1)
    return roar * 0.6 + crack * 0.25


def sfx():
    out = np.zeros((N, 2))
    t = np.arange(N) / SR
    # wind: soft by day in the fields, stronger at height (S4) and cold at night (S5)
    level = np.where(t < T_S3, 0.25, np.where(t < T_DONE, 0.0, np.where(t < T_S5, 0.55, 0.8)))
    level = lowpass(level, 3.0)
    for ch in (0, 1):
        w = bandpass(RNG.normal(0, 1, N), 180, 1300) * (0.35 + 0.65 * AL.smooth_noise(N, 0.35, 5 + ch))
        out[:, ch] += w * level * 0.12

    # S1: larks, the kilns, the ox cart, bricks stacked, a far bell
    for k, (tt, pan) in enumerate(((0.1, 0.6), (0.9, -0.5), (1.7, 0.4), (2.3, -0.2))):
        place(out, songbird(RNG.uniform(0.8, 1.3), seed=k), tt, pan=pan, gain=0.05)
    kiln = fire(3.2, 3)
    place(out, np.stack([kiln, np.roll(kiln, 400)], 1) * 0.12, 0.0, pan=-0.3)
    place(out, AL.creak(1.1, 88.0), 0.4, pan=0.2, gain=0.05)
    place(out, AL.creak(0.9, 104.0), 1.9, pan=0.25, gain=0.045)
    for k in range(6):                                                       # hooves on the road
        n = int(0.07 * SR)
        x = lowpass(RNG.normal(0, 1, n), 700) * np.exp(-np.arange(n) / SR * 60)
        place(out, x * 0.06, 0.2 + k * 0.48 + RNG.uniform(-0.03, 0.03), pan=0.2)
    for tt in (0.7, 1.35, 1.55, 2.45):
        place(out, clink(), tt, pan=-0.35, gain=0.06)
    place(out, bell(150.0, 3.5), 0.35, pan=0.3, gain=0.05)

    # S2: the time-lapse: trowels and bricks at speed, the crane, the hours struck
    tt = T_S2 + 0.05
    while tt < T_S3 - 0.1:
        tt += RNG.exponential(1.0 / 9.0)
        r = RNG.random()
        if r < 0.55:
            place(out, trowel(), tt, pan=RNG.uniform(-0.6, 0.6), gain=RNG.uniform(0.04, 0.07))
        elif r < 0.85:
            place(out, clink(), tt, pan=RNG.uniform(-0.6, 0.6), gain=RNG.uniform(0.03, 0.06))
        else:
            place(out, AL.mallet_on_chisel(), tt, pan=RNG.uniform(-0.5, 0.5), gain=0.03)
    for tt, f0 in ((3.4, 95.0), (4.9, 110.0), (6.3, 90.0), (7.7, 105.0)):
        place(out, AL.creak(RNG.uniform(0.7, 1.1), f0), tt, pan=0.15, gain=0.04)
    for tt in (4.6, 7.2):                                                    # the hours go by
        place(out, bell(150.0, 2.5), tt, pan=0.35, gain=0.04)
    crowd = AL.smooth_noise(int(6.0 * SR), 4.0, 77)
    murm = bandpass(RNG.normal(0, 1, len(crowd)), 350, 1800) * np.clip(crowd * 2 - 0.6, 0, 1)
    place(out, np.stack([murm, np.roll(murm, 800)], 1) * 0.05, T_S2)

    # S3: the workshop: the plane on its stroke (every 1.6 s), a quill, the candle's hush
    for j in range(3):
        place(out, plane_stroke(0.7), T_S3 + 0.15 + j * 1.6, pan=-0.2, gain=0.11)
    ct = T_S3 + 0.4
    while ct < T_DONE - 0.2:
        ct += RNG.exponential(0.12)
        m = int(0.03 * SR)
        x = bandpass(RNG.normal(0, 1, m), 3000, 9000) * np.sin(np.pi * np.arange(m) / m)
        place(out, x * RNG.uniform(0.01, 0.025), ct, pan=0.35)
    room = lowpass(RNG.normal(0, 1, int(3.5 * SR)), 400) * 0.02
    place(out, np.stack([room, np.roll(room, 300)], 1), T_S3)

    # S4: the Angelus from the cathedral on the cut, mallets on the platform, swifts
    for j in range(9):
        place(out, bell(147.0 if j % 3 else 110.0, 4.0), T_DONE + j * 0.33, pan=0.45, gain=0.09 if j == 0 else 0.055)
    for tt in (13.0, 13.4, 14.1, 14.6, 15.1):
        place(out, knock(), tt, pan=RNG.uniform(-0.4, 0.3), gain=0.06)
    for k, (tt, pan) in enumerate(((12.9, -0.6), (13.8, 0.5), (14.7, -0.3))):
        place(out, swift(0.6, seed=10 + k), tt, pan=pan, gain=0.05)

    # S5: night: an owl, the lantern's small hiss, otherwise the wind
    place(out, owl(), 16.3, pan=-0.5, gain=0.16)
    place(out, owl(), 18.6, pan=-0.45, gain=0.13)
    hiss = bandpass(RNG.normal(0, 1, int(4.5 * SR)), 2000, 6000) * 0.008
    place(out, np.stack([hiss, hiss], 1), T_S5)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    mus = A.reverb(music(), 2.6, 0.28)
    fx = A.reverb(sfx(), 1.2, 0.12, seed=4)
    mix = AL.master(mus * 0.8 + fx * 0.6)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    A.write_wav(args.out, mix)
    rms = np.sqrt((mix ** 2).mean())
    print(f'wrote {args.out}: peak {np.abs(mix).max():.3f} rms {20 * np.log10(rms):.1f} dBFS')


if __name__ == '__main__':
    main()
