'''The M5Dial on the fridge (esp-displays' lite, 240 x 240, round): the time over the solar clock, the timer on the
dial, the rest in a ring of apps, as M5's own launcher (M5Dial-UserDemo).

The dial and its button come as telemetry (as the HUB75 panels' remote), touches as the targets' 'dial' action.
Home: a turn sets a timer, a press or a tap opens the ring. The rings (apps, lights): a turn moves, a press or a tap
on the middle opens (switches). The other apps: a turn sets a timer, a press goes back to the ring. A long press:
home. Left alone a while: home.

The timer: a turn and the time shows, faster the further it goes (a pause: by the second again), down to 0 it hides;
a press or a tap on it starts it. The known timers sit round the edge: a tap starts one. The pill at the bottom
lends the dial for a while: 'pick' moves round the known ones (a press starts, a long press forgets), '+/-' changes
the timer in front (a long press cancels it). A long press while setting: save it as a known timer, its icon picked
from a grid. Running ones newest first, the front one big; a tap on another brings it. Ringing: any touch or turn
mutes it (the dial mutes itself first: its timers are its own too, sent as the 'timers' act; they ring there).
'''
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw

from discore.data_structures import FrameState
from discore.elements import Frame, Target
from discore.layouts import vstack, place_at
from discore.text import text, TextStyle

from disinfo import fonts
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage
from disinfo.utils import mdi
from disinfo.utils.func import throttle
from disinfo.utils.hass import HaWS, get_entity
from disinfo.web.telemetry import TelemetryStateManager, act
from disinfo.apps import timer as T
from disinfo.apps.timer import TimerEntry, timers, mmss, pixel_icon
from disinfo.screens import weather, now_playing, paris_metro, klipper
from disinfo.screens.solar.app import composer as solar, AnalogClockStyle
from disinfo.screens.entry import BUTTONS, HOLD, action, big

S = 240
C = S // 2
SS = 3                  # supersampled: smooth circles
IDLE = 30               # s, then home
IDLE_SET = 10           # s, a timer being set: dropped
MODE = 6                # s, the dial lent to pick / adjust
SYNC = 20               # s, the timers to the dial again, changed or not
LONG = 0.8              # s, a long press
MOVE = 0.3              # s, the selector from one item to the next
OPEN = 0.25             # s, an app growing from its icon
ORANGE = '#C7722D'
ON = '#EB8429'

# name, title, icon, colour (M5's launcher colours)
APPS = [
    ('timer', 'Timer', 'timer-outline', '#FD5C4C'),
    ('weather', 'Weather', 'weather-partly-cloudy', '#577EFF'),
    ('music', 'Music', 'music', '#03A964'),
    ('lights', 'Lights', 'lightbulb-group', ON),
    ('metro', 'Metro', 'subway-variant', '#1AA198'),
    ('printers', 'Printers', 'printer-3d', '#04A279'),
    ('home', 'Clock', 'clock-outline', '#5D7BA2'),
]
NAMES = [a[0] for a in APPS]


class DialRemote(AppBaseModel):
    n: int = 0
    cmds: list = []         # [n, payload], the newest last

