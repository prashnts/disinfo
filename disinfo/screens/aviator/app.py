import math
import time
import cairocffi as cairo

from discore.cairo import to_pil
from discore.elements import Frame, Target
from discore.data_structures import FrameState
from discore.layouts import place_at
from discore.text import TextStyle, text
from disinfo import fonts
from disinfo.config import app_config

from .state import ADSBxStateManager, OpenedStateManager
from .colors import marker_color
from .utils import airports, local_xy


airport_km = 9          # around an airport with a queue
sweep = 6               # s zoomed on the plane of a card when it comes on top
sweep_zoom = 2.5
rings = [5, 10, 20, 30]
spokes = 30             # degrees between them
# The radar is a background: dim, the cards go on top.
scope_center = (0.09, 0.10, 0.11)
scope_edge = (0.04, 0.045, 0.05)
# The LEDs crush the dark greys: the window's half needs a clear step, and its edges.
window_tint = (1, 1, 1, 0.08)
window_edge = (1, 1, 1, 0.22)
grid_color = (1, 1, 1, 0.09)
home_color = (0.9, 0.55, 0.2, 1)
airport_color = (0.55, 0.57, 0.6, 0.7)
trail_alpha = 0.4
trail_fade = 180        # s: the table keeps 10 minutes, the background shows the last few
watched_fade = 600      # the watched planes show their whole approach
ahead = 120             # s of the path ahead of the watched planes, dashed
plane_alpha = 0.8
label_style = TextStyle(font=fonts.microfont_35_reg, color='#8b8e94b0')
ring_style = TextStyle(font=fonts.exsmall, color='#5b5e6490')

_cams = {}              # screen -> [x, y, s, at]: center in km, px per km; eases towards the view
_following = {}         # screen -> the plane of the card on top of the stack
_swept = {}             # screen -> (plane, when its card came on top)


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

def zoomed(target: tuple, xy: tuple[float, float], clear: tuple, w: int, h: int) -> tuple[float, float, float]:
    # Closer, the plane in the middle of the clear box.
    s = target[2] * sweep_zoom
    bx, by = (clear[0] + clear[2]) / 2, (clear[1] + clear[3]) / 2
    return xy[0] - (bx - w / 2) / s, xy[1] + (by - h / 2) / s, s

def keep_in(target: tuple, xy: tuple[float, float], clear: tuple, w: int, h: int) -> tuple[float, float, float]:
    # Moves the view so the plane at xy lands in the clear box (x0, y0, x1, y1) of the frame, the cards cover the rest.
    cx, cy, s = target
    px, py = w / 2 + (xy[0] - cx) * s, h / 2 - (xy[1] - cy) * s
    dx = min(max(px, clear[0] + 6), clear[2] - 6) - px
    dy = min(max(py, clear[1] + 6), clear[3] - 6) - py
    return cx - dx / s, cy + dy / s, s

def camera(fs: FrameState, target: tuple[float, float, float]) -> tuple[float, float, float]:
    now = time.monotonic()
    c = _cams.setdefault(fs.config.name, [*target, now])
    k = 1 - math.exp(-(now - c[3]) / 0.8)
    c[:] = *(a + (b - a) * k for a, b in zip(c[:3], target)), now
    return c[0], c[1], c[2]

def follow(fs: FrameState, widget):
    # The stack's card on top: its plane is lit, zoomed on for a moment, and kept out from under the cards.
    name = getattr(widget, 'name', '') or ''
    hex = name.removeprefix('aviator.') if name.startswith('aviator.') else None
    if hex and _swept.get(fs.config.name, (None,))[0] != hex:
        _swept[fs.config.name] = (hex, time.monotonic())
    _following[fs.config.name] = hex

def following(fs: FrameState) -> str | None:
    return _following.get(fs.config.name)

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

def scope(ctx: cairo.Context, hx: float, hy: float, s: float, radius: float, up: float, w: int, h: int, labels: list):
    # A dim grey scope around home, the window's bearings a shade lighter, rings and spokes.
    r = max(w, h) * 1.5
    g = cairo.RadialGradient(hx, hy, 0, hx, hy, radius * s * 1.2)
    g.add_color_stop_rgb(0, *scope_center)
    g.add_color_stop_rgb(1, *scope_edge)
    ctx.set_source(g)
    ctx.paint()
    start, end = app_config.aviator_window
    start, end = start - up, end - up
    ctx.move_to(hx, hy)
    ctx.arc(hx, hy, r, to_angle(start), to_angle(start + (end - start) % 360))
    ctx.close_path()
    ctx.set_source_rgba(*window_tint)
    ctx.fill()
    ctx.set_source_rgba(*window_edge)
    for b in (start, start + (end - start) % 360):
        ctx.move_to(hx, hy)
        ctx.line_to(hx + r * math.sin(math.radians(b)), hy - r * math.cos(math.radians(b)))
    ctx.stroke()
    ctx.set_source_rgba(*grid_color)
    for b in range(-round(up), 360 - round(up), spokes):
        ctx.move_to(hx, hy)
        ctx.line_to(hx + r * math.sin(math.radians(b)), hy - r * math.cos(math.radians(b)))
    ctx.stroke()
    # Labelled on the window's middle bearing.
    b = math.radians(start + (end - start) % 360 / 2)
    for km in rings:
        ctx.new_sub_path()
        ctx.arc(hx, hy, km * s, 0, 2 * math.pi)
        labels.append((text(f'{km}', ring_style), round(hx + km * s * math.sin(b)) + 1, round(hy - km * s * math.cos(b)) + 1))
    ctx.stroke()

