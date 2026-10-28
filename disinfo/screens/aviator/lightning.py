'''Lightning around home: Blitzortung's strikes (Home Assistant's geo_location, 100 km, 2 h) and Sensei's AS3935 by
the window, together.

The data service keeps them in redis and says when it changed; the sky view flashes each strike as it comes, where
it is, and comes on while there's a storm (app.view_mode).

Sensei hears up to ~40 km at once, but not where: its flash lights the whole sky. Blitzortung comes seconds later
with the place: a strike within match_s of a hit is the one Sensei heard (its bolt shows where that flash was).
Sensei's distance is to the storm's front (1: overhead, 63: out of range): the cell it fits gets its mark. A hit
without strikes around is noise (a motor, the purifier): kept, never drawn.
'''
import json
import math
import time
import random
import datetime as dt
import threading
import cairocffi as cairo

from functools import cache

from discore.text import TextStyle, text
from disinfo import fonts
from disinfo.config import app_config
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage
from disinfo.redis import db, publish

from .utils import local_xy, bearing

KEY = 'di.lightning'    # {at, ids, s: [[t, seen, bearing, km, heard, demo]], hits: [[t, km, energy, matched, real, demo]]}
CHANNEL = 'di.pubsub.lightning'
window_s = 7200         # Blitzortung's time window: kept that long
ticks_s = 300           # each strike leaves a tick under the cloud, fading this long; the heard ones a plus, a minute
keep = 800              # strikes at most
match_s = 1.5           # s between a hit and a strike: the same one
hears_km = 40           # Sensei's reach
around_km = 100
around_s = 3600         # a hit counts with a strike this recent around, else noise
storm_s = 600           # a strike this recent (two, or a hit): a storm on
cell_km = 15            # strikes this close: one cell
cell_s = 1800
flash_s = 1.2           # s a flash flickers and fades
thunder_km = 15         # heard from there, and shakes the roofs
sound_kms = 0.343
base_m, mid_m, anvil_m, top_m = 1500, 5000, 7500, 11500     # a cumulonimbus: its base, its heart, the anvil's underside, top
front_far = 63          # the AS3935's 'out of range'
flash_rgb = (0.86, 0.84, 1.0)   # near: white-violet
far_rgb = (1.0, 0.78, 0.86)     # far: through more air, pinker
sensei_rgb = (0.45, 0.85, 0.9)
# Blitzortung's map colours by age.
ages = ((60, (1, 1, 1)), (600, (1, 0.95, 0.3)), (1800, (1, 0.6, 0.15)), (3600, (0.9, 0.25, 0.12)), (7200, (0.5, 0.12, 0.1)))
label_style = TextStyle(font=fonts.microfont_35_reg, color='#c9c3e8c0')
sensei_style = TextStyle(font=fonts.microfont_35_reg, color='#73d9e6d0')
# The receiver: ((•))
glyph = ('.#...#.', '#..#..#', '#.###.#', '#..#..#', '.#...#.')


# The data service's side.

_lock = threading.RLock()
_doc = None
_hits = []              # Sensei's hits as they come (HA's thread), waiting for the task
_listening = False

def load() -> dict:
    try:
        d = json.loads(db.get(KEY) or 'null')
    except ValueError:
        d = None
    return d or {'at': 0, 'ids': [], 's': [], 'hits': []}

def when(v) -> float | None:
    try:
        return dt.datetime.fromisoformat(str(v)).timestamp()
    except ValueError:
        return None

def on_event(event):
    # HA's thread: a hit flashes on the screens at once, the task files it.
    e, s = event.data.entity_id, event.data.new_state
    if s and e == app_config.lightning_alert and s.state == 'on':
        t = event.time_fired.timestamp()
        _hits.append(t)
        publish(CHANNEL, action='hit', payload={'t': t})
        task()
    elif s and e.startswith('geo_location.lightning_strike_') and not (event.data.old_state):
        task()

def number(name: str) -> float | None:
    from disinfo.utils.hass import get_entity
    try:
        return float(get_entity(name).state)
    except (AttributeError, TypeError, ValueError):
        return None

