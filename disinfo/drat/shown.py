'''What's shown: the widgets switched off (the web page's checkboxes), pressed up or away for a while (show_<name>),
the bottom stacks hidden on every screen, a screen in zen.

A press shows a widget that's not up (and checks it again), or hides one that is: it comes back on its schedule.
Unchecked, it stays away till checked or pressed. One writer, the data service; the renderers read it back.
'''
import json
import time

from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.redis import db, publish
from .app_states import PubSubStateManager, PubSubMessage

KEY = 'di.shown'
SEEN_KEY = 'di.shown.seen'      # name -> when a screen last had it up on its own
CHANNEL = 'di.pubsub.shown'
# name: its widgets (by name, the start of it), shown for and hidden for after a press, s (None: till the next press).
WIDGETS = {
    'weather': (('weather.widget',), 600, 900),
    'graphs': (('weather.graphs',), 600, 900),
    'moon': (('moon_phase',), 600, 900),
    'music': (('music', 'shazam.recognized'), 600, 900),
    'planes': ((), 600, 900),               # their cards (aviator.widgets): away, the planes go in the tile
    'plane_tile': (('aviator-tile',), 600, 900),
    'metro': (('di.metro',), 60, 900),
    'printers': (('printer_',), 600, 900),
    'dishwasher': (('dishwasher',), 600, 900),
    'washing_machine': (('washing_machine',), 600, 900),
    'trash_pickup': (('trash_pickup',), 600, 900),
    'sensors': (('info_sensors',), None, None),
    'news': ((), None, None),
    'twentytwo': ((), None, None),
    'fonts_credit': (('fonts_demo',), None, None),
    'stream': (('stream',), None, None),
    'design_demo': ((), None, None),
}
ZEN = {'weather.widget'}        # the cards zen keeps, with the ones asking for focus (a print starting, a tap)
zen_s = 3600                    # s, then a screen's zen ends
seen_every = 5                  # s between two notes that a widget is up
seen_s = 15                     # noted that long ago, it's still up


class Shown(AppBaseModel):
    off: list[str] = []
    press: dict[str, dict] = {}         # name -> {show, until (None: till the next press), at}
    bottom: bool = True                 # the bottom stacks, on every screen
    zen: dict[str, list] = {}           # screen -> [since, until]

def load() -> Shown:
    try:
        return Shown(**json.loads(db.get(KEY) or '{}'))
    except ValueError:
        return Shown()

def save(s: Shown):
    db.set(KEY, s.model_dump_json())
    publish(CHANNEL, 'update')

class ShownStateManager(PubSubStateManager[Shown]):
    model = Shown
    channels = (CHANNEL,)

    def initial_state(self) -> Shown:
        return load()

    def process_message(self, channel: str, data: PubSubMessage):
        self.state = load()


def pressed(s: Shown, name: str, now: float) -> dict | None:
    p = s.press.get(name)
    return p if p and (p['until'] is None or now < p['until']) else None

def zen_since(s: Shown, screen: str, now: float) -> float | None:
    z = s.zen.get(screen)
    return z[0] if z and now < z[1] else None

def wanted(s: Shown, name: str, scheduled: bool, now: float, screen: str | None = None) -> bool:
    '''Up: unchecked never, pressed as pressed, its schedule otherwise. In zen, only pressed up since.'''
    if name in s.off:
        return False
    p = pressed(s, name, now)
    if screen and (since := zen_since(s, screen, now)):
        return bool(p and p['show'] and p.get('at', 0) >= since)
    return p['show'] if p else scheduled

_saw = {}

def saw(name: str, now: float):
    # Up on its own: the press reads it, a press hides it.
    if now - _saw.get(name, 0) > seen_every:
        _saw[name] = now
        db.hset(SEEN_KEY, name, now)

def up(fs: FrameState, name: str, scheduled: bool = False) -> bool:
    s, now = ShownStateManager().get_state(fs), time.time()
    if scheduled and not pressed(s, name, now):
        saw(name, now)
    return wanted(s, name, scheduled, now, fs.config.name)

def is_pressed(fs: FrameState, name: str) -> bool:
    # Pressed up and still holding: it asks for focus.
    p = pressed(ShownStateManager().get_state(fs), name, time.time())
    return bool(p and p['show'])

def zen(fs: FrameState) -> bool:
    return zen_since(ShownStateManager().get_state(fs), fs.config.name, time.time()) is not None

def bottom(fs: FrameState) -> bool:
    return ShownStateManager().get_state(fs).bottom

def group(widget_name: str) -> str | None:
    return next((g for g, (names, *_) in WIDGETS.items() if any(widget_name.startswith(n) for n in names)), None)

def kept(fs: FrameState, widgets: list, where: str = 'side') -> list:
    '''The stack's widgets as wanted: a group away loses its frame (it shrinks away). In zen, or the bottom stacks
    hidden, only the ones asking for focus keep theirs (and zen's own).'''
    s, now = ShownStateManager().get_state(fs), time.time()
    z = zen_since(s, fs.config.name, now) is not None
    hidden = where == 'bottom' and not s.bottom
    out = []
    for w in filter(None, widgets):
        g = group(w.name)
        away = g and not wanted(s, g, True, now)
        if g and w.frame and not away and not pressed(s, g, now):
            saw(g, now)
        if away or ((z or hidden) and not w.focus and not (z and not hidden and w.name in ZEN)):
            w.frame = None
        out.append(w)
    return out


# The writer: the data service.

def press(name: str, now: float | None = None) -> bool:
    '''show_<name>: up if it's not (checked again), away if it is. Returns whether it's up now.'''
    s, now = load(), now or time.time()
    _, show_for, hide_for = WIDGETS[name]
    p = pressed(s, name, now)
    on = p['show'] if p else name not in s.off and now - float(db.hget(SEEN_KEY, name) or 0) < seen_s
    s.press[name] = {'show': not on, 'until': (hide_for if on else show_for) and now + (hide_for if on else show_for), 'at': now}
    if not on:
        s.off = [n for n in s.off if n != name]
    save(s)
    return not on

def act(action: str, payload: dict | None) -> bool:
    '''The remote's actions this is about, done; False for the others.'''
    payload, now = payload or {}, time.time()
    if action.startswith('show_') and action[5:] in WIDGETS:
        press(action[5:], now)
        return True
    s = load()
    match action:
        case 'widget':
            # A checkbox: off stays off. Unchecked, its press goes too.
            name, on = payload['name'], bool(payload['on'])
            s.off = [n for n in s.off if n != name] + ([] if on else [name])
            if not on:
                s.press.pop(name, None)
        case 'bottom':
            s.bottom = bool(payload['on']) if 'on' in payload else not s.bottom
        case 'zen':
            screen = payload['screen']
            on = bool(payload['on']) if 'on' in payload else zen_since(s, screen, now) is None
            s.zen = {k: v for k, v in s.zen.items() if k != screen and now < v[1]} | ({screen: [now, now + zen_s]} if on else {})
        case _:
            return False
    save(s)
    return True
