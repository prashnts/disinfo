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


def get_state(fs: FrameState):
    stateinfo = fs.rendererdata if fs.rendererdata else {
        'brightness': '--',
        'lux': '--',
        'draw_time': 1,
    }
    return {
        'is_visible': fs.enki_action == 'scene_3',
        **stateinfo,
    }


def draw(fs: FrameState):
    s = get_state(fs)
    if not s['is_visible']:
        return

    text_brightness.update(value=f"Bri: {s['brightness']}%")
    text_lux.update(value=f"Lux: {s['lux']:0.1f}")
    text_draw_time.update(value=f"t_dr: {s['draw_time']:0.4f}")

    debuginfo = stack_vertical([text_brightness, text_lux, text_draw_time], gap=2)

    return add_background(debuginfo, fill='#0000003c', padding=3)