def radar(fs: FrameState, clear: tuple | None = None) -> Frame:
    '''The planes around, framed on the window's slice or an airport with a queue.

    clear: the box of the frame the cards don't cover, the plane of the card on top is kept in it.
    '''
    st = ADSBxStateManager().get_state(fs)
    opened = OpenedStateManager().get_state(fs).opened
    w, h = fs.config.width, fs.config.height
    now = time.time()
    following = _following.get(fs.config.name)
    up = fs.config.aviator_map_up
    rot = rotated(up)
    target = view(st.focus, st.radius, rot, w, h)
    clear = clear or (0, 0, w, h)
    if following in st.planes:
        xy = rot(*position(st.planes[following], now))
        swept_at = _swept.get(fs.config.name, (None, 0))[1]
        target = zoomed(target, xy, clear, w, h) if time.monotonic() - swept_at < sweep else keep_in(target, xy, clear, w, h)
    cx, cy, s = camera(fs, target)
    project = lambda x, y: (w / 2 + (x - cx) * s, h / 2 - (y - cy) * s)
    to_px = lambda x, y: project(*rot(x, y))

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_line_width(1)
    labels = []
    hx, hy = to_px(0, 0)
    scope(ctx, hx, hy, s, st.radius, up, w, h, labels)

    for a in airports:
        ax, ay = to_px(a.x, a.y)
        ctx.set_source_rgba(*airport_color)
        ctx.rectangle(round(ax) - 1.5, round(ay) - 1.5, 4, 4)
        ctx.stroke()
        labels.append((text(a.code, label_style), round(ax) + 4, round(ay) - 2))
    ctx.set_source_rgba(*home_color)
    ctx.rectangle(round(hx) - 1, round(hy) - 1, 3, 3)
    ctx.fill()

    targets = []
    # The watched ones last: on top.
    for hex, p in sorted(st.planes.items(), key=lambda i: (i[0] == following, i[0] in st.watched)):
        color = marker_color(p['alt']).rgb
        watched = hex in st.watched or hex in opened
        fade = watched_fade if watched else trail_fade
        alpha = 2 * trail_alpha if watched else trail_alpha
        trail = p['trail']
        for (_, la0, lo0, _), (t1, la1, lo1, _) in zip(trail, trail[1:]):
            age = now - t1
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

        ctx.set_source_rgba(*color, 1 if watched else plane_alpha)
        chevron(ctx, px, py, p['track'] - up, 3 if watched else 2.2)
        ctx.fill()
        if hex == following:
            ctx.set_source_rgba(1, 1, 1, 0.55 + 0.35 * math.sin(now * 5))
            ctx.arc(px, py, 6.5, 0, 2 * math.pi)
            ctx.stroke()
        elif watched:
            ctx.set_source_rgba(1, 1, 1, 0.3)
            ctx.arc(px, py, 5.5, 0, 2 * math.pi)
            ctx.stroke()
        targets.append(Target(round(px) - 6, round(py) - 6, 13, 13, 'aviator.open', {'hex': hex}))

    img = to_pil(surface)
    for label, x, y in labels:
        place_at(label, img, x, y, 'tl')
    # Tagged: it moves every frame, the fade in is only for when it shows up.
    return Frame(img, targets=tuple(targets)).tag(('aviator.radar', fs.config.name))


hold = 90       # s the radar stays after the last reason to show it
_active_at = {}

def quiet(fs: FrameState) -> bool:
    t = fs.now.strftime('%H:%M')
    return any(a <= t < b for a, b in app_config.aviator_quiet)

def active(fs: FrameState) -> bool:
    # A plane seen from the window, a queue at an airport, a card open. Never in the quiet hours.
    if quiet(fs):
        return False
    st = ADSBxStateManager().get_state(fs)
    if st.focus or OpenedStateManager().get_state(fs).opened:
        _active_at[fs.config.name] = time.monotonic()
    return time.monotonic() - _active_at.get(fs.config.name, -hold) < hold
