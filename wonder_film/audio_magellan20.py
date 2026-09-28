"""Soundtrack for the game film "Magellans Expedition" (numpy/scipy only).

Follows the five shots of film_magellan20.py:
  S1 0-3 s      the Arenal in the morning: gulls, water at the bank, ropes creaking,
                an ox cart, the murmur of merchants and soldiers; a shawm and a
                tabor play a dance in D Dorian
  S2 3-9 s      time-lapse: scrapers on the hull, caulking mallets on their irons,
                the capstans' pawls, creaking tackles; the dance quickens
  S3 9-12 s     on deck: a cask lowered through the blocks, voices, the halyard
                squeals as the flag goes up; a drum roll and a shawm call at the top
  S4 12-15 s    the departure: shawms, sackbut and drums in D major, the bells of
                the cathedral, the crowd cheering, the ships' wash
  S5 15-20 s    dawn at Sanlucar, 1522: the surf, gulls, the salute gun and its echo,
                then the church bells and a quiet choir (a psalm tone)

Loudness matches the other wonder films (mean volume about -24 dB).

  python wonder_film/audio_magellan20.py --out build/magellan20.wav
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
RNG = np.random.default_rng(1519)
A.RNG = RNG
AL.RNG = RNG
AC.RNG = RNG
AK.RNG = RNG
T_S2, T_S3, T_S4, T_S5 = 3.0, 9.0, 12.0, 15.0
T_GUN = 16.4


# ------------------------------------------------------------------ instruments
def shawm(m, dur, gain=1.0):
    """A shawm: a loud double reed, buzzy and nasal, with a little vibrato."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(m)
    vib = 2 * np.pi * (0.005 * f / 5.8) * np.sin(2 * np.pi * 5.8 * t) * np.clip(t / 0.25, 0, 1)
    x = A.saw(f, n, RNG.uniform(0, 6), vib) + 0.6 * A.saw(f * 1.003, n, RNG.uniform(0, 6), vib)
    x = bandpass(x, 700, 2600) + 0.5 * bandpass(x, 2800, 4200) + 0.2 * lowpass(x, 500)
    return x * A.env_adsr(n, 0.03, 0.1, 0.85, 0.08) * gain * 0.45


