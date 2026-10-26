'''The air over home from the planes: readsb works out the outside air temperature (oat, tat) and the wind (wd, ws) from
what the planes answer to Mode S EHS (Mach, airspeeds, heading against the ground track). A profile of each 1000 ft
over the last half hour, the median of the planes there: one plane is a few degrees off (oat comes from Mach and TAS,
both rounded), many agree.

alt_baro is the pressure altitude (1013.25 hPa): a bin is a pressure level (850 hPa at 1457 m, 700 at 3012, 500 at 5574,
300 at 9164, 250 at 10363), the same levels the model gives. Heights above the sea add the planes' alt_geom - alt_baro.
'''
import math
import time
import numpy as np

from collections import deque

from .utils import local_xy

bin_ft = 1000
window_s = 30 * 60
every_s = 60            # one sample per plane a minute: a plane circling doesn't make a crowd
max_km = 150
min_n = 3               # planes in a bin for it to count
odd_c = 6               # a bin this far from its neighbours' median is dropped
oat_range = (-85, 45)
kt = 0.514444

_samples = deque()      # (t, hex, alt_ft, oat, u, v, geom - baro ft); the wind blowing towards u east, v north, m/s
_last = {}              # hex -> when it was last sampled


def add(now: float, aircraft: list):
    '''From each poll of aircraft.json (the data service, every second).'''
    for p in aircraft:
        alt = p.get('alt_baro')
        if not isinstance(alt, (int, float)) or ('oat' not in p and 'ws' not in p) or 'lat' not in p:
            continue
        if now - _last.get(p['hex'], 0) < every_s or math.hypot(*local_xy(p['lat'], p['lon'])) > max_km:
            continue
        _last[p['hex']] = now
        u = v = None
        if p.get('ws') is not None and p.get('wd') is not None:
            # wd is where it blows from.
            r = math.radians(p['wd'])
            u, v = -p['ws'] * kt * math.sin(r), -p['ws'] * kt * math.cos(r)
        geom = p['alt_geom'] - alt if isinstance(p.get('alt_geom'), (int, float)) else None
        oat = p.get('oat') if oat_range[0] < (p.get('oat') or 0) < oat_range[1] else None
        _samples.append((now, p['hex'], alt, oat, u, v, geom))
    while _samples and now - _samples[0][0] > window_s:
        _samples.popleft()
    for h in [h for h, t in _last.items() if now - t > window_s]:
        del _last[h]

def pressure_m(p_hpa: float) -> float:
    # The pressure altitude of a level (ISA troposphere, and the constant -56.5 °C stratosphere above 11 km).
    if p_hpa >= 226.32:
        return 44330.8 * (1 - (p_hpa / 1013.25) ** 0.190263)
    return 11000 + 6341.6 * math.log(226.32 / p_hpa)

def pressure_hpa(alt_m: float) -> float:
    if alt_m <= 11000:
        return 1013.25 * (1 - alt_m / 44330.8) ** 5.25588
    return 226.32 * math.exp(-(alt_m - 11000) / 6341.6)

def contrail_c(p_hpa: float) -> float:
    '''The Schmidt-Appleman threshold (Schumann 1996, dry air, an overall efficiency of 0.3): colder than this and a
    jet makes a trail. About -40 °C at 300 hPa.'''
    g = 1.25 * 1004 * p_hpa * 100 / (0.622 * 43.2e6 * 0.7)
    x = math.log(g - 0.053)
    return -46.46 + 9.43 * x + 0.72 * x * x

