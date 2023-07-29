from .drawer import draw_loop
from .colors import dark_gray, amber_red
from ..data_structures import FrameState
from ..components import fonts
from ..components.layers import div, DivStyle, reposition
from ..components.layouts import hstack, vstack
from ..components.text import TextStyle, text


s_day       = TextStyle(color='#6d7682', font=fonts.tamzen__rs)
s_date      = TextStyle(color='#50555a', font=fonts.tamzen__rs)
s_hour      = TextStyle(color=dark_gray.hex, font=fonts.px_op__l)
s_minute    = TextStyle(color=dark_gray.hex, font=fonts.px_op__l)
s_seconds   = TextStyle(color=dark_gray.darken(.3).hex, font=fonts.bitocra)
s_day_box = DivStyle(radius=0, background='#5f1111', padding=[0, 2, 0, 2])
s_colon = [
    TextStyle(color=amber_red.darken(.5).hex, font=fonts.bitocra),
    TextStyle(color=amber_red.hex, font=fonts.bitocra),
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
                div(text(t.strftime('%a'), s_day), s_day_box),
                text(t.strftime('%d/%m'), s_date),
            ], gap=2, align='center'),
        ], gap=2, align='right'),
        style=DivStyle(background='#000000ac'))

draw = draw_loop(composer, sleepms=200)
