import math
import time
import cairocffi as cairo

from functools import cache
from typing import NamedTuple

from discore.cairo import to_pil
from discore.elements import Frame, Target
from discore.data_structures import FrameState
from discore.layouts import place_at
from discore.layers import div
from discore.text import TextStyle, text
from disinfo import fonts
from disinfo.config import app_config

from .state import ADSBxStateManager, OpenedStateManager
from .colors import marker_color
from . import basemap
from .utils import airports, local_xy


airport_km = 9          # around an airport with a queue
sweep = 4               # s zoomed on the plane of a card the first time it comes on top
sweep_zoom = 2.5
rings = [5, 10, 20, 30]
spokes = 30             # degrees between them
class Theme(NamedTuple):
    scope_center: tuple
    scope_edge: tuple
    window_edge: tuple
    grid: tuple
    home: tuple
    airport: tuple
    landmark: tuple
    halo: tuple         # around the planes with a card
    label: TextStyle
    ring: TextStyle

# The radar is a background: dim, the cards go on top. Dark greys only (the lighter window half cost power and data).
dark = Theme(
    (0.09, 0.10, 0.11), (0.04, 0.045, 0.05), (1, 1, 1, 0.22), (1, 1, 1, 0.09),
    (0.9, 0.55, 0.2, 1), (0.55, 0.57, 0.6, 0.7), (0.6, 0.75, 0.95, 0.45), (1, 1, 1),
    TextStyle(font=fonts.microfont_35_reg, color='#8b8e94b0'), TextStyle(font=fonts.exsmall, color='#5b5e6490'))
# The light mode, for a bright room: the dark one inverted, on a medium grey, not a light one (an LED panel: glare
# and power). What's drawn over it is dark.
light = Theme(
    (0.60, 0.62, 0.65), (0.47, 0.49, 0.52), (0, 0, 0, 0.32), (0, 0, 0, 0.12),
    (0.80, 0.35, 0.02, 1), (0.12, 0.13, 0.16, 0.75), (0.05, 0.15, 0.45, 0.6), (0, 0, 0),
    TextStyle(font=fonts.microfont_35_reg, color='#1c1e24c8'), TextStyle(font=fonts.exsmall, color='#2c2f3698'))
landmark_px = (4, 1.5)  # dot size at the resting view, near to far; it grows with the zoom, by its square root
landmark_max = 8
landmark_far = 20       # km: the size of the farthest
trail_alpha = 0.4
# The table keeps 10 minutes, the background shows the last few: st.trail, from the web page.
watched_fade = 600      # the watched planes show their whole approach
ahead = 120             # s of the path ahead of the watched planes, dashed
plane_alpha = 0.8
plane_outline = (0, 0, 0, 0.7)
# Dark digits on the plane's color: the planes seen from the window are numbered, on the map and in the tile.
pill_style = TextStyle(font=fonts.microfont_35_reg, color='#000000')

_cams = {}              # screen -> [x, y, s, at]: center in km, px per km; eases towards the view
_on_top = {}            # screen -> the plane of the card on top of the stack
_following = {}         # screen -> the plane followed: the last card on top, while it has a card
_swept = {}             # screen -> (plane, when its card first came on top)
_seen_on_top = {}       # screen -> the planes zoomed on already: once each, cards take turns on top
_held = {}              # screen -> the view while following: moved only when the plane leaves the clear box
_moving = {}            # screen -> the camera's still easing towards its view
# The planes move about a pixel a second: redrawn every frame only while the camera moves, its view held still
# otherwise, the trails faded in steps. The displays (the Guition) then get frames that changed only where the
# clock and the scrollers are, and the planes.
redraw_every = 1
drift_px = 6             # how far the view wanders, px
drift_zoom = 0.05
drift_period = 150      # s
redraw_moving = 1 / 12  # while the camera moves: smooth enough, half the frames a 25 fps renderer makes
fade_step = 15
_drawn = {}             # screen -> (when, frame)