def task(fake: list = ()):
    '''New strikes from HA (or fake ones: the demo), Sensei's hits filed and matched.'''
    global _doc, _listening
    from disinfo.utils.hass import get_entities, HaWS
    if not _listening:
        HaWS().client.listeners.append(on_event)
        _listening = True
    with _lock:
        if _doc is None:
            # A demo cut short (a restart) leaves none behind.
            _doc = load()
            _doc['s'], _doc['hits'] = [s for s in _doc['s'] if not s[5]], [h for h in _doc['hits'] if not h[5]]
        d = _doc
        now, ids, changed = time.time(), set(d['ids']), False
        for e in get_entities(r'geo_location\.lightning_strike_'):
            a = e.attributes or {}
            sid = a.get('external_id') or e.entity_id
            if sid in ids or a.get('source') != 'blitzortung' or 'latitude' not in a:
                continue
            x, y = local_xy(a['latitude'], a['longitude'])
            ids.add(sid)
            d['ids'].append(sid)
            d['s'].append([when(a.get('publication_date')) or e.last_changed.timestamp(), now, round(bearing(x, y), 2), round(math.hypot(x, y), 2), None, 0])
            changed = True
        for t, b, km in fake:
            d['s'].append([t, now, b, km, None, 1])
            changed = True
        while _hits:
            t = _hits.pop(0)
            real = any(now - s[0] < around_s and s[3] < around_km for s in d['s'])
            d['hits'].append([t, number(app_config.lightning_distance), number(app_config.lightning_energy), False, real, 0])
            changed = True
        # Matched: the strike nearest in time to each hit, near enough for Sensei to hear.
        for h in d['hits']:
            if h[3] or now - h[0] > 120:
                continue
            near = [s for s in d['s'] if s[4] is None and abs(s[0] - h[0]) < match_s and s[3] < hears_km * 1.5]
            if near:
                s = min(near, key=lambda s: abs(s[0] - h[0]))
                s[4], h[3], h[4] = h[0], True, True
                changed = True
        d['s'] = [s for s in d['s'] if now - s[0] < window_s][-keep:]
        d['hits'] = [h for h in d['hits'] if now - h[0] < window_s][-200:]
        d['ids'] = d['ids'][-keep * 2:]
        if changed or now - d['at'] > 60:
            d['at'] = now
            db.set(KEY, json.dumps(d), ex=window_s)
            publish(CHANNEL, action='update')

def demo(span: float = 150):
    '''A storm passing a few km off, SW to NE: Blitzortung's strikes come 3-6 s late, Sensei hears the near ones at
    once (its distance to the front). Cleared a minute after.'''
    def run():
        r, t0 = random.Random(), time.time()
        a, b = (-32, -26), (26, 18)
        while (u := time.time() - t0) < span:
            k = u / span
            cx, cy = a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
            x, y = cx + r.gauss(0, 3), cy + r.gauss(0, 3)
            t, km = time.time(), math.hypot(x, y)
            if km < hears_km and r.random() < 0.7:
                front = min(math.hypot(cx, cy) - 4, km)
                buckets = (1, 5, 6, 8, 10, 12, 14, 17, 20, 24, 27, 31, 34, 37, 40)
                _hits.append(t)
                publish(CHANNEL, action='hit', payload={'t': t})
                with _lock:
                    task()
                    _doc['hits'][-1][1:3] = next((v for v in buckets if v >= front), front_far), r.randint(20000, 900000)
                    _doc['hits'][-1][5] = 1
            threading.Timer(r.uniform(3, 6), task, kwargs={'fake': [(t, round(bearing(x, y), 2), round(km, 2))]}).start()
            time.sleep(r.expovariate(0.5 + 1.5 * math.sin(math.pi * k)))
        time.sleep(60)
        with _lock:
            d = _doc or load()
            d['s'] = [s for s in d['s'] if not s[5]]
            d['hits'] = [h for h in d['hits'] if not h[5]]
            d['at'] = 0
        task()
    threading.Thread(target=run, daemon=True).start()


