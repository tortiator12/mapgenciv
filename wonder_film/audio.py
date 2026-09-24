"""Procedural soundtrack for the Great Lighthouse time-lapse (numpy/scipy only).

Score: dark D-Phrygian pulse at 96 BPM, bars aligned so the A7(b9) -> D major
cadence lands exactly when the beacon is lit (25.4 s).  Sound design follows
the time-lapse clock: sea and wind throughout, sped-up chisel/hammer ticks by
day, crickets by night, a whoosh and roar when the fire catches.

  python wonder_film/audio.py --out build/soundtrack.wav
"""
import argparse
import os
import sys
import wave

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as TL  # noqa: E402

SR = 48000
DUR = TL.DURATION
N = int(SR * DUR)
RNG = np.random.default_rng(1234)

BPM = 96.0
BEAT = 60.0 / BPM            # 0.625 s
BAR = 4 * BEAT               # 2.5 s
T0 = TL.PHASES['fire'][0] - 10 * BAR   # bar 10 starts on the ignition -> 0.4 s


def bar_t(b):
    return T0 + b * BAR


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def env_adsr(n, a, d, s, r, sr=SR):
    """ADSR over n samples (release inside n)."""
    e = np.ones(n) * s
    na, nd, nr = int(a * sr), int(d * sr), int(r * sr)
    na = min(na, n)
    e[:na] = np.linspace(0, 1, na, endpoint=False) ** 1.5 if na else e[:na]
    nd = min(nd, n - na)
    if nd > 0:
        e[na:na + nd] = np.linspace(1, s, nd)
    nr = min(nr, n)
    if nr > 0:
        e[n - nr:] *= np.linspace(1, 0, nr) ** 2
    return e


def lowpass(x, fc, order=2):
    b, a = signal.butter(order, min(fc / (SR / 2), 0.99), 'low')
    return signal.lfilter(b, a, x, axis=0)


def highpass(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), 'high')
    return signal.lfilter(b, a, x, axis=0)


def bandpass(x, f1, f2, order=2):
    b, a = signal.butter(order, [f1 / (SR / 2), min(f2 / (SR / 2), 0.99)], 'band')
    return signal.lfilter(b, a, x, axis=0)


def saw(freq, n, phase=0.0, vib=None):
    """Band-limited sawtooth (PolyBLEP); vib is an optional phase-modulation array (radians)."""
    t = np.arange(n) / SR
    ph = freq * t + phase / (2 * np.pi)
    if vib is not None:
        ph = ph + vib / (2 * np.pi)
    p = ph % 1.0
    dt = freq / SR
    y = 2.0 * p - 1.0
    m = p < dt
    x = p[m] / dt
    y[m] -= x + x - x * x - 1.0
    m = p > 1.0 - dt
    x = (p[m] - 1.0) / dt
    y[m] -= x * x + x + x + 1.0
    return y * 0.5


def place(buf, x, t, pan=0.0, gain=1.0):
    """Add mono/stereo signal x into stereo buf at time t with constant-power pan."""
    i = int(t * SR)
    if i >= len(buf):
        return
    if x.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        x = np.stack([x * l, x * r], 1)
    j = min(len(buf), i + len(x))
    if i < 0:
        x = x[-i:]
        i = 0
    buf[i:j] += x[:j - i] * gain


# ---------------------------------------------------------------- instruments
def pad_note(m, dur, bright=1800.0, a=0.9, r=1.4, detune=0.07, spread=0.5):
    n = int(dur * SR)
    f = midi_hz(m)
    out = np.zeros((n, 2))
    for i, dt in enumerate((-detune, 0.0, detune)):
        ff = f * 2 ** (dt / 12)
        v = saw(ff, n, phase=RNG.uniform(0, 6.28))
        pan = (i - 1) * spread
        out[:, 0] += v * np.cos((pan + 1) * np.pi / 4)
        out[:, 1] += v * np.sin((pan + 1) * np.pi / 4)
    out = lowpass(out, bright)
    return out * env_adsr(n, a, 0.5, 0.85, r)[:, None] / 3


