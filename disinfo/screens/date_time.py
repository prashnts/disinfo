from .drawer import draw_loop
from ..data_structures import FrameState
from ..components import fonts
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.text import TextStyle, text


s_time = [
    TextStyle(color='#1ba2ab', font=fonts.bitocra),
    TextStyle(color='#185e86', font=fonts.bitocra),
]
s_label = TextStyle(color='#6d7682', font=fonts.bitocra)


def composer(fs: FrameState):
    t = fs.now
    style = s_time[t.second % 2 == 0]

    return div(
        vstack([
            text(t.strftime('%H:%M:%S'), style),
            hstack([
                text(t.strftime('%a'), s_label),
                text(t.strftime('%d/%m'), s_label),
            ], gap=2, align='center'),
        ], gap=0, align='right'),
        style=DivStyle(background='#000000ac'))

draw = draw_loop(composer, sleepms=200)