class DialRemoteManager(PubSubStateManager[DialRemote]):
    model = DialRemote
    channels = ('di.pubsub.remote',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'dial':
            self.state.n += 1
            self.state.cmds = [*self.state.cmds[-7:], [self.state.n, data.payload]]

@dataclass
class Sel:
    # a ring's selected item, and the one its selector comes from
    i: int = 0
    prev: int = 0
    at: float = 0

    def to(self, i: int, n: int):
        i %= n
        if i != self.i:
            self.prev, self.i, self.at = self.i, i, time.monotonic()

@dataclass
class State:
    view: str = 'home'
    apps: Sel = field(default_factory=Sel)
    lights: Sel = field(default_factory=Sel)
    opened_at: float = 0
    since: float = field(default_factory=time.monotonic)     # the last input
    enc: int = 0
    enc_at: float | None = None         # the client's clock
    pressed_at: float | None = None
    down: bool = False
    down_at: float = 0
    long: bool = False
    seen: int = 0
    setting: int = 0            # s, a timer being set
    checkpt: int = 0
    turned_at: float = 0
    like: tuple = ()            # (label, icon): the time being set came from that timer
    mode: str = 'time'          # what a turn does on the timer: time, pick, adjust
    front: str = ''             # the timer in front
    known: Sel = field(default_factory=Sel)
    icons: Sel = field(default_factory=Sel)
    synced: tuple = ()
    synced_at: float = 0

states = defaultdict(State)


def turns(fs: FrameState, st: State) -> int:
    enc = TelemetryStateManager(fs.config.name).get_state(fs).remote.encoder
    if st.enc_at is None or enc.updated_at < st.enc_at:
        # First seen, or the client restarted (its clock and the position start over): no turn.
        st.enc, st.enc_at = enc.position, enc.updated_at
        return 0
    d, st.enc, st.enc_at = enc.position - st.enc, enc.position, enc.updated_at
    return d

def button(fs: FrameState, st: State) -> str | None:
    # 'press' on release, 'long' once held LONG (no press after it).
    b = TelemetryStateManager(fs.config.name).get_state(fs).remote.buttons.select
    if b.pressed_at != st.pressed_at:
        first = st.pressed_at is None or b.pressed_at < st.pressed_at
        st.pressed_at, st.down, st.long, st.down_at = b.pressed_at, b.pressed and not first, False, time.monotonic()
        return None if first or b.pressed else 'press'
    if st.down and not b.pressed:
        st.down = False
        return None if st.long else 'press'
    if st.down and not st.long and time.monotonic() - st.down_at > LONG:
        st.long = True
        return 'long'

def touched(fs: FrameState, st: State) -> list[dict]:
    r = DialRemoteManager().get_state(fs)
    new = [p for n, p in r.cmds if n > st.seen and p.get('screen') == fs.config.name]
    st.seen = r.n
    return new


def go(st: State, view: str):
    if view != st.view:
        st.view, st.opened_at = view, time.monotonic()
    if view in NAMES:
        st.apps.to(NAMES.index(view), len(APPS))

MODES = ('time', 'pick', 'adjust')

def set_timer(st: State, d: int, shown: list[TimerEntry]):
    # A pause starts small again (fast_increments); down to 0: hidden. The first click with a timer in front (if
    # prefs say so): its time, a new one like it.
    now = time.monotonic()
    if not st.setting and T.prefs()['from_front'] and (t := front(st, [t for t in shown if t.left() > -t.tail])):
        st.setting, st.checkpt, st.turned_at, st.like = t.duration, t.duration, now, (t.label, t.icon)
        return go(st, 'timer')
    if not st.setting:
        st.like = ()
    if now - st.turned_at > 0.5:
        st.checkpt = st.setting
    st.setting = T.stepped(st.setting, st.checkpt, d, T.dial_increments)
    st.turned_at = now
    go(st, 'timer')

def started(fs: FrameState, st: State, t: TimerEntry):
    st.setting, st.checkpt, st.like, st.front, st.mode = 0, 0, (), t.pk, 'time'
    act(fs, 'buzzer', 'ok', f'dial.{t.pk}')
    go(st, 'timer')

def start_known(fs: FrameState, st: State, i: int):
    ks = T.known()
    if ks:
        k = ks[i % len(ks)]
        started(fs, st, T.start(k['duration'], k['label'], k['icon'], fs.config.name))

def front(st: State, shown: list[TimerEntry]) -> TimerEntry | None:
    return next((t for t in shown if t.pk == st.front), shown[0] if shown else None)

def adjust(st: State, shown: list[TimerEntry], d: int):
    # the front one: 15 s a click, a minute past 10 minutes to go
    if (t := front(st, shown)):
        T.shift(t, d * (60 if t.left() > 600 else 15))

def save(fs: FrameState, st: State):
    T.remember(T.ICONS[st.icons.i], st.setting)
    act(fs, 'buzzer', 'ok', f'dial.save.{st.setting}')
    go(st, 'timer')

def sync(fs: FrameState, st: State, shown: list[TimerEntry]):
    # The dial's own copy: [id, end (epoch s), duration, label, muted], the newest first. It rings them itself.
    ts = tuple((t.pk[-8:], round(t.target.timestamp(), 1), t.duration, t.label[:12], t.muted) for t in shown[:8])
    if ts != st.synced or time.monotonic() - st.synced_at > SYNC:
        st.synced, st.synced_at = ts, time.monotonic()
        act(fs, 'timers', [list(t) for t in ts], f'dial.timers.{hash(ts)}')

def lights() -> list:
    # entry's buttons that Home Assistant has: (label, entity, icon, service, on)
    found = [(name, e, icon) for name, eid, icon, _ in BUTTONS if (e := get_entity(eid))]
    last = max((e.state for _, e, _ in found if e.entity_id.startswith('scene.')), default=None)
    return [(name, e, icon, *action(e, last)) for name, e, icon in found]

def switch(st: State, long: bool) -> bool:
    # The selected light: a press for the rest, a long press for a button (the vacuum: as entry's hold)
    ls = lights()
    if not ls:
        return False
    _, e, _, service, _ = ls[st.lights.i % len(ls)]
    if service.endswith('.press') != long:
        return False
    HaWS().call_service(service, target={'entity_id': e.entity_id})
    return True

def handle(fs: FrameState, st: State, shown: list[TimerEntry]):
    now = time.monotonic()
    d, b, taps = turns(fs, st), button(fs, st), touched(fs, st)
    if d or b or taps:
        st.since = now
        if T.mute(shown):           # quiet first: that's all a touch or a turn does then
            return
    if any(t.ringing() for t in shown):
        go(st, 'timer')
        st.since = now          # as a touch: the timer stays a while after
    timer = st.view not in ('menu', 'lights', 'save')
    if d:
        if st.view == 'menu':
            st.apps.to(st.apps.i + d, len(APPS))
        elif st.view == 'lights':
            st.lights.to(st.lights.i + d, max(len(lights()), 1))
        elif st.view == 'save':
            st.icons.to(st.icons.i + d, len(T.ICONS))
        elif st.mode == 'pick':
            st.known.to(st.known.i + d, max(len(T.known()), 1))
        elif st.mode == 'adjust':
            adjust(st, shown, d)
        else:
            set_timer(st, d, shown)
    if b == 'press':
        if st.view == 'save':
            save(fs, st)
        elif timer and st.mode == 'pick':
            start_known(fs, st, st.known.i)
        elif timer and st.mode == 'adjust':
            st.mode = 'time'
        elif timer and st.setting:
            started(fs, st, T.start(st.setting, *st.like, origin=fs.config.name))
        elif st.view == 'menu':
            go(st, NAMES[st.apps.i])
        elif st.view == 'lights':
            switch(st, False)
        else:
            go(st, 'menu')
    elif b == 'long':
        if timer and st.mode == 'pick' and (ks := T.known()):
            T.forget(ks[st.known.i % len(ks)]['icon'])
            act(fs, 'buzzer', 'boop', f'dial.forget.{now}')
        elif timer and st.mode == 'adjust' and (t := front(st, shown)):
            T.cancel(t.pk)
            st.mode = 'time'
        elif timer and st.setting:
            go(st, 'save')
        elif not (st.view == 'lights' and switch(st, True)):
            st.setting = 0
            go(st, 'home')
    for p in taps:
        if p.get('go') == 'start' and st.setting:
            started(fs, st, T.start(st.setting, *st.like, origin=fs.config.name))
        elif p.get('go') == 'open':
            go(st, NAMES[st.apps.i])
        elif 'known' in p:
            start_known(fs, st, p['known'])
        elif 'icon' in p:
            st.icons.to(p['icon'], len(T.ICONS))
            save(fs, st)
        elif 'front' in p:
            st.front = p['front']
        elif 'cancel' in p:
            T.cancel(p['cancel'])
        elif 'repeat' in p and (t := next((t for t in shown if t.pk == p['repeat']), None)):
            t.repeat = int(not t.repeat)
            t.save()
        elif 'mode' in p:
            st.mode = MODES[(MODES.index(st.mode) + 1) % len(MODES)]
        elif 'light' in p:
            st.lights.to(p['light'], max(len(lights()), 1))
        elif p.get('go'):
            go(st, p['go'])
    if st.mode != 'time' and now - st.since > MODE:
        st.mode = 'time'
    if st.setting and now - st.since > IDLE_SET:
        st.setting = 0
    if st.view == 'save' and not st.setting:
        go(st, 'timer')
    if st.view != 'home' and now - st.since > IDLE and not st.setting:
        go(st, 'home')


# --- drawing
def ease_back(t: float) -> float:
    # overshoots a little, then settles (M5's selector: LVGL's overshoot)
    t = min(max(t, 0), 1) - 1
    return t * t * (2.7 * t + 1.7) + 1

def polar(r: float, a: float) -> tuple[float, float]:
    return C + r * math.cos(a), C + r * math.sin(a)

def angle(i: int, n: int) -> float:
    return -math.pi / 2 + 2 * math.pi * i / n

def rgba(hex_: str, alpha: int = 255) -> tuple:
    h = hex_.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)

