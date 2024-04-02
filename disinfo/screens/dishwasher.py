from pyquery import PyQuery as pq
from functools import cache

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
from ..utils.cairo import load_svg, load_svg_string

dishwasher_icon = StillImage('assets/raster/dishwasher.png')
label_style = TextStyle(font=fonts.bitocra7, color=amber_red.darken(0.2).hex)
time_style = TextStyle(color=amber_red.darken(0.1).hex, font=fonts.pixel_lcd)

dishwasher_icon = load_svg('assets/dishwasher.svg')

@cache
def washer_lcd(hours):
    mapping = {
        1: ['b2', 'd2'],
        2: ['a', 'b2', 'c', 'e', 'd1'],
        3: ['a', 'b2', 'c', 'e', 'd2'],
        4: ['b1', 'b2', 'c', 'd2'],
        5: ['a', 'b1', 'c', 'd2', 'e'],
        6: ['a', 'b1', 'c', 'd1', 'd2', 'e'],
        7: ['a', 'b2', 'd2'],
        8: ['a', 'b1', 'b2', 'c', 'd1', 'd2', 'e'],
        9: ['a', 'b1', 'b2', 'c', 'd2', 'e'],
        0: ['a', 'b1', 'b2', 'd1', 'd2', 'e'],
    }
    lit_leds = mapping[hours]
    color = lambda x: amber_red.darken(0.1).hex if x in lit_leds else gray.darken(0.4).hex

    with open('assets/dishwasher-segment.svg', 'rb') as f:
        svg = pq(f.read())

    for led in lit_leds:
        svg(f'#{led}').attr('stroke', color(led))
    
    return load_svg_string(str(svg))


def timer_full_cycle(now):
    # The dishwasher should finish by 07:30.
    # Cycle time is about 3h30m, so it should start at 04:00.
    # now = now.replace(hour=23, minute=50)
    next_target = now.replace(hour=4, minute=0, second=0)
    if now > next_target:
        next_target = next_target.add(days=1)
    return next_target.diff(now).in_hours()

def is_visible(fs: FrameState):
    return fs.now.hour >= 20 and fs.now.hour <= 23


def composer(fs: FrameState):
    if not is_visible(fs):
        return

    next_timer = timer_full_cycle(fs.now)

    return div(
        hstack([
            dishwasher_icon,
            hstack([washer_lcd(next_timer), text('h', style=label_style)], align='bottom'),
        ], gap=1),
        style=DivStyle(padding=1, radius=1, background=gray.darken(0.7).hex)
    ).tag('dishwasher')

def widget(fs: FrameState):
    return Widget('dishwasher', composer(fs), priority=0.5, wait_time=8)

draw = draw_loop(composer)
