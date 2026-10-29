import json
import time
import pendulum
import math
import bisect

from datetime import datetime
from dataclasses import dataclass, field
from collections import namedtuple, defaultdict
from redis_om import HashModel, NotFoundError

from disinfo.data_structures import AppBaseModel
from discore.data_structures import FrameState
from discore.widget import Widget
from discore.text import text, TextStyle
from discore.layouts import vstack, hstack
from discore.layers import div, DivStyle
from discore.transitions import Resize, text_slide_in
from disinfo import fonts
from discore.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act
from disinfo.redis import om_db, db
from disinfo.utils import mdi
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage


LONG = 60           # s: a timer this long beeps its last COUNTDOWN seconds, then rings
COUNTDOWN = 7
RINGS = 8           # s the ring lasts: muting stops it meanwhile
KNOWN = 'di.timers.known'       # the known timers (templates): [{label, icon, duration}], as set from the screens
PREFS = 'di.timers.prefs'       # {from_front: a turn starts from the timer in front}

# What a known timer can wear: the kitchen, the chores, the rest.
ICONS = [
    'pasta', 'noodles', 'rice', 'egg-outline', 'pot-steam', 'kettle-steam', 'tea', 'coffee',
    'toaster-oven', 'pizza', 'bread-slice', 'cupcake', 'food-drumstick', 'fish',
    'washing-machine', 'tumble-dryer', 'dishwasher', 'iron', 'shower', 'watering-can', 'pill', 'bed',
    'alarm', 'timer-sand',
]


class TimerEntry(HashModel, index=True):
    target: datetime
    duration: int = 30   # seconds
    icon: str = 'clock'
    overflow: int = 1
    label: str = 'T'
    triggerred: int = 0
    created: float = 0      # epoch s: the newest first
    muted: int = 0
    origin: str = ''        # the screen it was set on
    repeat: int = 0         # done: again, as long

    class Meta:
        database = om_db

    @property
    def end(self):
        return pendulum.instance(self.target, tz='local')

    def left(self) -> float:
        '''Seconds to go, below 0 once done.'''
        return self.target.timestamp() - time.time()

    @property
    def tail(self) -> int:
        # s a done timer stays, counting on: soon minutes for a cake (20 s, 50 s at 1 min, 5 min at 15, 10 at most)
        return round(20 + 600 * (1 - math.exp(-self.duration / 1200)))

    def ringing(self) -> bool:
        l = self.left()
        return not self.muted and (COUNTDOWN if self.duration >= LONG else 0) >= l > -RINGS

@dataclass
class State:
    mode: str = 'init'
    duration: int = 0
    duration_checkpt: int = 0
    last_encoder: int = 0
    last_encoder_at: float | None = None     # the client's clock; None: not seen yet
    last_timer_at: float = 0
    active_pk: str = ''
    direction: bool = False
    down: bool = False

states = defaultdict(State)   # per screen
_pks = [0.0, []]              # when, the timers' keys: all_pks scans all of redis, so once a second at most
sounded = defaultdict(set)    # screen -> (pk, what) the buzzer had

def timers(tick: float) -> list[TimerEntry]:
    '''The timers there, the newest first.'''
    if tick - _pks[0] > 1:
        _pks[:] = tick, list(TimerEntry.all_pks())
    out = []
    for pk in _pks[1]:
        try:
            out.append(TimerEntry.get(pk))
        except NotFoundError:       # expired since
            pass
    again(out)
    return sorted(out, key=lambda t: -t.created)

def start(duration: int, label: str = 'T', icon: str = 'timer-outline', origin: str = '', repeat: int = 0) -> TimerEntry:
    t = TimerEntry(target=pendulum.now().add(seconds=duration), duration=duration, label=label, icon=icon,
                   created=time.time(), origin=origin, repeat=repeat).save()
    t.expire(duration + t.tail + 5)
    _pks[0] = 0
    return t

def again(ts: list[TimerEntry]):
    # The repeating ones done: started again, once (the renderers are many: the first one there). The old one
    # rings, then goes.
    for t in ts:
        if t.repeat and t.left() <= 0 and db.set(f'di.timers.again.{t.pk}', 1, nx=True, ex=60):
            ts.append(start(t.duration, t.label, t.icon, t.origin, 1))
            t.repeat = 0
            t.save()
            t.expire(RINGS + 2)

def prefs() -> dict:
    try:
        return {'from_front': True} | json.loads(db.get(PREFS) or '{}')
    except ValueError:
        return {'from_front': True}

def set_prefs(**kw):
    db.set(PREFS, json.dumps(prefs() | kw))

def cancel(pk: str):
    db.set(f'di.timers.again.{pk}', 1, ex=60)      # a repeating one: not again
    TimerEntry.delete(pk)
    _pks[0] = 0

