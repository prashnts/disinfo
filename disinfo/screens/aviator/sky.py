'''The planes as seen from home, out of the window.

The sky over the horizon, the elevation stretched near it (the approaches are a few degrees up), a drawn
Haussmann roofline with a few landmarks where they stand, the sun where it is. A quarter of the compass across,
turned towards the planes seen from the window. The view stays at home: it turns and zooms, never moves.
'''
import math
import time
import random
import numpy as np
import cairocffi as cairo

from functools import cache
from suncalc import get_position

from discore.cairo import to_pil
from discore.elements import Frame, Target
from discore.data_structures import FrameState
from discore.layouts import place_at
from discore.text import TextStyle, text
from disinfo import fonts
from disinfo.config import app_config
from disinfo.screens.solar.app import sky_color

from .state import ADSBxStateManager, OpenedStateManager
from .colors import marker_color
from .utils import airports, local_xy, bearing
from . import app, astro, skylook, skyline, weather


horizon = 0.6           # of the height, from the top
tilt = (0.45, 0.8)      # where the horizon may go: up to look down on the roofs, down to look up at a plane
tilt_sway, tilt_period = 0.06, 340      # the horizon drifts up and down that much while nothing's followed
elev_gamma = 0.5        # y ~ (elevation / top) ** gamma: the few degrees over the horizon get room
dip_max = 30            # degrees under the horizon at the bottom of the frame, the same stretch
earth_r = 6371
view_fov = 50           # degrees across, most of the time: the waypoints' piece of the skyline
fov_min = 20            # zoomed on a plane
wide_every, wide_for = 900, 45          # s: pulled back to the whole window that long, every so often
home_ground = 47        # m above the sea
compass = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
horizon_color = (1, 1, 1, 0.25)
sun_color = (1, 0.8, 0.4)
trail_alpha = 0.3       # the numbered planes' trails; the others are dots
dot_alpha = 0.45
sway = 4                # degrees
sway_period = 200       # s
# The roofs, far to near: dark greys, the far ones lighter; a faint rim on their tops.
far_color = (0.075, 0.08, 0.09)
near_color = (0.03, 0.032, 0.036)
hill_color = (0.11, 0.118, 0.13)        # the real roofline's farthest: the hills, hazy
window_m = 1.5          # a window across, lit at night
beacon_color = (1, 0.2, 0.12)           # the lights on the tall ones' tops
beacon_gap = 6          # px between them
band_m = (5000, 2000, 600, 150)         # m: how far the roofs of each band are, far to near (skyline.bands)
rim_color = (1, 1, 1, 0.15)
day_face = (1, 0.93, 0.8)       # the sun on the facades, by day
day_face_alpha, day_rim_alpha = 0.07, 0.3
label_style = TextStyle(font=fonts.microfont_35_reg, color='#8b8e94b0')

# Seen over the roofs, where they stand: (name, lat, lon, height m, ground m over the sea, width m, shape).
landmarks = [
    ('mercuriales', 48.8636, 2.4128, 122, 95, 30, 'twin'),
    ('vincennes', 48.8428, 2.4364, 52, 55, 30, 'keep'),
    ('sacre-coeur', 48.8867, 2.3431, 83, 130, 60, 'dome'),
    ('duo', 48.8273, 2.3779, 180, 40, 40, 'tower'),
    ('bnf', 48.8336, 2.3763, 79, 35, 120, 'twin'),
    ('montparnasse', 48.8421, 2.3220, 210, 60, 50, 'tower'),
    ('eiffel', 48.8584, 2.2945, 330, 35, 125, 'eiffel'),
]

_cams = {}              # screen -> [yaw, fov, at]: eases towards the view
_held = {}              # screen -> the yaw: turned only when what it looks at has moved away
_eye = {'m': home_ground + app_config.aviator_eye_m}


def wrap(a: float) -> float:
    return (a + 180) % 360 - 180

def sky_point(x: float, y: float, alt: float) -> tuple[float, float]:
    # Bearing and elevation, seen from the window, of a point km east, km north, m over the sea. The earth curves away.
    d = max(math.hypot(x, y), 0.01)
    return bearing(x, y), math.degrees(math.atan2(alt - _eye['m'], d * 1000)) - math.degrees(d / (2 * earth_r))

@cache
def city() -> tuple[list, list]:
    '''The roofline all around, in degrees: (far, near) blocks of (from, to, cornice, mansard's top, chimneys).

    Six floors and a mansard, the far ones about the horizon, the near ones under it (from the 11th floor one
    looks down on them). Drawn once, the same every time.
    '''
    rnd = random.Random(1853)       # Haussmann's year
    def row(widths, cornice, mansard, tall):
        blocks, b = [], 0.0
        while b < 360:
            w = rnd.uniform(*widths)
            c = cornice + rnd.uniform(-0.25, 0.25) + (tall if rnd.random() < 0.08 else 0)
            chimneys = [b + w * rnd.uniform(0.15, 0.85) for _ in range(rnd.randint(0, 3))]
            blocks.append((b, b + w, c, c + mansard * rnd.uniform(0.7, 1.2), chimneys))
            b += w
        return blocks
    return row((0.8, 2.2), -0.1, 0.25, 0.6), row((2.5, 5), -1.2, 0.5, 0.4)

def landmark_points(eye: float) -> list[tuple]:
    # (bearing, elevation of the top, angular width, shape) from the window.
    out = []
    for _, lat, lon, height, ground, width, shape in landmarks:
        x, y = local_xy(lat, lon)
        d = math.hypot(x, y) * 1000
        out.append((bearing(x, y), math.degrees(math.atan2(ground + height - eye, d)), math.degrees(width / d), shape))
    return out