def smooth(draw_fn, size: int = S) -> Image.Image:
    # drawn SS times bigger, then down: smooth edges
    img = Image.new('RGBA', (size * SS, size * SS), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(img), SS)
    return img.resize((size, size), Image.LANCZOS)

def label(s: str, font=fonts.px_op__l, color: str = '#e0e0e0') -> Frame:
    return text(s, TextStyle(font=font, color=color))

def tap(fs: FrameState, action: dict, x: int, y: int, w: int, h: int, hold: float = 0) -> Target:
    return Target(x, y, w, h, 'dial', {'screen': fs.config.name, **action}, hold)

R_ICON, R_DOT, ICON = 88, 56, 22

@lru_cache(maxsize=32)
def ring_image(items: tuple, sel: int) -> Image.Image:
    # items: (icon, colour, filled); the selected one bigger
    n = len(items)
    def draw(d, k):
        for i, (_, color, filled) in enumerate(items):
            x, y = polar(R_ICON, angle(i, n))
            r = (ICON + 3 if i == sel else ICON) * k
            box = (x * k - r, y * k - r, x * k + r, y * k + r)
            if filled:
                d.ellipse(box, fill=rgba(color, 255 if i == sel else 200))
            else:
                d.ellipse(box, fill=(40, 40, 40, 255), outline=rgba(color, 255 if i == sel else 150), width=2 * k)
    img = smooth(draw)
    for i, (icon, _, _) in enumerate(items):
        f = mdi.icon(icon, 30 if i == sel else 26, '#ffffff')
        if f:
            x, y = polar(R_ICON, angle(i, n))
            img.alpha_composite(f.image, (round(x - f.width / 2), round(y - f.height / 2)))
    return img