# The renderers' side.

class LightningState(AppBaseModel):
    s: list[list] = []
    hits: list[list] = []
    live: list[float] = []      # hits as they came, here: [when]
    news: float = 0             # monotonic: something new to draw

class LightningStateManager(PubSubStateManager[LightningState]):
    model = LightningState
    channels = (CHANNEL,)

    def initial_state(self) -> LightningState:
        d = load()
        return LightningState(s=d['s'], hits=d['hits'])

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            d = load()
            self.state.s, self.state.hits = d['s'], d['hits']
        elif data.action == 'hit':
            self.state.live = [t for t in self.state.live if time.time() - t < 10] + [time.time()]
        self.state.news = time.monotonic()

def state() -> LightningState:
    return LightningStateManager().get_state()

def news() -> float:
    return state().news

def storm(now: float) -> float | None:
    '''When the storm going on started: two strikes around within storm_s, or a real hit; None without one. Its start
    goes back while the strikes kept coming.'''
    st = state()
    ts = sorted([s[0] for s in st.s if s[3] < around_km] + [h[0] for h in st.hits if h[4]])
    recent = [t for t in ts if now - t < storm_s]
    if len(recent) < 2 and not any(h[4] and now - h[0] < storm_s for h in st.hits):
        return None
    start = recent[0]
    for t in reversed([t for t in ts if t < start]):
        if start - t > storm_s:
            break
        start = t
    return start

def real_live(st: LightningState, now: float) -> list[float]:
    # Hits just in: drawn only with strikes around (else noise).
    around = any(now - s[0] < around_s and s[3] < around_km for s in st.s)
    return [t for t in st.live if now - t < flash_s] if around else []

def cells(st: LightningState, now: float) -> list[dict]:
    '''The storm cells: strikes within cell_s, greedily together within cell_km. {b, km (the centre), near (the
    nearest strike), wide (km across), n, last}.'''
    pts = [(s[3] * math.sin(math.radians(s[2])), s[3] * math.cos(math.radians(s[2])), s) for s in st.s if now - s[0] < cell_s]
    out = []
    for x, y, s in sorted(pts, key=lambda p: -p[2][0]):
        c = next((c for c in out if math.hypot(c['x'] - x, c['y'] - y) < cell_km), None)
        if c is None:
            out.append(c := {'x': x, 'y': y, 'pts': []})
        c['pts'].append((x, y, s))
        c['x'] = sum(p[0] for p in c['pts']) / len(c['pts'])
        c['y'] = sum(p[1] for p in c['pts']) / len(c['pts'])
    for c in out:
        xs, ys = [p[0] for p in c['pts']], [p[1] for p in c['pts']]
        c.update(b=bearing(c['x'], c['y']), km=max(math.hypot(c['x'], c['y']), 0.5), near=min(p[2][3] for p in c['pts']),
                 wide=max(max(xs) - min(xs), max(ys) - min(ys), 6), n=len(c['pts']), last=max(p[2][0] for p in c['pts']),
                 seed=round(c['pts'][-1][2][0] * 10) % 100000)
    return [c for c in out if c['n'] >= 3 or now - c['last'] < 120]

def front(st: LightningState, now: float) -> tuple[float, float] | None:
    # Sensei's last distance to the storm, and when: real hits only, the last half hour.
    h = next((h for h in reversed(st.hits) if h[4] and h[1] is not None), None)
    return (h[1], h[0]) if h and now - h[0] < cell_s else None

def heard_cell(cs: list[dict], fr: tuple | None) -> dict | None:
    # The cell Sensei's front fits: its nearest strike within the AS3935's buckets' slack.
    if not fr or fr[0] >= front_far:
        return None
    fit = [c for c in cs if c['near'] < hears_km and abs(c['near'] - fr[0]) < max(4, fr[0] * 0.4)]
    return min(fit, key=lambda c: abs(c['near'] - fr[0])) if fit else None

