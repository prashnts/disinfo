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
from . import app, astro, skylook, weather


horizon = 0.7           # of the height, from the top
elev_gamma = 0.5        # y ~ (elevation / 90) ** gamma: the few degrees over the horizon get room
dip_max = 30            # degrees under the horizon at the bottom of the frame, the same stretch
earth_r = 6371
view_fov = 90           # degrees across
fov_min = 25            # zoomed on a plane
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
rim_color = (1, 1, 1, 0.15)
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

def roofs(ctx: cairo.Context, in_view, to_px, h: int, sunlight: tuple[float, float] | None = None):
    # Pixel-crisp: sharp on the LEDs, and nothing changes between frames when the view's still.
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    far, near = city()
    for blocks, color in ((far, far_color), (near, near_color)):
        rims, lit = [], []
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
        ctx.set_source_rgb(*color)
        ctx.fill()
        ctx.set_source_rgba(*rim_color)
        for outline in rims:
            ctx.move_to(*outline[0])
            for p in outline[1:]:
                ctx.line_to(*p)
        ctx.stroke()
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

def camera(fs: FrameState, target: tuple[float, float]) -> tuple[float, float]:
    now = time.monotonic()
    c = _cams.setdefault(fs.config.name, [*target, now])
    k = 1 - math.exp(-(now - c[2]) / 0.8)
    c[:] = c[0] + wrap(target[0] - c[0]) * k, c[1] + (target[1] - c[1]) * k, now
    app._moving[fs.config.name] = abs(wrap(target[0] - c[0])) > 0.3 or abs(target[1] - c[1]) > 0.3
    if not app._moving[fs.config.name]:
        c[:2] = target
    return c[0], c[1]

def aim(st, fov: float) -> float:
    # Towards the planes seen from the window (their mean bearing), kept within the window.
    start, end = app_config.aviator_window
    span = (end - start) % 360 or 360
    seen = [st.planes[h]['bearing'] for h in st.watched if h in st.planes]
    if seen:
        yaw = math.degrees(math.atan2(sum(math.sin(math.radians(b)) for b in seen), sum(math.cos(math.radians(b)) for b in seen)))
    else:
        yaw = start + span / 2
    if fov < span:
        yaw = start + min(max(wrap(yaw - start) % 360, fov / 2), span - fov / 2)
    return yaw

def look(fs: FrameState, st, clear: tuple, w: int) -> tuple[float, float]:
    # Held still while what it looks at stays in view: zoomed on the plane of a card the first time it's on top,
    # then turned only when the followed plane leaves the clear box, or the planes seen move a quarter view away.
    fov = view_fov
    yaw = _held.get(fs.config.name)
    followed = app.following(fs)
    middle = (clear[0] + clear[2]) / 2 - w / 2
    if followed:
        p = st.planes[followed]
        b, _ = sky_point(*app.position(p, time.time()), p['alt'])
        swept_hex, swept_at = app._swept.get(fs.config.name, (None, 0))
        if swept_hex == followed and time.monotonic() - swept_at < app.sweep:
            zoom = max(fov_min, fov / app.sweep_zoom)
            return b - middle / w * zoom, zoom
        px = w / 2 + wrap(b - (yaw if yaw is not None else b)) / fov * w
        if yaw is None or not clear[0] + 6 <= px <= clear[2] - 6:
            yaw = b - middle / w * fov
    else:
        target = aim(st, fov)
        if yaw is None or abs(wrap(target - yaw)) > fov / 4:
            yaw = target
        _held[fs.config.name] = yaw
        # Slow motion while nothing's followed: the heading sways a few degrees, over a few minutes.
        return yaw + sway * math.sin(2 * math.pi * time.time() / sway_period), fov
    _held[fs.config.name] = yaw
    return yaw, fov

def shade(hex: str, k: float) -> tuple[float, float, float]:
    return tuple(min(int(hex[i:i + 2], 16) / 255 * k, 1) for i in (1, 3, 5))

cloud_color = (0.72, 0.75, 0.82)
cloud_alpha = 0.55
cloud_weights = (0.4, 0.3, 0.2, 0.1)       # the nearer, the more it counts
rain_color = (0.68, 0.76, 0.9)
rain_weights = (1, 0.8, 0.6, 0.45, 0.3)
cloud_base_km = 4       # the rain hangs from here: higher in the view the nearer it is
col_step = 2            # px between the columns of a band

def clouds(ctx: cairo.Context, yaw: float, fov: float, w: int, hz: int, h: int):
    # A band of cloud over the horizon, as high as the cover is thick in each direction, grey going to nothing upwards.
    # Returns the cover (0..1) by bearing, for what it hides.
    if not (prof := weather.sky_profile('clouds')):
        return lambda b: 0.0
    values = prof[0]
    xs = np.arange(0, w + col_step, col_step)
    cover = (weather.along(values, yaw + (xs - w / 2) / w * fov) * np.array(cloud_weights, np.float32)).sum(axis=1)
    top = hz - hz * 0.95 * np.clip(cover * 2.5, 0, 1) ** 0.8
    if top.min() < hz - 1:
        g = cairo.LinearGradient(0, top.min(), 0, hz)
        g.add_color_stop_rgba(0, *cloud_color, 0)
        g.add_color_stop_rgba(1, *cloud_color, cloud_alpha)
        ctx.set_source(g)
        ctx.move_to(0, hz)
        for x, y in zip(xs, top):
            ctx.line_to(float(x), float(y))
        ctx.line_to(w, hz)
        ctx.close_path()
        ctx.fill()
    return lambda b: float(np.clip(weather.along(values, np.array([b]))[0] @ np.array(cloud_weights, np.float32) * 2.5, 0, 1))

