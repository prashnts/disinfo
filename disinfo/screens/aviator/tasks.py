import json
import math
import time
import requests

from disinfo.config import app_config
from disinfo.redis import db, publish
from .utils import Airport, airports, local_xy, closest_approach, elevation, bearing, in_window


TABLE_KEY = 'di.aviator.table'
RADIUS_KEY = 'di.aviator.radius'      # km, set from the web page: how far the radar shows and cards go
# Only planes within this of home are kept, the receiver sees ~300 km around.
keep_km = 60
trail_every = 5         # s between trail points
trail_len = 120         # points: 10 minutes
forget_after = 60       # s without a position
# Overhead: degrees above the horizon, now or at the closest approach within lookahead. Seen from anywhere.
overhead_deg = 60
lookahead = 150
passed_for = 60         # s a pass stays 'overhead' after it
# Seen from the window: in its bearings, above the roofs, not too far. The nearest ones are watched.
min_elev = 2
radius_km = 40
max_watched = 2
# A queue: planes low around an airport, climbing or descending.
queue_km = 15
queue_alt = 1800
queue_min = 4

table: dict[str, dict] = {}


def load_table():
    global table
    try:
        table = json.loads(db.get(TABLE_KEY) or '{}')['planes']
    except (KeyError, ValueError):
        table = {}

def fetch_planes() -> tuple[float, list]:
    r = requests.get(f'{app_config.adsbx_url}/data/aircraft.json', timeout=3)
    r.raise_for_status()
    data = r.json()
    return data['now'], data['aircraft']

def plane_of(p: dict, at: float) -> dict | None:
    if 'lat' not in p or 'alt_baro' not in p:
        return None
    x, y = local_xy(p['lat'], p['lon'])
    dist = math.hypot(x, y)
    if dist > keep_km:
        return None
    ground = p['alt_baro'] == 'ground'
    alt = 0 if ground else round(p['alt_baro'] * 0.3048)
    return {
        'hex': p['hex'],
        'flight': (p.get('flight') or '').strip(),
        'r': p.get('r'),
        't': p.get('t'),
        'desc': p.get('desc'),
        'cat': p.get('category'),
        'squawk': p.get('squawk'),
        'lat': p['lat'],
        'lon': p['lon'],
        'alt': alt,
        'ground': ground,
        'gs': round(p.get('gs', 0) * 1.852),                    # km/h
        'track': p.get('track', p.get('true_heading', 0)),
        'vr': round((p.get('baro_rate') or p.get('geom_rate') or 0) * 0.3048),  # m/min
        'at': at - p.get('seen_pos', 0),
        'x': round(x, 3),
        'y': round(y, 3),
        'dist': round(dist, 3),
        'slant': round(math.hypot(dist, alt / 1000), 3),
        'bearing': round(bearing(x, y)),
        'elev': round(elevation(alt, dist), 1),
    }

def update(now: float, aircraft: list):
    for p in aircraft:
        plane = plane_of(p, now)
        if not plane:
            continue
        prev = table.get(plane['hex'], {})
        trail = prev.get('trail', [])
        if not trail or plane['at'] - trail[-1][0] >= trail_every:
            trail = (trail + [[round(plane['at'], 1), plane['lat'], plane['lon'], plane['alt']]])[-trail_len:]
        plane['trail'] = trail
        # The flight and db fields come and go between messages.
        for k in ('flight', 'r', 't', 'desc', 'cat', 'squawk'):
            plane[k] = plane[k] or prev.get(k)
        plane['cpa'] = closest_approach(plane, lookahead)
        plane['overhead_at'] = prev.get('overhead_at')
        if max(plane['elev'], plane['cpa']['elev']) >= overhead_deg and not plane['ground']:
            plane['overhead_at'] = now
        table[plane['hex']] = plane

    for hex in [h for h, p in table.items() if now - p['at'] > forget_after]:
        del table[hex]

def is_overhead(p: dict, now: float) -> bool:
    return bool(p.get('overhead_at')) and now - p['overhead_at'] < passed_for

def radius() -> float:
    try:
        return float(db.get(RADIUS_KEY) or radius_km)
    except ValueError:
        return radius_km

def is_visible(p: dict, r: float) -> bool:
    return not p['ground'] and in_window(p['bearing']) and p['elev'] >= min_elev and p['slant'] <= r

_watched = []

def watched(now: float, r: float) -> list[str]:
    # Overhead ones, then the nearest seen from the window. A plane keeps its card while it's seen.
    global _watched
    seen = sorted((h for h, p in table.items() if is_visible(p, r)), key=lambda h: table[h]['slant'])
    overhead = [h for h, p in table.items() if is_overhead(p, now)]
    kept = [h for h in _watched if h in seen or h in overhead]
    _watched = list(dict.fromkeys([*overhead, *kept, *seen]))[:max(max_watched, len(overhead))]
    return _watched

def nearest_airport(p: dict) -> tuple[float, Airport]:
    return min((math.hypot(p['x'] - a.x, p['y'] - a.y), a) for a in airports)

def queues() -> dict[str, list[str]]:
    # Planes low around their nearest airport, climbing or descending. CDG and LBG are 9 km apart.
    q = {a.code: [] for a in airports}
    for h, p in table.items():
        d, a = nearest_airport(p)
        if d < queue_km and not p['ground'] and p['alt'] < queue_alt and abs(p['vr']) > 60:
            q[a.code].append(h)
    return q

_queue_focus = None

def scene(now: float) -> dict:
    # What's worth looking at: the planes seen from the window, then the airports in order.
    # An airport keeps the focus until its queue is a plane under: counts hover around queue_min.
    global _queue_focus
    r = radius()
    watch = watched(now, r)
    q = queues()
    if not (_queue_focus and len(q[_queue_focus]) >= queue_min - 1):
        _queue_focus = next((a.code for a in airports if len(q[a.code]) >= queue_min), None)
    focus = 'home' if watch else _queue_focus
    return {'focus': focus, 'watched': watch, 'queues': q, 'radius': r}

def adsbx_task():
    now, aircraft = fetch_planes()
    if not table:
        load_table()
    update(now, aircraft)
    state = {'now': now, 'planes': table, **scene(now)}
    db.set(TABLE_KEY, json.dumps(state), ex=300)
    publish('di.pubsub.aviator', action='update', payload={'now': now})
