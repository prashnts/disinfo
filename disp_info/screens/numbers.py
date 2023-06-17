from .screen import composer_thread
from .. import config
from ..components import fonts
from ..components.text import Text, TextStyle
from ..components.layouts import stack_horizontal, stack_vertical
from ..components.layers import add_background, DivStyle
from ..redis import rkeys, get_dict
from ..components.scroller import HScroller
from ..utils.func import throttle
from ..data_structures import FrameState

text_info = Text('i', style=TextStyle(font=fonts.tamzen__rs, color='#fff'))

hscroller_main = HScroller(size=config.matrix_w - text_info.width - 2, delta=1, speed=0.02)
hscroller_num = HScroller(size=40, delta=1, speed=0.02, pause_at_loop=True)

text_number_info = Text('', style=TextStyle(font=fonts.px_op__r, color='#12cce1'))
text_number = Text('', style=TextStyle(font=fonts.px_op__r, color='#9bb10d'))


@throttle(1163)
def get_state():
    numbers = get_dict(rkeys['random_msg'])
    return numbers

def composer(fs: FrameState):
    numbers = get_state()
    num_str = f'#{numbers["number"]}'

    info_changed = text_number_info.update(value=numbers['text'])
    number_changed = text_number.update(value=num_str)

    hscroller_main.set_frame(text_number_info, info_changed)
    hscroller_num.set_frame(text_number, number_changed)

    info_ticker = stack_horizontal([
        text_info,
        hscroller_main.draw(fs.tick),
    ], gap=2, align='center')

    return stack_vertical([
        add_background(hscroller_num.draw(fs.tick), style=DivStyle(background='#0131176c', padding=1, radius=2, corners=[0, 1, 0, 0])),
        add_background(info_ticker, style=DivStyle(background='#010a298c', padding=1)),
    ], gap=0, align='left')


draw = composer_thread(composer, sleepms=10)
