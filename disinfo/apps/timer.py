import pendulum
import math

from datetime import datetime
from dataclasses import dataclass
from redis_om import HashModel

from disinfo.data_structures import AppBaseModel, FrameState
from disinfo.components.widget import Widget
from disinfo.components.text import text, TextStyle
from disinfo.components.layouts import vstack, hstack
from disinfo.components.layers import div
from disinfo.components import fonts
from disinfo.components.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act


class TimerEntry(HashModel):
    start_time: datetime
    duration: int = 30   # seconds
    icon: str = 'clock'
    overflow: int = 1
    label: str = 'Timer'

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
    last_encoder: int = 0
    active_pk: str = ''

state = State()

def timer_app(fs: FrameState):
    remote = TelemetryStateManager().remote_reader('timer', fs)

    if remote('encoder') != state.last_encoder:
        if remote('encoder') < 0:
            state.mode = 'idle'
            state.last_encoder = remote('encoder')
            state.duration = 0
        else:
            state.duration += (remote('encoder') - state.last_encoder)
            state.last_encoder = remote('encoder')
            state.mode = 'create'
    if remote('select') and state.mode == 'create':
        entry = TimerEntry(start_time=fs.now.add(seconds=state.duration), duration=state.duration).save()
        state.active_pk = entry.pk
        state.mode = 'idle'
        state.duration = 0
        state.last_encoder = remote('encoder')
        act('buzzer', 'ok')

    if remote('down'):
        act('buzzer', 'nokia')

    style_list = TextStyle(font=fonts.px_op__r)
    style_main = TextStyle(font=fonts.px_op__l)

    def display(secs: int):
        t_mm = secs // 60
        t_ss = secs % 60
        mmss = text(f'{t_mm}:{t_ss}')
        return mmss

    def timecard(timer: TimerEntry):
        next_secs = timer.start.diff(fs.now).in_seconds()
        t_mm = next_secs // 60
        t_ss = next_secs % 60
        sign = '-' if timer.end >= fs.now else ' '
        hhmm = text(f'{sign}{t_mm}:{t_ss}', style=style_main if timer.pk == state.active_pk else style_list)
        return hstack([
            text(f'{timer.label} {timer.duration}'),
            hhmm,
        ])

    rows = [display(state.duration)]
    timers = [TimerEntry.get(tid) for tid in TimerEntry.all_pks()]
    timers.sort(key=lambda t: t.end)
    for timer in timers:
        rows.append(timecard(timer))
        if fs.now.diff(timer.start_time).in_seconds() == 0:
            act('buzzer', 'tone' if timer.duration < 15 else 'siren')
        if timer.end.add(seconds=180) > fs.now:
            timer.expire(1)

    view = Frame(vstack(rows).image, hash=('timer', 'main'))

    return Widget('di.timer', view)