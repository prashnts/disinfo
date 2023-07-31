from .drawer import draw_loop
from .colors import gray, amber_red, black, light_gray, light_blue
from ..data_structures import FrameState
from ..components import fonts
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.text import TextStyle, text


s_date      = TextStyle(color=gray.darken(.2).hex, font=fonts.bitocra)
s_hour      = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_minute    = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_seconds   = TextStyle(color=light_blue.darken(.1).hex, font=fonts.bitocra)
s_day = {
    'weekend': {
        'text': TextStyle(color=light_gray.darken(.1).hex, font=fonts.tamzen__rs),
        'div': DivStyle(radius=2, background=amber_red.darken(.1).hex, padding=[1, 1, 1, 2]),
    },
    'weekday': {
        'text': TextStyle(color=black.hex, font=fonts.tamzen__rs),
        'div': DivStyle(radius=2, background=gray.hex, padding=[1, 1, 1, 2]),
    },
}
s_colon = [
    TextStyle(color=light_blue.darken(.5).hex, font=fonts.bitocra),
    TextStyle(color=light_blue.hex, font=fonts.bitocra),
]


def weekday(fs: FrameState):
    t = fs.now
    style = s_day['weekend' if t.day_of_week in (6, 0) else 'weekday']
    return div(text(t.strftime('%a').upper(), style['text']), style['div'])


def composer(fs: FrameState):
    t = fs.now

    return div(
        vstack([
            hstack([
                text(t.strftime('%H'), s_hour),
                text(':', s_colon[t.microsecond > 500_000]).reposition(x=1),
                text(t.strftime('%M'), s_minute),
                text(t.strftime('%S'), s_seconds).reposition(y=-1),
            ], gap=0, align='bottom'),
            hstack([
                weekday(fs),
                text(t.strftime('%d/%m'), s_date),
            ], gap=2, align='bottom'),
        ], gap=2, align='center'),
        style=DivStyle(background='#000000ac'))

draw = draw_loop(composer, sleepms=200)
