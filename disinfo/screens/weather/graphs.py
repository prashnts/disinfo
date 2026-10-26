'''The weather card's graphs: the temperature the stations saw and the one ahead, the rain, the air. Opened by a touch on
the weather card, in a card of their own in the bottom stack; under the weather card itself while the metro's up (the
bottom stack is the metro's then). Each slides down in turn when they open.
'''
import math
import time

from functools import cache
from PIL import Image, ImageDraw

from disinfo import fonts
from discore import ease
from discore.elements import Frame, Target
from discore.text import TextStyle, text
from discore.layouts import hstack, vstack
from discore.transitions import NumberTransition
from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage
from disinfo.screens.colors import light_gray

from . import stations
from .assets import temperature_color

max_width = 140         # the bottom card's graphs on the wide screens
keep_open = 300         # s a touch holds the graphs open (or shut) before the metro decides again
slide_s = 0.35
slide_gap = 0.12        # s between two graphs sliding in
rain_full = 4           # mm/h a rain bar is full at (by its square root: a drizzle shows)
rain_color = (127, 181, 232)        # the forecast lines' blue
dim = '#5b5e64'
s_label = TextStyle(font=fonts.bitocra7, color=dim)
s_value = TextStyle(font=fonts.bitocra7, color=light_gray.darken(0.1).hex)
s_tick = TextStyle(font=fonts.ttpixels, color=dim)


class GraphsState(AppBaseModel):
    tapped: dict[str, list] = {}        # screen -> [shown, when]