def profile(now: float | None = None) -> dict | None:
    '''{bins: [[alt_m, t °C or None, n_t, u, v, n_w]], geom_m} with min_n planes, from the ground up; None without any.'''
    now = now or time.time()
    rows = [s for s in _samples if now - s[0] <= window_s]
    if not rows:
        return None
    # Each plane once per bin (the median of its samples), then the median of the planes.
    by = {}
    for _, hex, alt, t, u, v, _g in rows:
        by.setdefault(int(alt // bin_ft), {}).setdefault(hex, []).append((t, u, v))
    bins = []
    for k in sorted(by):
        planes = by[k].values()
        ts = [float(np.median(t)) for s in planes if (t := [x[0] for x in s if x[0] is not None])]
        ws = [np.median(w, axis=0) for s in planes if (w := [x[1:] for x in s if x[1] is not None])]
        if len(ts) < min_n and len(ws) < min_n:
            continue
        t = round(float(np.median(ts)), 1) if len(ts) >= min_n else None
        u, v = (round(float(x), 1) for x in np.median(ws, axis=0)) if len(ws) >= min_n else (None, None)
        bins.append([round((k + 0.5) * bin_ft * 0.3048), t, len(ts), u, v, len(ws)])
    # A bin far off the line through its neighbours (2000 m either way) is a plane or two saying nonsense: its
    # temperature goes.
    odd = []
    for b in bins:
        near = [(c[0], c[1]) for c in bins if c is not b and c[1] is not None and abs(c[0] - b[0]) <= 2000]
        if b[1] is not None and len(near) >= 3:
            fit = np.polyfit(*zip(*near), 1)
            odd.append(abs(b[1] - np.polyval(fit, b[0])) > odd_c)
        else:
            odd.append(False)
    for b, o in zip(bins, odd):
        if o:
            b[1], b[2] = None, 0
    bins = [b for b in bins if b[1] is not None or b[3] is not None]
    geoms = [g for *_, g in rows if g is not None]
    return {'bins': bins, 'geom_m': round(float(np.median(geoms)) * 0.3048) if geoms else 0} if bins else None

def temp_at(bins: list, alt_m: float) -> float | None:
    # Between the two nearest bins with a temperature, within 1500 m.
    pts = [(a, t) for a, t, *_ in bins if t is not None]
    if not pts or alt_m < pts[0][0] - 1500 or alt_m > pts[-1][0] + 1500:
        return None
    return float(np.interp(alt_m, [a for a, _ in pts], [t for _, t in pts]))

def wind_at(bins: list, alt_m: float, near: float = 1000) -> tuple[float, float] | None:
    '''(where it blows from, degrees; m/s) from the nearest bin with wind, within near metres.'''
    pts = [(abs(a - alt_m), u, v) for a, _, _, u, v, _ in bins if u is not None]
    if not pts or (best := min(pts))[0] > near:
        return None
    _, u, v = best
    return round(math.degrees(math.atan2(-u, -v)) % 360), round(math.hypot(u, v), 1)

def derived(prof: dict) -> dict:
    '''What the profile says: the freezing level (m above the sea), the lapse rate (°C/km, 1.5-9 km), an inversion in
    the lowest 3 km, the strongest wind, and where the trails start (the lowest bin colder than the threshold).'''
    bins, geom = prof['bins'], prof['geom_m']
    pts = [(a, t) for a, t, *_ in bins if t is not None]
    out = {'freezing_m': None, 'lapse': None, 'inversion': None, 'jet': None, 'contrail_m': None}
    for (a0, t0), (a1, t1) in zip(pts, pts[1:]):
        if t0 >= 0 > t1:
            out['freezing_m'] = round(a0 + (a1 - a0) * t0 / (t0 - t1) + geom)
            break
    mid = [(a, t) for a, t in pts if 1500 <= a <= 9000]
    if len(mid) >= 4 and mid[-1][0] - mid[0][0] > 3000:
        out['lapse'] = round(-float(np.polyfit([a / 1000 for a, _ in mid], [t for _, t in mid], 1)[0]), 1)
    low = [(a, t) for a, t in pts if a <= 3000]
    for i, (a0, t0) in enumerate(low):
        warmer = [(a, t) for a, t in low[i + 1:] if t - t0 >= 1]
        if warmer:
            a1, t1 = max(warmer, key=lambda x: x[1])
            out['inversion'] = {'base_m': a0 + geom, 'top_m': a1 + geom, 'dt': round(t1 - t0, 1)}
            break
    winds = [(math.hypot(u, v), a) for a, _, _, u, v, _ in bins if u is not None]
    if winds:
        ms, a = max(winds)
        out['jet'] = {'alt_m': a, 'ms': round(ms, 1), 'dir': wind_at(bins, a)[0]}
    for a, t in pts:
        if a > 6000 and t < contrail_c(pressure_hpa(a)):
            out['contrail_m'] = a
            break
    return out