@lru_cache(maxsize=1)
def dot() -> Image.Image:
    return smooth(lambda d, k: d.ellipse((0, 0, 12 * k - 1, 12 * k - 1), fill=rgba('#F3E9D2')), 12)

def ring_page(fs: FrameState, items: tuple, sel: Sel, title: str, sub: str, targets: list) -> Frame:
    n = len(items)
    img = Image.new('RGBA', (S, S), (0, 0, 0, 255))
    img.alpha_composite(ring_image(items, sel.i % n))
    t = ease_back((time.monotonic() - sel.at) / MOVE)
    a0, a1 = angle(sel.prev, n), angle(sel.i, n)
    if a1 - a0 > math.pi:           # the short way round
        a0 += 2 * math.pi
    elif a0 - a1 > math.pi:
        a1 += 2 * math.pi
    a = a0 + (a1 - a0) * t
    x, y = polar(R_DOT, a)
    img.alpha_composite(dot(), (round(x - 6), round(y - 6)))
    lines = [big(label(title, fonts.px_op__lb, '#F3E9D2'))]
    if sub:
        lines.append(label(sub, fonts.px_op__l, '#a0a0a0'))
    # the label leans towards the selector, as M5's
    lx, ly = polar(R_DOT * 20 / 120, a)
    f = place_at(vstack(lines, gap=2, align='center'), Frame(img), round(lx), round(ly), 'mm')
    return Frame(f.image, hash=('dial.ring', items, sel.i, t >= 1, title, sub), targets=tuple(targets))

def icon_box(i: int, n: int) -> tuple[int, int, int, int]:
    x, y = polar(R_ICON, angle(i, n))
    return round(x - ICON - 4), round(y - ICON - 4), 2 * ICON + 8, 2 * ICON + 8

def subtitle(fs: FrameState, name: str, shown: list[TimerEntry]) -> str:
    if name == 'timer':
        running = [t for t in shown if t.left() > 0]
        return f'{len(running)} running' if running else 'turn to set'
    if name == 'weather' and (w := weather.state.get_weather_data(fs)):
        return f'{round(w.data.temperature)}°'
    return ''

