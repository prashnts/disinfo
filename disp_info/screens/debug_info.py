import arrow

from datetime import timedelta

from ..components.text import Text
from ..components.layouts import stack_vertical
from ..components.layers import add_background
from ..components import fonts
from ..redis import rkeys, get_dict
from ..utils.func import throttle
from ..data_structures import FrameState


text_brightness = Text(font=fonts.bitocra, fill='#fff')
text_lux = Text(font=fonts.bitocra, fill='#fff')
text_draw_time = Text(font=fonts.bitocra, fill='#fff')

@throttle(11177)
def get_state(fs: FrameState):
    if fs.rendererdata:
        return fs.rendererdata
    return {
        'brightness': '--',
        'lux': '--',
        'draw_time': 1,
    }


def draw(fs: FrameState):
    s = get_state(fs)
    text_brightness.update(value=f"{s['brightness']}%")
    text_lux.update(value=f"{s['lux']}")
    text_draw_time.update(value=f"{s['draw_time']:0.1f}")

    debuginfo = stack_vertical([text_brightness, text_lux, text_draw_time], gap=2)

    return add_background(debuginfo, fill='#0000003c', padding=3)
