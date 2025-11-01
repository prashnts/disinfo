import pendulum
import math
import bisect

from datetime import datetime
from dataclasses import dataclass
from collections import namedtuple
from redis_om import HashModel

from disinfo.data_structures import AppBaseModel, FrameState
from disinfo.components.widget import Widget
from disinfo.components.text import text, TextStyle
from disinfo.components.layouts import vstack, hstack
from disinfo.components.layers import div, DivStyle
from disinfo.components import fonts
from disinfo.components.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act


class TimerEntry(HashModel):
    start_time: datetime
    duration: int = 30   # seconds
    icon: str = 'clock'
    overflow: int = 1
    label: str = 'T'

    @property
    def start(self):
        return pendulum.instance(self.start_time)

    @property
    def end(self):
        return self.start.add(seconds=self.duration)

@dataclass
class State:
    mode: str = 'create'
    duration: int = 0
    duration_checkpt: int = 0
    last_encoder: int = 0
    last_encoder_at: float = 0
    last_timer_at: float = 0
    active_pk: str = ''

state = State()

IncrementMap = namedtuple('IncrementMap', ['step', 'delta'])

fast_increments = IncrementMap(
    # duration, delta
    [0, 45, 120, 420, 800],
    [1,  5, 15, 30,  60],
)

def timer_view(fs: FrameState):
    remote = TelemetryStateManager().remote_reader('timer', fs)
    encoder = TelemetryStateManager().get_state(fs).remote.encoder
    encoder_pos = encoder.position

    if encoder.updated_at != state.last_encoder_at:
        encoder_pos -= state.last_encoder
        if encoder_pos == 0:
            state.duration = 0
            state.mode = 'idle'
        else:
            # posdelta = state.duration
            posdelta = state.duration - state.duration_checkpt
            if (encoder.updated_at - state.last_encoder_at) > 0.5:
                state.duration_checkpt = state.duration
                posdelta = 0
            deltaindex = bisect.bisect(fast_increments.step, posdelta) - 1
            delta = fast_increments.delta[max(0, deltaindex)]
            state.duration += encoder_pos * delta
            if state.duration < 0:
                state.duration = 0
            state.mode = 'create'
        state.last_encoder = encoder.position
        state.last_encoder_at = encoder.updated_at
        act('buzzer', 'boop', 'beep')
    if remote('select') and state.mode == 'create' and (fs.tick - state.last_timer_at) > 1:
        entry = TimerEntry(start_time=fs.now.add(seconds=state.duration), duration=state.duration).save()
        state.active_pk = entry.pk
        state.mode = 'idle'
        state.duration = 0
        state.last_encoder = encoder.position
        state.last_timer_at = fs.tick
        act('buzzer', 'ok', 'ok')

    if remote('down'):
        act('buzzer', 'boop', str(fs.tick))

    style_list = TextStyle(font=fonts.px_op__r)
    style_main = TextStyle(font=fonts.px_op__l)
    display_style = TextStyle(font=fonts.px_op__xl)

    def display(secs: int):
        t_mm = secs // 60
        t_ss = secs % 60
        mmss = text(f'{t_mm:02d}:{t_ss:02d}', display_style)
        return mmss

    def timecard(timer: TimerEntry):
        next_secs = timer.start.diff(fs.now).in_seconds()
        t_mm = next_secs // 60
        t_ss = next_secs % 60
        is_active = timer.pk == state.active_pk
        sign = '-' if fs.now.diff(timer.end, False).in_seconds() < 0 else ' '
        hhmm = text(f'{sign}{t_mm:02d}:{t_ss:02d}', style=style_main if is_active else style_list)
        tc = hstack([
            text(f'{timer.label} {timer.duration}'),
            hhmm,
        ]).tag(('timerentry', str(timer.pk)))
        itc = div(tc, DivStyle(padding=2, radius=2, background="#AB4711AD" if is_active else "#092B5787"))
        return Widget(f'di.timer.timecard.{timer.pk}', itc).draw(fs, active=is_active)

    rows = []

    if state.duration > 0 and state.last_encoder_at + 5 < fs.tick:
        rows.append(display(state.duration))


    timers = [TimerEntry.get(tid) for tid in TimerEntry.all_pks()]
    timers.sort(key=lambda t: t.end)
    for timer in timers:
        rows.append(timecard(timer))
        if fs.now.diff(timer.start_time, False).in_seconds() == 0:
            act('buzzer', 'ok' if timer.duration < 15 else 'fmart', timer.pk)
        if fs.now.diff(timer.end, False).in_minutes() < 10:
            timer.expire(1)
        
    if not rows:
        return

    return Frame(vstack(rows, gap=2).image, hash=('timer', 'main'))


def timer_app(fs: FrameState):
    return Widget('di.timer', timer_view(fs))