@cache
def pill(n: int, color: str) -> Frame:
    return div(text(f'{n}', pill_style), padding=(1, 1, 0, 1), radius=1, background=color)

def number(st, hex: str) -> int | None:
    return st.watched.index(hex) + 1 if hex in st.watched else None

def label_at(label: Frame, x: int, y: int, taken: list) -> tuple[int, int] | None:
    # Right of the point, else left, under, over: where it overlaps no label placed yet. None when it's all taken.
    w, h = label.size
    for lx, ly in ((x + 4, y - 2), (x - w - 3, y - 2), (x - w // 2, y + 4), (x - w // 2, y - h - 3)):
        if not any(lx < tx + tw and tx < lx + w and ly < ty + th and ty < ly + h for tx, ty, tw, th in taken):
            taken.append((lx, ly, w, h))
            return lx, ly
    return None

def rotated(up: float):
    # Turns (km east, km north) so the bearing up is up.
    c, s = math.cos(math.radians(up)), math.sin(math.radians(up))
    return lambda x, y: (x * c - y * s, x * s + y * c)

def to_angle(b: float) -> float:
    # A bearing (clockwise from north) as cairo's angle (clockwise from +x).
    return math.radians(b - 90)

def fit(points: list[tuple[float, float]], w: int, h: int, margin: int = 4) -> tuple[float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    s = min((w - 2 * margin) / (max(xs) - min(xs)), (h - 2 * margin) / (max(ys) - min(ys)))
    return (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, s

def view(focus: str | None, radius: float, rot, w: int, h: int) -> tuple[float, float, float]:
    # The window's slice: home and the arc of its bearings at the radius. Or an airport with a queue.
    airport = next((a for a in airports if a.code == focus), None)
    if airport:
        k = airport_km
        return fit([rot(airport.x + dx, airport.y + dy) for dx in (-k, k) for dy in (-k, k)], w, h)
    start, end = app_config.aviator_window
    arc = [start + (end - start) % 360 * i / 12 for i in range(13)]
    return fit([(0, 0), *[rot(radius * math.sin(math.radians(b)), radius * math.cos(math.radians(b))) for b in arc]], w, h)

def zoomed(target: tuple, xy: tuple[float, float], clear: tuple, w: int, h: int, zoom: float = sweep_zoom) -> tuple[float, float, float]:
    # Closer, the plane in the middle of the clear box (x0, y0, x1, y1) of the frame, the cards cover the rest.
    s = target[2] * zoom
    bx, by = (clear[0] + clear[2]) / 2, (clear[1] + clear[3]) / 2
    return xy[0] - (bx - w / 2) / s, xy[1] + (by - h / 2) / s, s

def inside(target: tuple, xy: tuple[float, float], clear: tuple, w: int, h: int, margin: int = 6) -> bool:
    cx, cy, s = target
    px, py = w / 2 + (xy[0] - cx) * s, h / 2 - (xy[1] - cy) * s
    return clear[0] + margin <= px <= clear[2] - margin and clear[1] + margin <= py <= clear[3] - margin

def held(fs: FrameState, base: tuple, xy: tuple[float, float], clear: tuple, w: int, h: int) -> tuple[float, float, float]:
    # Still while the plane's in the clear box; it's put back in its middle when it leaves.
    t = _held.get(fs.config.name)
    if t is None or t[2] != base[2] or not inside(t, xy, clear, w, h):
        t = zoomed(base, xy, clear, w, h, 1)
    _held[fs.config.name] = t
    return t

def drift(target: tuple[float, float, float]) -> tuple[float, float, float]:
    # Slow motion while nothing's followed: the view wanders about its middle and breathes, over a couple of minutes.
    # A fraction of a pixel a second: redrawn once a second, the displays get a small change each time.
    cx, cy, s = target
    t = time.time()
    r = drift_px / s
    return (cx + r * math.sin(2 * math.pi * t / drift_period),
            cy + r * math.sin(2 * math.pi * t / (drift_period * 1.37)),
            s * (1 + drift_zoom * math.sin(2 * math.pi * t / (drift_period * 0.83))))

def camera(fs: FrameState, target: tuple[float, float, float]) -> tuple[float, float, float]:
    now = time.monotonic()
    c = _cams.setdefault(fs.config.name, [*target, now])
    k = 1 - math.exp(-(now - c[3]) / 0.8)
    c[:] = *(a + (b - a) * k for a, b in zip(c[:3], target)), now
    # Close enough: on it. Easing on by fractions of a pixel would change every pixel of every frame.
    _moving[fs.config.name] = abs(c[2] - target[2]) / target[2] > 0.01 or math.hypot(c[0] - target[0], c[1] - target[1]) * c[2] > 0.5
    if not _moving[fs.config.name]:
        c[:3] = target
    return c[0], c[1], c[2]

def follow(fs: FrameState, widget):
    # The stack's card on top shows its photo. Its plane is followed while it has a card, the tile on top or not:
    # lit, zoomed on for a moment, and kept out from under the cards.
    name = getattr(widget, 'name', '') or ''
    hex = name.removeprefix('aviator.') if name.startswith('aviator.') else None
    _on_top[fs.config.name] = hex
    if hex:
        seen = _seen_on_top.setdefault(fs.config.name, set())
        if hex not in seen:
            seen.add(hex)
            _swept[fs.config.name] = (hex, time.monotonic())
            if len(seen) > 64:
                seen.clear()
        _following[fs.config.name] = hex

def on_top(fs: FrameState) -> str | None:
    return _on_top.get(fs.config.name)

def following(fs: FrameState) -> str | None:
    st = ADSBxStateManager().get_state(fs)
    hex = _following.get(fs.config.name)
    return hex if hex in st.planes and (hex in st.overhead or hex in OpenedStateManager().get_state(fs).opened) else None

def position(p: dict, now: float, after: float = 0) -> tuple[float, float]:
    # Dead reckoning from the last position: the poller updates every second, the frames are smoother.
    v = p['gs'] / 3600 * (min(now - p['at'], 10) + after)
    return p['x'] + v * math.sin(math.radians(p['track'])), p['y'] + v * math.cos(math.radians(p['track']))

def chevron(ctx: cairo.Context, x: float, y: float, track: float, size: float):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(math.radians(track))
    ctx.scale(size, size)
    ctx.move_to(0, -1.4)
    ctx.line_to(1, 1)
    ctx.line_to(0, 0.4)
    ctx.line_to(-1, 1)
    ctx.close_path()
    ctx.restore()

def scope(ctx: cairo.Context, hx: float, hy: float, s: float, radius: float, up: float, w: int, h: int, labels: list, theme: Theme):
    # A dim grey scope around home, rings and spokes, the window's bearings between brighter ones.
    r = max(w, h) * 1.5
    g = cairo.RadialGradient(hx, hy, 0, hx, hy, radius * s * 1.2)
    g.add_color_stop_rgb(0, *theme.scope_center)
    g.add_color_stop_rgb(1, *theme.scope_edge)
    ctx.set_source(g)
    ctx.paint()
    start, end = app_config.aviator_window
    start, end = start - up, end - up
    ctx.set_source_rgba(*theme.window_edge)
    for b in (start, start + (end - start) % 360):
        ctx.move_to(hx, hy)
        ctx.line_to(hx + r * math.sin(math.radians(b)), hy - r * math.cos(math.radians(b)))
    ctx.stroke()
    ctx.set_source_rgba(*theme.grid)
    for b in range(-round(up), 360 - round(up), spokes):
        ctx.move_to(hx, hy)
        ctx.line_to(hx + r * math.sin(math.radians(b)), hy - r * math.cos(math.radians(b)))
    ctx.stroke()
    # Labelled on the window's middle bearing.
    b = math.radians(start + (end - start) % 360 / 2)
    for km in rings:
        ctx.new_sub_path()
        ctx.arc(hx, hy, km * s, 0, 2 * math.pi)
        labels.append((text(f'{km}', theme.ring), round(hx + km * s * math.sin(b)) + 1, round(hy - km * s * math.cos(b)) + 1))
    ctx.stroke()

def radar(fs: FrameState, clear: tuple | None = None) -> Frame:
    '''The planes around, framed on the window's slice or an airport with a queue.

    clear: the box of the frame the cards don't cover, the plane of the card on top is kept in it.
    '''
    st = ADSBxStateManager().get_state(fs)
    opened = OpenedStateManager().get_state(fs).opened
    w, h = fs.config.width, fs.config.height
    now = time.time()
    followed = following(fs)
    up = map_up(fs)
    rot = rotated(up)
    opened_state = OpenedStateManager().get_state(fs)
    is_light = opened_state.light
    theme = light if is_light else dark
    rest = view(st.focus, st.radius, rot, w, h)
    target = zoomed_view(rest, zoom(fs))
    clear = clear or (0, 0, w, h)
    if followed:
        xy = rot(*position(st.planes[followed], now))
        swept_at = _swept.get(fs.config.name, (None, 0))[1]
        target = zoomed(target, xy, clear, w, h) if time.monotonic() - swept_at < sweep else held(fs, target, xy, clear, w, h)
    else:
        _held.pop(fs.config.name, None)
        target = drift(target)
    cx, cy, s = camera(fs, target)
    project = lambda x, y: (w / 2 + (x - cx) * s, h / 2 - (y - cy) * s)
    to_px = lambda x, y: project(*rot(x, y))

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_line_width(1)
    labels, taken = [], []
    hx, hy = to_px(0, 0)
    scope(ctx, hx, hy, s, st.radius, up, w, h, labels, theme)
    basemap.draw(ctx, now, (cx, cy, s), up, w, h, is_light, frozenset(opened_state.off), fs.config.name)

    for a in airports:
        ax, ay = to_px(a.x, a.y)
        ctx.set_source_rgba(*theme.airport)
        ctx.rectangle(round(ax) - 1.5, round(ay) - 1.5, 4, 4)
        ctx.stroke()
        if at := label_at(code := text(a.code, theme.label), round(ax), round(ay), taken):
            labels.append((code, *at))
    near, far = landmark_px
    grow = math.sqrt(s / rest[2])
    ctx.set_source_rgba(*theme.landmark)
    for lat, lon in app_config.screen_data.aviator.landmarks:
        x, y = local_xy(lat, lon)
        lx, ly = to_px(x, y)
        if -4 < lx < w + 4 and -4 < ly < h + 4:
            ctx.arc(lx, ly, min((near + (far - near) * min(math.hypot(x, y) / landmark_far, 1)) * grow, landmark_max) / 2, 0, 2 * math.pi)
            ctx.fill()
    ctx.set_source_rgba(*theme.home)
    ctx.rectangle(round(hx) - 1, round(hy) - 1, 3, 3)
    ctx.fill()

    targets = []
    # The watched ones last: on top.
    for hex, p in sorted(st.planes.items(), key=lambda i: (i[0] == followed, i[0] in st.watched)):
        color = marker_color(p['alt']).rgb
        watched = hex in st.watched or hex in opened
        fade = watched_fade if watched else st.trail
        alpha = 2 * trail_alpha if watched else trail_alpha
        trail = p['trail']
        for (_, la0, lo0, _), (t1, la1, lo1, _) in zip(trail, trail[1:]):
            age = max(now // fade_step * fade_step - t1, 0)
            if age > fade:
                continue
            ctx.set_source_rgba(*color, alpha * (1 - age / fade))
            ctx.move_to(*to_px(*local_xy(la0, lo0)))
            ctx.line_to(*to_px(*local_xy(la1, lo1)))
            ctx.stroke()

        px, py = to_px(*position(p, now))
        if trail:
            ctx.set_source_rgba(*color, alpha)
            ctx.move_to(*to_px(*local_xy(*trail[-1][1:3])))
            ctx.line_to(px, py)
            ctx.stroke()
        if watched:
            ctx.set_dash([1, 2])
            ctx.set_source_rgba(*color, 0.5)
            ctx.move_to(px, py)
            ctx.line_to(*to_px(*position(p, now, ahead)))
            ctx.stroke()
            ctx.set_dash([])
        if not (-8 < px < w + 8 and -8 < py < h + 8):
            continue

        chevron(ctx, px, py, p['track'] - up, 3 if watched else 2.2)
        # The outline is drawn first and the fill over it: only its outer half shows.
        ctx.set_source_rgba(*plane_outline)
        ctx.set_line_width(1.6)
        ctx.stroke_preserve()
        ctx.set_line_width(1)
        # SOURCE: the fill replaces what's under it, the outline's inner half too, or it would darken the plane.
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgba(*color, 1 if watched else plane_alpha)
        ctx.fill()
        ctx.set_operator(cairo.OPERATOR_OVER)
        if hex == followed:
            ctx.set_source_rgba(*theme.halo, 0.85)
            ctx.arc(px, py, 6.5, 0, 2 * math.pi)
            ctx.stroke()
        elif watched:
            ctx.set_source_rgba(*theme.halo, 0.3)
            ctx.arc(px, py, 5.5, 0, 2 * math.pi)
            ctx.stroke()
        if n := number(st, hex):
            labels.append((pill(n, marker_color(p['alt']).hex), round(px) + 5, round(py) - 10))
        targets.append(Target(round(px) - 6, round(py) - 6, 13, 13, 'aviator.open', {'hex': hex}))

    img = to_pil(surface)
    for label, x, y in labels:
        place_at(label, img, x, y, 'tl')
    # Tagged: it moves every frame, the fade in is only for when it shows up.
    return Frame(img, targets=tuple(targets)).tag(('aviator.radar', fs.config.name))


def plane_marks(fs: FrameState) -> list[tuple[float, float, float]]:
    # The planes on the radar (or the sky) drawn last: where, and how much they matter. The followed one most,
    # then the numbered ones, then the others.
    f = _drawn.get(fs.config.name, (0, None))[1]
    if not f:
        return []
    st, followed = ADSBxStateManager().get_state(fs), following(fs)
    return [(t.x + t.w / 2, t.y + t.h / 2, 8 if t.payload['hex'] == followed else 4 if number(st, t.payload['hex']) else 1)
            for t in f.targets if t.action == 'aviator.open']

def throttled(fs: FrameState, draw) -> Frame:
    at, f = _drawn.get(fs.config.name, (0, None))
    now = time.monotonic()
    if f is None or now - at >= (redraw_moving if _moving.get(fs.config.name) else redraw_every):
        f = draw()
        _drawn[fs.config.name] = (now, f)
    return f

def quiet(fs: FrameState) -> bool:
    t = fs.now.strftime('%H:%M')
    return any(a <= t < b for a, b in app_config.aviator_quiet)

def map_up(fs: FrameState) -> float:
    m = OpenedStateManager().get_state(fs)
    return m.map_up.get(fs.config.name, m.map_up.get('*', fs.config.aviator_map_up))

def zoom(fs: FrameState) -> float:
    m = OpenedStateManager().get_state(fs)
    return m.zoom.get(fs.config.name, m.zoom.get('*', fs.config.aviator_zoom))

def zoomed_view(target: tuple[float, float, float], z: float) -> tuple[float, float, float]:
    # z times closer. Pulling out, the center comes to home: all around it shows.
    cx, cy, s = target
    k = min(z, 1)
    return cx * k, cy * k, s * z

def view_mode(fs: FrameState) -> str:
    return OpenedStateManager().get_state(fs).view or fs.config.aviator_view