def roofs(ctx: cairo.Context, in_view, to_px, h: int, sunlight: tuple[float, float] | None = None, rim: tuple = rim_color,
          daylit: tuple[float, float] | None = None):
    # Pixel-crisp: sharp on the LEDs, and nothing changes between frames when the view's still.
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    far, near = city()
    for blocks, color in ((far, far_color), (near, near_color)):
        rims, lit, faces = [], [], []
        for b0, b1, cornice, top, chimneys in blocks:
            if not (in_view(b0, 5) or in_view(b1, 5)):
                continue
            (x0, yc), (x1, _) = to_px(b0, cornice), to_px(b1, cornice)
            _, yt = to_px(0, top)
            inset = (x1 - x0) * 0.12
            outline = [(x0, yc), (x0 + inset, yt), (x1 - inset, yt), (x1, yc)]
            ctx.move_to(x0, h)
            for p in outline:
                ctx.line_to(*p)
            ctx.line_to(x1, h)
            ctx.close_path()
            for c in chimneys:
                cx, _ = to_px(c, top)
                ctx.rectangle(round(cx), round(yt) - 2, 1, 2)
            rims.append(outline)
            if sunlight and (k := max(0, 1 - abs(wrap((b0 + b1) / 2 - sunlight[0])) / 70) * sunlight[1]) > 0.03:
                lit.append((outline, k, x0, x1, yc, b0))
            # By day: the facades turned to the sun (it's behind us when they face us), as much as it's out.
            if daylit and (k := math.cos(math.radians(wrap((b0 + b1) / 2 + 180 - daylit[0]))) * daylit[1]) > 0.05:
                faces.append((outline, k, x0, x1, yc, b0))
        ctx.set_source_rgb(*color)
        ctx.fill()
        ctx.set_source_rgba(*rim)     # wet: shining with the rain's light
        for outline in rims:
            ctx.move_to(*outline[0])
            for p in outline[1:]:
                ctx.line_to(*p)
        ctx.stroke()
        for outline, k, x0, x1, yc, b0 in faces:
            ctx.move_to(x0, h)
            for p in outline:
                ctx.line_to(*p)
            ctx.line_to(x1, h)
            ctx.close_path()
            ctx.set_source_rgba(*day_face, day_face_alpha * k)
            ctx.fill()
            ctx.set_source_rgba(*day_face, day_rim_alpha * k)
            ctx.move_to(*outline[0])
            for p in outline[1:]:
                ctx.line_to(*p)
            ctx.stroke()
            # A window here and there sends the sun back: the same ones every frame.
            rnd = random.Random(round(b0 * 1000) + 7)
            for _ in range(max(1, round((x1 - x0) / 6))):
                if rnd.random() < 0.5:
                    ctx.set_source_rgba(1, 0.95, 0.8, min(0.8 * k, 0.8) * rnd.uniform(0.4, 1))
                    ctx.rectangle(round(rnd.uniform(x0 + 1, x1 - 1)), round(yc + rnd.uniform(2, 12)), 1, 1)
                    ctx.fill()
        # The sunset on the roofs facing it: a warm rim and a few windows catching it.
        for outline, k, x0, x1, yc, b0 in lit:
            ctx.set_source_rgba(*(c / 255 for c in skylook.glow_rgb), min(0.75 * k, 0.75))
            ctx.move_to(*outline[0])
            for p in outline[1:]:
                ctx.line_to(*p)
            ctx.stroke()
            rnd = random.Random(round(b0 * 1000))
            for _ in range(max(1, round((x1 - x0) / 3))):
                ctx.set_source_rgba(1, 0.75, 0.45, min(0.9 * k, 0.85) * rnd.uniform(0.5, 1))
                ctx.rectangle(round(rnd.uniform(x0, x1)), round(yc + rnd.uniform(2, 14)), 1, 1)
                ctx.fill()
    ctx.set_source_rgb(*far_color)
    for b, e, width, shape in landmark_points(_eye['m']):
        if not in_view(b, 5):
            continue
        x, y = to_px(b, e)
        _, base = to_px(b, -1)
        wpx = max(1, round(to_px(b + width / 2, 0)[0] - to_px(b - width / 2, 0)[0]))
        x, y, base = round(x), round(y), round(base)
        match shape:
            case 'twin':
                ctx.rectangle(x - wpx, y, max(1, wpx * 2 // 3), base - y)
                ctx.rectangle(x + wpx // 3, y, max(1, wpx * 2 // 3), base - y)
            case 'keep':
                ctx.rectangle(x - wpx // 2, y, wpx, base - y)
                ctx.rectangle(x - wpx // 2 - 1, y - 1, 1, 1)
                ctx.rectangle(x + wpx // 2, y - 1, 1, 1)
            case 'dome':
                ctx.rectangle(x - wpx // 2, y + 2, wpx, base - y - 2)
                ctx.arc(x, y + 2, max(wpx / 3, 1), math.pi, 0)
            case 'eiffel':
                ctx.move_to(x - wpx / 2, base)
                ctx.line_to(x, y)
                ctx.line_to(x + wpx / 2, base)
            case _:
                ctx.rectangle(x - wpx // 2, y, wpx, base - y)
        ctx.fill()
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)

def runs(v: np.ndarray) -> list[tuple[int, int, int]]:
    # (from, to, value) of the stretches where v stays the same.
    cut = [0, *(np.flatnonzero(np.diff(v)) + 1), len(v)]
    return [(a, b, int(v[a])) for a, b in zip(cut, cut[1:])]

def real_roofs(ctx: cairo.Context, sk: skyline.Skyline, yaw: float, fov: float, w: int, h: int, to_y,
               sunlight: tuple[float, float] | None = None, rim: tuple = rim_color, daylit: tuple[float, float] | None = None,
               night: float = 0):
    '''The roofline from the window (skyline.py), a pixel's column at a time: the hills, then the roofs far to near.
    Lit the same as the drawn one: the sun on the facades, the sunset on the tops facing it, a window catching it.
    At night the windows light up here and there, each in its place, on and off over the evening.'''
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    rows = sk.columns(yaw - fov / 2, fov / w, w)[::-1]
    bs = yaw - fov / 2 + (np.arange(w) + 0.5) * fov / w
    # The windows by bearing, a fifth of a degree each: they stay where they are when the view turns.
    cell = np.floor(bs * 5)
    r = (np.sin(cell * 12.9898) * 43758.5453) % 1
    off = lambda b: np.abs((b + 180) % 360 - 180)
    glow = np.clip(1 - off(bs - sunlight[0]) / 70, 0, None) * sunlight[1] if sunlight else np.zeros(w)
    face = np.cos(np.radians(bs + 180 - daylit[0])) * daylit[1] if daylit else np.zeros(w)
    for n, row in enumerate(rows):
        k = n / (len(rows) - 1)
        ys = np.minimum(np.round(to_y(row)), h).astype(int)
        top = runs(ys)
        ctx.move_to(0, h)
        for a, b, y in top:
            ctx.line_to(a, y)
            ctx.line_to(b, y)
        ctx.line_to(w, h)
        ctx.close_path()
        ctx.set_source_rgb(*(c0 + (c1 - c0) * k for c0, c1 in zip(hill_color, near_color)))
        ctx.fill()
        if n == 0:
            continue
        on = ys < h
        # By day: the facades turned to the sun (it's behind us when they face us), as much as it's out.
        for level in range(1, 5):
            sel = on & (np.ceil(face * 4) == level) & (face > 0.05)
            if sel.any():
                for a, b, v in runs(np.where(sel, ys + 1, 0)):
                    if v:
                        ctx.rectangle(a, v - 1, b - a, h)
                ctx.set_source_rgba(*day_face, day_face_alpha * level / 4)
                ctx.fill()
        for a, b, y in top:
            if y < h:
                ctx.rectangle(a, y, b - a, 1)
        ctx.set_source_rgba(*rim)     # wet: shining with the rain's light
        ctx.fill()
        # The sunset on the tops facing it, a few windows catching it; by day a window sends the sun back.
        for level in range(1, 5):
            sel = on & (np.ceil(glow * 4) == level) & (glow > 0.03)
            if sel.any():
                for x in np.flatnonzero(sel):
                    ctx.rectangle(int(x), int(ys[x]), 1, 1)
                ctx.set_source_rgba(*(c / 255 for c in skylook.glow_rgb), 0.75 * level / 4)
                ctx.fill()
        lit = on & (r < 0.3 * np.maximum(glow, 0.15 * face))
        for x in np.flatnonzero(lit):
            ctx.rectangle(int(x), int(ys[x] + 2 + (r[x] * 97 % 1) * 8), 1, 1)
        ctx.set_source_rgba(1, 0.85, 0.6, 0.7)
        ctx.fill()
        if night > 0.05:
            # The nearer, the more of them and the deeper down the facade; a few have the TV's blue. As big as a
            # window there is (px), dimmer the farther; a soft halo once it's a pixel or more.
            q = (np.sin(cell * 78.233 + n * 31.7 + np.floor(time.time() / 600 + r * 7)) * 43758.5453) % 1
            on_ = on & (q < night * 0.09 * (0.4 + k))
            px = window_m / band_m[n - 1] * w / math.radians(fov)
            size, alpha = min(max(round(px), 1), 3), 0.1 + 0.2 * min(px / 2, 1)
            for cool in (False, True):
                spots = [(int(x), int(ys[x] + 2 + (q[x] * 37 % 1) * (4 + 24 * k))) for x in np.flatnonzero(on_ & ((q * 113 % 1 < 0.15) == cool))]
                color = (0.65, 0.75, 1) if cool else (1, 0.78, 0.45)
                for grow, a in ((1, alpha * 0.35), (0, alpha)) if px >= 0.9 else ((0, alpha),):
                    for x, y in spots:
                        ctx.rectangle(x - grow, y - grow, size + 2 * grow, size + 2 * grow)
                    ctx.set_source_rgba(*color, a)
                    ctx.fill()
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)
    if night > 0.05:
        beacons(ctx, sk, yaw, fov, w, to_y, rows, night)

def beacons(ctx: cairo.Context, sk: skyline.Skyline, yaw: float, fov: float, w: int, to_y, rows: np.ndarray, night: float):
    # The red lights on the tall ones' tops, each pulsing slowly at its own pace; hidden by nearer roofs. Bigger and
    # brighter the nearer: a glow around a bright pixel.
    # The highest first, a few pixels apart: on a small screen only the tallest of a cluster.
    now, taken = time.time(), []
    for b, e, d in sorted(sk.beacons, key=lambda s: -s[1]):
        x = w / 2 + wrap(b - yaw) / fov * w
        if not 0 <= x < w or any(abs(x - t) < beacon_gap for t in taken):
            continue
        nearer = rows[len(rows) - 1 - np.searchsorted(skyline.bands, d) + 1:, int(x)]
        if len(nearer) and nearer.max() > e:
            continue
        taken.append(x)
        y = float(to_y(np.array([e]))[0])
        k = min((600 / d) ** 0.5, 1.5)
        pulse = 0.55 + 0.45 * math.sin(2 * math.pi * (now / (2 + b % 1.5) + b))
        a = night * pulse * (0.35 + 0.4 * min(k, 1))
        r = 1.5 + 2.5 * k
        g = cairo.RadialGradient(int(x) + 0.5, y, 0, int(x) + 0.5, y, r)
        g.add_color_stop_rgba(0, *beacon_color, a * 0.6)
        g.add_color_stop_rgba(1, *beacon_color, 0)
        ctx.set_source(g)
        ctx.arc(int(x) + 0.5, y, r, 0, 2 * math.pi)
        ctx.fill()
        ctx.set_source_rgba(*beacon_color, min(a * 1.6, 1))
        ctx.rectangle(int(x), int(y), 1, 1)
        ctx.fill()

def camera(fs: FrameState, target: tuple[float, float, float]) -> tuple[float, float, float]:
    now = time.monotonic()
    c = _cams.setdefault(fs.config.name, [*target, now])
    k = 1 - math.exp(-(now - c[3]) / 0.8)
    c[:] = c[0] + wrap(target[0] - c[0]) * k, c[1] + (target[1] - c[1]) * k, c[2] + (target[2] - c[2]) * k, now
    app._moving[fs.config.name] = abs(wrap(target[0] - c[0])) > 0.3 or abs(target[1] - c[1]) > 0.3 or abs(target[2] - c[2]) > 0.004
    if not app._moving[fs.config.name]:
        c[:3] = target
    return c[0], c[1], c[2]

def top_of(fov: float) -> float:
    # Degrees over the horizon at the top of the frame: zoomed in, the few over the roofs get the room.
    return min(90, max(fov * 1.2, 30))

def dip_of(fov: float) -> float:
    return dip_max * min(max(fov, fov_min) / 90, 1)

def tilt_to(e: float, fov: float) -> float:
    # The horizon where a plane e degrees up sits a third down the frame.
    s = (min(max(e, 0), 90) / top_of(fov)) ** elev_gamma
    return min(max(0.33 / max(1 - s, 0.01), tilt[0]), tilt[1])

def mean_bearing(bs: list[float]) -> float:
    return math.degrees(math.atan2(sum(math.sin(math.radians(b)) for b in bs), sum(math.cos(math.radians(b)) for b in bs)))

def aim(st, fov: float) -> tuple[float, float]:
    '''(yaw, fov): towards the planes seen from the window, wide enough for them all; without any, on the waypoints
    (the landmarks seen from here), now and then pulled back to the whole window. Kept within the window.'''
    start, end = app_config.aviator_window
    span = (end - start) % 360 or 360
    seen = [st.planes[h]['bearing'] for h in st.watched if h in st.planes]
    marks = [bearing(*local_xy(*p)) for p in app_config.screen_data.aviator.landmarks]
    if seen:
        yaw = mean_bearing(seen)
        fov = min(max(fov, 2 * max(abs(wrap(b - yaw)) for b in seen) + 15), span)
    elif time.time() % wide_every < wide_for:
        yaw, fov = start + span / 2, span
    else:
        yaw = mean_bearing(marks) if marks else start + span / 2
    if fov < span:
        yaw = start + min(max(wrap(yaw - start) % 360, fov / 2), span - fov / 2)
    return yaw, fov

def look(fs: FrameState, st, clear: tuple, w: int) -> tuple[float, float, float]:
    # Held still while what it looks at stays in view: zoomed on the plane of a card the first time it's on top,
    # then turned only when the followed plane leaves the clear box, or the planes seen move a quarter view away.
    # The horizon goes down to look up at the followed plane; otherwise it drifts, now the roofs, now the sky.
    fov = view_fov
    yaw = _held.get(fs.config.name)
    followed = app.following(fs)
    middle = (clear[0] + clear[2]) / 2 - w / 2
    if followed:
        p = st.planes[followed]
        b, e = sky_point(*app.position(p, time.time()), p['alt'])
        swept_hex, swept_at = app._swept.get(fs.config.name, (None, 0))
        if swept_hex == followed and time.monotonic() - swept_at < app.sweep:
            zoom = max(fov_min, fov / app.sweep_zoom)
            return b - middle / w * zoom, zoom, tilt_to(e, zoom)
        px = w / 2 + wrap(b - (yaw if yaw is not None else b)) / fov * w
        if yaw is None or not clear[0] + 6 <= px <= clear[2] - 6:
            yaw = b - middle / w * fov
        _held[fs.config.name] = yaw
        return yaw, fov, tilt_to(e, fov)
    target, fov = aim(st, fov)
    if yaw is None or abs(wrap(target - yaw)) > fov / 4:
        yaw = target
    _held[fs.config.name] = yaw
    # Slow motion while nothing's followed: the heading sways a few degrees, over a few minutes.
    t = time.time()
    return yaw + sway * math.sin(2 * math.pi * t / sway_period), fov, horizon + tilt_sway * math.sin(2 * math.pi * t / tilt_period)

def shade(hex: str, k: float) -> tuple[float, float, float]:
    return tuple(min(int(hex[i:i + 2], 16) / 255 * k, 1) for i in (1, 3, 5))

cloud_alpha = 0.55      # 0.8 in a downpour
cloud_weights = (0.4, 0.3, 0.2, 0.1)       # the nearer, the more it counts
rain_color = (0.68, 0.76, 0.9)
rain_weights = (1, 0.8, 0.6, 0.45, 0.3)
cloud_base_km = 4       # the rain hangs from here: higher in the view the nearer it is
col_step = 2            # px between the columns of a band
# The drops at home, far then near: (per px of the view, length px, px/s falling, alpha).
drop_layers = ((1 / 380, 3, 55, 0.22), (1 / 1100, 6, 120, 0.42))
puff_alpha = 0.7
puff_base_km = 1.5      # the cumulus' base
puff_km = 1.6           # a cloud across
# Far to near: (km away, the satellite's bin). The three nearest are over home, in the nearest bin.
puff_layers = ((100, 3), (60, 2), (30, 1), (10, 0), (6, 0), (3.5, 0), (2, 0))
snow_color = (0.93, 0.95, 1.0)
# The flakes, the same: (per px of the view, size px, px/s falling, alpha).
flake_layers = ((1 / 260, 1, 9, 0.35), (1 / 700, 2, 18, 0.6))
# The wind at home: streaks over the roofs going with it, some curling on the way.
curl_ms = 3             # from this wind on
curl_life = 5           # s a streak lives
curl_trail = 16         # points along its tail, a 40th of its life apart
curl_r = 1 / 150        # of the width, the loop's radius (more in the gusts)

def clouds(ctx: cairo.Context, yaw: float, fov: float, w: int, hz: int, h: int, color: tuple, floor: float = 0, alpha: float = cloud_alpha):
    # A band of cloud over the horizon, as high as the cover is thick in each direction, going to nothing upwards.
    # floor: the cover all around when it rains at home. Returns the cover (0..1) by bearing, for what it hides.
    prof = weather.sky_profile('clouds')
    if not prof and not floor:
        return lambda b: 0.0
    xs = np.arange(0, w + col_step, col_step)
    weights = np.array(cloud_weights, np.float32)
    cover_at = lambda bs: np.maximum(np.clip((weather.along(prof[0], bs) * weights).sum(axis=1) * 2.5, 0, 1) if prof else np.zeros(len(bs)), floor)
    top = hz - hz * 0.95 * cover_at(yaw + (xs - w / 2) / w * fov) ** 0.8
    if top.min() < hz - 1:
        g = cairo.LinearGradient(0, top.min(), 0, hz)
        g.add_color_stop_rgba(0, *color, 0)
        g.add_color_stop_rgba(1, *color, alpha)
        ctx.set_source(g)
        ctx.move_to(0, hz)
        for x, y in zip(xs, top):
            ctx.line_to(float(x), float(y))
        ctx.line_to(w, hz)
        ctx.close_path()
        ctx.fill()
    return lambda b: float(cover_at(np.array([b]))[0])

def puffs(ctx: cairo.Context, yaw: float, fov: float, w: int, to_px, color: tuple, floor: float = 0, alpha: float = puff_alpha):
    # The clouds themselves where the satellite sees them, a puff a cloud wide as often as the cover is thick: the far
    # ones low and small, the ones over home high up and big. Each has its place by bearing, the same every frame.
    prof = weather.sky_profile('clouds')
    if not prof and not floor:
        return
    for d, k in puff_layers:
        size = math.degrees(puff_km / d)
        step = size * 0.8
        i0 = math.floor((yaw - fov / 2 - size) / step)
        bs = np.arange(i0, i0 + math.ceil((fov + 2 * size) / step) + 1) * step
        cover = np.maximum(np.clip(weather.along(prof[0], bs)[:, k] * 3, 0, 1) if prof else np.zeros(len(bs)), floor)
        e = math.degrees(math.atan2(puff_base_km, d))
        near = min(size / 20, 1)
        a = alpha * (1 - 0.4 * near)    # the near ones thin: one sees through their edges
        for i, b, c in zip(range(i0, i0 + len(bs)), bs, cover):
            r = (math.sin(i * 12.9898 + d * 78.233) * 43758.5453) % 1
            if r >= c:
                continue
            j = (r * 7.31) % 1
            x, y = to_px(b + (j - 0.5) * step * 0.6, e * (0.85 + 0.3 * j))
            rx = max(size / fov * w * (0.45 + 0.4 * j) * (1 - 0.4 * near), 0.6)
            ry = max(rx * (0.3 + 0.35 * near), 0.6)
            puff(ctx, x, y, rx, ry, color, a * (0.6 + 0.4 * c), r)

def lobes(rx: float, r: float) -> list[tuple[float, float, float]]:
    '''A cumulus' heaps (x, y, radius in units of rx and ry), r its own number: a row along the base, then smaller
    tiers piled up the middle, the more the bigger it shows (a few pixels: one row of three).'''
    out = []
    tiers = 1 if rx < 8 else 2 if rx < 30 else 3
    for tier in range(tiers):
        n = int(min(max(rx / 6, 3), 8)) - 2 * tier
        width = 0.95 * (1 - 0.3 * tier)
        for k in range(max(n, 1)):
            t = 0.5 if n <= 1 else k / (n - 1)
            j = (r * (31.7 + 17.3 * k + 7.1 * tier)) % 1
            hump = math.sin(math.pi * t)
            out.append((-width + 2 * width * t + (j - 0.5) * 0.2, 0.25 - 0.55 * tier - 0.3 * hump * (tier + 1) / tiers - 0.15 * j,
                        (0.3 + 0.25 * hump + 0.12 * j) * (1 - 0.15 * tier)))
    return out

def puff(ctx: cairo.Context, x: float, y: float, rx: float, ry: float, color: tuple, a: float, r: float):
    # Lit on top, grey under, a flat base; a big one gets a lit rim on its heaps.
    heaps = lobes(rx, r)
    g = cairo.LinearGradient(0, y - ry * 1.4, 0, y + ry * 0.45)
    g.add_color_stop_rgba(0, *(min(v * 1.15, 1) for v in color), a)
    g.add_color_stop_rgba(1, *(v * 0.75 for v in color), a)
    ctx.save()
    ctx.rectangle(x - rx * 2, y - ry * 3, rx * 4, ry * 3.45)        # the base, flat
    ctx.clip()
    ctx.set_source(g)
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(rx, ry)
    for hx, hy, hr in heaps:
        ctx.new_sub_path()
        ctx.arc(hx, hy, hr, 0, 2 * math.pi)
    ctx.restore()
    ctx.fill()
    if rx > 12:
        ctx.set_source_rgba(*(min(v * 1.25, 1) for v in color), a * 0.35)
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(rx, ry)
        for hx, hy, hr in heaps:
            ctx.new_sub_path()
            ctx.arc(hx - 0.1 * hr, hy - 0.15 * hr, hr * 0.7, 0, 2 * math.pi)
        ctx.restore()
        ctx.fill()
    ctx.restore()

cirrus_alpha = 0.35
# The streaks: (per degree of the view, elevation range, length in degrees).
cirrus_density, cirrus_elev, cirrus_len = 0.12, (20, 60), (5, 14)

def cirrus(ctx: cairo.Context, yaw: float, fov: float, w: int, to_px, color: tuple, lk, k: float):
    # High cloud (the model's, the light can't tell it): thin streaks high up, each where it is by bearing. They keep
    # the sunset's colour after it's gone from the low ones.
    c = tuple(v * (1 - lk.glow) + g / 255 * lk.glow for v, g in zip(color, skylook.glow_rgb))
    ctx.set_line_width(1)
    step = 1 / cirrus_density
    for i in range(math.floor((yaw - fov / 2 - cirrus_len[1]) / step), math.ceil((yaw + fov / 2) / step) + 1):
        r = (math.sin(i * 91.345 + 3.1) * 43758.5453) % 1
        if r >= k:
            continue
        j = (r * 13.17) % 1
        b, e = i * step, cirrus_elev[0] + (cirrus_elev[1] - cirrus_elev[0]) * j
        length = cirrus_len[0] + (cirrus_len[1] - cirrus_len[0]) * ((r * 7.7) % 1)
        (x0, y0), (x1, y1) = to_px(b, e), to_px(b + length, e - 2 * (j - 0.5))
        g = cairo.LinearGradient(x0, y0, x1, y1)
        g.add_color_stop_rgba(0, *c, 0)
        g.add_color_stop_rgba(0.4, *c, cirrus_alpha * (0.5 + 0.5 * k))
        g.add_color_stop_rgba(1, *c, 0)
        ctx.set_source(g)
        ctx.move_to(x0, y0)
        ctx.line_to(x1, y1)
        ctx.stroke()

contrail_alpha = 0.5
contrail_life = (25, 600)       # s a trail stays: in dry air, in air saturated over ice

def contrails(ctx: cairo.Context, planes, now: float, in_view, to_px, color: tuple, trails: tuple):
    # Behind the planes flying where it's cold enough (skystate.py: the planes' own temperatures, else the model's):
    # short in dry air, long and spreading when the air is saturated over ice, drifting with the wind up there.
    form, persist, u, v = trails
    life = contrail_life[0] + (contrail_life[1] - contrail_life[0]) * persist
    for p in planes:
        if p['ground'] or p['alt'] < form:
            continue
        pts = [(t, *local_xy(la, lo), alt or p['alt']) for t, la, lo, alt in p['trail'] if now - t < life]
        pts.append((now, *app.position(p, now), p['alt']))
        prev = None
        for t, x, y, alt in pts:
            age = now - t
            b, e = sky_point(x + u * age / 1000, y + v * age / 1000, alt)
            if prev and in_view(b) and in_view(prev[0]):
                k = 1 - age / life
                ctx.set_line_width(1 + 2 * persist * (1 - k))
                ctx.set_source_rgba(*color, contrail_alpha * k * (1 - 0.5 * persist * (1 - k)))
                ctx.move_to(*to_px(*prev))
                ctx.line_to(*to_px(b, e))
                ctx.stroke()
            prev = b, e
    ctx.set_line_width(1)

def fall_tint(lk, color: tuple, k: float = 0.6) -> tuple:
    # Rain and snow are lit by what's around: at night the streetlights.
    k *= lk.city
    return tuple(c * (1 - k) + v / 255 * k for c, v in zip(color, skylook.city_rgb))

def rain(ctx: cairo.Context, yaw: float, fov: float, w: int, hz: int, to_px, tint: tuple):
    # Curtains of rain hanging in the directions it rains in, nearer ones higher and stronger.
    if not (prof := weather.sky_profile('rain')):
        return
    values = prof[0]
    xs = np.arange(0, w, col_step)
    along = weather.along(values, yaw + (xs - w / 2) / w * fov) * np.array(rain_weights, np.float32)
    best = along.argmax(axis=1)
    power = along.max(axis=1)
    ctx.set_line_width(1)
    for i, (x, k) in enumerate(zip(xs, best)):
        if power[i] < 0.05:
            continue
        _, top = to_px(0, math.degrees(math.atan2(cloud_base_km, weather.rain_bins[k])))
        # Streaky: each column its own strength.
        streak = 0.5 + 0.5 * ((x * 37 + k * 11) % 7) / 6
        ctx.set_source_rgba(*tint, min(power[i] * 1.4, 0.6) * streak)
        ctx.move_to(float(x) + 0.5, top)
        ctx.line_to(float(x) + 0.5, hz)
        ctx.stroke()

def drops(ctx: cairo.Context, w: int, h: int, now: float, wet: float, slant: float, tint: tuple, share: float = 1):
    # The rain at home, across the whole view: the near drops longer, brighter and faster. They fall along the wind.
    for depth, (per_px, length, speed, alpha) in enumerate(drop_layers):
        ctx.set_source_rgba(*tint, alpha * (0.5 + 0.5 * wet))
        for i in range(int(w * h * per_px * (0.3 + wet) * share)):
            y = ((i * 0.7548776662 + depth * 0.37) % 1 * h + now * speed) % (h + length) - length
            x = ((i * 0.6180339887 + depth * 0.5) % 1 * (w + 40) - 20 + slant * y) % (w + 40) - 20
            ctx.move_to(x, y)
            ctx.line_to(x + slant * length, y + length)
        ctx.stroke()

def flakes(ctx: cairo.Context, w: int, h: int, now: float, wet: float, slant: float, tint: tuple, share: float = 1):
    # The snow at home: slow, the near flakes bigger, each its own speed and sway, blown further than the rain.
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    for depth, (per_px, size, speed, alpha) in enumerate(flake_layers):
        ctx.set_source_rgba(*tint, alpha * (0.5 + 0.5 * wet))
        for i in range(int(w * h * per_px * (0.3 + wet) * share)):
            v = speed * (0.7 + 0.6 * ((i * 0.381966) % 1))
            y = ((i * 0.7548776662 + depth * 0.37) % 1 * h + now * v) % (h + size) - size
            x = ((i * 0.6180339887 + depth * 0.5) % 1 * (w + 40) - 20 + 2 * slant * y + 1.5 * math.sin(now * 1.2 + i)) % (w + 40) - 20
            ctx.rectangle(round(x), round(y), size, size)
        ctx.fill()
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)

def curls(ctx: cairo.Context, w: int, top: float, hz: int, now: float, yaw: float, wind: float, gust: float, dir: float, color: tuple):
    # Each streak is born at its own place and time, drifts across with the wind (its part across the view), every
    # other one loops once half way: a trochoid. Fading in and out, the tail fainter.
    r = math.radians(yaw)
    e, n = -wind * math.sin(math.radians(dir)), -wind * math.cos(math.radians(dir))   # where it blows to
    across = e * math.cos(r) - n * math.sin(r)
    side = 1 if across >= 0 else -1
    run = (abs(across) + 1) * w * 0.03                      # px over its life; a wind at us still stirs
    loop = max(curl_r * w, 3) * min(gust / max(wind, 1), 2)
    alpha = min(0.3 + 0.04 * wind, 0.65)
    color = tuple(min(c * 1.6 + 0.15, 1) for c in color)     # a little brighter than the clouds behind
    count = round(min(wind * 1.5, 18) * max(w / 400, 0.4))
    frac = lambda x: x % 1
    def at(i: int, born: int, u: float) -> tuple[float, float]:
        x0, y0 = frac(i * 0.6180339887 + born * 0.381966) * w, top + frac(i * 0.7548776662 + born * 0.2763932) * (hz - top - 6)
        th = 2 * math.pi * min(max((u - 0.35) / 0.3, 0), 1) if i % 2 else 0
        return (x0 + side * (run * u + loop * math.sin(th)),
                y0 - loop * (1 - math.cos(th)) + 1.5 * math.sin(2 * math.pi * (u * 1.5 + i * 0.3)))
    for i in range(count):
        life = now / curl_life + frac(i * 0.414213)
        born, u = int(life), life % 1
        points = [at(i, born, max(u - k * 0.025, 0)) for k in range(curl_trail)]
        for k, (a, b) in enumerate(zip(points, points[1:])):
            ctx.set_source_rgba(*color, alpha * math.sin(math.pi * u) * (1 - k / curl_trail) ** 0.5)
            ctx.move_to(*a)
            ctx.line_to(*b)
            ctx.stroke()

def drop_slant(yaw: float) -> float:
    # The wind at home across the view (right is yaw + 90), in px sideways per px falling.
    doc = weather.wind_doc()
    if not doc or not (wv := weather.wind_at(doc, 0, 0)):
        return -0.25
    u, v = wv
    r = math.radians(yaw)
    return float(np.clip((u * math.cos(r) - v * math.sin(r)) / 8, -0.8, 0.8))

def sky(fs: FrameState, clear: tuple | None = None) -> Frame:
    st = ADSBxStateManager().get_state(fs)
    opened = OpenedStateManager().get_state(fs).opened
    w, h = fs.config.width, fs.config.height
    now = time.time()
    followed = app.following(fs)
    sk = skyline.get(now)
    _eye['m'] = sk.eye[2] if sk else home_ground + fs.config.aviator_eye_m
    yaw, fov, tl = camera(fs, look(fs, st, clear or (0, 0, w, h), w))
    hz = round(h * tl)
    top, dip = top_of(fov), dip_of(fov)
    in_view = lambda b, margin=10: abs(wrap(b - yaw)) < fov / 2 + margin
    to_x = lambda b: w / 2 + wrap(b - yaw) / fov * w
    to_px = lambda b, e: (to_x(b), hz - hz * (min(e, 90) / top) ** elev_gamma if e >= 0 else hz + (h - hz) * (min(-e, dip) / dip) ** elev_gamma)
    to_y = lambda e: np.where(e >= 0, hz - hz * (np.minimum(np.abs(e), 90) / top) ** elev_gamma, hz + (h - hz) * (np.minimum(np.abs(e), dip) / dip) ** elev_gamma)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_line_width(1)
    labels, taken = [], []

    # The sky: the sun's height, the weather state and the room's light (skylook.py).
    sun = get_position(fs.now.in_tz('UTC'), fs.config.longitude, fs.config.latitude)
    sb, se = (math.degrees(sun['azimuth']) + 180) % 360, math.degrees(sun['altitude'])
    off = OpenedStateManager().get_state(fs).off
    # The sky state: every source over home together (skystate.py, the same for all screens).
    seen = skylook.seen(fs)
    wet, snow = seen.wet, seen.snow
    lk = skylook.look(se, seen.cond, skylook.light_gain(fs), None, seen.warmth)
    skylook.paint(ctx, lk, w, hz, h, to_x(sb) if in_view(sb, 30) else None)
    ctx.set_source_rgba(*horizon_color)
    ctx.move_to(0, hz)
    ctx.line_to(w, hz)
    ctx.stroke()

    info, show_planes = 'info' not in off, 'planes' not in off
    tint, snow_tint = fall_tint(lk, rain_color), fall_tint(lk, snow_color, 0.5)
    if 'clouds' not in off or wet:
        cc = skylook.cloud_color(lk, wet * (1 - 0.7 * snow))
        if seen.high > 0.05:
            cirrus(ctx, yaw, fov, w, to_px, cc, lk, seen.high)
        # The low and mid cloud all around: the satellite (infrared) misses the low, warm ones.
        # A deck when it's steady, puffs when the sun goes in and out.
        deck, broken = seen.deck, 0.3 if seen.broken is None else seen.broken
        cloud_dim = clouds(ctx, yaw, fov, w, hz, h, cc, max(min(wet * 1.4, 0.8), 0.6 * deck * (1 - 0.5 * broken)), cloud_alpha + 0.25 * wet)
        puffs(ctx, yaw, fov, w, to_px, cc, max(min(wet * 1.4, 0.8), deck * (0.2 + 0.5 * broken)))
    else:
        cloud_dim = lambda b: 0.0

    # The sun where it is, its glow over the horizon a little after it's set.
    if se > -6 and in_view(sb, 20):
        sx, sy = to_px(sb, se)
        glow = cairo.RadialGradient(sx, sy, 0, sx, sy, 16)
        dim = 1 - 0.8 * cloud_dim(sb)       # a cloud band in front of it, or the sky state says it's in
        if seen.sun is not None:
            dim = min(dim, (0.15 + 0.85 * seen.sun) * (1 - 0.9 * seen.dark))
        glow.add_color_stop_rgba(0, *sun_color, (0.35 if se > 0 else 0.2) * dim)
        glow.add_color_stop_rgba(1, *sun_color, 0)
        ctx.set_source(glow)
        ctx.paint()
        if se > 0:
            ctx.set_source_rgba(*sun_color, dim)
            ctx.arc(sx, sy, 2.5, 0, 2 * math.pi)
            ctx.fill()

    # Stars once the sun is well down (dimmed by the cloud), the moon where it is, fainter in daylight.
    clear_sky = (1 - 0.9 * lk.cloud) * max(1 - 2 * wet, 0)
    astro.draw_stars(ctx, now, fs.config.latitude, fs.config.longitude, to_px, in_view, min(max((-se - 3) / 12, 0), 1) * clear_sky)
    mb, me, phase = astro.moon_at(now, fs.config.latitude, fs.config.longitude)
    if me > -1 and in_view(mb, 10):
        mx, my = to_px(mb, max(me, 0))
        astro.draw_moon(ctx, mx, my, 3, phase, (1 - 0.65 * min(max(se / 10, 0), 1)) * (1 - 0.8 * cloud_dim(mb)) * (1 - 0.5 * lk.cloud) * max(1 - 2 * wet, 0))

    if 'rain' not in off:
        rain(ctx, yaw, fov, w, hz, to_px, tint)

    if show_planes and seen.trails and 'clouds' not in off:
        contrails(ctx, st.planes.values(), now, in_view, to_px, skylook.cloud_color(lk), seen.trails)

    targets, lit = [], []
    for hex, p in sorted(st.planes.items() if show_planes else (), key=lambda i: (i[0] == followed, i[0] in st.watched)):
        color = marker_color(p['alt']).rgb
        x, y = app.position(p, now)
        b, e = sky_point(x, y, p['alt'])
        if not in_view(b):
            continue
        px, py = to_px(b, e)
        targets.append(Target(round(px) - 6, round(py) - 6, 13, 13, 'aviator.open', {'hex': hex}))
        if not (hex in st.watched or hex in opened):
            # The others: a dot.
            ctx.set_source_rgba(*color, dot_alpha)
            ctx.rectangle(round(px), round(py), 1, 1)
            ctx.fill()
            continue
        stepped = now // app.fade_step * app.fade_step
        points = [(t, sky_point(*local_xy(la, lo), alt or 0)) for t, la, lo, alt in p['trail'] if stepped - t < app.watched_fade]
        for (_, (b0, e0)), (t1, (b1, e1)) in zip(points, points[1:]):
            if in_view(b0) and in_view(b1):
                ctx.set_source_rgba(*color, trail_alpha * (1 - max(stepped - t1, 0) / app.watched_fade))
                ctx.move_to(*to_px(b0, e0))
                ctx.line_to(*to_px(b1, e1))
                ctx.stroke()
        ctx.set_dash([1, 2])
        ctx.set_source_rgba(*color, 0.4)
        ctx.move_to(px, py)
        for k in range(1, 7):
            ax, ay = app.position(p, now, app.ahead * k / 6)
            ctx.line_to(*to_px(*sky_point(ax, ay, p['alt'] + p['vr'] * app.ahead * k / 6 / 60)))
        ctx.stroke()
        ctx.set_dash([])
        # Pointing where it goes on the screen, bigger when near.
        nx, ny = to_px(*sky_point(*app.position(p, now, 20), p['alt'] + p['vr'] / 3))
        heading = math.degrees(math.atan2(nx - px, py - ny)) if (nx, ny) != (px, py) else 90
        size = min(max(1.5 + 6 / max(p['slant'], 1) ** 0.7, 1.8), 4)
        ctx.set_source_rgb(*color)
        app.chevron(ctx, px, py, heading, size * 1.3)
        ctx.fill()
        if hex == followed:
            lit.append((px, py))
        if info and (n := app.number(st, hex)):
            labels.append((app.pill(n, marker_color(p['alt']).hex), round(px) + 5, round(py) - 10))

    # The roofs over all that: a low plane goes behind them. Its number and the ring stay on top.
    # Wet roofs shine with the rain's light, snowy ones are white along their tops.
    rim = (*snow_tint, 0.3 + 0.3 * wet) if snow >= 0.5 else (*tint, rim_color[3] + 0.2 * wet)
    # The sun on the facades: the light says how much it's out, else the cloud does.
    sun_out = (seen.sun if seen.sun is not None else 1 - lk.cloud) * float(np.clip(se / 8, 0, 1)) * (1 - wet)
    lights = (sb, lk.glow) if lk.glow > 0.03 else None, rim if wet > 0.05 else rim_color, (sb, sun_out) if sun_out > 0.05 else None
    if sk:
        real_roofs(ctx, sk, yaw, fov, w, h, to_y, *lights, min(max((-se - 2) / 8, 0), 1))
    else:
        roofs(ctx, in_view, to_px, h, *lights)
    # The wind over the roofs, then the rain or snow at home in front of all that, at a few frames a second.
    windy = 'wind' not in off and (seen.wind or 0) >= curl_ms and seen.wind_dir is not None
    if windy:
        curls(ctx, w, hz * 0.3, hz, now, yaw, seen.wind, seen.gust or seen.wind, seen.wind_dir, skylook.cloud_color(lk))
    app._raining[fs.config.name] = wet > 0.05 or windy
    if wet > 0.05:
        slant = drop_slant(yaw)
        drops(ctx, w, h, now, wet, slant, tint, 1 - snow)
        flakes(ctx, w, h, now, wet, slant, snow_tint, snow)
    for px, py in (lit if info else ()):
        ctx.set_source_rgba(1, 1, 1, 0.85)
        ctx.arc(px, py, 6.5, 0, 2 * math.pi)
        ctx.stroke()
    for i, name in enumerate(compass if info else ()):
        if in_view(i * 45, 0):
            if at := app.label_at(t := text(name, label_style), round(to_x(i * 45)), hz + 4, taken):
                labels.append((t, *at))
    for a in (airports if info else ()):
        ab = bearing(a.x, a.y)
        if in_view(ab, 0) and (at := app.label_at(t := text(a.code, label_style), round(to_x(ab)), hz + 4, taken)):
            labels.append((t, *at))

    img = to_pil(surface)
    for label, x, y in labels:
        place_at(label, img, x, y, 'tl')
    return Frame(img, targets=tuple(targets)).tag(('aviator.sky', fs.config.name))