def aim(now: float, fov: float) -> tuple[float, float] | None:
    '''(yaw, fov) on the storm: the recent strikes, the near and new ones counting most, wide enough for most.'''
    st = state()
    pts = [s for s in st.s if now - s[0] < storm_s and s[3] < around_km]
    if not pts:
        return None
    ws = [(1 / (1 + s[3] / 20)) * (1.5 - (now - s[0]) / storm_s) for s in pts]
    yaw = math.degrees(math.atan2(sum(w * math.sin(math.radians(s[2])) for w, s in zip(ws, pts)),
                                  sum(w * math.cos(math.radians(s[2])) for w, s in zip(ws, pts)))) % 360
    off = sorted(abs((s[2] - yaw + 180) % 360 - 180) for s in pts)
    return yaw, min(max(fov, 2 * off[int(len(off) * 0.8)] + 20), 140)

@cache
def bolt(seed: int) -> tuple:
    '''A bolt from the cloud base (0, 0) to the ground (x, 1), x in units of its height; then its branches.'''
    r = random.Random(seed)
    n = 16
    x, main = 0.0, [(0.0, 0.0)]
    for i in range(1, n + 1):
        x += r.uniform(-0.07, 0.07)
        main.append((x, i / n))
    branches = []
    for _ in range(r.choice((1, 2, 2, 3, 4))):
        i = r.randint(2, n // 2 + 2)
        side, (bx, by), br = r.choice((-1, 1)), main[i], []
        for k in range(r.randint(3, 7)):
            bx += side * r.uniform(0.02, 0.08)
            by += r.uniform(0.02, 0.06)
            br.append((bx, by))
        branches.append(((main[i]), *br))
    return tuple(main), tuple(branches)

@cache
def strokes(seed: int) -> tuple[float, ...]:
    # The return strokes down the same channel, 40-120 ms apart.
    r = random.Random(seed * 7 + 1)
    t, out = 0.0, [0.0]
    for _ in range(r.choice((0, 1, 1, 2, 2, 3))):
        t += r.uniform(0.04, 0.12)
        out.append(t)
    return tuple(out)

def level(u: float, seed: int) -> float:
    return max((math.exp(-(u - s) / 0.06) for s in strokes(seed) if u >= s), default=0.0)

def tint(km: float) -> tuple:
    k = min(km / 80, 1)
    return tuple(a + (b - a) * k for a, b in zip(flash_rgb, far_rgb))

def age_color(age: float) -> tuple:
    return next((c for a, c in ages if age < a), ages[-1][1])

def seed_of(s: list) -> int:
    return int(s[0] * 1000) % 1000003

def back(ctx: cairo.Context, now: float, yaw: float, fov: float, sky_point, to_px, in_view, w: int, hz: int,
         cloud_rgb: tuple, night: float, cover: float, info: bool) -> dict:
    '''Behind the roofs: the cells' towers, the strikes so far, the flashes and the sky they light. Returns what the
    front needs: {light (the sky lit, 0..1), near (how near the brightest, km), cells, busy}.'''
    st = state()
    cs = cells(st, now)
    at = lambda b, km, alt: to_px(b, sky_point(km * math.sin(math.radians(b)), km * math.cos(math.radians(b)), alt)[1])
    lit = {}    # cell seed -> (how much it's lit now, from where)

    flashes = []
    for s in st.s:
        u = now - s[1]
        if 0 <= u < flash_s:
            heard_late = s[4] is not None and s[1] - s[4] > match_s
            flashes.append((s, level(u, seed_of(s)) * (0.45 if heard_late else 1), heard_late))
    for c in cs:
        for s, l, late in flashes:
            if (s in [p[2] for p in c['pts']]) and not late and l > lit.get(c['seed'], (0,))[0]:
                lit[c['seed']] = l, at(s[2], s[3], mid_m)

    # The towers: far enough to see them standing (under one, it's the deck over home), hidden by a cover at home.
    for c in cs:
        if c['km'] < 12 or not in_view(c['b'], 30):
            continue
        tower(ctx, c, at, w, cloud_rgb, night, cover, *lit.get(c['seed'], (0, None)))

    # The strikes so far where they left the cloud, by their age: the heard ones a plus.
    if info:
        ctx.set_antialias(cairo.ANTIALIAS_NONE)
        for s in st.s:
            if not in_view(s[2], 2) or now - s[0] > ticks_s:
                continue
            x, y = at(s[2], s[3], base_m)
            age = now - s[0]
            ctx.set_source_rgba(*age_color(age), 0.55 * (1 - age / ticks_s))
            ctx.rectangle(round(x), round(y), 1, 3)
            if s[4] is not None and age < 60:
                ctx.rectangle(round(x) - 1, round(y) + 1, 3, 1)
            ctx.fill()
        ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)

    light, near = 0.0, 99.0
    for s, l, late in flashes:
        b, km = s[2], s[3]
        if l < 0.02:
            continue
        rgb = tint(km)
        see = 0.4 + 0.6 * night
        if not late:
            # The sky lit: everywhere for a near one, else a glow along the horizon towards it.
            k = min((12 / max(km, 1)) ** 0.8, 1) * l * see
            light, near = max(light, k), min(near, km) if k > 0.05 else near
            x = w / 2 + ((b - yaw + 180) % 360 - 180) / fov * w
            g = cairo.RadialGradient(x, hz, 0, x, hz, w * (0.25 + min(8 / max(km, 1), 1)))
            g.add_color_stop_rgba(0, *rgb, min(0.45, (0.18 + 0.4 * k)) * l * see)
            g.add_color_stop_rgba(1, *rgb, 0)
            ctx.set_source(g)
            ctx.paint()
        if not in_view(b, 5):
            continue
        # The cloud's heart lit from inside, then the channel down to the ground.
        cx, cy = at(b, km, mid_m)
        r = max(min(math.degrees(10 / max(km, 1)) / fov * w, w / 3), 4)
        g = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
        g.add_color_stop_rgba(0, *rgb, 0.35 * l * see)
        g.add_color_stop_rgba(1, *rgb, 0)
        ctx.set_source(g)
        ctx.paint()
        channel(ctx, s, l, at, rgb)
    return {'light': light, 'near': near, 'cells': cs, 'busy': bool(flashes)}

