from .drawer import draw_loop
from .colors import gray, amber_red
from ..components import fonts
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.widget import Widget
from ..components.text import TextStyle, text
from ..components.transitions import text_slide_in
from ..data_structures import FrameState
from ..utils.cairo import load_svg

dishwasher_icon = StillImage('assets/raster/dishwasher.png')
label_style = TextStyle(font=fonts.bitocra7, color=gray.darken(0.6).hex)
time_style = TextStyle(color=amber_red.darken(0.1).hex, font=fonts.bitocra7)



dishwasher_icon = load_svg('assets/mui-icons/dishwasher_gen_FILL1_wght400_GRAD-25_opsz20.svg')


def timer_full_cycle(now):
    # The dishwasher should finish by 07:00.
    # Cycle time is about 3h30m, so it should start at 03:30.
    # now = fs.now.replace(hour=20, minute=0)
    next_target = now.replace(hour=3, minute=30, second=0)
    if now > next_target:
        next_target = next_target.add(days=1)
    return next_target.diff(now).in_hours()

def is_visible(fs: FrameState):
    return fs.now.hour >= 20 and fs.now.hour <= 23


def composer(fs: FrameState):
    # if not is_visible(fs):
    #     return

    next_timer = timer_full_cycle(fs.now)

    return div(
        hstack([
            dishwasher_icon,
            vstack([
                text('Timer', style=label_style),
                text_slide_in(fs, 'dishwasher.timer', f'{next_timer}h', time_style, 'top'),
            ], align='center'),
        ], gap=2),
        style=DivStyle(padding=1, radius=1, background=gray.darken(0.2).hex)
    ).tag('dishwasher')

def widget(fs: FrameState):
    return Widget('dishwasher', composer(fs), priority=0.5, wait_time=8)

draw = draw_loop(composer)