def rain(ctx: cairo.Context, yaw: float, fov: float, w: int, hz: int, h: int, now: float):
    # Curtains of rain hanging in the directions it rains in, nearer ones higher and stronger; a few drops across
    # the whole view when it rains at home.
    if not (prof := weather.sky_profile('rain')):
        return
    values, home_mm = prof
    xs = np.arange(0, w, col_step)
    along = weather.along(values, yaw + (xs - w / 2) / w * fov) * np.array(rain_weights, np.float32)
    best = along.argmax(axis=1)
    power = along.max(axis=1)
    ctx.set_line_width(1)
    for i, (x, k) in enumerate(zip(xs, best)):
        if power[i] < 0.05:
            continue
        e = math.degrees(math.atan2(cloud_base_km, weather.rain_bins[k]))
        top = hz - hz * (min(e, 90) / 90) ** elev_gamma
        # Streaky: each column its own strength.
        streak = 0.5 + 0.5 * ((x * 37 + k * 11) % 7) / 6
        ctx.set_source_rgba(*rain_color, min(power[i] * 1.4, 0.6) * streak)
        ctx.move_to(float(x) + 0.5, top)
        ctx.line_to(float(x) + 0.5, hz)
        ctx.stroke()
    if home_mm >= 0.2:
        a = min(0.15 + home_mm / 12, 0.45)
        ctx.set_source_rgba(*rain_color, a)
        for i in range(int(w * h / 500)):
            x = (i * 0.6180339887) % 1 * w
            y = ((i * 0.7548776662) % 1 * h + now * 40 + i * 13) % h
            ctx.move_to(x, y)
            ctx.line_to(x - 1.5, y + 5)
        ctx.stroke()

def overhead_cover() -> float | None:
    # The cloud cover over home from the satellite (the nearest bins, every bearing), 0..1; None without data.
    if not (prof := weather.sky_profile('clouds')):
        return None
    return float(np.clip(prof[0][:, :2].mean() * 2.5, 0, 1))

def sky(fs: FrameState, clear: tuple | None = None) -> Frame:
    st = ADSBxStateManager().get_state(fs)
    opened = OpenedStateManager().get_state(fs).opened
    w, h = fs.config.width, fs.config.height
    hz = round(h * horizon)
    now = time.time()
    followed = app.following(fs)
    _eye['m'] = home_ground + fs.config.aviator_eye_m
    yaw, fov = camera(fs, look(fs, st, clear or (0, 0, w, h), w))
    in_view = lambda b, margin=10: abs(wrap(b - yaw)) < fov / 2 + margin
    to_x = lambda b: w / 2 + wrap(b - yaw) / fov * w
    to_px = lambda b, e: (to_x(b), hz - hz * (min(e, 90) / 90) ** elev_gamma if e >= 0 else hz + (h - hz) * (min(-e, dip_max) / dip_max) ** elev_gamma)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_line_width(1)
    labels, taken = [], []

    # The sky: the sun's height, the weather state and the room's light (skylook.py).
    sun = get_position(fs.now.in_tz('UTC'), fs.config.longitude, fs.config.latitude)
    sb, se = (math.degrees(sun['azimuth']) + 180) % 360, math.degrees(sun['altitude'])
    state = skylook.weather_state(fs)
    # No weather state (HA down): the satellite's cover over home stands in.
    lk = skylook.look(se, state or skylook.conditions['partlycloudy'], skylook.light_gain(fs), None if state else overhead_cover())
    skylook.paint(ctx, lk, w, hz, h, to_x(sb) if in_view(sb, 30) else None)
    ctx.set_source_rgba(*horizon_color)
    ctx.move_to(0, hz)
    ctx.line_to(w, hz)
    ctx.stroke()

    off = OpenedStateManager().get_state(fs).off
    info, show_planes = 'info' not in off, 'planes' not in off
    cloud_dim = clouds(ctx, yaw, fov, w, hz, h) if 'clouds' not in off else lambda b: 0.0

    # The sun where it is, its glow over the horizon a little after it's set.
    if se > -6 and in_view(sb, 20):
        sx, sy = to_px(sb, se)
        glow = cairo.RadialGradient(sx, sy, 0, sx, sy, 16)
        dim = 1 - 0.8 * cloud_dim(sb)       # a cloud band in front of it
        glow.add_color_stop_rgba(0, *sun_color, (0.35 if se > 0 else 0.2) * dim)
        glow.add_color_stop_rgba(1, *sun_color, 0)
        ctx.set_source(glow)
        ctx.paint()
        if se > 0:
            ctx.set_source_rgba(*sun_color, dim)
            ctx.arc(sx, sy, 2.5, 0, 2 * math.pi)
            ctx.fill()

    # Stars once the sun is well down (dimmed by the cloud), the moon where it is, fainter in daylight.
    clear_sky = 1 - 0.9 * lk.cloud
    astro.draw_stars(ctx, now, fs.config.latitude, fs.config.longitude, to_px, in_view, min(max((-se - 3) / 12, 0), 1) * clear_sky)
    mb, me, phase = astro.moon_at(now, fs.config.latitude, fs.config.longitude)
    if me > -1 and in_view(mb, 10):
        mx, my = to_px(mb, max(me, 0))
        astro.draw_moon(ctx, mx, my, 3, phase, (1 - 0.65 * min(max(se / 10, 0), 1)) * (1 - 0.8 * cloud_dim(mb)) * (1 - 0.5 * lk.cloud))

    if 'rain' not in off:
        rain(ctx, yaw, fov, w, hz, h, now)

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
    roofs(ctx, in_view, to_px, h, (sb, lk.glow) if lk.glow > 0.03 else None)
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