def tower(ctx: cairo.Context, c: dict, at, w: int, cloud_rgb: tuple, night: float, cover: float, lit: float, flash: tuple | None):
    # A cumulonimbus: the tower widening up into the anvil, flat on top, spread both ways (further downwind, its own
    # lean here); sunlit white by day, a dark mass at night with the city's orange under it, lit in patches from
    # inside by its flashes (flash: where).
    b, km = c['b'], c['km']
    half = math.degrees(min(max(c['wide'], 6), 14) / 2 / km)
    x0, yb = at(b - half, km, base_m)
    x1, _ = at(b + half, km, base_m)
    _, ya = at(b, km, anvil_m)
    _, yt = at(b, km, top_m)
    if yb - yt < 3:
        return
    a = (0.62 - 0.07 * night) * (1 - 0.8 * cover)
    if a <= 0.02 and lit <= 0.02:
        return
    path = lambda: shape(ctx, x0, x1, yb, ya, yt, random.Random(c['seed']))
    top = tuple((0.5 * min(v * 1.15, 1) + 0.5) * (1 - 0.75 * night) for v in cloud_rgb)
    under = tuple(v * 0.45 * (1 - night) + u * night for v, u in zip(cloud_rgb, city_under))
    g = cairo.LinearGradient(0, yt, 0, yb)
    g.add_color_stop_rgba(0, *top, a)
    g.add_color_stop_rgba(0.5, *(v * (0.8 - 0.5 * night) for v in cloud_rgb), a)
    g.add_color_stop_rgba(1, *under, a)
    ctx.set_source(g)
    path()
    ctx.fill()
    if lit > 0.02 and flash:
        # Bright where it struck, a patch, the rest of it barely.
        fx, fy = flash
        r = random.Random(int(fx * 31 + fy))
        ctx.save()
        path()
        ctx.clip()
        hw = max(x1 - x0, 4) / 2
        for k in range(3):
            px, py = fx + r.uniform(-0.6, 0.6) * hw, fy + r.uniform(-0.8, 0.3) * hw
            g = cairo.RadialGradient(px, py, 0, px, py, hw * (1.1 if k == 0 else 0.6))
            g.add_color_stop_rgba(0, *tint(km), (0.6 if k == 0 else 0.35) * lit)
            g.add_color_stop_rgba(1, *tint(km), 0)
            ctx.set_source(g)
            ctx.paint()
        ctx.set_source_rgba(*tint(km), 0.12 * lit)
        ctx.paint()
        ctx.restore()

