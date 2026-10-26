'''The roofline seen from the window, from the buildings themselves (IGN's BD TOPO: their roofs' heights over the sea)
and the hills behind them (HeyWhatsThat's horizon, in its Stellarium export with the window's place and height).

Built once in a thread and kept in redis for months: by bearing, how high the roofs stand (degrees over the horizon)
at a few distances, near to far. The window is nudged, a few metres, until the places seen from it (the landmarks of
screen_data) are over the roofs in front of them: they're the planes' waypoints from here.

    python -m disinfo.screens.aviator.skyline       # builds it now, and says what it sees
'''
import json
import math
import time
import zipfile
import hashlib
import threading
import configparser
import requests
import numpy as np

from typing import NamedTuple
from concurrent.futures import ThreadPoolExecutor

from disinfo.config import app_config, landscape_path
from disinfo.redis import db
from .utils import home, km_lat, km_lon, local_xy, bearing


version = 3
reach_km = 7
res = 0.05              # degrees a bin
margin = 30             # degrees around the window
bands = (300, 1200, 3500)       # m: the near roofs, the street's, the district's, the city's; then the hills
canopy = 0.1            # degrees over the hills: the town on them
nudge = (30, 5, (0, 1, 2, 3))   # m around the window, the step, m up
seen_tol = 0.15         # degrees: a place this little under a roof still counts as seen
beacon_m = 45           # m tall and up: may have a red light on top at night (the sky view picks)
earth_r = 6371000
ttl = 180 * 24 * 3600
retry = 600
wfs = 'https://data.geopf.fr/wfs/ows'
_loaded = {}
_checked = [0.0]


class Skyline(NamedTuple):
    eye: tuple              # lat, lon, m over the sea
    start: float            # the first bin's bearing
    p: np.ndarray           # (bands + hills, bins): degrees over the horizon, -90 where there's nothing
    seen: list              # per landmark: degrees over what's in front of it
    beacons: list = []      # the tall ones' lights: (bearing, degrees up, m away, m tall)

    def at(self, b: float) -> np.ndarray:
        # Each band at that bearing.
        i = int(((b - self.start) % 360) / res)
        return self.p[:, i] if i < self.p.shape[1] else np.full(len(self.p), -90.0)

    def columns(self, b0: float, step: float, n: int) -> np.ndarray:
        '''(bands, n): the highest in each column step degrees wide from b0, -90 out of it.'''
        edges = ((b0 + np.arange(n + 1) * step - self.start) % 360) / res
        lo, hi = np.floor(edges[:-1]).astype(int), np.maximum(np.ceil(edges[1:]).astype(int), np.floor(edges[:-1]).astype(int) + 1)
        out = np.full((len(self.p), n), -90.0, np.float32)
        ok = (hi <= self.p.shape[1]) & (hi > lo)
        if ok.any():
            # The max over each column's bins: reduceat over their starts.
            idx = np.stack([lo[ok], hi[ok]], 1).ravel()
            idx = np.minimum(idx, self.p.shape[1] - 1)
            red = np.maximum.reduceat(self.p, idx, axis=1)[:, ::2]
            out[:, ok] = red
        return out


def landscape(path=landscape_path) -> tuple[tuple, list]:
    '''The window (lat, lon, m over the sea) and the hills' horizon [(azimuth, altitude)...] from the export.'''
    files = {}
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as z:
            files = {n.split('/')[-1]: z.read(n).decode() for n in z.namelist()}
    else:
        files = {p.name: p.read_text() for p in path.iterdir()}
    c = configparser.ConfigParser()
    c.read_string(files['landscape.ini'])
    loc = c['location']
    eye = float(loc['latitude']), float(loc['longitude']), float(loc['altitude'])
    hills = [tuple(map(float, l.split()[:2])) for l in files.get('horizon.txt', '').splitlines() if l.strip() and not l.startswith('#')]
    return eye, hills

