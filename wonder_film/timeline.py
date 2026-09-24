"""Shared timing for the Great Lighthouse time-lapse.

Everything is expressed in *video seconds* (0..30).  The scene builder, the
renderer, the stylizer and the soundtrack all import this module so that the
construction phases, the day/night cycle, the camera and the music stay in
sync.  No bpy imports here.
"""
import math

import numpy as np

FPS = 24
DURATION = 30.0
NFRAMES = int(round(FPS * DURATION))  # 720

# --------------------------------------------------------------------------
# Construction phases (video seconds).  Inside a phase, progress is warped by
# the amount of daylight: work slows to a crawl at night, like a real
# time-lapse of a building site.
# --------------------------------------------------------------------------
PHASES = {
    'survey':     (0.0, 1.4),    # stakes + ropes on the empty headland
    'platform':   (1.0, 4.6),    # stepped stone podium
    'tier1':      (4.4, 14.8),   # square tier, 40 courses
    'tier1cap':   (14.5, 15.6),  # cornice, roof slab, parapet, tritons
    'tier2':      (15.4, 20.6),  # octagonal tier, 20 courses
    'tier2cap':   (20.4, 21.2),
    'tier3':      (21.0, 22.8),  # drum, colonnade, entablature, dome
    'statue':     (22.6, 23.6),  # bronze Zeus hoisted onto the dome
    'scaf1_down': (15.8, 17.6),  # tier-1 scaffolding dismantled top-down
    'scaf2_down': (23.4, 24.9),  # remaining scaffolding + cranes removed
    'fire':       (25.4, 26.1),  # the beacon is lit
}
T_TITLE = 26.2          # "wonder completed" card starts
T_FADE = (29.25, 30.0)  # fade to black
T_FADE_IN = (0.0, 0.7)

# --------------------------------------------------------------------------
# Time-lapse clock: video seconds -> hour of day (monotonic, can exceed 24).
# Dawn opening, three days of work that get shorter (accelerating rhythm),
# and a final night for the lighting of the beacon.
# --------------------------------------------------------------------------
CLOCK_KEYS = [
    (0.0, 5.80), (1.2, 6.55), (8.3, 17.90), (9.4, 20.00), (10.6, 28.60),
    (11.7, 30.50), (16.6, 41.80), (17.7, 43.80), (18.7, 52.80), (19.7, 54.60),
    (23.4, 65.80), (24.6, 67.30), (25.6, 68.60), (30.0, 69.80),
]

LATITUDE = math.radians(31.2)    # Alexandria
DECLINATION = math.radians(-9.0)  # autumn sun: long, raking shadows


def _pchip(xk, yk, x):
    """Monotone cubic (Fritsch-Carlson) interpolation, scalar x."""
    xk = np.asarray(xk, float)
    yk = np.asarray(yk, float)
    n = len(xk)
    h = np.diff(xk)
    d = np.diff(yk) / h
    m = np.zeros(n)
    for k in range(1, n - 1):
        if d[k - 1] * d[k] <= 0:
            m[k] = 0.0
        else:
            w1 = 2 * h[k] + h[k - 1]
            w2 = h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0] = d[0]
    m[-1] = d[-1]
    x = min(max(x, xk[0]), xk[-1])
    k = int(np.clip(np.searchsorted(xk, x) - 1, 0, n - 2))
    t = (x - xk[k]) / h[k]
    h00 = 2 * t**3 - 3 * t**2 + 1
    h10 = t**3 - 2 * t**2 + t
    h01 = -2 * t**3 + 3 * t**2
    h11 = t**3 - t**2
    return h00 * yk[k] + h10 * h[k] * m[k] + h01 * yk[k + 1] + h11 * h[k] * m[k + 1]


def clock(t):
    """Hour of day (continuous, may exceed 24) at video time t."""
    return _pchip([k[0] for k in CLOCK_KEYS], [k[1] for k in CLOCK_KEYS], t)


def sun_angles(hour):
    """(elevation, azimuth) in radians; azimuth measured CCW from +X (east)."""
    H = math.radians(15.0 * ((hour % 24.0) - 12.0))
    sin_el = (math.sin(LATITUDE) * math.sin(DECLINATION)
              + math.cos(LATITUDE) * math.cos(DECLINATION) * math.cos(H))
    el = math.asin(max(-1.0, min(1.0, sin_el)))
    # compass azimuth (0 = north, 90 = east)
    az_c = math.atan2(math.sin(H),
                      math.cos(H) * math.sin(LATITUDE)
                      - math.tan(DECLINATION) * math.cos(LATITUDE)) + math.pi
    # convert compass (N=0, E=90, clockwise) to math angle CCW from +X(east)
    az = math.radians(90.0) - az_c
    return el, az


def sun_dir(hour):
    el, az = sun_angles(hour)
    return np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])


def moon_dir(hour):
    # full moon: roughly opposite the sun, a little higher in the sky
    el, az = sun_angles(hour + 12.0)
    el = el * 0.85 + math.radians(6)
    return np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def daylight(t):
    """0 at night, 1 in daylight, smooth through twilight."""
    el, _ = sun_angles(clock(t))
    return smoothstep(math.radians(-7), math.radians(5), el)


# --------------------------------------------------------------------------
# Work-rate warp: progress inside each phase advances faster in daylight.
# --------------------------------------------------------------------------
_TS = np.linspace(0.0, DURATION, 3001)
_RATE = np.array([0.18 + 0.82 * daylight(x) for x in _TS])
_WORK = np.concatenate([[0.0], np.cumsum(0.5 * (_RATE[1:] + _RATE[:-1]) * np.diff(_TS))])


def work(t):
    return float(np.interp(t, _TS, _WORK))


def phase_progress(name, t, warp=True):
    """0..1 progress of a construction phase at video time t."""
    t0, t1 = PHASES[name]
    if t <= t0:
        return 0.0
    if t >= t1:
        return 1.0
    if not warp:
        return (t - t0) / (t1 - t0)
    return (work(t) - work(t0)) / (work(t1) - work(t0))


def phase_time(name, p):
    """Inverse of phase_progress (warped): video time at which progress p is reached."""
    t0, t1 = PHASES[name]
    w = work(t0) + p * (work(t1) - work(t0))
    return float(np.interp(w, _WORK, _TS))


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ease_io(x):
    x = min(max(x, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * x)