def pluck(m, dur=0.9, bright=0.55, damp=0.994):
    """Karplus-Strong (oud-ish) via an IIR comb filter."""
    f = midi_hz(m)
    n = int(dur * SR)
    L = int(SR / f)
    exc = RNG.uniform(-1, 1, L)
    exc = lowpass(exc, 1500 + 3500 * bright)
    x = np.zeros(n)
    x[:L] = exc
    a = np.zeros(L + 2)
    a[0] = 1.0
    a[L] = -damp * 0.5
    a[L + 1] = -damp * 0.5
    y = signal.lfilter([1.0], a, x)
    y *= env_adsr(n, 0.002, 0.05, 1.0, 0.08)
    return highpass(y, 70) * 0.5


def drum_dum(gain=1.0):
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    f = 55.0 + 50 * np.exp(-t * 30)          # settles on A1 (the dominant)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 7.5)
    thump = lowpass(RNG.normal(0, 1, n), 900) * np.exp(-t * 60) * 0.35
    return np.tanh((body + thump) * 1.4) * 0.8 * gain


def drum_tek(gain=1.0):
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    nz = bandpass(RNG.normal(0, 1, n), 2200, 7000) * np.exp(-t * 70)
    ring = np.sin(2 * np.pi * 820 * t) * np.exp(-t * 55) * 0.3
    return (nz * 0.8 + ring) * 0.55 * gain


def boom(dur=3.5, f0=48.0, gain=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (1 + 0.6 * np.exp(-t * 12))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t * 1.3)
    x += 0.5 * np.sin(2 * ph) * np.exp(-t * 2.5)
    x += lowpass(RNG.normal(0, 1, n), 400) * np.exp(-t * 8) * 0.5
    return np.tanh(x * 1.6) * 0.85 * gain


