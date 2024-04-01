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

dishwasher_icon = load_svg('assets/raster/dishwasher.svg')
segments_icon = load_svg('assets/segment.svg')

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
    color = lambda x: amber_red.hex if x in lit_leds else gray.darken(0.4).hex

    segments = f'''\
<?xml version="1.0" encoding="UTF-8"?>
<svg width="11px" height="15px" viewBox="0 0 11 15" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <title>segment</title>
    <g id="segment" stroke="none" stroke-width="1" fill="none" fill-rule="evenodd">
        <path d="M8.5,1.5 L2.5,1.5 C1.94771525,1.5 1.5,1.94771525 1.5,2.5 L1.5,2.5 L1.5,2.5" id="a" stroke="{color('a')}" stroke-width="1.5"></path>
        <line x1="9.5" y1="1.5" x2="9.5" y2="6.5" id="b2" stroke="{color('b2')}" stroke-width="1.5"></line>
        <line x1="9.5" y1="8.5" x2="9.5" y2="13.5" id="d2" stroke="{color('d2')}" stroke-width="1.5"></line>
        <path d="M8.5,13.5 L2.5,13.5 C1.94771525,13.5 1.5,13.0522847 1.5,12.5 L1.5,12.5 L1.5,12.5" id="e" stroke="{color('e')}" stroke-width="1.5"></path>
        <line x1="1.5" y1="12" x2="1.5" y2="8.5" id="d1" stroke="{color('d1')}" stroke-width="1.5"></line>
        <line x1="1.5" y1="3" x2="1.5" y2="6.5" id="b1" stroke="{color('b1')}" stroke-width="1.5"></line>
        <line x1="2.5" y1="7.5" x2="8.5" y2="7.5" id="c" stroke="{color('c')}" stroke-width="1.5"></line>
    </g>
</svg>
'''
    return load_svg_string(segments)


def timer_full_cycle(now):
    # The dishwasher should finish by 07:00.
    # Cycle time is about 3h30m, so it should start at 03:30.
    # now = now.replace(hour=23, minute=50)
    next_target = now.replace(hour=3, minute=30, second=0)
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
            washer_lcd(next_timer),
            hstack([
                # text_slide_in(fs, 'dishwasher.timer', f'{next_timer}', time_style, 'top'),
                text('h', style=label_style),
            ], align='top'),
        ], gap=4),
        style=DivStyle(padding=1, radius=1, background=gray.darken(0.7).hex)
    ).tag('dishwasher')

def widget(fs: FrameState):
    return Widget('dishwasher', composer(fs), priority=0.5, wait_time=8)

draw = draw_loop(composer)