def sackbut(m, dur, gain=1.0):
    """A sackbut (the early trombone): mellow, the brightness opening with the attack."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(m)
    x = A.saw(f, n, RNG.uniform(0, 6))
    y = lowpass(x, 1400) * 0.6 + bandpass(x, 300, 900) * 0.6
    y *= (0.8 + 0.4 * np.exp(-t / 0.15))
    return y * A.env_adsr(n, 0.05, 0.15, 0.8, 0.15) * gain * 0.5


def chant(m, dur, gain=1.0):
    return A.choir_note(m, dur, a=0.35, r=0.5) * gain


# ------------------------------------------------------------------ music
Q = 0.4
TUNE_A = [[(69, 0, 1), (74, 1, 1), (74, 2, 1)], [(76, 0, 1), (77, 1, 1), (76, 2, 1)], [(74, 0, 1), (72, 1, 1), (74, 2, 1)],
          [(69, 0, 3)], [(77, 0, 1), (79, 1, 1), (81, 2, 1)], [(79, 0, 1), (77, 1, 1), (76, 2, 1)], [(77, 0, 1), (76, 1, 1), (74, 2, 1)],
          [(73, 0, 3)]]
DRONE = [50, 50, 50, 45, 50, 50, 46, 45]                  # D .. A, Bb-A (the Phrygian cadence)


def music():
    mus = np.zeros((N, 2))
    # S1 + S2: the dance on shawm and tabor over a sackbut drone; faster in the time-lapse
    tb = 0.1
    bar = 0
    while tb < T_S3 - 0.3:
        q = Q if tb < T_S2 else 0.3
        b = bar % 8
        for m, st, du in TUNE_A[b]:
            place(mus, shawm(m, du * q * 0.95 + 0.04), tb + st * q, pan=0.2, gain=0.55 if tb < T_S2 else 0.6)
        place(mus, sackbut(DRONE[b], 3 * q), tb, pan=-0.25, gain=0.5)
        for pos, g in ((0, 0.55), (1, 0.3), (2, 0.4), (2.5, 0.25)):
            place(mus, AK.tabor(g), tb + pos * q, pan=0.3)
        tb += 3 * q
        bar += 1
    # S3: a drum roll as the flag goes up, a shawm call at the top
    t = T_S3 + 0.3
    while t < T_S4 - 0.6:
        place(mus, AK.tabor(0.12 + 0.3 * (t - T_S3) / 3.0), t, pan=0.2)
        t += 0.07
    for m, st, du in ((74, 11.3, 0.25), (74, 11.55, 0.25), (81, 11.8, 0.45)):
        place(mus, shawm(m, du), st, pan=0.1, gain=0.7)
    # S4: the departure in D major, all together
    tune = [[(74, 0, 1), (78, 1, 1), (81, 2, 1)], [(79, 0, 1), (78, 1, 1), (76, 2, 1)], [(78, 0, 1), (76, 1, 1), (74, 2, 1)],
            [(73, 0, 1), (74, 1, 2)]]
    tb = T_S4
    for b in range(4):
        for m, st, du in tune[b]:
            place(mus, shawm(m, du * 0.26 + 0.03), tb + st * 0.28, pan=0.25, gain=0.6)
            place(mus, shawm(m - 5 if m - 5 > 62 else m + 7, du * 0.26 + 0.03), tb + st * 0.28, pan=-0.2, gain=0.35)
        for m in (50, 57):
            place(mus, sackbut(m + (0 if b < 3 else -5 if m == 57 else 7), 0.84), tb, pan=-0.3, gain=0.45)
        for pos in (0, 1, 2, 2.5):
            place(mus, AK.tabor(0.5), tb + pos * 0.28, pan=0.3)
        place(mus, A.drum_dum(0.5), tb, pan=-0.1)
        tb += 0.84
    place(mus, sackbut(50, 1.2), tb, pan=-0.3, gain=0.5)
    place(mus, shawm(74, 1.1), tb, pan=0.2, gain=0.55)
    # S5: after the salute, a psalm tone sung quietly: intonation, the reciting note, the cadence
    notes = [(65, 0.0, 0.5), (67, 0.5, 0.5), (69, 1.0, 1.1), (69, 2.1, 0.5), (70, 2.6, 0.5), (69, 3.1, 0.6), (67, 3.7, 0.5),
             (65, 4.2, 0.9)]
    for m, st, du in notes:
        for dm, g, pan in ((0, 0.3, 0.1), (-12, 0.22, -0.15)):
            place(mus, chant(m + dm, du + 0.25), 17.0 + st * 0.72, pan=pan, gain=g)
    return mus


# ------------------------------------------------------------------ sound effects
def scrape():
    """A scraper on the ship's bottom: a gritty, rasping stroke."""
    n = int(0.45 * SR)
    k = np.arange(n) / SR
    grit = (RNG.random(n) < 0.02).astype(float) * RNG.uniform(0.3, 1.0, n)
    x = bandpass(RNG.normal(0, 1, n) * 0.4 + grit, 900, 6000) * np.sin(np.pi * k / k[-1]) ** 0.6
    return x * 0.35


def pawl():
    """The capstan's pawl dropping into its rack."""
    n = int(0.08 * SR)
    k = np.arange(n) / SR
    return (np.sin(2 * np.pi * 2300 * k) * np.exp(-k * 90) + bandpass(RNG.normal(0, 1, n), 2000, 7000) * np.exp(-k * 150)) * 0.25


def gun():
    """The salute: a heavy report and its roll off the shore."""
    n = int(3.0 * SR)
    k = np.arange(n) / SR
    b = A.boom(3.0, 42.0, 1.0)
    x = np.zeros(n)
    x[:min(n, len(b))] = b[:n]
    crack = lowpass(RNG.normal(0, 1, n), 2500) * np.exp(-k * 25) * 0.9
    roll = lowpass(RNG.normal(0, 1, n), 400) * np.exp(-k * 1.6) * 0.35
    y = x * 0.8 + crack + roll
    echo = np.zeros(n)
    d = int(0.55 * SR)
    echo[d:] = lowpass(y[:-d], 900) * 0.3
    return (y + echo) * 0.6