def tiles(ex: float, ey: float) -> list[tuple[int, int]]:
    # The km squares within reach, around the window's bearings.
    start, end = app_config.aviator_window
    span = (end - start) % 360 or 360
    out = []
    n = math.ceil(reach_km)
    for i in range(-n - 1, n + 1):
        for j in range(-n - 1, n + 1):
            x0, y0 = i * 1000 - ex, j * 1000 - ey
            nx, ny = min(max(0, x0), x0 + 1000), min(max(0, y0), y0 + 1000)
            if math.hypot(nx, ny) > reach_km * 1000:
                continue
            if x0 <= 0 <= x0 + 1000 and y0 <= 0 <= y0 + 1000:
                out.append((i, j))
                continue
            corners = [bearing(x0 + dx, y0 + dy) for dx in (0, 500, 1000) for dy in (0, 500, 1000)]
            if any((b - start + margin) % 360 <= span + 2 * margin for b in corners):
                out.append((i, j))
    return out

def fetch(tile: tuple[int, int]) -> list:
    # One km square's buildings: (ring as (lon, lat), roof, roof's top) over the sea, and how tall.
    i, j = tile
    s, w, n, e = home[0] + j / km_lat, home[1] + i / km_lon, home[0] + (j + 1) / km_lat, home[1] + (i + 1) / km_lon
    out, at = [], 0
    while True:
        r = requests.get(wfs, timeout=120, params={
            'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature', 'TYPENAMES': 'BDTOPO_V3:batiment',
            'outputFormat': 'application/json', 'SRSNAME': 'EPSG:4326', 'COUNT': 5000, 'STARTINDEX': at,
            'BBOX': f'{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326'})
        r.raise_for_status()
        fs = r.json()['features']
        for f in fs:
            p, g = f['properties'], f['geometry']
            roof = p['altitude_minimale_toit'] or ((p['altitude_minimale_sol'] or 0) + p['hauteur'] if p['hauteur'] and p['altitude_minimale_sol'] else None)
            if roof is None:
                continue
            for poly in (g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]):
                out.append(([q[:2] for q in poly[0]], roof, p['altitude_maximale_toit'] or roof, p['hauteur'] or 0))
        if len(fs) < 5000:
            return out
        at += 5000

def walls(buildings: list, ex: float, ey: float, targets: list) -> tuple[np.ndarray, list]:
    '''Every wall's top as (x0, y0, x1, y1, m over the sea), m from home. A roof higher than its walls (a mansard,
    a pitched roof) gets its top inside, half the size. The window's own building is left out: one doesn't see it.
    Also the roofs at each target (x, y): the highest within 8 m, None if none.'''
    out, tops = [], [None] * len(targets)
    for ring, roof, top, _ in buildings:
        pts = np.array([local_xy(la, lo) for lo, la in ring]) * 1000
        if len(pts) < 3:
            continue
        a, b = pts[:-1], pts[1:]
        d, r = b - a, a - (ex, ey)
        t = np.clip(-(r * d).sum(1) / np.maximum((d * d).sum(1), 1e-9), 0, 1)
        if np.hypot(*(r + d * t[:, None]).T).min() < 2:
            continue
        lo, hi = pts.min(0) - 8, pts.max(0) + 8
        for k, (tx, ty) in enumerate(targets):
            if lo[0] <= tx <= hi[0] and lo[1] <= ty <= hi[1]:
                tops[k] = max(tops[k] or 0, top)
        out.append(np.column_stack([a, b, np.full(len(a), roof)]))
        if top > roof + 1:
            m = pts.mean(0)
            inner = m + (pts - m) * 0.5
            out.append(np.column_stack([inner[:-1], inner[1:], np.full(len(a), top)]))
    return (np.concatenate(out).astype(np.float32) if out else np.zeros((0, 5), np.float32)), tops

def angle(z, ez: float, t):
    return np.degrees(np.arctan2(z - ez, t) - t / (2 * earth_r))

