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
from disinfo.components.transitions import Resize, text_slide_in
from disinfo.components import fonts
from disinfo.components.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act


class TimerEntry(HashModel):
    target: datetime
    duration: int = 30   # seconds
    icon: str = 'clock'
    overflow: int = 1
    label: str = 'T'
    triggerred: int = 0

    @property
    def end(self):
        return pendulum.instance(self.target)

@dataclass
class State:
    mode: str = 'create'
    duration: int = 0
    duration_checkpt: int = 0
    last_encoder: int = 0
    last_encoder_at: float = 0
    last_timer_at: float = 0
    active_pk: str = ''
    direction: bool = False

state = State()

IncrementMap = namedtuple('IncrementMap', ['step', 'delta'])
DisplayFontMap = namedtuple('DisplayFontMap', ['step', 'font'])

fast_increments = IncrementMap(
    # duration, delta
    [0, 45, 120, 420, 800],
    [1,  5, 15, 30,  60],
)

display_font_map = DisplayFontMap(
    # duration, delta
    [0, 30, 120],
    [fonts.px_op__xl, fonts.px_op__xl, fonts.zx_spectrum],
)

def timer_view(fs: FrameState):
    remote = TelemetryStateManager().remote_reader('timer', fs)
    encoder = TelemetryStateManager().get_state(fs).remote.encoder
    encoder_pos = encoder.position

    if encoder.updated_at != state.last_encoder_at:
        encoder_pos -= state.last_encoder
        if (fs.tick - state.last_encoder_at) > 5:
            state.mode = 'idle'
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
        state.direction = encoder_pos > 0
        state.last_encoder = encoder.position
        state.last_encoder_at = encoder.updated_at
        act('buzzer', 'boop', 'beep')

    if remote('select') and state.mode == 'create' and (fs.tick - state.last_timer_at) > 1:
        entry = TimerEntry(target=fs.now.add(seconds=state.duration), duration=state.duration).save()
        entry.expire(int(state.duration * 1.5))
        state.active_pk = entry.pk
        state.mode = 'idle'
        state.duration = 0
        state.last_encoder = encoder.position
        state.last_timer_at = fs.tick
        act('buzzer', 'ok', 'ok')

    if remote('down'):
        act('buzzer', 'boop', str(fs.tick))

    style_list = TextStyle(font=fonts.px_op__r)
    style_done = TextStyle(font=fonts.px_op__r, color="#b7b7b7")
    style_main = TextStyle(font=fonts.px_op__l)

    def display(secs: int):
        fontix = bisect.bisect(display_font_map.step, secs) - 1
        display_style = TextStyle(font=display_font_map.font[fontix])
        t_mm = secs // 60
        t_ss = secs % 60
        mmss = text_slide_in(fs, 'timer.main.display', f'{t_mm:02d}:{t_ss:02d}', display_style, edge='top' if state.direction > 0 else 'bottom')
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
            text(f'{timer.label} {dur_t_mm}:{dur_t_ss}'),
            hhmm,
        ]).tag(('timerentry', str(timer.pk)))
        itc = div(tc, DivStyle(padding=2, radius=2, background="#AB4711AD" if is_active else "#092B5787"))
        return itc

    rows = []

    if state.mode != 'idle' and state.last_encoder_at + 5 < fs.tick:
        rows.append(display(max(state.duration, 0)))


    timers = [TimerEntry.get(tid) for tid in TimerEntry.all_pks()]
    timers.sort(key=lambda t: t.end)
    for timer in timers:
        rows.append(timecard(timer))
        trigger = 7 if timer.duration > 10 else 1
        if timer.triggerred < 2 and fs.now.diff(timer.end, False).in_seconds() < trigger:
            melody = 'boop' if timer.duration < 10 else 'ok'
            melody = 'fmart' if timer.duration > 25 else melody
            melody = 'fmart.slow' if timer.duration > 180 else melody
            act('buzzer', melody, timer.pk)
            timer.triggerred += 1
            timer.save()
        
    if not rows:
        return

    return Frame(vstack(rows, gap=2).image, hash=('timer', 'main', state.mode, len(timers), state.duration > 0))


def timer_app(fs: FrameState):
    return Widget(
        'di.timer',
        timer_view(fs),
        transition_enter=Resize,
    )
