"""Soundtrack for the game film 'Koloss von Rhodos' (numpy/scipy only).

Follows the five shots of film_colossus20.py:
  S1 0-3 s      harbour morning: sea, gulls, the treadwheel crane creaking, copper ingots
                set down, the smith's hammer on the anvil, an ox cart, oars; a lyre alone
  S2 3-8 s      time-lapse: frame drum and plucked ostinato (A Dorian), sped-up hammering
                on bronze and shovelling by day, crickets and the furnaces' roar at night
  S3 8-11.5 s   the top of the mound: bellows breathing, furnace crackle, rivets struck
                on the bronze in real time; the aulos over a thinner groove
  S4 11.5-15 s  the mound carried away: shovels and baskets, a crowd growing, a riser into
                the cadence on the cut (15.0 s): A major, choir, gong
  S5 15-20 s    sunset: the galley's oars on the stroke (every 3.2 s), the stroke-caller,
                the harbour's murmur, the altar fire, gulls; lyre and aulos in A major

Loudness matches the other wonder films (mean volume about -24 dB).

  python wonder_film/audio_colossus20.py --out build/colossus20.wav
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
RNG = np.random.default_rng(2303)
A.RNG = RNG
AL.RNG = RNG
BAR = A.BAR                      # 2.5 s at 96 BPM
EIGHTH = A.BEAT / 2
T_DONE = 15.0                    # the cut to the finished Colossus: the cadence lands here
T0 = T_DONE - 4 * BAR            # groove bars 5.0, 7.5, 10.0, 12.5
NIGHT = (6.1, 6.95)              # the short night in the S2 time-lapse
GALLEY_T = 3.2                   # film_colossus20.GALLEY_T: a catch every 3.2 s (at 16.0, 19.2 s)

CH = {'Am': [45, 52, 57, 60, 64], 'G': [43, 50, 55, 59, 62], 'D': [38, 45, 50, 54, 57],
      'E7': [40, 47, 52, 56, 62], 'A': [45, 52, 57, 61, 64, 69], 'Aadd9': [45, 52, 57, 59, 61, 64, 69]}
OST = [57, 59, 60, 62, 64, 62, 60, 59]          # A Dorian
OST_E = [52, 53, 56, 59, 62, 59, 56, 53]        # over the dominant


def music():
    mus = np.zeros((N, 2))
    t = np.arange(N) / SR
    drone = sum(A.saw(midi_hz(m), N, RNG.uniform(0, 6)) * g for m, g in ((33, 0.45), (40, 0.25), (45, 0.12)))
    drone = lowpass(drone, 360) * (0.3 + 0.7 * np.clip((t - 2.6) / 1.4, 0, 1))
    drone *= 1 - 0.85 * np.clip((t - T_DONE + 0.1) / 0.3, 0, 1)
    mus += np.stack([drone, drone], 1) * 0.15
    # S1: the lyre alone, A Dorian, unhurried
    for k, (m, dt) in enumerate(((64, 0.2), (62, 0.6), (64, 0.95), (66, 1.3), (67, 1.75), (66, 2.1), (64, 2.45), (62, 2.8))):
        place(mus, AL.lyre(m, 1.6, 0.5), dt, pan=-0.2 + 0.05 * k)
    # S2..S4: the groove, four bars into the cadence (pickup fill before)
    for k in (3, 2, 1):
        place(mus, A.drum_tek(0.7 - 0.12 * k), T0 - k * EIGHTH, pan=0.2)
    chords = ['Am', 'G', 'D', 'E7']
    for b, ch in enumerate(chords):
        tb = T0 + b * BAR
        for i, m in enumerate(CH[ch]):
            place(mus, A.pad_note(m, BAR + 1.0, bright=900 + 250 * b, a=0.5, r=1.0), tb,
                  pan=(i / (len(CH[ch]) - 1) - 0.5) * 0.8, gain=0.19)
        night = NIGHT[0] - 0.3 < tb < NIGHT[1]
        pat = OST_E if ch == 'E7' else OST
        for k in range(8):
            m = pat[k] + (12 if (b >= 2 and k % 2) else 0)
            place(mus, A.pluck(m, 0.8, bright=0.45 + 0.05 * b), tb + k * EIGHTH, pan=0.25 * np.sin(k),
                  gain=(0.2 if night else 0.3) + 0.03 * b)
        g = (0.35 if night else 0.56) + 0.05 * b
        if b == 2:                                  # S3 (real time): the groove thins to dum-tek
            for kind, pos in (('D', 0), ('T', 3), ('D', 4), ('T', 7)):
                place(mus, A.drum_dum(g * 0.7) if kind == 'D' else A.drum_tek(g * 0.7), tb + pos * EIGHTH,
                      pan=-0.1 if kind == 'D' else 0.2)
            continue
        for kind, pos in A.MAQSUM:
            place(mus, A.drum_dum(g) if kind == 'D' else A.drum_tek(g), tb + pos * EIGHTH, pan=-0.1 if kind == 'D' else 0.2)
        if b == 3:                                  # the reveal: riser into the cadence
            for pos in (2, 5, 6, 7):
                place(mus, A.drum_tek(0.32), tb + pos * EIGHTH, pan=-0.3)
            riser = A.noise_riser(BAR, 250, 7000)
            place(mus, np.stack([riser, np.roll(riser, 700)], 1) * 0.1, tb)
    # the aulos over the top of the mound (S3)
    for m, st, du in ((69, 8.4, 0.8), (71, 9.2, 0.5), (72, 9.7, 0.6), (74, 10.3, 0.5), (72, 10.8, 0.9)):
        place(mus, AL.aulos(m, du + 0.3), st, pan=0.2, gain=0.2)
    # the cadence: A major, choir, gong
    place(mus, A.boom(3.5, 36.7, 0.55), T_DONE)
    place(mus, A.gong(6.0, 110, 0.55), T_DONE - 0.02, 0.1)
    for i, m in enumerate(CH['Aadd9']):
        place(mus, A.pad_note(m, DUR - T_DONE + 0.2, bright=2400, a=0.15, r=2.5), T_DONE, pan=(i / 6 - 0.5) * 0.8, gain=0.3)
    for i, m in enumerate([57, 61, 64, 69]):
        place(mus, A.choir_note(m, DUR - T_DONE, a=0.7, r=2.5), T_DONE, pan=(i - 1.5) * 0.3, gain=0.13)
    # S5: lyre and aulos answer the opening in A major
    for k, m in enumerate((64, 66, 69, 71, 73, 71, 69, 66)):
        place(mus, AL.lyre(m, 1.8, 0.2), 15.6 + k * 0.45, pan=0.1)
    for m, st, du in ((76, 17.4, 1.0), (73, 18.5, 1.2)):
        place(mus, AL.aulos(m, du + 0.3), st, pan=-0.15, gain=0.12)
    return mus


# ------------------------------------------------------------------ sound effects
def bronze_hit(big=False):
    """A hammer on bronze sheet: inharmonic plate modes over a dull thud."""
    n = int((0.7 if big else 0.4) * SR)
    k = np.arange(n) / SR
    f0 = RNG.uniform(380, 620) * (0.7 if big else 1.0)
    x = np.zeros(n)
    for i, r in enumerate((1.0, 1.59, 2.14, 2.65, 3.16, 3.93, 4.6)):
        x += np.sin(2 * np.pi * f0 * r * k + RNG.uniform(0, 6)) * np.exp(-k * (6 + 5 * i)) / (1 + 0.5 * i)
    x += 0.8 * lowpass(RNG.normal(0, 1, n), 900) * np.exp(-k * 90)
    return x * 0.6


def anvil():
    n = int(0.5 * SR)
    k = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * k) * np.exp(-k * d) for f, d in ((1850, 9), (2710, 12), (4220, 18), (5630, 25)))
    x += 0.6 * lowpass(RNG.normal(0, 1, n), 1500) * np.exp(-k * 120)
    return x * 0.35


def clank():
    """Copper ingots set down on a pile: a duller clack."""
    n = int(0.25 * SR)
    k = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * RNG.uniform(700, 1600) * k) * np.exp(-k * RNG.uniform(25, 45)) for _ in range(3))
    x += lowpass(RNG.normal(0, 1, n), 2000) * np.exp(-k * 80)
    return x * 0.4


def shovel():
    n = int(0.35 * SR)
    k = np.arange(n) / SR
    scrape = bandpass(RNG.normal(0, 1, n), 1200, 5000) * np.exp(-((k - 0.1) / 0.07) ** 2)
    thud = lowpass(RNG.normal(0, 1, n), 500) * np.exp(-((k - 0.24) / 0.03) ** 2) * 1.5
    return (scrape * 0.6 + thud) * 0.5


def bellows(dur=0.6):
    """The breath of a bag bellows: filtered air, a leather creak at the turn."""
    n = int(dur * SR)
    k = np.arange(n) / SR
    env = np.sin(np.pi * np.clip(k / dur, 0, 1)) ** 1.5
    x = bandpass(RNG.normal(0, 1, n), 180, 1100) * env
    x += 0.3 * AL.creak(dur, 140.0)[:n] * np.exp(-k * 6)
    return x


def murmur(dur, seed):
    """A crowd's murmur: vowel formants on noise, gated at syllable rate."""
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    out = np.zeros(n)
    for v in range(8):
        f1, f2 = rng.uniform(350, 750), rng.uniform(900, 2000)
        src = rng.normal(0, 1, n)
        voc = bandpass(src, f1 * 0.85, f1 * 1.15) + 0.5 * bandpass(src, f2 * 0.9, f2 * 1.1)
        gate = np.clip(AL.smooth_noise(n, rng.uniform(3.5, 6.0), seed * 10 + v) * 2.2 - 0.9, 0, 1)
        out += voc * gate
    return lowpass(out, 2600) * 0.3