city_under = (0.2, 0.13, 0.09)     # the city's sodium glow on the base at night

def shape(ctx: cairo.Context, x0: float, x1: float, yb: float, ya: float, yt: float, r: random.Random):
    # One path, all drawn the same way round (their union): the body, cauliflower bumps up its sides, the anvil.
    ctx.new_path()
    hw, mid = (x1 - x0) / 2, (x0 + x1) / 2
    side = r.choice((-1, 1))
    lean = side * hw * r.uniform(0, 0.3)
    th = ya - yt
    ax = mid + lean
    wide = hw * 1.25                    # the tower at the anvil
    reach_a, reach_b = hw * r.uniform(1.6, 2.4), hw * r.uniform(1.0, 1.5)
    left, right = (ax - reach_b, ax + reach_a) if side > 0 else (ax - reach_a, ax + reach_b)
    pts = [(x0, yb), (x1, yb), (ax + wide, ya + th * 0.1),
           (right, yt + th * 0.45), (right + hw * 0.15, yt + th * 0.2), (right - hw * 0.1, yt + th * 0.05),
           (ax + hw * 0.3, yt), (ax - hw * 0.3, yt),
           (left + hw * 0.1, yt + th * 0.05), (left - hw * 0.15, yt + th * 0.2), (left, yt + th * 0.45),
           (ax - wide, ya + th * 0.1)]
    ctx.new_sub_path()
    for x, y in reversed(pts):      # clockwise on the screen, like the arcs
        ctx.line_to(x, y)
    ctx.close_path()
    rows = 6
    for k in range(rows):
        u = (k + 1.5) / (rows + 1)
        y = yb + (ya - yb) * u
        edge = hw + (wide - hw) * u
        for sgn in (-1, 1):
            bump = hw * (0.16 + 0.1 * r.random())
            ctx.new_sub_path()
            ctx.arc(mid + lean * u + sgn * (edge - bump * 0.5), y, bump, 0, 2 * math.pi)
    # A low dome where the updraft overshoots, and lobes hanging under the anvil (mammatus).
    ctx.new_sub_path()
    ctx.save()
    ctx.translate(ax, yt)
    ctx.scale(max(hw * 0.45, 1), max(th * 0.12, 0.5))
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()
    for i in range(int(min(max(hw / 5, 2), 6))):
        u = r.uniform(0.35, 0.9)
        x = ax + (right - ax) * u if i % 2 else ax + (left - ax) * u
        ctx.new_sub_path()
        ctx.arc(x, yt + th * (0.45 - 0.35 * (u - 0.35)), max(hw * 0.1, 0.8), 0, 2 * math.pi)

def channel(ctx: cairo.Context, s: list, l: float, at, rgb: tuple):
    # The bolt from the cloud base to the ground, in whole pixels: a white core, a halo when it's big.
    b, km = s[2], s[3]
    (x0, y0), (_, y1) = at(b, km, base_m), at(b, km, 47)
    hgt = y1 - y0
    if hgt < 3:
        return
    main, branches = bolt(seed_of(s))
    big = hgt > 50
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    for width, color, a in (((3, rgb, 0.35 * l),) if big else ()) + ((2 if big else 1, (1, 1, 1), l),):
        ctx.set_line_width(width)
        ctx.set_source_rgba(*color, min(a, 1))
        for k, pts in enumerate((main, *branches)):
            ctx.move_to(x0 + pts[0][0] * hgt, y0 + pts[0][1] * hgt)
            for px, py in pts[1:]:
                ctx.line_to(round(x0 + px * hgt), round(y0 + py * hgt))
        ctx.stroke()
    ctx.set_line_width(1)
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)

