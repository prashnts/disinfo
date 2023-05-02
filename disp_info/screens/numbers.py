from PIL import Image
from functools import cache

from disp_info import config
from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.components.layers import add_background
from disp_info.sprite_icons import SpriteImage
from disp_info.redis import rkeys, get_dict
from disp_info.components.scroller import HScroller

text_info = Text('i', font=fonts.tamzen__rs, fill='#fff')

hscroller_main = HScroller(size=config.matrix_w - text_info.width - 2, delta=2, speed=0.01)
hscroller_num = HScroller(size=40, delta=1, speed=0.01)

text_number_info = Text('', font=fonts.px_op__r, fill='#12cce1')
text_number = Text('', font=fonts.px_op__r, fill='#12cce1')


def draw(tick: float):
    numbers = get_dict(rkeys['random_msg'])
    num_str = f'#{numbers["number"]}'

    info_changed = text_number_info.set_value(numbers['text'])
    number_changed = text_number.set_value(num_str)

    hscroller_main.set_frame(text_number_info, info_changed)
    hscroller_num.set_frame(text_number, number_changed)

    info_ticker = stack_horizontal([
        text_info,
        hscroller_main.draw(),
    ], gap=2, align='center')

    return stack_vertical([
        add_background(hscroller_num.draw(tick), fill='#013117', padding=1),
        add_background(info_ticker, fill='#010a29', padding=1),
    ], gap=0, align='left')