def sfx():
    out = np.zeros((N, 2))
    t = np.arange(N) / SR
    near = np.where(t < 3.0, 1.5, np.where(t < 15.0, 0.5, 1.4))
    for ch in (0, 1):
        w = np.cumsum(RNG.normal(0, 1, N))
        w = lowpass(highpass(w, 80), 700)
        w /= np.abs(w).max()
        swell = 0.45 + 0.55 * AL.smooth_noise(N, 0.5, 10 + ch) ** 2
        lap = bandpass(RNG.normal(0, 1, N), 500, 3000) * (AL.smooth_noise(N, 1.3, 20 + ch) ** 4) * 0.3
        out[:, ch] += (w * swell * 0.55 + lap) * near
    top = np.where((t > 8.0) & (t < 11.5), 1.6, 1.0)            # wind is stronger on top of the mound
    wind = bandpass(RNG.normal(0, 1, N), 250, 1100) * (0.3 + 0.7 * AL.smooth_noise(N, 0.3, 5)) * top
    out += np.stack([wind, np.roll(wind, 900)], 1) * 0.08
    out *= 0.35

    # S1: gulls, the crane, ingots, the smith, an ox cart, oars
    for tt, pan in ((0.25, 0.5), (0.9, -0.4), (1.6, 0.6), (2.3, 0.2)):
        place(out, AL.gull(RNG.uniform(0.35, 0.6)), tt, pan=pan, gain=0.08)
    place(out, AL.creak(1.3, 95.0), 0.5, pan=0.25, gain=0.05)
    place(out, AL.creak(0.8, 125.0), 1.9, pan=0.3, gain=0.04)
    for tt, pan in ((0.45, 0.35), (1.25, 0.3), (2.15, 0.4)):
        place(out, clank(), tt, pan=pan, gain=0.07)
    for tt in (0.3, 0.95, 1.6, 2.25, 2.9):                      # the smith up the mole
        place(out, anvil(), tt, pan=-0.2, gain=0.035)
    for k in range(9):
        n = int(0.06 * SR)
        x = lowpass(RNG.normal(0, 1, n), 900) * np.exp(-np.arange(n) / SR * 70)
        place(out, x * 0.05, 0.15 + k * 0.32 + RNG.uniform(-0.03, 0.03), pan=-0.25)
    place(out, murmur(3.0, 1) * 0.35, 0.0, pan=0.0)
    for tt, pan, g in ((0.02, 0.6, 0.08), (2.5, 0.6, 0.08), (1.35, 0.75, 0.04)):
        place(out, AL.oar_stroke(), tt, pan=pan, gain=g)

    # S2: sped-up work: bronze struck, shovels by day; crickets and the furnaces at night
    tt = 3.05
    while tt < 8.0:
        night = NIGHT[0] < tt < NIGHT[1]
        tt += RNG.exponential(1.0 / (1.8 if night else 10.0))
        r = RNG.random()
        if r < 0.55:
            place(out, bronze_hit(), tt, pan=RNG.uniform(-0.6, 0.6), gain=RNG.uniform(0.03, 0.06))
        elif r < 0.85 and not night:
            place(out, shovel(), tt, pan=RNG.uniform(-0.7, 0.7), gain=RNG.uniform(0.04, 0.08))
        else:
            place(out, AL.mallet_on_chisel(), tt, pan=RNG.uniform(-0.5, 0.5), gain=0.03)
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
    n = int((NIGHT[1] - NIGHT[0] + 0.6) * SR)
    k = np.arange(n) / SR
    roar = lowpass(RNG.normal(0, 1, n), 300) * np.sin(np.pi * k / k[-1]) * 0.25
    place(out, np.stack([roar, np.roll(roar, 300)], 1) * 0.5, NIGHT[0] - 0.3)

    # S3: bellows on their stroke (0.8 Hz, two bags in turn), the furnaces, rivets on the head
    n = int(3.5 * SR)
    k = np.arange(n) / SR
    fire = lowpass(RNG.normal(0, 1, n), 420) * (0.6 + 0.4 * AL.smooth_noise(n, 2.0, 33)) * 0.3
    place(out, np.stack([fire, np.roll(fire, 500)], 1) * 0.55, 8.0)
    for j in range(9):
        for side, off in ((-0.35, 0.0), (0.3, 0.3)):
            place(out, bellows(0.55), 8.0 + j * 1.25 + off * 1.25 + 0.2, pan=side, gain=0.12)
    tt = 8.05
    while tt < 11.45:
        tt += RNG.exponential(0.45)
        place(out, bronze_hit(big=RNG.random() < 0.3), tt, pan=RNG.uniform(-0.2, 0.5), gain=RNG.uniform(0.05, 0.09))
    ct = 8.0
    while ct < 11.5:
        ct += RNG.exponential(0.05)
        m = int(0.01 * SR)
        x = bandpass(RNG.normal(0, 1, m), 1500, 7000) * np.exp(-np.arange(m) / SR * 450)
        place(out, x * RNG.uniform(0.01, 0.035), ct, pan=RNG.uniform(-0.5, -0.1))

    # S4: the mound carried away: shovels, baskets tipped, a crowd gathering
    tt = 11.5
    while tt < 14.9:
        tt += RNG.exponential(1.0 / 9.0)
        place(out, shovel(), tt, pan=RNG.uniform(-0.7, 0.7), gain=RNG.uniform(0.03, 0.07))
    crowd = murmur(4.0, 2)
    crowd *= np.linspace(0.2, 1.0, len(crowd))
    place(out, np.stack([crowd, np.roll(crowd, 1100)], 1) * 0.3, 11.5)
    shimmer = highpass(RNG.normal(0, 1, int(2.5 * SR)), 5000) * np.linspace(0, 1, int(2.5 * SR)) ** 2
    place(out, np.stack([shimmer, np.roll(shimmer, 600)], 1) * 0.05, 12.5)

    # S5: the galley's stroke, the stroke-caller, the harbour, the altar fire, gulls
    for c in (16.0, 19.2):
        for j in range(5):
            place(out, AL.oar_stroke(n_oars=5, spread=0.12), c + 0.07 * j - 0.1, pan=0.35 + 0.05 * j, gain=0.07)
        place(out, AL.voice_call(0.7, 50), c - 0.75, pan=0.4, gain=0.04)
    for tt, f0 in ((15.5, 90.0), (17.2, 115.0), (18.4, 85.0)):
        place(out, AL.creak(RNG.uniform(0.6, 1.0), f0), tt, pan=0.4, gain=0.035)
    harbour = murmur(5.0, 3)
    place(out, np.stack([harbour, np.roll(harbour, 1500)], 1) * 0.18, 15.0)
    n = int(5.0 * SR)
    crack = np.zeros(n)
    ct = 0.0
    while ct < 4.95:
        ct += RNG.exponential(0.08)
        m = int(0.012 * SR)
        i0 = int(ct * SR)
        if i0 + m < n:
            crack[i0:i0 + m] += bandpass(RNG.normal(0, 1, m), 1500, 7000) * np.exp(-np.arange(m) / SR * 400) * RNG.uniform(0.2, 1)
    place(out, crack * 0.04, 15.0, pan=-0.2)
    for tt, pan in ((15.4, -0.6), (16.6, -0.3), (17.9, 0.5), (19.0, -0.4)):
        place(out, AL.gull(RNG.uniform(0.35, 0.6)), tt, pan=pan, gain=0.07)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    mus = A.reverb(music(), 3.0, 0.3)
    fx = A.reverb(sfx(), 1.4, 0.14, seed=4)
    mix = AL.master(mus * 0.75 + fx * 0.6)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    A.write_wav(args.out, mix)
    rms = np.sqrt((mix ** 2).mean())
    print(f'wrote {args.out}: peak {np.abs(mix).max():.3f} rms {20 * np.log10(rms):.1f} dBFS')


if __name__ == '__main__':
    main()
