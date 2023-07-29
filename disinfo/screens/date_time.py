from .drawer import draw_loop
from .colors import smoky_uniform
from ..data_structures import FrameState
from ..components import fonts
from ..components.layers import div, DivStyle, reposition
from ..components.layouts import hstack, vstack
from ..components.text import TextStyle, text


s_day       = TextStyle(color='#6d7682', font=fonts.tamzen__rs)
s_date      = TextStyle(color='#50555a', font=fonts.px_op__r)
s_hour      = TextStyle(color=smoky_uniform.hex, font=fonts.px_op__l)
s_minute    = TextStyle(color=smoky_uniform.hex, font=fonts.px_op__l)
s_seconds   = TextStyle(color=smoky_uniform.darken(.3).hex, font=fonts.bitocra)
s_day_box = DivStyle(radius=2, background='#5f1111', padding=[1, 2, 1, 2])
s_colon = [
    TextStyle(color='#71480e', font=fonts.bitocra),
    TextStyle(color='#291a05', font=fonts.bitocra),
]


def composer(fs: FrameState):
    t = fs.now

    return div(
        vstack([
            hstack([
                text(t.strftime('%H'), s_hour),
                reposition(text(':', s_colon[t.second % 2]), x=1),
                text(t.strftime('%M'), s_minute),
                reposition(text(t.strftime('%S'), s_seconds), y=-1),
            ], gap=0, align='top'),
            hstack([
                # div(text(t.strftime('%a'), s_day), s_day_box),
                text(t.strftime('%d/%m'), s_date),
            ], gap=2, align='center'),
        ], gap=2, align='right'),
        style=DivStyle(background='#000000ac'))

draw = draw_loop(composer, sleepms=200)