def menu(fs: FrameState, st: State, shown: list[TimerEntry]) -> Frame:
    items = tuple((icon, color, True) for _, _, icon, color in APPS)
    name, title, *_ = APPS[st.apps.i]
    targets = [tap(fs, {'go': 'home'}, 0, 0, S, S), tap(fs, {'go': 'open'}, C - 50, C - 50, 100, 100)]
    targets += [tap(fs, {'go': n}, *icon_box(i, len(APPS))) for i, n in enumerate(NAMES)]
    return ring_page(fs, items, st.apps, title, subtitle(fs, name, shown), targets)

def lights_page(fs: FrameState, st: State) -> Frame:
    ls = lights()
    if not ls:
        return app_page(fs, st)
    i = st.lights.i % len(ls)
    items = tuple((icon or 'lightbulb', ON, on) for _, _, icon, _, on in ls)
    name, e, _, service, on = ls[i]
    sub = 'hold the dial' if service.endswith('.press') else 'on' if on else 'off'
    targets = [tap(fs, {'go': 'menu'}, 0, 0, S, S)]
    # a tap on the middle switches the selected one (a button entity: held, as on entry)
    hold = HOLD if service.endswith('.press') else 0
    targets.append(Target(C - 50, C - 50, 100, 100, 'ha.call', {'service': service, 'target': {'entity_id': e.entity_id}}, hold))
    targets += [tap(fs, {'light': k}, *icon_box(k, len(ls))) for k in range(len(ls))]
    return ring_page(fs, items, st.lights, name, sub, targets)

@lru_cache(maxsize=4)
def edge_arc(deg: int, color: str) -> Image.Image:
    return smooth(lambda d, k: d.arc((2 * k, 2 * k, (S - 2) * k, (S - 2) * k), -90, -90 + deg, fill=rgba(color), width=4 * k))

# The timer: pixel art, drawn at 1x. The known ones round the edge, the time in the middle, an arc between.
R_KNOWN, R_ARC, KNOWN_N, SPAN = 96, 62, 10, 270     # the known ones over SPAN degrees: the bottom left for the pill

def known_xy(i: int, n: int) -> tuple[int, int]:
    step = SPAN / max(n - 1, 1) if n > 5 else 54
    a = math.radians(-90 + (i - (n - 1) / 2) * step)
    return round(C + R_KNOWN * math.cos(a)), round(C + R_KNOWN * math.sin(a))

def arc(d: ImageDraw.ImageDraw, frac: float, color: str, r: int = R_ARC, width: int = 3):
    # the lap gone dim, what's left bright, from the top
    box = (C - r, C - r, C + r, C + r)
    d.ellipse(box, outline=rgba(color, 60), width=1)
    if frac > 0:
        d.arc(box, -90, -90 + 360 * min(frac, 1), fill=rgba(color), width=width)

def known_ring(fs: FrameState, st: State, d: ImageDraw.ImageDraw, img: Image.Image, targets: list, plus: bool):
    ks = T.known()[:KNOWN_N]
    n = len(ks) + plus
    for i, k in enumerate(ks):
        x, y = known_xy(i, n)
        sel = st.mode == 'pick' and i == st.known.i % len(ks)
        d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=(40, 40, 40, 255), outline=rgba(ORANGE if sel else '#606060'), width=2 if sel else 1)
        if (f := pixel_icon(k['icon'], 12, '#f3e9d2' if sel else '#c0c0c0')):
            img.alpha_composite(f.image, (x - 12, y - 12))
        targets.append(tap(fs, {'known': i}, x - 20, y - 20, 40, 40))
    if plus:
        x, y = known_xy(n - 1, n)
        d.ellipse((x - 18, y - 18, x + 18, y + 18), outline=rgba(ORANGE), width=1)
        if (f := pixel_icon('plus', 12, ORANGE)):
            img.alpha_composite(f.image, (x - 12, y - 12))
        targets.append(tap(fs, {'go': 'save'}, x - 20, y - 20, 40, 40))

def pill(fs: FrameState, st: State, img: Image.Image, targets: list):
    # what the dial does: a tap lends it to the next
    s = {'time': 'time', 'pick': 'pick', 'adjust': '+/-'}[st.mode]
    f = place_at(label(s, fonts.px_op__r, '#000000' if st.mode != 'time' else '#a0a0a0'), Frame(Image.new('RGBA', (44, 14), rgba(ORANGE) if st.mode != 'time' else (40, 40, 40, 255))), 22, 7, 'mm')
    img.alpha_composite(f.image, (C - 22, 214))
    targets.append(tap(fs, {'mode': 1}, C - 30, 208, 60, 30))

