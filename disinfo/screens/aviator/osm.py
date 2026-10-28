'''Land around home from OpenStreetMap (Overpass): greenery, water, built-up areas, the motorways.

Asked once per place and group, kept in redis for months. Fetched in a thread: the map fills in when it's there.
The shapes are simplified and snapped to 45 degrees (shapes.py), in km east and north of home.
'''
import json
import math
import re
import time
import threading
import requests

from typing import NamedTuple
from PIL import ImageColor

from disinfo.config import app_config
from disinfo.redis import db
from .shapes import simplify, octilinear, area, length, chains
from .utils import local_xy


reach_km = 80           # around home: past the planes' 60 km, the corners of a wide view too
old_reach_km = 50       # shown until the bigger one is fetched
ttl = 90 * 24 * 3600
retry = 600             # s before asking again after a failure
# km, the shapes stay that close to the real ones: the built-up areas are the loosest, they're only a tint.
tolerance = {'builtup': 0.6, 'green': 0.3, 'water': 0.2, 'river': 0.2, 'coast': 0.4, 'motorway': 0.3, 'metro': 0.15, 'rer': 0.2}
version = 1

# group -> (the Overpass selectors, a query each for ways and for relations)
groups = {
    'builtup': ['["landuse"~"^(residential|commercial|industrial|retail)$"]'],
    'green': ['["leisure"="park"]', '["landuse"~"^(forest|meadow|grass)$"]', '["natural"="wood"]'],
    'water': ['["natural"="water"]', '["waterway"="riverbank"]', '["waterway"="river"]', '["natural"="coastline"]'],
    'road': ['["highway"="motorway"]'],
}
# The transit lines are routes (relations, no ways of their own): metro, and the suburban trains (RER, S-Bahn).
transit = {'rail': ['["route"="subway"]', '["route"="train"]["name"~"RER|S-Bahn"]']}
# Smaller than that is left out: km2 for an area, km for a line.
areas_kinds = {'builtup', 'green', 'water'}
min_size = {'builtup': 1.0, 'green': 0.2, 'water': 0.05, 'river': 1.0, 'coast': 2.0, 'motorway': 2.0, 'metro': 1.0, 'rer': 2.0}
_pending = set()
_turn = threading.Lock()
_loaded = {}            # group -> features
_interim = {}           # group -> the old reach's features, meanwhile
_checked = {}           # group -> when we last looked in redis


class Feature(NamedTuple):
    kind: str
    size: float                 # km2 or km
    parts: list                 # rings or the line: [(x, y)...] in km
    bbox: tuple                 # x0, y0, x1, y1
    color: tuple | None = None  # r, g, b of a line that has its own
    ends: tuple = ()            # where its dots go: (x, y)...


def refine(pts: list, kind: str) -> list | None:
    # Fewer points, 45 degree edges. None when nothing's left of it.
    tol, closed = tolerance[kind], kind in areas_kinds
    pts = simplify(pts + pts[:1], tol)[:-1] if closed else simplify(pts, tol)
    if len(pts) < (3 if closed else 2) or (closed and area(pts) < tol ** 2):
        return None
    out = octilinear(pts, closed)
    return out if len(out) >= (3 if closed else 2) else None

def feature_of(f: dict) -> Feature | None:
    # Cached with an earlier tolerance: simplified again, a no-op when it's the same.
    parts = [r for part in f['p'] if (r := refine([tuple(p) for p in part], f['k']))]
    if not parts:
        return None
    xs, ys = [x for p in parts for x, _ in p], [y for p in parts for _, y in p]
    return Feature(f['k'], f['s'], parts, (min(xs), min(ys), max(xs), max(ys)), tuple(f['c']) if f.get('c') else None, tuple(tuple(e) for e in f.get('e', ())))


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

def transit_kind(tags: dict) -> str | None:
    if tags.get('route') == 'subway':
        return 'metro'
    if tags.get('route') == 'train' and re.search(r'RER|S-Bahn', f"{tags.get('name', '')} {tags.get('network', '')}"):
        return 'rer'
    return None