class GraphsStateManager(PubSubStateManager[GraphsState]):
    model = GraphsState
    channels = ('di.pubsub.remote',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'weather.graphs' and data.payload:
            self.state.tapped[data.payload['screen']] = [bool(data.payload['show']), time.time()]

def metro_up(fs: FrameState) -> bool:
    from disinfo.screens.paris_metro import MetroStateManager
    from disinfo.drat import idfm
    return idfm.visible(fs.now, MetroStateManager().get_state(fs).press)

def shown(fs: FrameState) -> tuple[bool, str]:
    '''Whether the graphs are open, and where: 'side' (under the weather card, the metro's up) or 'bottom'.'''
    metro = metro_up(fs)
    tap = GraphsStateManager().get_state(fs).tapped.get(fs.config.name)
    on = tap[0] if tap and time.time() - tap[1] < keep_open else metro
    return on, 'side' if metro else 'bottom'

def toggle(fs: FrameState, on: bool):
    # What a touch on a card does, (w, h) -> its target: the other way.
    return lambda w, h: Target(0, 0, w, h, 'weather.graphs', {'screen': fs.config.name, 'show': not on})


def slide(fs: FrameState, name: str, frame: Frame | None, on: bool, i: int = 0) -> Frame | None:
    '''A graph sliding down into view (its bottom first, as from under the one above), and back up.'''
    if frame is None:
        return None
    p = NumberTransition(f'weather.graphs.{name}', slide_s, ease.cubic.cubic_out, 0, i * slide_gap).mut(1 if on else 0).value(fs)
    h = round(frame.height * p)
    if h < 1:
        return None
    return Frame(frame.image.crop((0, frame.height - h, frame.width, frame.height)), hash=('weather.slide', name, frame.hash))


def series(sky: dict | None, past_h: float, ahead_h: float, now: float) -> tuple[list, list]:
    '''The stations' [t, °C, mm/h] since past_h, the forecast's [t, °C, spread, mm, rain_p] until ahead_h.'''
    seen = [[r[0], r[1], r[5]] for r in stations.recent(past_h)]
    hours = ((sky or {}).get('forecast') or {}).get('hours') or []
    ahead = [[r[0], r[1], r[9], r[6], r[7]] for r in hours if r[1] is not None and r[0] <= now + ahead_h * 3600 + 3600]
    return seen, ahead

def at(rows: list, i: int, t: float, within: float = 1800) -> float | None:
    # The value at t, between the two rows around it; None away from them.
    for a, b in zip(rows, rows[1:]):
        if a[0] <= t <= b[0] and a[i] is not None and b[i] is not None and b[0] - a[0] <= 2 * within + 3600:
            return a[i] + (b[i] - a[i]) * (t - a[0]) / (b[0] - a[0])
    near = [r for r in rows if r[i] is not None and abs(r[0] - t) <= within]
    return min(near, key=lambda r: abs(r[0] - t))[i] if near else None

def rgba(c, a: int = 255) -> tuple:
    return (*(round(x * 255) for x in c.rgb), a)

def temp_graph(seen: list, ahead: list, now: float, w: int, h: int, past_h: float, ahead_h: float, labels: bool = True) -> Frame | None:
    '''The temperature, a column a time step: the stations' up to now, the forecast after it with its spread as a band,
    each pixel the colour of its temperature. Its highest and lowest ahead are written by them (labels), the hours under.'''
    t0, t1 = now - past_h * 3600, now + ahead_h * 3600
    ts = [t0 + (t1 - t0) * x / (w - 1) for x in range(w)]
    vs = [at(seen, 1, t, 900) if t <= now else at(ahead, 1, t) for t in ts]
    sp = [at(ahead, 2, t) if t > now else None for t in ts]
    known = [v for v in vs if v is not None]
    if len(known) < w // 4:
        return None
    band = [(v - s, v + s) for v, s in zip(vs, sp) if v is not None and s is not None]
    lo, hi = min(known + [b[0] for b in band]), max(known + [b[1] for b in band])
    if hi - lo < 2:
        lo, hi = (lo + hi) / 2 - 1, (lo + hi) / 2 + 1
    top, bottom = (6, h - 13) if labels else (1, h - 7)        # room for the labels over and under the line, the hours
    y = lambda v: round(bottom - (v - lo) / (hi - lo) * (bottom - top))
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x, (v, s) in enumerate(zip(vs, sp)):
        if v is not None and s is not None:
            d.line([(x, y(v + s)), (x, y(v - s))], fill=rgba(temperature_color(v), 70))
    nx = round((now - t0) / (t1 - t0) * (w - 1))
    for yy in range(top - 2, bottom + 2, 2):
        img.putpixel((nx, yy), rgba(light_gray.darken(0.5)))
    prev = None
    for x, v in enumerate(vs):
        if v is None:
            prev = None
            continue
        c = rgba(temperature_color(v) if x <= nx else temperature_color(v).darken(0.1))
        # Steep: the column joins the last one's pixel, no gaps in the line.
        y0 = y(v) if prev is None else prev
        d.line([(x, y0), (x, y(v))], fill=c)
        img.putpixel((x, y(v)), c)
        prev = y(v)
    # The hours, every 6 (local), under the line.
    off = time.localtime(now).tm_gmtoff
    for t in range(int((t0 + off) // 21600 + 1) * 21600 - off, int(t1), 21600):
        x = round((t - t0) / (t1 - t0) * (w - 1))
        label = text(f'{time.localtime(t).tm_hour}', s_tick)
        if 0 <= x - label.width // 2 and x + label.width // 2 < w:
            img.alpha_composite(label.image, (x - label.width // 2, h - label.height))
            img.putpixel((x, bottom + 1), rgba(light_gray.darken(0.6)))
    # The highest and lowest ahead, by them.
    future = [(x, v) for x, v in enumerate(vs) if v is not None and x > nx]
    for (x, v), above in ((max(future, key=lambda p: p[1]), True), (min(future, key=lambda p: p[1]), False)) if future and labels else ():
        label = text(f'{round(v)}', TextStyle(font=fonts.ttpixels, color=temperature_color(v).hex))
        lx = min(max(x - label.width // 2, nx + 2), w - label.width)
        img.alpha_composite(label.image, (lx, max(y(v) - label.height - 1, 0) if above else y(v) + 2))
    return Frame(img, hash=('weather.temp', w, h, now // 60, len(seen), len(ahead)))

def rain_graph(seen: list, ahead: list, now: float, w: int, h: int, past_h: float, ahead_h: float) -> Frame | None:
    '''The rain on the same hours: what the stations measured, then the forecast's hours, paler as fewer models agree.
    None when it's dry throughout.'''
    t0, t1 = now - past_h * 3600, now + ahead_h * 3600
    cols = []
    for x in range(w):
        t = t0 + (t1 - t0) * x / (w - 1)
        if t <= now:
            cols.append((at(seen, 2, t, 900) or 0, 1))
        else:
            # An hour's rain is the hour that ends at its time.
            hr = next((r for r in ahead if r[0] - 3600 < t <= r[0]), None)
            cols.append((hr[3] or 0, hr[4] or 0) if hr else (0, 0))
    if not any(mm >= 0.1 and p >= 0.2 for mm, p in cols):
        return None
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(0, h - 1), (w - 1, h - 1)], fill=rgba(light_gray.darken(0.75)))
    for x, (mm, p) in enumerate(cols):
        if mm >= 0.1:
            bar = max(1, min(h, round(h * math.sqrt(mm / rain_full))))
            d.line([(x, h - 1), (x, h - bar)], fill=(*rain_color, round(255 * (0.35 + 0.65 * p))))
    return Frame(img, hash=('weather.rain', w, h, now // 60, len(seen), len(ahead)))

@cache
def arrow(up: bool) -> Frame:
    img = Image.new('RGBA', (5, 3), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon([(0, 2), (4, 2), (2, 0)] if up else [(0, 0), (4, 0), (2, 2)], fill=light_gray.darken(0.1).hex)
    return Frame(img, hash=('weather.arrow', up))

def air_row(sky: dict | None) -> Frame | None:
    '''The humidity, the wind (and its gusts), the pressure (an arrow when it moves): what the card has no room for.'''
    from disinfo.screens.aviator.skystate import v
    parts = []
    if (rh := v(sky, 'air.rh')) is not None:
        parts.append(hstack([text(f'{rh}', s_value), text('%', s_label)], gap=1, align='bottom'))
    if (wind := v(sky, 'air.wind')) is not None:
        gust = v(sky, 'air.gust', conf=0.3)
        speed = f'{wind * 3.6:.0f}' + (f'-{gust * 3.6:.0f}' if gust and gust * 3.6 >= wind * 3.6 + 10 else '')
        parts.append(hstack([text(speed, s_value), text('km/h', s_label)], gap=1, align='bottom'))
    if (p := v(sky, 'air.pressure')) is not None:
        tend = v(sky, 'air.tendency')
        parts.append(hstack([text(f'{p:.0f}', s_value), arrow(tend > 0) if tend is not None and abs(tend) >= 1 else None],
                            gap=1, align='center'))
    return hstack(parts, gap=5, align='bottom') if parts else None


_drawn = {}         # (where, w, the minute, the sky state's time) -> the graphs: drawn once a minute

def drawn(sky: dict | None, w: int, where: str, now: float) -> list:
    key = where, w, now // 60, (sky or {}).get('at')
    if key not in _drawn:
        past_h, ahead_h, th = (3, 12, 18) if where == 'side' else (6, 18, 34)
        now = now // 60 * 60
        seen, ahead = series(sky, past_h, ahead_h, now)
        rows = [] if where == 'side' else [('air', air_row(sky))]
        rows += [('temp', temp_graph(seen, ahead, now, w, th, past_h, ahead_h, labels=where != 'side')),
                 ('rain', rain_graph(seen, ahead, now, w, 5, past_h, ahead_h))]
        for k in [k for k in _drawn if k[:2] == key[:2]]:
            del _drawn[k]
        _drawn[key] = rows
    return _drawn[key]

def graphs(fs: FrameState, sky: dict | None, w: int, on: bool, where: str) -> Frame | None:
    '''The graphs, each sliding in (or out) in turn. The side's are smaller: under the weather card, its width.'''
    rows = drawn(sky, w, where, fs.now.timestamp())
    shown = [slide(fs, f'{where}.{name}', f, on, i) for i, (name, f) in enumerate(rows)]
    shown = [f for f in shown if f]
    return vstack(shown, gap=2, align='hstretch') if shown else None