def profile(w: np.ndarray, ez: float, start: float, n: int, chunk: int = 200_000) -> np.ndarray:
    '''(bands + 1, n): the highest wall top in each bin, by distance band. Each wall crosses the rays of the bins
    between its ends' bearings: where it does, the height it stands.'''
    out = np.full((len(bands) + 2, n), -90.0, np.float32)
    flat = out[:-1].ravel()
    for c in range(0, len(w), chunk):
        x0, y0, x1, y1, z = w[c:c + chunk].T.astype(np.float64)
        a0 = (np.degrees(np.arctan2(x0, y0)) - start) % 360
        a1 = (np.degrees(np.arctan2(x1, y1)) - start) % 360
        lo, hi = np.minimum(a0, a1), np.maximum(a0, a1)
        i0 = np.ceil(lo / res - 0.5).astype(int)
        i1 = np.minimum(np.floor(hi / res - 0.5).astype(int), n - 1)
        keep = (hi - lo < 180) & (i1 >= i0) & (i0 < n)
        x0, y0, x1, y1, z, i0, i1 = (v[keep] for v in (x0, y0, x1, y1, z, i0, i1))
        cnt = i1 - i0 + 1
        e = np.repeat(np.arange(len(cnt)), cnt)
        bins = i0[e] + np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        th = np.radians(start + (bins + 0.5) * res)
        dx, dy = np.sin(th), np.cos(th)
        wx, wy = (x1 - x0)[e], (y1 - y0)[e]
        den = dx * wy - dy * wx
        t = (x0[e] * wy - y0[e] * wx) / np.where(np.abs(den) < 1e-9, 1e-9, den)
        ok = t > 1
        band = np.searchsorted(bands, t[ok])
        np.maximum.at(flat, band * n + bins[ok], angle(z[e][ok], ez, t[ok]).astype(np.float32))
    return out

def blocked(w: np.ndarray, ex: float, ey: float, ez: float, tx: float, ty: float) -> float:
    # The highest wall top (degrees) on the way to (tx, ty), short of its own block.
    x0, y0, x1, y1, z = (w[:, i].astype(np.float64) for i in range(5))
    x0, y0, x1, y1 = x0 - ex, y0 - ey, x1 - ex, y1 - ey
    d = math.hypot(tx - ex, ty - ey)
    dx, dy = (tx - ex) / d, (ty - ey) / d
    wx, wy = x1 - x0, y1 - y0
    den = dx * wy - dy * wx
    den = np.where(np.abs(den) < 1e-9, 1e-9, den)
    t = (x0 * wy - y0 * wx) / den
    s = (x0 * dy - y0 * dx) / den
    hit = (s >= 0) & (s <= 1) & (t > 8) & (t < d - 60)
    return float(angle(z[hit], ez, t[hit]).max()) if hit.any() else -90.0

def margins(w: np.ndarray, ex: float, ey: float, ez: float, targets: list) -> list:
    # Each target's degrees over what's in front of it.
    return [float(angle(tz, ez, math.hypot(tx - ex, ty - ey))) - blocked(w, ex, ey, ez, tx, ty) for tx, ty, tz in targets]

def fit(w: np.ndarray, ex: float, ey: float, ez: float, targets: list) -> tuple[tuple, list]:
    '''The window nudged to see the most targets, then the least hidden, then the least moved.'''
    near = []
    for tx, ty, _ in targets:
        # The walls along the way, wide enough for every nudge.
        d = math.hypot(tx - ex, ty - ey)
        ux, uy = (tx - ex) / d, (ty - ey) / d
        mx, my = (w[:, 0] + w[:, 2]) / 2 - ex, (w[:, 1] + w[:, 3]) / 2 - ey
        along, side = mx * ux + my * uy, np.abs(mx * uy - my * ux)
        half = np.hypot(w[:, 2] - w[:, 0], w[:, 3] - w[:, 1]) / 2
        near.append(w[(along > -50) & (along < d + 50) & (side < nudge[0] + 10 + half)])
    best = None
    r, step, ups = nudge
    for dx in range(-r, r + 1, step):
        for dy in range(-r, r + 1, step):
            for dz in ups:
                ms = [float(angle(tz, ez + dz, math.hypot(tx - ex - dx, ty - ey - dy))) - blocked(nw, ex + dx, ey + dy, ez + dz, tx, ty)
                      for (tx, ty, tz), nw in zip(targets, near)]
                score = (sum(m > -seen_tol for m in ms), sum(min(m + seen_tol, 0) for m in ms), -math.hypot(dx, dy, dz))
                if best is None or score > best[0]:
                    best = score, (dx, dy, dz), ms
    return best[1], best[2]