def timer_page(fs: FrameState, st: State, shown: list[TimerEntry]) -> Frame:
    img = Image.new('RGBA', (S, S), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    targets = [tap(fs, {'go': 'menu'}, 0, 0, S, S)]
    known_ring(fs, st, d, img, targets, plus=bool(st.setting))
    live = [t for t in shown if t.left() > -t.tail]
    t = front(st, live)
    if st.setting:
        arc(d, (st.setting % 3600) / 3600 or 1, ORANGE)
        rows = [label('new', fonts.px_op__r, '#808080'), label(mmss(st.setting), fonts.px_op__xl, '#f0f0f0'), label('press to start', fonts.px_op__r, '#808080')]
        targets.append(tap(fs, {'go': 'start'}, C - 55, C - 35, 110, 70))
    elif t:
        l = t.left()
        ringing = t.ringing()
        if l > 0:
            arc(d, l / max(t.duration, 1), '#577EFF' if not ringing else ORANGE)
        else:       # done: counting on, the arc running down (tail)
            arc(d, 1 + l / t.tail, ORANGE)
        flash = ringing and int(time.time() * 4) % 2
        ic = pixel_icon(t.icon, 14, ORANGE if l <= 0 else '#c0c0c0')
        rows = [ic or label(t.label, fonts.px_op__r, '#a0a0a0'),
                label(T.over(t), fonts.px_op__xl, '#f3e9d2' if flash else ORANGE if l <= 0 else '#f0f0f0'),
                label(f'{t.label if t.label != "T" else "of"} {mmss(t.duration)}', fonts.px_op__r, '#808080')]
        targets.append(tap(fs, {'cancel': t.pk}, C - 45, C - 30, 90, 60, hold=1.2))
        if (r := pixel_icon('repeat', 8, ORANGE if t.repeat else '#808080')):
            img.alpha_composite(r.image, (C + 44, C + 20))
            targets.append(tap(fs, {'repeat': t.pk}, C + 38, C + 14, 28, 28))
    else:
        arc(d, 0, '#606060')
        rows = [label('00:00', fonts.px_op__xl, '#606060'), label('turn to set', fonts.px_op__r, '#808080')]
    f = place_at(vstack([r for r in rows if r], gap=2, align='center'), Frame(img), C, C - 4, 'mm')
    img = f.image
    # the others, newest first: a tap brings one in front
    others = [o for o in live if o is not t or st.setting][:3]
    if others and (st.setting or len(live) > 1):
        chips = [label(T.over(o), fonts.px_op__r, ORANGE if o.left() <= 0 else '#a0a0a0') for o in others]
        x = C - (sum(c.width for c in chips) + 6 * (len(chips) - 1)) // 2
        for o, c in zip(others, chips):
            img.alpha_composite(c.image, (x, 194))
            targets.append(tap(fs, {'front': o.pk}, x - 3, 190, c.width + 6, 16))
            x += c.width + 6
    pill(fs, st, img, targets)
    if any(o.ringing() for o in shown):
        targets.append(tap(fs, {'mute': 1}, 0, 0, S, S))
    return Frame(img, targets=tuple(targets))

def save_page(fs: FrameState, st: State) -> Frame:
    # the icon for a known timer of this long: a 5 x 5 grid, the dial moves, a tap picks
    img = Image.new('RGBA', (S, S), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    targets = [tap(fs, {'go': 'timer'}, 0, 0, S, S)]
    have = {k['icon'] for k in T.known()}
    cell, x0, y0 = 30, C - 75, C - 66
    for i, name in enumerate(T.ICONS):
        x, y = x0 + i % 5 * cell, y0 + i // 5 * cell
        sel = i == st.icons.i
        if sel:
            d.rectangle((x, y, x + cell - 2, y + cell - 2), outline=rgba(ORANGE), width=2)
        if (f := pixel_icon(name, 10, '#f3e9d2' if sel else '#909090' if name not in have else '#577EFF')):
            img.alpha_composite(f.image, (x + 4, y + 4))
        targets.append(tap(fs, {'icon': i}, x, y, cell, cell))
    f = place_at(label(f'save {mmss(st.setting)} as', fonts.px_op__r, '#a0a0a0'), Frame(img), C, 30, 'tm')
    f = place_at(label(T.ICONS[st.icons.i].replace('-outline', '').replace('-', ' '), fonts.px_op__l, ORANGE), f, C, 210, 'bm')
    return Frame(f.image, targets=tuple(targets))

def cards(fs: FrameState, name: str) -> list:
    match name:
        case 'weather':
            return [weather.widgets.weather(fs), weather.widgets.moon_phase(fs)]
        case 'music':
            return [now_playing.widget(fs)]
        case 'metro':
            return paris_metro.widgets(fs)
        case 'printers':
            return klipper.widget(fs)
    return []

def app_page(fs: FrameState, st: State) -> Frame:
    # the app's cards, as the panels have them, twice as big when they fit
    name, title, icon, color = APPS[NAMES.index(st.view)]
    f = place_at(label(title, fonts.px_op__lb, color), Frame(Image.new('RGBA', (S, S), (0, 0, 0, 255))), C, 22, 'tm')
    frames = [x for w in cards(fs, name) if w and (x := w.draw(fs))]
    body = vstack(frames, gap=3, align='center') if frames else label('nothing now', fonts.px_op__l, '#606060')
    if body.width * 2 <= 176 and body.height * 2 <= 160:
        body = big(body)
    f = place_at(body, f, C, C + 12, 'mm')
    return Frame(f.image, targets=(tap(fs, {'go': 'menu'}, 0, 0, S, S), *f.targets))

@throttle(5000)
def sky(fs: FrameState) -> Frame:
    # the solar clock moves slowly: drawn anew every 5 s (it was most of the dial's time on the server)
    return solar(fs, AnalogClockStyle(cx=C, cy=C, dial_radius_multiplier=0.48, tick_radius_multiplier=0.44, needle_radius_multiplier=0.5))

def home(fs: FrameState, st: State, shown: list[TimerEntry]) -> Frame:
    f = sky(fs)
    rows = [label(fs.now.strftime('%H:%M'), fonts.px_op__xl, '#f0f0f0'), label(fs.now.strftime('%a %d %b'), fonts.px_op__l, '#a0a0a0')]
    running = sorted((t for t in shown if t.left() > -t.tail), key=lambda t: t.end)
    if running:
        rows.append(label(T.over(running[0]), fonts.px_op__lb, ORANGE))
    f = place_at(vstack(rows, gap=2, align='center'), f, C, 196, 'bm', frost=1.5)
    if (w := weather.state.get_weather_data(fs)):
        f = place_at(label(f'{round(w.data.temperature)}°', fonts.px_op__lb, '#f0f0f0'), f, C, 30, 'tm', frost=1.5)
    img = f.image
    if running:
        # the soonest timer's time left, round the edge
        t = running[0]
        img = img.copy()
        l = t.left()
        img.alpha_composite(edge_arc(round(360 * (l / max(t.duration, 1) if l > 0 else 1 + l / t.tail)), ORANGE))
    return Frame(img, targets=(tap(fs, {'go': 'menu'}, 0, 0, S, S),))

def opening(fs: FrameState, st: State, page: Frame) -> Frame:
    # the app comes in a circle growing from its icon, its colour round it (M5's grows a circle of it)
    t = (time.monotonic() - st.opened_at) / OPEN
    if t >= 1 or st.view not in NAMES:
        return page
    x, y = polar(R_ICON, angle(NAMES.index(st.view), len(APPS)))
    r = 24 + t * 240
    edge = smooth(lambda d, k: d.ellipse(((x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k), fill=rgba(APPS[NAMES.index(st.view)][3])))
    inside = smooth(lambda d, k: d.ellipse(((x - r + 4) * k, (y - r + 4) * k, (x + r - 4) * k, (y + r - 4) * k), fill=(255, 255, 255, 255)))
    img = Image.new('RGBA', (S, S), (0, 0, 0, 255))
    img.alpha_composite(edge)
    img.paste(page.image, (0, 0), inside.getchannel('A'))
    return Frame(img, targets=page.targets)

def compose(fs: FrameState) -> Frame:
    st = states[fs.config.name]
    shown = timers(fs.tick)
    handle(fs, st, shown)
    sync(fs, st, shown)
    match st.view:
        case 'menu':
            page = menu(fs, st, shown)
        case 'timer':
            page = timer_page(fs, st, shown)
        case 'save':
            page = save_page(fs, st)
        case 'lights':
            page = lights_page(fs, st)
        case 'home':
            page = home(fs, st, shown)
        case _:
            page = app_page(fs, st)
    return opening(fs, st, page).tag('dial')
