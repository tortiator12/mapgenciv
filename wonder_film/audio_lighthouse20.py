"""Soundtrack for the 20-s game film 'Der Leuchtturm' (numpy/scipy only).

Follows the five shots of film_lighthouse20.py:
  S1 0-3 s     harbour: sea, gulls, the quay crane creaking, an ox cart; a lyre alone
  S2 3-11 s    time-lapse: frame-drum groove, plucked ostinato, chisels by day, crickets at night
  S3 11-13.5 s the statue: groove thins out, winch creaks, A7(b9) with a riser
  S4 13.5-16 s the beacon catches at 14.0 s: whoosh, boom, gong, D major with choir
  S5 16-20 s   night harbour: waves on a hull, creaking timber, a sailor's call, soft lyre

Loudness matches the existing wonder films (mean volume about -24 dB).

  python wonder_film/audio_lighthouse20.py --out build/lighthouse20.wav
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio as A  # noqa: E402
from audio import SR, bandpass, highpass, lowpass, midi_hz, place  # noqa: E402

DUR = 20.0
N = int(SR * DUR)
RNG = np.random.default_rng(2024)
A.RNG = RNG
T_FIRE = 14.0
BAR = A.BAR                    # 2.5 s at 96 BPM
EIGHTH = A.BEAT / 2
T0 = T_FIRE - 4 * BAR          # groove bars: 4.0, 6.5, 9.0, 11.5 -> ignition on 14.0
NIGHT = (6.5, 7.9)             # the short night in the time-lapse


def smooth_noise(n, rate, seed):
    rng = np.random.default_rng(seed)
    k = int(DUR * rate) + 3
    pts = rng.uniform(0, 1, k)
    return np.interp(np.linspace(0, k - 3, n), np.arange(k), pts)


def lyre(m, dur=1.4, gain=1.0):
    """Plucked lyre: brighter, longer-ringing Karplus-Strong plus a soft octave."""
    x = A.pluck(m, dur, bright=0.75, damp=0.997)
    x += 0.25 * A.pluck(m + 12, dur, bright=0.5, damp=0.995)[:len(x)]
    return x * gain


def aulos(m, dur, gain=1.0):
    """Double-reed pipe: a buzzy saw through a nasal formant, with vibrato."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(m)
    vib = 2 * np.pi * (0.006 * f / 5.5) * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.4, 0, 1)
    x = A.saw(f, n, RNG.uniform(0, 6), vib) + 0.5 * A.saw(f * 1.004, n, RNG.uniform(0, 6), vib)
    x = bandpass(x, 500, 1700) + 0.35 * bandpass(x, 2400, 3400)
    return x * A.env_adsr(n, 0.08, 0.2, 0.8, 0.35) * gain * 0.6


def music():
    mus = np.zeros((N, 2))
    t = np.arange(N) / SR
    # drone on D/A throughout, swelling into the time-lapse
    drone = sum(A.saw(midi_hz(m), N, RNG.uniform(0, 6)) * g for m, g in ((38, 0.45), (45, 0.25), (50, 0.12)))
    drone = lowpass(drone, 380) * (0.35 + 0.65 * np.clip((t - 2.5) / 1.5, 0, 1))
    drone *= 1 - 0.8 * np.clip((t - T_FIRE + 0.1) / 0.3, 0, 1)          # hands over to D major
    mus += np.stack([drone, drone], 1) * 0.16

    # S1: a lyre alone (D Dorian), unhurried
    for k, (m, dt) in enumerate(((62, 0.15), (65, 0.55), (67, 0.95), (69, 1.35), (67, 1.95), (65, 2.3), (64, 2.6), (62, 2.95))):
        place(mus, lyre(m, 1.6, 0.55), dt, pan=-0.15 + 0.05 * k)

    # S2..S3: the groove (pickup fill, then four bars into the ignition)
    for k in (3, 2, 1):
        place(mus, A.drum_tek(0.75 - 0.12 * k), T0 - k * EIGHTH, pan=0.2)
    chords = ['Dm', 'Dm', 'Eb', 'A7b9']
    for b, ch in enumerate(chords):
        tb = T0 + b * BAR
        for i, m in enumerate(A.CHORDS[ch]):
            place(mus, A.pad_note(m, BAR + 1.0, bright=900 + 300 * b, a=0.5, r=1.0), tb,
                  pan=(i / (len(A.CHORDS[ch]) - 1) - 0.5) * 0.8, gain=0.2)
        night = b == 1
        pattern = A.OSTINATO_A if ch == 'A7b9' else A.OSTINATO
        for k in range(8):
            m = pattern[k] + (12 if (b >= 2 and k % 2) else 0)
            place(mus, A.pluck(m, 0.8, bright=0.45 + 0.05 * b), tb + k * EIGHTH, pan=0.25 * np.sin(k),
                  gain=(0.22 if night else 0.32) + 0.03 * b)
        if b == 3:        # the statue: the groove thins to a pulse, riser into the fire
            for k in range(4):
                place(mus, A.drum_dum(0.45 + 0.1 * k), tb + k * A.BEAT, pan=-0.1)
            riser = A.noise_riser(BAR, 250, 7000)
            place(mus, np.stack([riser, np.roll(riser, 700)], 1) * 0.12, tb)
            continue
        g = (0.38 if night else 0.6) + 0.05 * b
        for kind, pos in A.MAQSUM:
            place(mus, A.drum_dum(g) if kind == 'D' else A.drum_tek(g), tb + pos * EIGHTH,
                  pan=-0.1 if kind == 'D' else 0.2)
        if b == 2:
            for pos in (2, 5, 7):
                place(mus, A.drum_tek(0.3), tb + pos * EIGHTH, pan=-0.3)
            place(mus, A.boom(1.2, 55.0, 0.3), tb)
    # aulos line over the statue shot
    for m, st, du in ((69, 11.0, 0.9), (70, 11.9, 0.5), (73, 12.4, 0.6), (76, 13.0, 1.0)):
        place(mus, aulos(m, du + 0.3), st, pan=0.2, gain=0.22)

    # S4: the beacon
    place(mus, A.boom(4.5, 36.7, 0.75), T_FIRE)
    place(mus, A.gong(6.0, 92, 0.8), T_FIRE - 0.02, 0.1)
    for i, m in enumerate(A.CHORDS['Dadd9']):
        place(mus, A.pad_note(m, DUR - T_FIRE + 0.2, bright=2600, a=0.12, r=2.5), T_FIRE,
              pan=(i / 6 - 0.5) * 0.8, gain=0.34)
    for i, m in enumerate([62, 66, 69, 74]):
        place(mus, A.choir_note(m, DUR - T_FIRE, a=0.6, r=2.5), T_FIRE, pan=(i - 1.5) * 0.3, gain=0.14)
    # S5: the lyre again, answering the opening in D major
    for k, m in enumerate((62, 66, 69, 74, 73, 69, 66, 62)):
        place(mus, lyre(m, 1.8, 0.22), 16.3 + k * 0.42, pan=0.1)
    return mus


