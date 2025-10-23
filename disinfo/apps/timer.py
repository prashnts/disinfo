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

def _read_btn(fs: FrameState, button: str):
    remote_state = TelemetryStateManager().get_state(fs).remote
    button = getattr(remote_state.buttons, button)
    return button.pressed.read('timer')

_state = 'create'

@dataclass
class State:
    mode: str = 'create'
    duration: int = 0
    last_encoder: int = 0
    active_pk: str = ''

state = State()


def timer_app(fs: FrameState):
    remote_state = TelemetryStateManager().get_state(fs).remote

    if remote_state.encoder.position != state.last_encoder:
        if remote_state.encoder.position < 0:
            state.mode = 'idle'
            state.last_encoder = remote_state.encoder.position
            state.duration = 0
        else:
            state.duration += (remote_state.encoder.position - state.last_encoder)
            state.last_encoder = remote_state.encoder.position
            state.mode = 'create'

    next_timer = fs.now.add(seconds=state.duration)

    if _read_btn(fs, 'select') and state.mode == 'create':
        entry = TimerEntry(start_time=next_timer, duration=state.duration).save()
        entry.expire(int(state.duration * 1.5))
        state.active_pk = entry.pk
        state.mode = 'idle'
        state.duration = 0
        state.last_encoder = remote_state.encoder.position
        act('buzzer', 'ok')

    style_list = TextStyle(font=fonts.px_op__r)
    style_main = TextStyle(font=fonts.px_op__l)

    def hhmm(dt, duration=None, style=style_list):
        if isinstance(dt, datetime):
            dt = pendulum.instance(dt)
        next_secs = dt.diff(fs.now).in_seconds()
        t_mm = next_secs // 60
        sign = ' '
        if dt < fs.now:
            sign = '-'
        t_ss = next_secs % 60
        return text(f'{sign}{t_mm}:{t_ss}', style=style)

    rows = [hhmm(next_timer, None, style_main)]
    timers = [TimerEntry.get(tid) for tid in TimerEntry.all_pks()]
    timers.sort(key=lambda t: t.start_time)
    for timer in timers:
        dt = timer.start_time
        rows.append(hstack([
            text(f'{timer.label} {timer.duration}'),
            hhmm(timer.start_time, timer.duration, style_main if timer.pk == state.active_pk else style_list),
        ]))
        if fs.now.diff(timer.start_time).in_seconds() == 0:
            act('buzzer', 'tone' if timer.duration < 15 else 'siren')

    view = Frame(vstack(rows).image, hash=('timer', 'main'))

    return Widget('di.timer', view)