def rgb_of(name: str | None) -> tuple | None:
    # OSM's colour: a hex or a CSS name.
    try:
        return tuple(round(c / 255, 2) for c in ImageColor.getrgb(name)) if name else None
    except ValueError:
        return None

def near(p: tuple, line: list, d: float) -> bool:
    # p within d of the line.
    for (ax, ay), (bx, by) in zip(line, line[1:]):
        dx, dy = bx - ax, by - ay
        t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
        if math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy) <= d:
            return True
    return False

def lines_of(elements: list) -> list[dict]:
    '''The transit lines: the ways of all the routes of one line (both directions, the variants) joined, a dot at the
    ends that aren't on another piece of it (a branch's end is the line's too, its start isn't).'''
    found = {}      # (kind, line) -> [colour, {way: geometry}]
    for e in elements:
        if e['type'] != 'relation' or not (kind := transit_kind(tags := e.get('tags', {}))):
            continue
        line = found.setdefault((kind, tags.get('ref') or tags.get('name') or str(e['id'])), [rgb_of(tags.get('colour')), {}])
        line[0] = line[0] or rgb_of(tags.get('colour'))
        for m in e.get('members', []):
            if m['type'] == 'way' and m.get('role', '') in ('', 'forward', 'backward') and (g := geometry(m.get('geometry'))):
                line[1][m['ref']] = g
    out = []
    for (kind, _), (color, ways) in found.items():
        pieces = []
        for c in chains(list(ways.values())):
            pts = [local_xy(la, lo) for la, lo in c]
            if length(pts) >= min_size[kind] and (r := refine(pts, kind)):
                pieces.append(r)
        ends = [pt for i, r in enumerate(pieces) for pt in (r[0], r[-1])
                if not any(near(pt, o, 0.3) for j, o in enumerate(pieces) if j != i)]
        if pieces:
            out.append({'k': kind, 's': round(sum(length(r) for r in pieces), 1), 'p': pieces, 'c': color, 'e': ends})
    return out

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
            parts = [r for ring in rings + holes if len(ring) > 2 and (r := refine(km(ring[:-1] if ring[0] == ring[-1] else ring), kind))]
            if parts:
                out.append({'k': kind, 's': round(size, 2), 'p': parts})
    for kind, ways in lines.items():
        for line in chains(ways):
            pts = km(line)
            size = length(pts)
            if size >= min_size[kind] and (r := refine(pts, kind)):
                out.append({'k': kind, 's': round(size, 1), 'p': [r]})
    out += lines_of(elements)
    for f in out:
        f['p'] = [[(round(x, 2), round(y, 2)) for x, y in p] for p in f['p']]
        if f.get('e'):
            f['e'] = [(round(x, 2), round(y, 2)) for x, y in f['e']]
    return out

def query(group: str) -> str:
    la, lo = app_config.latitude, app_config.longitude
    dla = reach_km / 110.574
    dlo = reach_km / (111.320 * math.cos(math.radians(la)))
    box = f'({la - dla:.4f},{lo - dlo:.4f},{la + dla:.4f},{lo + dlo:.4f})'
    if group in transit:
        sel = ''.join(f'relation{s}[type=route]{box};' for s in transit[group])
    else:
        sel = ''.join(f'way{s}{box};relation{s}[type=multipolygon]{box};' for s in groups[group])
    return f'[out:json][timeout:180];({sel});out geom;'

def key(group: str, reach: float = reach_km) -> str:
    return f'di.osm.{version}.{group}.{app_config.latitude:.3f},{app_config.longitude:.3f}.{reach}'

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
    for group in [*groups, *transit]:
        if group not in _loaded and now - _checked.get(group, 0) > 20:
            _checked[group] = now
            if v := db.get(key(group)):
                _loaded[group] = [x for f in json.loads(v) if (x := feature_of(f))]
                _interim.pop(group, None)
            else:
                ask(group)
                if group not in _interim and (v := db.get(key(group, old_reach_km))):
                    _interim[group] = [x for f in json.loads(v) if (x := feature_of(f))]
        out += _loaded.get(group) or _interim.get(group, [])
    return out