def gull(dur=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 1300 + 900 * np.exp(-t * 9) - 350 * t
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.3 * np.sin(3 * ph)
    x = bandpass(x + 0.3 * RNG.normal(0, 1, n), 700, 5000)
    return x * A.env_adsr(n, 0.02, 0.1, 0.7, 0.2)


def creak(dur=0.6, f0=110.0):
    """Timber / rope under load: a stick-slip rasp at a wandering pitch."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (1 + 0.25 * np.sin(2 * np.pi * RNG.uniform(0.8, 2.0) * t))
    ph = np.cumsum(f) / SR
    pulses = (np.diff(np.floor(ph), prepend=0) > 0).astype(float)
    x = lowpass(pulses, 3000) + 0.2 * bandpass(RNG.normal(0, 1, n), 800, 2500)
    x = bandpass(x, 300, 2500)
    return x * A.env_adsr(n, 0.08, 0.1, 0.8, 0.2)


def voice_call(dur=1.1, m=55):
    """A distant sailor's 'ho-o' call: glide on an 'o' vowel."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(m) * (1 + 0.12 * np.clip(t / 0.25, 0, 1) - 0.1 * np.clip((t - 0.6) / 0.4, 0, 1))
    ph = np.cumsum(f) / SR
    x = sum(np.sin(2 * np.pi * k * ph) / k for k in range(1, 18))
    x = bandpass(x, 350, 600) * 1.0 + bandpass(x, 750, 1000) * 0.5 + bandpass(x, 2300, 2700) * 0.08
    return lowpass(x, 2500) * A.env_adsr(n, 0.08, 0.2, 0.8, 0.35)


def sfx():
    out = np.zeros((N, 2))
    t = np.arange(N) / SR
    near = np.where(t < 3.0, 1.7, np.where(t < 16.0, 0.55, 1.25))
    for ch in (0, 1):
        w = np.cumsum(RNG.normal(0, 1, N))
        w = lowpass(highpass(w, 80), 700)
        w /= np.abs(w).max()
        swell = 0.45 + 0.55 * smooth_noise(N, 0.5, 10 + ch) ** 2
        lap = bandpass(RNG.normal(0, 1, N), 500, 3000) * (smooth_noise(N, 1.3, 20 + ch) ** 4) * 0.3
        out[:, ch] += (w * swell * 0.55 + lap) * near
    wind = bandpass(RNG.normal(0, 1, N), 250, 1100) * (0.3 + 0.7 * smooth_noise(N, 0.3, 5))
    out += np.stack([wind, np.roll(wind, 900)], 1) * 0.08
    out *= 0.35

    # S1: gulls, the crane, the ox cart
    for tt, pan in ((0.3, -0.5), (1.1, 0.4), (1.5, 0.55), (2.4, -0.2), (3.6, 0.3)):
        place(out, gull(RNG.uniform(0.35, 0.6)), tt, pan=pan, gain=0.08)
    place(out, creak(1.4, 95.0), 0.6, pan=0.1, gain=0.05)
    place(out, creak(0.9, 130.0), 2.0, pan=0.15, gain=0.04)
    for k in range(9):          # hooves and a wooden wheel
        n = int(0.06 * SR)
        x = lowpass(RNG.normal(0, 1, n), 900) * np.exp(-np.arange(n) / SR * 70)
        place(out, x * 0.05, 0.2 + k * 0.31 + RNG.uniform(-0.03, 0.03), pan=-0.35)
    rumble = lowpass(RNG.normal(0, 1, int(3.0 * SR)), 180) * 0.05
    place(out, rumble * A.env_adsr(len(rumble), 0.3, 0.1, 1.0, 0.5), 0.0, pan=-0.3)

    # S2/S3: chisels and mallets (dense by day), crickets in the short night
    tt = 3.1
    while tt < 13.4:
        night = NIGHT[0] < tt < NIGHT[1]
        rate = (1.5 if night else 9.0) if tt < 11.0 else 3.0
        tt += RNG.exponential(1.0 / rate)
        if RNG.random() < 0.75:
            n = int(0.07 * SR)
            k = np.arange(n) / SR
            x = np.sin(2 * np.pi * RNG.uniform(2300, 4600) * k) * np.exp(-k * RNG.uniform(60, 110))
            x += bandpass(RNG.normal(0, 1, n), 3000, 9000) * np.exp(-k * 300) * 0.4
            place(out, x * RNG.uniform(0.025, 0.07), tt, pan=RNG.uniform(-0.7, 0.7))
        else:
            n = int(0.12 * SR)
            k = np.arange(n) / SR
            x = np.sin(2 * np.pi * RNG.uniform(150, 260) * k) * np.exp(-k * 40)
            x += lowpass(RNG.normal(0, 1, n), 1500) * np.exp(-k * 90) * 0.5
            place(out, x * RNG.uniform(0.04, 0.09), tt, pan=RNG.uniform(-0.5, 0.5))
    for c in range(4):
        tt = NIGHT[0] - 0.2 + RNG.uniform(0, 0.3)
        f = RNG.uniform(4200, 5200)
        pan = RNG.uniform(-0.8, 0.8)
        while tt < NIGHT[1] + 0.2:
            n = int(0.16 * SR)
            k = np.arange(n) / SR
            gate = lowpass((np.sin(2 * np.pi * 28 * k) > 0.2).astype(float), 400)
            place(out, np.sin(2 * np.pi * f * k) * gate * np.exp(-k * 6) * 0.02, tt, pan=pan)
            tt += RNG.uniform(0.3, 0.6)
    place(out, creak(1.2, 80.0), 11.2, pan=-0.3, gain=0.05)     # the windlass under load
    place(out, creak(1.0, 70.0), 12.4, pan=-0.25, gain=0.045)

    # S4: the beacon catches, then burns (quieter from across the water in S5)
    whoosh = A.noise_riser(0.9, 150, 2500)
    place(out, np.stack([whoosh, whoosh], 1) * 0.22, T_FIRE - 0.5)
    n = int((DUR - T_FIRE) * SR)
    k = np.arange(n) / SR
    fade = np.where(k < 2.0, 1.0, 0.45)
    roar = lowpass(RNG.normal(0, 1, n), 380) * (1 - np.exp(-k * 3)) * 0.3 * fade
    place(out, np.stack([roar, np.roll(roar, 400)], 1) * 0.5, T_FIRE)
    tt = T_FIRE
    while tt < DUR:
        tt += RNG.exponential(0.06)
        m = int(0.012 * SR)
        x = bandpass(RNG.normal(0, 1, m), 1500, 8000) * np.exp(-np.arange(m) / SR * 400)
        place(out, x * RNG.uniform(0.01, 0.04) * (1.0 if tt < 16 else 0.4), tt, pan=RNG.uniform(-0.3, 0.3))

    # S5: the ship - hull creaks, water on the planks, a call from the deck
    for tt, f0 in ((16.2, 90.0), (17.4, 120.0), (18.6, 85.0), (19.3, 105.0)):
        place(out, creak(RNG.uniform(0.6, 1.0), f0), tt, pan=RNG.uniform(-0.2, 0.4), gain=0.04)
    place(out, voice_call(1.2, 55), 17.1, pan=0.25, gain=0.035)
    place(out, voice_call(0.9, 52), 18.5, pan=0.3, gain=0.025)
    return out


def master(x, target_db=-24.0):
    t = np.arange(len(x)) / SR
    fade = np.clip(t / 0.25, 0, 1) * (1 - np.clip((t - (DUR - 0.7)) / 0.7, 0, 1))
    x = highpass(x * fade[:, None], 30)
    x = x - 0.45 * lowpass(x, 110)
    rms = np.sqrt((x ** 2).mean())
    x = x * (10 ** (target_db / 20) / rms)
    return A.limiter(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    mus = A.reverb(music(), 3.0, 0.3)
    fx = A.reverb(sfx(), 1.4, 0.14, seed=4)
    mix = master(mus * 0.75 + fx * 0.6)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    A.write_wav(args.out, mix)
    rms = np.sqrt((mix ** 2).mean())
    print(f'wrote {args.out}: peak {np.abs(mix).max():.3f} rms {20 * np.log10(rms):.1f} dBFS')


if __name__ == '__main__':
    main()
