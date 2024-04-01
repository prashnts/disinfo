import pendulum

from .drawer import draw_loop
from .colors import gray
from ..components import fonts
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.widget import Widget
from ..components.text import TextStyle, text
from ..components.transitions import text_slide_in
from ..data_structures import FrameState

dishwasher_icon = StillImage('assets/raster/dishwasher.png')

def timer_full_cycle(now):
    # The dishwasher should finish by 07:00.
    # Cycle time is about 3h30m, so it should start at 03:30.
    # now = pendulum.now().replace(hour=20, minute=0)
    next_target = now.replace(hour=3, minute=30, second=0)
    if now > next_target:
        next_target = next_target.add(days=1)
    return next_target.diff(now).in_hours()


def composer(fs: FrameState):
    next_timer = timer_full_cycle(fs.now)
    label = text('Timer', style=TextStyle(font=fonts.bitocra7, color=gray.hex))
    timer_widget = text_slide_in(fs, 'dishwasher.timer', f'{next_timer}h', TextStyle(color=gray.hex, font=fonts.bitocra7), 'top')
    schedules = hstack([dishwasher_icon, vstack([label, timer_widget])], gap=2)

    return div(
        schedules,
        style=DivStyle(padding=1, radius=2, background=gray.darken(0.8).hex)
    ).tag('dishwasher')

def widget(fs: FrameState):
    return Widget('dishwasher', composer(fs), priority=0.5)

draw = draw_loop(composer)
