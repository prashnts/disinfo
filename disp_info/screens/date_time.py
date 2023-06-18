import dataclasses

from .screen import composer_thread
from ..data_structures import FrameState
from ..components import fonts
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, stack_vertical
from ..components.text import Text, TextStyle

colors_time = ['#1ba2ab', '#185e86']
color_date = '#6d7682'

text_time = Text(style=TextStyle(color=colors_time[0], font=fonts.bitocra))
text_day = Text(style=TextStyle(color=color_date, font=fonts.bitocra))
text_date = Text(style=TextStyle(color=color_date, font=fonts.bitocra))

def composer(fs: FrameState):
    t = fs.now

    text_time.update(
        value=t.strftime('%H:%M:%S'),
        style=dataclasses.replace(text_time.style, color=colors_time[t.second % 2 == 0]))
    text_day.update(value=t.strftime('%a'))
    text_date.update(value=t.strftime('%d/%m'))

    view = stack_vertical([
        text_time,
        hstack([text_day, text_date], gap=2, align='center'),
    ], gap=0, align='right')
    return div(view, style=DivStyle(background='#000000ac'))

draw = composer_thread(composer, sleepms=200)