def gong(dur=6.0, f0=98.0, gain=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ratios = [1.0, 1.52, 2.03, 2.61, 3.17, 3.79, 4.48, 5.2, 6.1, 7.3]
    out = np.zeros(n)
    for i, rr in enumerate(ratios):
        dec = 0.6 + 0.35 * i
        bloom = 1 - np.exp(-t * (8 + 4 * i))
        out += np.sin(2 * np.pi * f0 * rr * t * (1 + 0.002 * np.sin(2 * np.pi * 0.7 * t)) + RNG.uniform(0, 6)) \
            * np.exp(-t * dec) * bloom / (1 + 0.4 * i)
    shimmer = highpass(RNG.normal(0, 1, n), 3500) * np.exp(-t * 2.2) * 0.06
    return (out * 0.28 + shimmer) * gain


def choir_note(m, dur, a=1.2, r=1.8):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(m)
    out = np.zeros(n)
    for dt in (-0.1, 0.0, 0.1):
        fv = 5.1 + dt
        vib = 2 * np.pi * (0.004 * f / fv) * np.sin(2 * np.pi * fv * t)   # +-0.4 % vibrato
        out += saw(f * 2 ** (dt / 12), n, RNG.uniform(0, 6), vib)
    # 'ah' formants
    y = (bandpass(out, 650, 820) * 1.0 + bandpass(out, 1000, 1200) * 0.6 + bandpass(out, 2300, 2600) * 0.25)
    return y * env_adsr(n, a, 0.4, 0.9, r) * 0.9


def noise_riser(dur, f_lo=300, f_hi=6000):
    n = int(dur * SR)
    x = RNG.normal(0, 1, n)
    bands = np.geomspace(f_lo, f_hi, 7)
    stages = [bandpass(x, b * 0.7, b * 1.4) for b in bands]
    pos = np.linspace(0, len(bands) - 1, n)
    out = np.zeros(n)
    for i, st in enumerate(stages):
        w = np.clip(1 - np.abs(pos - i), 0, 1)
        out += st * w
    return out * np.linspace(0, 1, n) ** 2.2


# ---------------------------------------------------------------- the score
CHORDS = {
    'Dm': [38, 45, 50, 53, 57], 'Eb': [39, 46, 51, 55, 58], 'Cm': [36, 43, 48, 51, 55],
    'Bb': [34, 41, 46, 50, 53], 'A7b9': [33, 45, 49, 55, 58], 'D': [38, 45, 50, 54, 57, 62],
    'Dadd9': [38, 45, 50, 52, 54, 57, 62],
}
PROG = ['Dm', 'Dm', 'Dm', 'Eb', 'Dm', 'Cm', 'Bb', 'Eb', 'Cm', 'A7b9', 'D', 'Dadd9']
OSTINATO = [50, 51, 53, 55, 57, 55, 53, 51]          # D Phrygian
OSTINATO_A = [45, 46, 49, 52, 55, 52, 49, 46]        # A Phrygian dominant
MAQSUM = [('D', 0), ('T', 1), ('T', 3), ('D', 4), ('T', 6)]


def music():
    mus = np.zeros((N, 2))
    # opening boom and drone
    place(mus, boom(4.0, 36.7, 0.9), T0 - 0.05, 0.0)
    drone = np.zeros(N)
    t = np.arange(N) / SR
    for m, g in ((26, 0.5), (38, 0.35), (45, 0.18)):
        drone += saw(midi_hz(m), N, RNG.uniform(0, 6)) * g
    drone = lowpass(drone, 320)
    drone *= np.clip(t / 2.5, 0, 1) * (1 - np.clip((t - 22.6) / 1.2, 0, 1) * 0.6)
    mus += np.stack([drone, drone], 1) * 0.2

    for b, ch in enumerate(PROG):
        tb = bar_t(b)
        dur = BAR + 1.2
        if b == 10:
            dur = BAR + 0.2
        if b == 11:
            dur = DUR - tb + 0.1
        bright = 700 + 110 * b if b < 10 else 2600
        for i, m in enumerate(CHORDS[ch]):
            place(mus, pad_note(m, dur, bright=bright, a=0.7 if b < 10 else 0.15, r=1.2),
                  tb, pan=(i / max(len(CHORDS[ch]) - 1, 1) - 0.5) * 0.8, gain=0.22 if b < 10 else 0.42)
        # strings an octave up in the second half
        if 6 <= b <= 9:
            for m in CHORDS[ch][2:]:
                place(mus, pad_note(m + 12, dur, bright=3000, a=1.0, r=1.2, detune=0.12), tb, gain=0.09 * (b - 5))

    # plucked ostinato + frame drum groove: bars 2..8 (construction), fill in bar 9
    eighth = BEAT / 2
    for b in range(2, 10):
        tb = bar_t(b)
        pattern = OSTINATO_A if b == 9 else OSTINATO
        for k in range(8):
            if b == 9 and k >= 6:
                break
            m = pattern[k] + (12 if (b >= 6 and k % 2 == 1) else 0)
            place(mus, pluck(m, 0.8, bright=0.4 + 0.05 * (b - 2)), tb + k * eighth,
                  pan=0.25 * np.sin(k), gain=0.32 + 0.03 * (b - 2))
        if b == 9:
            continue
        for kind, pos in MAQSUM:
            g = 0.55 + 0.06 * (b - 2)
            place(mus, drum_dum(g) if kind == 'D' else drum_tek(g), tb + pos * eighth, pan=-0.1 if kind == 'D' else 0.2)
        if b >= 5:   # extra teks and a low boom on the downbeat
            for pos in (2, 5, 7):
                place(mus, drum_tek(0.35), tb + pos * eighth, pan=-0.3)
            place(mus, boom(1.2, 55.0, 0.35), tb)
        if b >= 7:
            for pos in range(16):
                if RNG.random() < 0.35:
                    place(mus, drum_tek(0.22), tb + pos * eighth / 2, pan=RNG.uniform(-0.6, 0.6))

    # breakdown -> ignition
    tb9 = bar_t(9)
    riser = noise_riser(BAR, 250, 7000)
    place(mus, np.stack([riser, np.roll(riser, 700)], 1) * 0.12, tb9)
    t_fire = bar_t(10)
    place(mus, boom(4.5, 36.7, 0.75), t_fire)
    place(mus, gong(6.5, 92, 0.9), t_fire - 0.02, 0.1)
    for i, m in enumerate([62, 66, 69, 74]):
        place(mus, choir_note(m, DUR - t_fire, a=0.6, r=2.0), t_fire, pan=(i - 1.5) * 0.3, gain=0.16)
    # soft closing pluck line under the title
    for k, m in enumerate([62, 61, 62, 57, 58, 57, 54, 50]):
        place(mus, pluck(m, 1.2, 0.3), bar_t(10) + 1.0 + k * 0.5, pan=0.1, gain=0.18)
    return mus


# ---------------------------------------------------------------- sound design
def smooth_noise(n, rate, seed):
    rng = np.random.default_rng(seed)
    k = int(DUR * rate) + 3
    pts = rng.uniform(0, 1, k)
    x = np.linspace(0, k - 3, n)
    return np.interp(x, np.arange(k), pts)


def sfx():
    out = np.zeros((N, 2))
    t = np.arange(N) / SR
    # sea: brown-ish noise with swells, separate L/R for width
    for ch in (0, 1):
        w = np.cumsum(RNG.normal(0, 1, N))
        w = highpass(w, 80)
        w = lowpass(w, 700)
        w /= np.abs(w).max()
        swell = 0.45 + 0.55 * smooth_noise(N, 0.45, 10 + ch) ** 2
        surf = bandpass(RNG.normal(0, 1, N), 400, 3500) * (smooth_noise(N, 0.8, 20 + ch) ** 4) * 0.25
        out[:, ch] += (w * swell * 0.55 + surf)
    # wind
    wind = bandpass(RNG.normal(0, 1, N), 250, 1100) * (0.3 + 0.7 * smooth_noise(N, 0.3, 5))
    out += np.stack([wind, np.roll(wind, 900)], 1) * 0.09
    out *= 0.35

    # construction ticks (chisels, hammers), denser in daylight
    t_end = TL.PHASES['scaf2_down'][1]
    tt = 0.8
    while tt < t_end:
        day = TL.daylight(tt)
        rate = 1.0 + 7.0 * day * min(1.0, tt / 3.0)
        tt += RNG.exponential(1.0 / rate)
        if RNG.random() < 0.75:   # chisel ping
            n = int(0.07 * SR)
            k = np.arange(n) / SR
            f = RNG.uniform(2300, 4600)
            x = np.sin(2 * np.pi * f * k) * np.exp(-k * RNG.uniform(60, 110))
            x += bandpass(RNG.normal(0, 1, n), 3000, 9000) * np.exp(-k * 300) * 0.4
            place(out, x * RNG.uniform(0.03, 0.08), tt, pan=RNG.uniform(-0.7, 0.7))
        else:                     # mallet on wood / stone
            n = int(0.12 * SR)
            k = np.arange(n) / SR
            f = RNG.uniform(150, 260)
            x = np.sin(2 * np.pi * f * k) * np.exp(-k * 40) + lowpass(RNG.normal(0, 1, n), 1500) * np.exp(-k * 90) * 0.5
            place(out, x * RNG.uniform(0.05, 0.1), tt, pan=RNG.uniform(-0.5, 0.5))

    # crickets at night
    for c in range(4):
        tt = RNG.uniform(0, 1)
        f = RNG.uniform(4200, 5200)
        pan = RNG.uniform(-0.8, 0.8)
        while tt < DUR:
            night = 1 - TL.daylight(tt)
            if night > 0.2:
                n = int(0.16 * SR)
                k = np.arange(n) / SR
                gate = (np.sin(2 * np.pi * 28 * k) > 0.2).astype(float)
                gate = lowpass(gate, 400)
                x = np.sin(2 * np.pi * f * k) * gate * np.exp(-k * 6)
                place(out, x * 0.02 * night, tt, pan=pan)
            tt += RNG.uniform(0.45, 0.9)

    # the beacon catches: whoosh + roar + crackle
    tf = TL.PHASES['fire'][0]
    whoosh = noise_riser(0.9, 150, 2500)
    place(out, np.stack([whoosh, whoosh], 1) * 0.22, tf - 0.55)
    n = int((DUR - tf) * SR)
    k = np.arange(n) / SR
    roar = lowpass(RNG.normal(0, 1, n), 380) * (1 - np.exp(-k * 3)) * 0.35
    place(out, np.stack([roar, np.roll(roar, 400)], 1) * 0.5, tf)
    tt = tf
    while tt < DUR:
        tt += RNG.exponential(0.05)
        m = int(0.012 * SR)
        x = bandpass(RNG.normal(0, 1, m), 1500, 8000) * np.exp(-np.arange(m) / SR * 400)
        place(out, x * RNG.uniform(0.01, 0.05), tt, pan=RNG.uniform(-0.3, 0.3))
    return out


def reverb(x, rt60=2.8, wet=0.3, seed=9):
    rng = np.random.default_rng(seed)
    n = int(rt60 * SR)
    k = np.arange(n) / SR
    decay = np.exp(-6.9 * k / rt60)
    ir = np.stack([rng.normal(0, 1, n), rng.normal(0, 1, n)], 1) * decay[:, None]
    ir = lowpass(ir, 5000)
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]
    ir /= np.sqrt((ir ** 2).sum(0))
    y = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in (0, 1)], 1)
    return x * (1 - wet) + y * wet * 1.4


