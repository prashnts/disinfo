from .drawer import draw_loop
from ..config import app_config
from ..components import fonts
from ..components.text import Text, TextStyle
from ..components.layouts import hstack, vstack
from ..components.layers import div, DivStyle
from ..redis import rkeys, get_dict
from ..components.scroller import HScroller
from ..utils.func import throttle
from ..data_structures import FrameState

text_info = Text('i', style=TextStyle(font=fonts.tamzen__rs, color='#fff'))

hscroller_main = HScroller(size=app_config.width - text_info.width - 2, delta=1, speed=0.02)
hscroller_num = HScroller(size=40, delta=1, speed=0.02, pause_at_loop=True)

text_number_info = Text('', style=TextStyle(font=fonts.cozette, color='#12cce1'))
text_number = Text('', style=TextStyle(font=fonts.px_op__r, color='#9bb10d'))


@throttle(1163)
def get_state():
    numbers = get_dict(rkeys['random_msg'])
    return numbers

def composer(fs: FrameState):
    # return
    numbers = get_state()
    num_str = f'#{num}' if (num := numbers['number']) else ' (*_*)'

    info_changed = text_number_info.update(value=numbers['text'])
    number_changed = text_number.update(value=num_str)

    hscroller_main.set_frame(text_number_info, info_changed)
    hscroller_num.set_frame(text_number, number_changed)

    info_ticker = hstack([
        text_info,
        hscroller_main.draw(fs.tick),
    ], gap=2, align='center')

    return vstack([
        div(
            hscroller_num.draw(fs.tick),
            style=DivStyle(
                background='#013117',
                padding=2,
                radius=(3, 0, 0, 0),
                border=1,
                border_color='#25470e',
            ),
        ),
        div(info_ticker, style=DivStyle(background='#081542', padding=1)),
    ], gap=0, align='left')


draw = draw_loop(composer, sleepms=10)
