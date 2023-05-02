import arrow

from disp_info.components import fonts
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.components.text import Text

colors_time = ['#2BBEC9', '#0E699D']
color_date = '#9F4006'

text_time = Text('', font=fonts.tamzen__rs, fill=colors_time[0])
text_day = Text('', font=fonts.tamzen__rs, fill=color_date)
text_date = Text('', font=fonts.tamzen__rs, fill=color_date)

def draw():
    t = arrow.now()

    text_time.set_value(t.strftime('%H:%M:%S'))
    text_time.set_fill(colors_time[t.second % 2 == 0])
    text_day.set_value(t.strftime('%a'))
    text_date.set_value(t.strftime('%d/%m'))

    return stack_vertical([
        text_time,
        stack_horizontal([text_day, text_date], gap=2, align='center'),
    ], gap=1, align='right')
