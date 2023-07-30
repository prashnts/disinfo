from .drawer import draw_loop
from .colors import gray, amber_red, black, light_gray, light_blue
from ..data_structures import FrameState
from ..components import fonts
from ..components.layers import div, DivStyle, reposition
from ..components.layouts import hstack, vstack
from ..components.text import TextStyle, text


s_date      = TextStyle(color=gray.darken(.2).hex, font=fonts.tamzen__rs)
s_hour      = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_minute    = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_seconds   = TextStyle(color=gray.darken(.2).hex, font=fonts.bitocra)
s_day = {
    'weekend': TextStyle(color=light_gray.darken(.1).hex, font=fonts.tamzen__rs),
    'weekday': TextStyle(color=black.hex, font=fonts.tamzen__rs),
}
s_day_box = {
    'weekend': DivStyle(radius=0, background=amber_red.darken(.1).hex, padding=[1, 0, 1, 1]),
    'weekday': DivStyle(radius=0, background=gray.hex, padding=[1, 0, 1, 1]),
}
s_colon = [
    TextStyle(color=light_blue.darken(.5).hex, font=fonts.bitocra),
    TextStyle(color=light_blue.hex, font=fonts.bitocra),
]


def composer(fs: FrameState):
    t = fs.now
    day_of_week = 'weekend' if t.day_of_week in (6, 0) else 'weekday'

    return div(
        vstack([
            hstack([
                text(t.strftime('%H'), s_hour),
                reposition(text(':', s_colon[t.second % 2]), x=1),
                text(t.strftime('%M'), s_minute),
                reposition(text(t.strftime('%S'), s_seconds), y=-1),
            ], gap=0, align='top'),
            hstack([
                div(text(t.strftime('%a'), s_day[day_of_week]), s_day_box[day_of_week]),
                text(t.strftime('%d/%m'), s_date),
            ], gap=2, align='bottom'),
        ], gap=2, align='center'),
        style=DivStyle(background='#000000ac'))

draw = draw_loop(composer, sleepms=200)
