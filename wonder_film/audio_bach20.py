"""Soundtrack for the game film "J. S. Bachs Kathedrale" (numpy/scipy only).

Follows the five shots of film_bach20.py:
  S1 0-3 s      the Elbe landing, morning: water at the quay, the treadwheel crane,
                chisels on sandstone, a horse cart on the cobbles, gulls; a harpsichord
                plays the Minuet in G from the notebook for Anna Magdalena Bach
  S2 3-10 s     time-lapse: the minuet goes on with strings; sped-up chisels, mallets
                and cranes by day, the hours struck by the bells; at night the torches
                crackle and the watchman blows his horn
  S3 10-13 s    the empty church: the organ builders voice the new pipes one by one
                (single sustained tones in the long reverberation), a few hammer taps
  S4 13-15.5 s  the church is finished: the bells ring out, the crowd murmurs and walks in
  S5 15.5-20 s  the organ: the chorale "Jesus bleibet meine Freude" (BWV 147), its
                triplet melody on a flute stop over a pedal bass, in the church's reverb

Loudness matches the other wonder films (mean volume about -24 dB).

  python wonder_film/audio_bach20.py --out build/bach20.wav
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio as A  # noqa: E402
import audio_colossus20 as AC  # noqa: E402
import audio_copernicus20 as AK  # noqa: E402
import audio_lighthouse20 as AL  # noqa: E402
from audio import SR, bandpass, highpass, lowpass, midi_hz, place  # noqa: E402

DUR = 20.0
N = int(SR * DUR)
RNG = np.random.default_rng(1736)
A.RNG = RNG
AL.RNG = RNG
AC.RNG = RNG
AK.RNG = RNG
T_S2, T_S3, T_S4, T_S5 = 3.0, 10.0, 13.0, 15.5
NIGHT = (5.55, 6.5)                    # film_bach20.S2_LAPSE: the night between the two days


# ------------------------------------------------------------------ instruments
def harpsichord(m, dur=1.2, gain=1.0):
    """Two choirs of plucked strings, 8' and 4': bright, quick to decay."""
    x = A.pluck(m, dur, bright=0.95, damp=0.9955)
    x += 0.45 * A.pluck(m + 12, dur, bright=0.85, damp=0.994)[:len(x)]
    return lowpass(x, 7000) * gain


def pipe(m, dur, harm=(1.0, 0.35, 0.22, 0.1, 0.08, 0.05), chiff=0.25, a=0.05, r=0.3):
    """One organ pipe: a few harmonics, a breathy chiff at the speech, a soft release."""
    f = midi_hz(m)
    n = int((dur + r) * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for h, amp in enumerate(harm, start=1):
        if f * h > 9000:
            break
        x += amp * np.sin(2 * np.pi * f * h * t * (1 + RNG.uniform(-0.0004, 0.0004)) + RNG.uniform(0, 6))
    env = np.clip(t / a, 0, 1) * (1 + 0.15 * np.exp(-t / 0.06))
    env *= np.clip((dur + r - t) / r, 0, 1)
    ch = bandpass(RNG.normal(0, 1, n), min(f * 2.0, 6000), min(f * 5.0, 12000)) * np.exp(-t / 0.035) * chiff
    return (x + ch) * env * 0.3


def organ(m, dur, stop='flute'):
    """A registration: flute 8' + 4' for the melody, principal 8' for the middle,
    pedal 16' + 8' for the bass."""
    if stop == 'flute':
        return pipe(m, dur, (1.0, 0.18, 0.1), chiff=0.35) + 0.45 * pipe(m + 12, dur, (1.0, 0.12), chiff=0.2)
    if stop == 'principal':
        return pipe(m, dur, (1.0, 0.45, 0.3, 0.15, 0.1, 0.06), chiff=0.15) * 0.8
    return pipe(m - 12, dur, (1.0, 0.5, 0.2), chiff=0.1, a=0.08) + 0.6 * pipe(m, dur, (1.0, 0.4, 0.2), chiff=0.1)


def strings(m, dur, gain=1.0):
    return A.pad_note(m, dur, bright=2600, a=0.12, r=0.5, detune=0.05, spread=0.4) * gain


# ------------------------------------------------------------------ music
Q = 0.38                                       # the minuet's quarter
MINUET = [[(74, 0, 1), (67, 1, 0.5), (69, 1.5, 0.5), (71, 2, 0.5), (72, 2.5, 0.5)],      # D | G A B C
          [(74, 0, 1), (67, 1, 1), (67, 2, 1)],                                         # D G G
          [(76, 0, 1), (72, 1, 0.5), (74, 1.5, 0.5), (76, 2, 0.5), (78, 2.5, 0.5)],     # E | C D E F#
          [(79, 0, 1), (67, 1, 1), (67, 2, 1)],                                         # G G G
          [(72, 0, 1), (74, 1, 0.5), (72, 1.5, 0.5), (71, 2, 0.5), (69, 2.5, 0.5)],     # C | D C B A
          [(71, 0, 1), (72, 1, 0.5), (71, 1.5, 0.5), (69, 2, 0.5), (67, 2.5, 0.5)],     # B | C B A G
          [(66, 0, 1), (67, 1, 0.5), (69, 1.5, 0.5), (71, 2, 0.5), (67, 2.5, 0.5)],     # F# | G A B G
          [(69, 0, 3)]]                                                                  # A
MINUET_BASS = [[55, 57], [59], [60], [59], [57], [55], [50], [54]]       # G A | B | C | B | A | G | D | F#
MINUET_CHORDS = [(55, 59, 62), (55, 59, 62), (60, 64, 67), (55, 59, 62), (57, 60, 64), (55, 59, 62), (50, 57, 62), (50, 54, 57)]
# "Jesus bleibet meine Freude": the triplet melody (9/8), bass and middle voice per beat
JESU = [67, 69, 71, 74, 72, 72, 76, 74, 74, 79, 78, 79, 74, 71, 67, 69, 71, 72,
        74, 76, 74, 72, 71, 69, 71, 67, 66, 67, 69, 62, 66, 69, 72, 71, 69, 71]
JESU_BASS = [43, 42, 40, 47, 43, 45, 47, 48, 50, 43, 50, 43]            # one per dotted quarter
JESU_MID = [(59, 62), (57, 62), (55, 59), (55, 62), (55, 59), (57, 60), (55, 62), (57, 60), (54, 57), (55, 59), (54, 60), (55, 62)]
E3 = 0.27                                      # a triplet eighth of the chorale


def music():
    mus = np.zeros((N, 2))
    # S1 + S2: the minuet on the harpsichord; strings join in the time-lapse
    t0 = 0.15
    bars = 0
    tb = t0
    while tb < T_S3 - 0.6:
        b = bars % 8
        q = Q if tb < T_S2 else 0.33                  # the time-lapse quickens the dance
        night = NIGHT[0] - 0.2 < tb < NIGHT[1]
        g = 0.85 if not night else 0.45
        for m, st, du in MINUET[b]:
            place(mus, harpsichord(m, du * q + 0.5), tb + st * q, pan=0.15, gain=g)
        for k, m in enumerate(MINUET_BASS[b]):
            place(mus, harpsichord(m - 12, 3 * q / len(MINUET_BASS[b]) + 0.4), tb + k * 3 * q / len(MINUET_BASS[b]), pan=-0.2, gain=g * 0.8)
        if tb >= T_S2:
            for i, m in enumerate(MINUET_CHORDS[b]):
                place(mus, strings(m, 3 * q + 0.3, gain=0.24 if not night else 0.12), tb, pan=(i - 1) * 0.35)
        tb += 3 * q
        bars += 1
    # S3: the pipes voiced one by one in the empty church (no music besides)
    for k, (m, st, du) in enumerate(((67, 10.2, 0.7), (74, 10.9, 0.5), (79, 11.4, 0.6), (71, 11.95, 0.45), (62, 12.4, 0.5))):
        place(mus, pipe(m, du, (1.0, 0.4, 0.25, 0.1), chiff=0.4), st, pan=0.3 - 0.12 * k, gain=0.3)
    # S5: the chorale on the organ
    for k, m in enumerate(JESU):
        st = T_S5 + 0.05 + k * E3
        if st > DUR - 0.2:
            break
        place(mus, organ(m, E3 * 0.92, 'flute'), st, pan=0.15, gain=0.3)
    for k, m in enumerate(JESU_BASS):
        st = T_S5 + 0.05 + k * 3 * E3
        if st > DUR - 0.3:
            break
        place(mus, organ(m, 3 * E3 * 0.95, 'pedal'), st, pan=-0.1, gain=0.26)
        for i, mm in enumerate(JESU_MID[k]):
            place(mus, organ(mm, 3 * E3 * 0.95, 'principal'), st, pan=-0.3 + 0.3 * i, gain=0.12)
    return mus


# ------------------------------------------------------------------ sound effects
def chisel():
    """A mason's chisel struck on sandstone: a bright tick and a spray of grit."""
    n = int(0.2 * SR)
    k = np.arange(n) / SR
    x = np.sin(2 * np.pi * RNG.uniform(2800, 4200) * k) * np.exp(-k * 90)
    x += bandpass(RNG.normal(0, 1, n), 2000, 9000) * np.exp(-k * 60) * 0.7
    x += lowpass(RNG.normal(0, 1, n), 900) * np.exp(-k * 140) * 0.8
    return x * 0.35


