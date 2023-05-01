import arrow

from disp_info.components import fonts
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.components.text import Text

def draw():
    t = arrow.now()
    time_color = '#2BBEC9' if t.second % 2 == 0 else '#0E699D'
    date_color = '#9F4006'

    return stack_vertical([
        Text(t.strftime('%H:%M:%S'), font=fonts.tamzen__rs, fill=time_color),
        stack_horizontal([
            Text(t.strftime('%a'), font=fonts.tamzen__rs, fill=date_color),
            Text(t.strftime('%d/%m'), font=fonts.tamzen__rs, fill=date_color),
        ], gap=2, align='center'),
    ], gap=1, align='right')
