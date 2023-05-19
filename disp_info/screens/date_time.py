import arrow

from disp_info.components import fonts
from disp_info.components.layers import add_background
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.components.text import Text

colors_time = ['#1ba2ab', '#185e86']
color_date = '#6d7682'

text_time = Text(font=fonts.bitocra, fill=colors_time[0])
text_day = Text(font=fonts.bitocra, fill=color_date)
text_date = Text(font=fonts.bitocra, fill=color_date)

def draw(tick: float):
    t = arrow.now()

    text_time.update(
        value=t.strftime('%H:%M:%S'),
        fill=colors_time[t.second % 2 == 0])
    text_day.update(value=t.strftime('%a'))
    text_date.update(value=t.strftime('%d/%m'))

    view = stack_vertical([
        text_time,
        stack_horizontal([text_day, text_date], gap=2, align='center'),
    ], gap=0, align='right')
    return add_background(view, fill='#000000ac')