def limiter(x, thr=0.89, release=0.08, look=0.004):
    """Look-ahead peak limiter (no distortion on the body of the mix)."""
    from scipy.ndimage import maximum_filter1d
    a = np.abs(x).max(axis=1)
    w = int(look * SR) * 2 + 1
    pk = maximum_filter1d(a, w)
    pk = np.roll(pk, -int(look * SR))
    g = np.minimum(1.0, thr / np.maximum(pk, 1e-9))
    # smooth: instant attack (min filter), exponential release
    alpha = np.exp(-1.0 / (release * SR))
    gs = signal.lfilter([1 - alpha], [1, -alpha], g - 1.0) + 1.0
    gs = np.minimum(gs, g)
    return x * gs[:, None]


def master(x, target_rms_db=-19.0):
    t = np.arange(len(x)) / SR
    fade = np.clip(t / 0.5, 0, 1) * (1 - np.clip((t - 29.0) / 1.0, 0, 1))
    x = highpass(x * fade[:, None], 30)
    x = x - 0.45 * lowpass(x, 110)          # low-shelf cut: less boom, more clarity
    rms = np.sqrt((x ** 2).mean())
    x = x * (10 ** (target_rms_db / 20) / rms)
    return limiter(x)


def write_wav(path, x):
    y = np.clip(x, -1, 1)
    pcm = (y * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    mus = reverb(music(), 3.2, 0.32)
    fx = reverb(sfx(), 1.6, 0.15, seed=4)
    mix = mus * 0.78 + fx * 0.55
    mix = master(mix)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_wav(args.out, mix)
    rms = np.sqrt((mix ** 2).mean())
    print(f'wrote {args.out}: peak {np.abs(mix).max():.3f} rms {20 * np.log10(rms):.1f} dBFS')


if __name__ == '__main__':
    main()