def front_light(ctx: cairo.Context, now: float, w: int, h: int, night: float, lit: dict):
    '''Over the roofs: a near flash lights them too, and a hit Sensei just heard lights the whole view (it can't tell
    where): twice, as strong as it was near and loud.'''
    st = state()
    if lit['near'] < 8 and lit['light'] > 0.05:
        ctx.set_source_rgba(*flash_rgb, 0.3 * lit['light'] * (1 - lit['near'] / 8))
        ctx.paint()
    fr = front(st, now)
    for t in real_live(st, now):
        u = now - t
        l = max(math.exp(-u / 0.07), math.exp(-(u - 0.15) / 0.07) * 0.7 if u > 0.15 else 0)
        km = fr[0] if fr and fr[0] < front_far else 20
        ctx.set_source_rgba(*flash_rgb, l * (0.15 + 0.35 * night) * min(10 / max(km, 1), 1) ** 0.5)
        ctx.paint()

def rumble(now: float) -> int:
    '''The thunder: from each strike near enough, km / 0.343 s after it (Sensei's time when it heard it), a second or
    more; the roofs shake a pixel (two, very near).'''
    dy = 0
    for s in state().s:
        if s[3] >= thunder_km:
            continue
        u = now - ((s[4] or s[0]) + s[3] / sound_kms)
        long = 1 + s[3] / 4
        if 0 <= u < long:
            env = (1 - u / long) * min(u / 0.1, 1)
            amp = 2 if s[3] < 3 else 1
            dy = max(dy, round(amp * env * (0.5 + 0.5 * math.sin(u * 47 + s[0]))))
    return dy

def busy(now: float, lit: dict) -> bool:
    # Flashing or thundering: drawn every frame.
    st = state()
    return lit['busy'] or bool(real_live(st, now)) or any(
        s[3] < thunder_km and 0 <= now - ((s[4] or s[0]) + s[3] / sound_kms) < 1 + s[3] / 4 for s in st.s)

def labels(now: float, lit: dict, to_px, in_view, sky_point) -> list[tuple]:
    '''The cells' distances under their base, the one Sensei hears marked; (frame, x, y, glyph) each.'''
    st = state()
    hc = heard_cell(lit['cells'], front(st, now))
    out = []
    for c in lit['cells']:
        if not in_view(c['b'], 0):
            continue
        e = sky_point(c['near'] * math.sin(math.radians(c['b'])), c['near'] * math.cos(math.radians(c['b'])), base_m)[1]
        x, y = to_px(c['b'], e)
        out.append((text(f"{c['near']:.0f} km", label_style), round(x), round(y), c is hc))
    return out

def sensei(ctx: cairo.Context, now: float, x: int, y: int) -> tuple | None:
    '''Sensei's receiver at (x, y) while there's a storm: lit as it hears, its distance to the front next to it.'''
    st = state()
    fr = front(st, now)
    if not fr and not storm(now):
        return None
    on = max((math.exp(-(now - t) / 0.4) for t in real_live(st, now)), default=0)
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    draw_glyph(ctx, x, y, 0.45 + 0.55 * on)
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)
    if not fr:
        return text('–', sensei_style), x + 9, y
    km = fr[0]
    return text('overhead' if km <= 1 else 'far' if km >= front_far else f'{km:.0f} km', sensei_style), x + 9, y

def draw_glyph(ctx: cairo.Context, x: int, y: int, a: float):
    ctx.set_source_rgba(*sensei_rgb, a)
    for j, row in enumerate(glyph):
        for i, ch in enumerate(row):
            if ch == '#':
                ctx.rectangle(x + i, y + j, 1, 1)
    ctx.fill()
