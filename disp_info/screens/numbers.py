from PIL import Image
from functools import cache

from .. import config
from ..components import fonts
from ..components.elements import Frame
from ..components.text import Text
from ..components.layouts import stack_horizontal, stack_vertical
from ..components.layers import add_background
from ..sprite_icons import SpriteImage
from ..redis import rkeys, get_dict
from ..components.scroller import HScroller
from ..utils.func import throttle

text_info = Text('i', font=fonts.tamzen__rs, fill='#fff')

hscroller_main = HScroller(size=config.matrix_w - text_info.width - 2, delta=1, speed=0.0001)
hscroller_num = HScroller(size=40, delta=1, speed=0.01, pause_at_loop=True)

text_number_info = Text('', font=fonts.px_op__r, fill='#12cce1')
text_number = Text('', font=fonts.px_op__r, fill='#9bb10d')


@throttle(1163)
def get_state():
    numbers = get_dict(rkeys['random_msg'])
    return numbers


def draw(tick: float):
    numbers = get_state()
    num_str = f'#{numbers["number"]}'

    info_changed = text_number_info.update(value=numbers['text'])
    number_changed = text_number.update(value=num_str)

    hscroller_main.set_frame(text_number_info, info_changed)
    hscroller_num.set_frame(text_number, number_changed)

    info_ticker = stack_horizontal([
        text_info,
        hscroller_main.draw(),
    ], gap=2, align='center')

    return stack_vertical([
        add_background(hscroller_num.draw(tick), fill='#0131176c', padding=1, radius=2, corners=[0, 1, 0, 0]),
        add_background(info_ticker, fill='#010a298c', padding=1),
    ], gap=0, align='left')