def shift(t: TimerEntry, secs: int):
    # more (or less) time to go: the duration too, its ring and tail follow
    left = max(5, round(t.left()) + secs)
    t.target, t.duration, t.muted = pendulum.now().add(seconds=left), max(5, t.duration + secs), 0
    t.save()
    t.expire(left + t.tail + 5)

def mute(shown: list[TimerEntry]) -> bool:
    '''Mutes the ringing ones, everywhere: True if one was.'''
    ringing = [t for t in shown if t.ringing()]
    for t in ringing:
        t.muted = 1
        t.save()
    return bool(ringing)

def melody(duration: int) -> str:
    return 'boop' if duration < 10 else 'ok' if duration <= 25 else 'fmart' if duration <= 180 else 'fmart.slow'

def ring(fs: FrameState, shown: list[TimerEntry]):
    '''This screen's buzzer: the long ones' last seconds a boop each, then the melody; once each, as the timer is.
    Muted while it sounds: stopped.'''
    had = sounded[fs.config.name]
    for t in shown:
        l = t.left()
        if t.muted:
            if any(k[0] == t.pk for k in had) and (t.pk, 'stop') not in had and l > -RINGS:
                act(fs, 'buzzer', 'stop', f'timer.stop.{t.pk}')
                had.add((t.pk, 'stop'))
        elif t.duration >= LONG and 0 < l <= COUNTDOWN and (t.pk, s := math.ceil(l)) not in had:
            act(fs, 'buzzer', 'boop', f'timer.{t.pk}.{s}')
            had.add((t.pk, s))
        elif -RINGS < l <= 0 and (t.pk, 'end') not in had:
            act(fs, 'buzzer', [melody(t.duration), 'boop'], f'timer.{t.pk}')
            had.add((t.pk, 'end'))
    alive = {t.pk for t in shown}
    had -= {k for k in had if k[0] not in alive}

class Taps(AppBaseModel):
    n: int = 0
    cmds: list = []         # [n, payload], the newest last

