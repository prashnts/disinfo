'''Land around home from OpenStreetMap (Overpass): greenery, water, built-up areas, the motorways.

Asked once per place and group, kept in redis for months. Fetched in a thread: the map fills in when it's there.
The shapes are simplified and snapped to 45 degrees (shapes.py), in km east and north of home.
'''
import json
import math
import time
import threading
import requests

from typing import NamedTuple

from disinfo.config import app_config
from disinfo.redis import db
from .shapes import simplify, octilinear, area, length, chains
from .utils import local_xy


reach_km = 50           # around home
ttl = 90 * 24 * 3600
retry = 600             # s before asking again after a failure
tolerance = 0.25        # km, the shapes stay that close to the real ones
version = 1

# group -> (the Overpass selectors, a query each for ways and for relations)
groups = {
    'builtup': ['["landuse"~"^(residential|commercial|industrial|retail)$"]'],
    'green': ['["leisure"="park"]', '["landuse"~"^(forest|meadow|grass)$"]', '["natural"="wood"]'],
    'water': ['["natural"="water"]', '["waterway"="riverbank"]', '["waterway"="river"]', '["natural"="coastline"]'],
    'road': ['["highway"="motorway"]'],
}
# Smaller than that is left out: km2 for an area, km for a line.
min_size = {'builtup': 1.0, 'green': 0.2, 'water': 0.05, 'river': 1.0, 'coast': 2.0, 'motorway': 2.0}
_pending = set()
_turn = threading.Lock()
_loaded = {}            # group -> features
_checked = {}           # group -> when we last looked in redis


class Feature(NamedTuple):
    kind: str
    size: float                 # km2 or km
    parts: list                 # rings or the line: [(x, y)...] in km
    bbox: tuple                 # x0, y0, x1, y1


def feature_of(f: dict) -> Feature:
    parts = [[tuple(p) for p in part] for part in f['p']]
    xs, ys = [x for p in parts for x, _ in p], [y for p in parts for _, y in p]
    return Feature(f['k'], f['s'], parts, (min(xs), min(ys), max(xs), max(ys)))


def classify(tags: dict, relation: bool) -> tuple[str, bool] | None:
    # (kind, is an area), None for what the map leaves out.
    if tags.get('natural') == 'water' or tags.get('waterway') == 'riverbank':
        return 'water', True
    if tags.get('waterway') == 'river' and not relation:
        return 'river', False
    if tags.get('natural') == 'coastline' and not relation:
        return 'coast', False
    if tags.get('leisure') == 'park' or tags.get('landuse') in ('forest', 'meadow', 'grass') or tags.get('natural') == 'wood':
        return 'green', True
    if tags.get('landuse') in ('residential', 'commercial', 'industrial', 'retail'):
        return 'builtup', True
    if tags.get('highway') == 'motorway' and not relation:
        return 'motorway', False
    return None

def geometry(g: list) -> list:
    return [(p['lat'], p['lon']) for p in g or [] if p]

def build(elements: list) -> list[dict]:
    '''Overpass elements (out geom) as simplified features: {'k': kind, 's': size, 'p': [[(x, y)...]...]}.'''
    areas, lines = {}, {}      # kind -> ways (lat, lon); an area: [outer ways, inner ways]
    for e in elements:
        c = classify(e.get('tags', {}), e['type'] == 'relation')
        if not c:
            continue
        kind, is_area = c
        if e['type'] == 'way':
            if g := geometry(e.get('geometry')):
                if is_area:
                    if g[0] == g[-1]:
                        areas.setdefault(kind, []).append(([g], []))
                else:
                    lines.setdefault(kind, []).append(g)
        elif is_area:
            outer = [g for m in e.get('members', []) if m['role'] != 'inner' and len(g := geometry(m.get('geometry'))) > 1]
            inner = [g for m in e.get('members', []) if m['role'] == 'inner' and len(g := geometry(m.get('geometry'))) > 1]
            if outer:
                areas.setdefault(kind, []).append((outer, inner))

    def km(pts):
        return [local_xy(la, lo) for la, lo in pts]

    out = []
    for kind, shapes in areas.items():
        for outer, inner in shapes:
            rings = [r for r in chains(outer)]
            holes = [r for r in chains(inner)]
            size = sum(area(km(r)) for r in rings) - sum(area(km(r)) for r in holes)
            if size < min_size[kind]:
                continue
            parts = []
            for r in rings + holes:
                if len(r) > 2:
                    ring = simplify(km(r), tolerance)[:-1] if r[0] == r[-1] else simplify(km(r), tolerance)
                    if len(ring) > 2 and area(ring) > tolerance ** 2:
                        parts.append(octilinear(ring, closed=True))
            if parts:
                out.append({'k': kind, 's': round(size, 2), 'p': parts})
    for kind, ways in lines.items():
        for line in chains(ways):
            pts = km(line)
            size = length(pts)
            if size >= min_size[kind]:
                out.append({'k': kind, 's': round(size, 1), 'p': [octilinear(simplify(pts, tolerance))]})
    for f in out:
        f['p'] = [[(round(x, 2), round(y, 2)) for x, y in p] for p in f['p']]
    return out

def query(group: str) -> str:
    la, lo = app_config.latitude, app_config.longitude
    dla = reach_km / 110.574
    dlo = reach_km / (111.320 * math.cos(math.radians(la)))
    box = f'({la - dla:.4f},{lo - dlo:.4f},{la + dla:.4f},{lo + dlo:.4f})'
    sel = ''.join(f'way{s}{box};relation{s}[type=multipolygon]{box};' for s in groups[group])
    return f'[out:json][timeout:180];({sel});out geom;'

def key(group: str) -> str:
    return f'di.osm.{version}.{group}.{app_config.latitude:.3f},{app_config.longitude:.3f}.{reach_km}'

def fetch(group: str) -> list[dict]:
    r = requests.post(app_config.overpass_url, data={'data': query(group)}, timeout=240,
                      headers={'User-Agent': 'disinfo (+https://github.com/prashnts/disinfo)'})
    r.raise_for_status()
    return build(r.json()['elements'])

def ask(group: str):
    # One process asks (the lock is in redis), the others find it in redis when it's done.
    if group in _pending or not db.set(f'{key(group)}.lock', 1, nx=True, ex=retry):
        return
    _pending.add(group)

    def run():
        # One at a time, with a pause: Overpass answers 429 to a burst.
        with _turn:
            try:
                db.set(key(group), json.dumps(fetch(group)), ex=ttl)
            except Exception as e:
                print(f'[osm] {group}: {e}')
            finally:
                _pending.discard(group)
                time.sleep(10)
    threading.Thread(target=run, daemon=True).start()

def features(now: float) -> list[Feature]:
    '''All there is, groups still missing are asked for and looked for again every 20 s.'''
    out = []
    for group in groups:
        if group not in _loaded and now - _checked.get(group, 0) > 20:
            _checked[group] = now
            if v := db.get(key(group)):
                _loaded[group] = [feature_of(f) for f in json.loads(v)]
            else:
                ask(group)
        out += _loaded.get(group, [])
    return out