def hooves(dur, rate=1.7):
    """A horse walking on cobbles: four beats to the stride."""
    n = int(dur * SR)
    out = np.zeros(n)
    t = 0.0
    k = 0
    while t < dur - 0.05:
        m = int(0.03 * SR)
        i0 = int(t * SR)
        out[i0:i0 + m] += bandpass(RNG.normal(0, 1, m), 700, 3000) * np.exp(-np.arange(m) / SR * 150) * (1.0 if k % 2 else 0.7)
        t += (0.23 if k % 2 else 0.35) / rate * 1.7
        k += 1
    return out * 0.5


def horn_call():
    """The night watchman's horn: two long, wavering notes."""
    out = np.zeros(int(1.8 * SR))
    for st, du, f in ((0.0, 0.7, 233.0), (0.8, 0.9, 311.0)):
        n = int(du * SR)
        t = np.arange(n) / SR
        ph = 2 * np.pi * np.cumsum(f * (1 + 0.004 * np.sin(2 * np.pi * 5 * t))) / SR
        x = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
        x *= np.clip(t / 0.08, 0, 1) * np.clip((du - t) / 0.15, 0, 1)
        out[int(st * SR):int(st * SR) + n] += lowpass(x, 1800)
    return out * 0.2


def sfx():
    out = np.zeros((N, 2))
    t = np.arange(N) / SR
    # water at the quay (S1), the wind over the roofs (S2, S4)
    water = np.zeros(N)
    w = bandpass(RNG.normal(0, 1, N), 250, 1800) * (0.3 + 0.7 * AL.smooth_noise(N, 1.4, 12) ** 3)
    water = w * np.clip((T_S2 - t) / 0.3, 0, 1)
    out += np.stack([water, np.roll(water, 700)], 1) * 0.07
    wind = bandpass(RNG.normal(0, 1, N), 200, 1200) * (0.4 + 0.6 * AL.smooth_noise(N, 0.4, 13))
    level = np.where((t > T_S2) & (t < T_S3), 0.6, np.where((t > T_S4) & (t < T_S5), 0.4, 0.0))
    out += np.stack([wind * level, np.roll(wind * level, 900)], 1) * 0.05

    # S1: the crane, chisels, the cart, gulls, a bargeman's call
    place(out, AL.creak(1.2, 92.0), 0.3, pan=-0.2, gain=0.06)
    place(out, AL.creak(0.9, 118.0), 1.8, pan=-0.2, gain=0.05)
    for tt in (0.25, 0.62, 0.98, 1.4, 1.75, 2.2, 2.6):
        place(out, chisel(), tt + RNG.uniform(-0.04, 0.04), pan=RNG.uniform(-0.5, 0.1), gain=0.06)
    place(out, hooves(3.0), 0.0, pan=0.25, gain=0.1)
    place(out, AL.creak(2.5, 70.0), 0.2, pan=0.3, gain=0.025)              # the cart's axle
    for tt, pan in ((0.4, 0.6), (1.9, -0.5)):
        place(out, AL.gull(RNG.uniform(0.4, 0.6)), tt, pan=pan, gain=0.05)
    place(out, AL.voice_call(0.8, 52), 1.2, pan=0.4, gain=0.03)

    # S2: sped-up work by day, the hours struck, torches and the watchman at night
    tt = T_S2 + 0.05
    while tt < T_S3 - 0.1:
        night = NIGHT[0] < tt < NIGHT[1]
        tt += RNG.exponential(1.0 / (1.5 if night else 10.0))
        r = RNG.random()
        if night:
            continue
        if r < 0.6:
            place(out, chisel(), tt, pan=RNG.uniform(-0.6, 0.6), gain=RNG.uniform(0.03, 0.06))
        elif r < 0.85:
            place(out, AL.mallet_on_chisel(), tt, pan=RNG.uniform(-0.6, 0.6), gain=0.035)
        else:
            place(out, AL.creak(RNG.uniform(0.5, 0.9), RNG.uniform(85, 120)), tt, pan=RNG.uniform(-0.4, 0.4), gain=0.03)
    for tt in (4.2, 8.3):                                                   # the hours go by
        place(out, AK.bell(185.0, 2.5), tt, pan=0.3, gain=0.05)
    n = int((NIGHT[1] - NIGHT[0] + 0.4) * SR)
    k = np.arange(n) / SR
    fire = AK.fire(n / SR, 31) * np.sin(np.pi * k / k[-1])
    place(out, np.stack([fire, np.roll(fire, 400)], 1) * 0.15, NIGHT[0] - 0.2)
    place(out, horn_call(), NIGHT[0] + 0.05, pan=-0.4, gain=0.12)

    # S3: the empty church: hammer taps on the case, the reverberant hush
    for tt in (10.5, 11.2, 12.1, 12.7):
        place(out, AK.knock(), tt, pan=0.3, gain=0.05)
    hush = lowpass(RNG.normal(0, 1, int(3.0 * SR)), 300) * 0.015
    place(out, np.stack([hush, np.roll(hush, 500)], 1), T_S3)

    # S4: the bells ring out (four of them, in rounds), the crowd, feet on the cobbles
    bells = (147.0, 165.0, 185.0, 220.0)
    tt = T_S4 + 0.02
    j = 0
    while tt < T_S5 + 1.8:
        f = bells[(3 - j) % 4]
        g = (0.45 if j == 0 else 0.32) if tt < T_S5 else 0.32 * max(0.0, 1.0 - (tt - T_S5) / 1.8)
        place(out, AK.bell(f, 4.0), tt, pan=0.35 - 0.2 * (j % 4), gain=g)
        tt += 0.42
        j += 1
    crowd = AC.murmur(3.0, 7)
    place(out, np.stack([crowd, np.roll(crowd, 1100)], 1) * 0.5, T_S4)
    place(out, hooves(2.5, rate=2.4), T_S4, pan=-0.3, gain=0.05)             # footsteps and a carriage

    # S5: the full church: a cough, the rustle of the congregation under the organ
    rustle = bandpass(RNG.normal(0, 1, int(4.5 * SR)), 1500, 6000) * 0.006
    place(out, np.stack([rustle, np.roll(rustle, 800)], 1), T_S5)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    mus = music()
    t = np.arange(N) / SR
    church = (t > T_S3 - 0.05)[:, None]                                    # the long reverberation inside
    mus = np.where(church, A.reverb(mus, 4.5, 0.42, seed=5), A.reverb(mus, 1.6, 0.18))
    fx = A.reverb(sfx(), 1.4, 0.14, seed=4)
    mix = AL.master(mus * 0.8 + fx * 0.6)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    A.write_wav(args.out, mix)
    rms = np.sqrt((mix ** 2).mean())
    print(f'wrote {args.out}: peak {np.abs(mix).max():.3f} rms {20 * np.log10(rms):.1f} dBFS')


if __name__ == '__main__':
    main()