class TapsManager(PubSubStateManager[Taps]):
    '''The touch screens' timer targets (action 'timer', payload with 'screen').'''
    model = Taps
    channels = ('di.pubsub.remote',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'timer':
            self.state.n += 1
            self.state.cmds = [*self.state.cmds[-7:], [self.state.n, data.payload]]

_seen = defaultdict(int)

def taps(fs: FrameState) -> list[dict]:
    r = TapsManager().get_state(fs)
    new = [p for n, p in r.cmds if n > _seen[fs.config.name] and p.get('screen') == fs.config.name]
    _seen[fs.config.name] = r.n
    return new

def known() -> list[dict]:
    try:
        return json.loads(db.get(KNOWN) or '[]')
    except ValueError:
        return []

def remember(icon: str, duration: int, label: str = ''):
    # A known timer: one per icon, the newest duration
    ks = [k for k in known() if k['icon'] != icon]
    db.set(KNOWN, json.dumps([*ks, {'label': label or icon.replace('-outline', '').replace('-', ' '), 'icon': icon, 'duration': duration}]))

def forget(icon: str):
    db.set(KNOWN, json.dumps([k for k in known() if k['icon'] != icon]))

def over(t: TimerEntry) -> str:
    # its time left, or since it was done: +02:13
    l = t.left()
    return mmss(math.ceil(l)) if l > 0 else '+' + mmss(-l)

def mmss(secs: int) -> str:
    secs = abs(int(secs))
    return f'{secs // 3600}:{secs // 60 % 60:02d}:{secs % 60:02d}' if secs >= 3600 else f'{secs // 60:02d}:{secs % 60:02d}'

def pixel_icon(name: str, size: int, color: str = '#e0e0e0', k: int = 2) -> Frame | None:
    # an mdi icon as pixel art: size px, alpha cut at half, k times whole pixels
    f = mdi.icon(name, size, color)
    if not f:
        return None
    img = f.image.copy()
    img.putalpha(img.getchannel('A').point(lambda a: 255 if a >= 110 else 0))
    return Frame(img.resize((size * k, size * k), 0), hash=('pixel_icon', name, size, color, k))

IncrementMap = namedtuple('IncrementMap', ['step', 'delta'])
DisplayFontMap = namedtuple('DisplayFontMap', ['step', 'font'])

fast_increments = IncrementMap(
    # duration, delta
    [1, 45, 120, 420, 800],
    [1,  5, 15, 30,  60],
)

# the dial: its clicks are many, its turns quick
dial_increments = IncrementMap(
    [0, 10, 60, 300, 1200],
    [1,  5, 15,  60,  300],
)

def stepped(secs: int, since: int, d: int, steps: IncrementMap = fast_increments) -> int:
    '''secs turned d clicks. The further this turn went from since (where it began), the bigger the steps, landing on
    them: a pause starts small again, for the exact second.'''
    step = steps.delta[max(0, bisect.bisect(steps.step, abs(secs - since)) - 1)]
    base = secs // step if d > 0 else -(-secs // step)
    return max(0, (base + d) * step)

display_font_map = DisplayFontMap(
    # duration, delta
    [0, 30, 120],
    [fonts.zx_spectrum, fonts.px_op__r, fonts.px_op__l],
)

def timer_view(fs: FrameState):
    state = states[fs.config.name]
    remote = TelemetryStateManager(fs.config.name).remote_reader('timer', fs)
    encoder = TelemetryStateManager(fs.config.name).get_state(fs).remote.encoder
    encoder_pos = encoder.position

    if state.last_encoder_at is None or encoder.updated_at < state.last_encoder_at:
        # First seen, or the client restarted (its clock and the position start over): where it is now is no turn.
        state.last_encoder = encoder.position
        state.last_encoder_at = encoder.updated_at
    elif encoder.updated_at != state.last_encoder_at:
        encoder_pos -= state.last_encoder
        if (encoder.updated_at - state.last_encoder_at) > 5:
            state.mode = 'idle'
        if encoder_pos == 0:
            state.duration = 0
            state.mode = 'idle'
        elif mute(timers(fs.tick)):
            pass        # a turn while one rings: quiet
        else:
            if (encoder.updated_at - state.last_encoder_at) > 0.5:
                state.duration_checkpt = state.duration
            state.duration = stepped(state.duration, state.duration_checkpt, encoder_pos)
            state.mode = 'create'
        state.direction = encoder_pos > 0
        state.last_encoder = encoder.position
        state.last_encoder_at = encoder.updated_at
        act(fs, 'buzzer', 'encoder' if state.direction else 'encoder-', 'beep')

    if remote('select') and state.mode == 'create' and (fs.tick - state.last_timer_at) > 2:
        entry = start(state.duration, origin=fs.config.name)
        state.active_pk = entry.pk
        state.mode = 'idle'
        state.duration = 0
        state.last_encoder = encoder.position
        state.last_timer_at = fs.tick
        act(fs, 'haptics', 'boop', 'ok')
        act(fs, 'buzzer', 'ok', 'ok')

    if remote('down') and not state.down:
        act(fs, 'buzzer', 'boop', str(fs.tick))
    state.down = remote('down')

    style_list = TextStyle(font=fonts.px_op__r)
    style_done = TextStyle(font=fonts.px_op__r, color="#b7b7b7")
    style_main = TextStyle(font=fonts.px_op__l)

    def display(secs: int):
        fontix = bisect.bisect(display_font_map.step, secs) - 1
        display_style = TextStyle(font=display_font_map.font[fontix])
        t_mm = secs // 60
        t_ss = secs % 60
        mmss = text_slide_in(fs, f'{t_mm:02d}:{t_ss:02d}', display_style)
        return div(mmss, padding=5, margin=1, border=1, border_color="#C7722DFF", radius=3)

    def timecard(timer: TimerEntry):
        next_secs = timer.end.diff(fs.now).in_seconds()
        sign = '-' if fs.now.diff(timer.end, False).in_seconds() < 0 else ' '
        t_mm = next_secs // 60
        t_ss = next_secs % 60
        is_active = timer.pk == state.active_pk
        style = style_main
        if is_active:
            style = style_list
        if sign == '-':
            style = style_done
        
        hhmm = text(f'{sign}{t_mm:02d}:{t_ss:02d}', style=style)
        dur_t_mm = timer.duration // 60
        dur_t_ss = timer.duration % 60

        tc = hstack([
            pixel_icon(timer.icon, 8, k=1) if timer.icon in ICONS else text(timer.label),
            text(f'{dur_t_mm}:{dur_t_ss}'),
            hhmm,
        ]).tag(('timerentry', str(timer.pk)))
        itc = div(tc, DivStyle(padding=2, radius=2, background="#AB4711AD" if is_active else "#092B5787"))
        return itc

    rows = []

    if state.duration > 0 and state.last_encoder_at + 5 < fs.tick:
        rows.append(display(max(state.duration, 0)))


    shown = sorted(timers(fs.tick), key=lambda t: t.end)
    for timer in shown:
        rows.append(timecard(timer))
    ring(fs, shown)

    if not rows:
        return

    return Frame(vstack(rows, gap=2).image, hash=('timer', 'main', state.mode, len(shown), state.duration > 0))


def timer_app(fs: FrameState):
    return Widget(
        'di.timer',
        timer_view(fs),
        transition_enter=Resize,
    )