def beacons(buildings: list, ex: float, ey: float, ez: float, start: float, n: int) -> list:
    # The tall ones, a light on their top each (the tallest of a few close together): (bearing, degrees up, m away, m tall).
    out = []
    for ring, _, top, height in sorted(buildings, key=lambda b: -b[2]):
        if height < beacon_m:
            continue
        x, y = np.array([local_xy(la, lo) for lo, la in ring]).mean(0) * 1000 - (ex, ey)
        b, d = bearing(x, y), math.hypot(x, y)
        if (b - start) % 360 >= n * res or any(abs((b - o[0] + 180) % 360 - 180) < 0.3 and abs(d - o[2]) < 150 for o in out):
            continue
        out.append((round(b, 3), round(float(angle(top + 1, ez, d)), 3), round(d), round(height)))
    return out

def build(path=landscape_path, log=print) -> dict:
    (lat, lon, ez), hills = landscape(path)
    ex, ey = (v * 1000 for v in local_xy(lat, lon))
    marks = [tuple(v * 1000 for v in local_xy(*p)) for p in app_config.screen_data.aviator.landmarks]
    ts = tiles(ex, ey)
    log(f'[skyline] {len(ts)} tiles')
    with ThreadPoolExecutor(4) as ex_:
        buildings = [b for t in ex_.map(fetch, ts) for b in t]
    w, tops = walls(buildings, ex, ey, marks)
    targets = [(x, y, z) for (x, y), z in zip(marks, tops) if z]
    (dx, dy, dz), ms = fit(w, ex, ey, ez, targets) if targets else ((0, 0, 0), [])
    ex, ey, ez = ex + dx, ey + dy, ez + dz
    log(f'[skyline] {len(buildings)} buildings, {len(w)} walls; window moved {dx:+} m E {dy:+} m N {dz:+} m up: '
        f'{sum(m > -seen_tol for m in ms)}/{len(ms)} places seen')
    start, end = app_config.aviator_window
    span = (end - start) % 360 or 360
    start -= margin
    n = int((span + 2 * margin) / res)
    w[:, :4] -= np.array([ex, ey, ex, ey], np.float32)
    p = profile(w, ez, start, n)
    if hills:
        az, alt = np.array(hills).T
        o = np.argsort(az)
        p[-1] = np.interp((start + (np.arange(n) + 0.5) * res) % 360, az[o], alt[o], period=360) + canopy
    return {'eye': [home[0] + ey / 1000 / km_lat, home[1] + ex / 1000 / km_lon, ez], 'start': start,
            'p': np.round(p * 100).astype(int).tolist(), 'seen': [round(m, 2) for m in ms], 'beacons': beacons(buildings, ex, ey, ez, start, n)}

def key(path=landscape_path) -> str:
    h = hashlib.sha1(path.read_bytes() + json.dumps([app_config.aviator_window, app_config.screen_data.aviator.landmarks]).encode())
    return f'di.skyline.{version}.{h.hexdigest()[:12]}'

def of(doc: dict) -> Skyline:
    return Skyline(tuple(doc['eye']), doc['start'], np.array(doc['p'], np.float32) / 100, doc['seen'], doc.get('beacons', []))

def ask(k: str):
    # One process builds it (the lock is in redis), the others find it there.
    if not db.set(f'{k}.lock', 1, nx=True, ex=retry):
        return
    def run():
        try:
            db.set(k, json.dumps(build()), ex=ttl)
        except Exception as e:
            print(f'[skyline] {e}')
    threading.Thread(target=run, daemon=True).start()

def get(now: float) -> Skyline | None:
    '''The roofline, None until it's built (or without a landscape): looked for again every 20 s.'''
    if 'sky' in _loaded:
        return _loaded['sky']
    if now - _checked[0] < 20 or not landscape_path.exists():
        return None
    _checked[0] = now
    k = key()
    if v := db.get(k):
        _loaded['sky'] = of(json.loads(v))
        return _loaded['sky']
    ask(k)
    return None


if __name__ == '__main__':
    t = time.monotonic()
    doc = build()
    db.set(key(), json.dumps(doc), ex=ttl)
    print(f'[skyline] built in {time.monotonic() - t:.0f} s; seen:', ' '.join(f'{m:+.1f}' for m in doc['seen']))