def sfx():
    out = np.zeros((N, 2))
    t = np.arange(N) / SR
    # water: lapping at the bank (S1-S3), the ships' wash (S4), the surf at Sanlucar (S5)
    lap = bandpass(RNG.normal(0, 1, N), 300, 2000) * (0.3 + 0.7 * AL.smooth_noise(N, 1.2, 3) ** 3)
    surf = lowpass(RNG.normal(0, 1, N), 900) * (0.25 + 0.75 * np.clip(np.sin(2 * np.pi * t / 5.5) * 1.3, 0, 1) ** 2)
    level = np.where(t < T_S4, 0.6, np.where(t < T_S5, 1.0, 0.0))
    out += np.stack([lap * level, np.roll(lap * level, 600)], 1) * 0.07
    out += np.stack([surf * (t >= T_S5), np.roll(surf * (t >= T_S5), 900)], 1) * 0.12
    # S1: gulls, creaking ropes, a cart, the crowd
    for tt, pan in ((0.3, 0.6), (1.4, -0.4), (2.4, 0.3)):
        place(out, AL.gull(RNG.uniform(0.4, 0.6)), tt, pan=pan, gain=0.07)
    for tt, f0 in ((0.2, 85.0), (1.1, 110.0), (2.2, 95.0)):
        place(out, AL.creak(RNG.uniform(0.6, 1.0), f0), tt, pan=-0.3, gain=0.05)
    place(out, AL.creak(2.8, 72.0), 0.1, pan=0.2, gain=0.03)
    crowd = AC.murmur(3.2, 5)
    place(out, np.stack([crowd, np.roll(crowd, 900)], 1) * 0.3, 0.0)
    # S2: scraping, caulking mallets, capstans, tackles at time-lapse speed
    tt = T_S2 + 0.05
    while tt < T_S3 - 0.1:
        tt += RNG.exponential(1.0 / 10.0)
        r = RNG.random()
        if tt < 5.8 and r < 0.45:
            place(out, scrape(), tt, pan=RNG.uniform(-0.5, 0.3), gain=RNG.uniform(0.04, 0.07))
        elif r < 0.75:
            place(out, AL.mallet_on_chisel(), tt, pan=RNG.uniform(-0.6, 0.6), gain=0.04)
        elif r < 0.88:
            place(out, pawl(), tt, pan=0.4, gain=0.05)
        else:
            place(out, AL.creak(RNG.uniform(0.4, 0.8), RNG.uniform(80, 130)), tt, pan=RNG.uniform(-0.4, 0.4), gain=0.03)
    for tt, pan in ((4.0, -0.5), (6.6, 0.5), (8.1, -0.2)):
        place(out, AL.gull(RNG.uniform(0.35, 0.55)), tt, pan=pan, gain=0.05)
    # S3: the cask through the blocks, a thud in the hold, the halyard, voices
    place(out, AL.creak(2.4, 150.0), T_S3 + 0.1, pan=0.2, gain=0.05)
    n = int(0.3 * SR)
    k = np.arange(n) / SR
    place(out, lowpass(RNG.normal(0, 1, n), 300) * np.exp(-k * 25) * 0.6, 11.6, pan=0.1, gain=0.12)
    for tt in np.arange(T_S3 + 0.3, 11.7, 0.18):                         # the halyard squealing through its sheave
        place(out, AL.creak(0.12, 420.0 + 30.0 * RNG.random()), tt, pan=-0.1, gain=0.02)
    place(out, AL.voice_call(0.8, 50), 9.6, pan=0.3, gain=0.04)
    place(out, AL.voice_call(0.6, 55), 10.8, pan=-0.2, gain=0.035)
    # S4: the crowd cheering, the cathedral's bells, the wash
    cheer = AC.murmur(3.2, 9) * np.linspace(0.6, 1.0, int(3.2 * SR))
    place(out, np.stack([cheer, np.roll(cheer, 1300)], 1) * 0.55, T_S4)
    for j in range(7):
        place(out, AK.bell((196.0, 247.0, 165.0)[j % 3], 3.0), T_S4 + 0.1 + j * 0.42, pan=0.5, gain=0.12)
    # S5: gulls, the salute gun, then the town's bells
    for tt, pan in ((15.3, -0.6), (18.6, 0.4)):
        place(out, AL.gull(RNG.uniform(0.4, 0.6)), tt, pan=pan, gain=0.05)
    place(out, gun(), T_GUN, pan=-0.2, gain=0.8)
    for j in range(5):
        place(out, AK.bell(220.0 if j % 2 else 185.0, 3.0), 17.4 + j * 0.62, pan=0.45, gain=0.09)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    mus = A.reverb(music(), 1.8, 0.2)
    fx = A.reverb(sfx(), 1.2, 0.12, seed=4)
    mix = AL.master(mus * 0.75 + fx * 0.65)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    A.write_wav(args.out, mix)
    rms = np.sqrt((mix ** 2).mean())
    print(f'wrote {args.out}: peak {np.abs(mix).max():.3f} rms {20 * np.log10(rms):.1f} dBFS')


if __name__ == '__main__':
    main()
