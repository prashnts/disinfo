from functools import cache
from .drawer import draw_loop
from ..components.text import text, TextStyle
from ..components.layouts import vstack, composite_at, hstack
from ..components.fonts import register as font_register, small_bars
from ..components.scroller import VScroller
from ..components.layers import div, DivStyle
from ..utils.func import throttle
from ..data_structures import FrameState
from ..drat.app_states import RemoteStateManager
from disinfo.components.widget import Widget
from disinfo.components import fonts


sample_vscroll = VScroller(size=120, pause_at_loop=True, pause_duration=2.5, speed=0.001, delta=3, scrollbar=True)

@cache
def font_demo():
    sample = """A quick brown fox jumps over the lazy dog.
10/20/2023 12:34:56 PM
-> [ ] { } < > # $ % ^ & * - + = ~ ` | \ /
"""

    samples = []
    pauses = [0]
    spacing = 10
    _p = 0
    font_bg = DivStyle(border=1, border_color='#444444', background='#22222244', padding=3, radius=2)

    for fname, font in font_register.items():
        demo = vstack([
            text(fname, style=TextStyle(line_width=20, width=80, font=fonts.tamzen__rm), multiline=True),
            div(text(sample, style=TextStyle(font=font, width=100), multiline=True), style=font_bg),
        ], gap=2)
        _p += demo.height + spacing
        pauses.append(_p)
        samples.append(demo)

    
    return vstack(samples, gap=spacing, align='left'), False, pauses

def info_content(fs: FrameState):
    sample_vscroll.set_frame(*font_demo())
    if not RemoteStateManager().get_state(fs).show_debug:
        sample_vscroll.reset_position()
        return

    header = div(hstack([
        text('Font Demo', style=TextStyle(font=small_bars, width=42, color='#222222cc')),
    ], gap=2), style=DivStyle(
        background='#ffffff88',
        padding=2,
        radius=(2, 1, 1, 2),
        border=0,
        border_color='#444444',
    ))
    return composite_at(header, div(sample_vscroll.draw(fs.tick)), 'tr', frosted=True)


def widget(fs: FrameState):
    return Widget('debug_info', info_content(fs), style=DivStyle(
        background="#100F1D88",
        padding=3,
        margin=0,
        radius=(3, 5, 3, 0),
        border=1,
        border_color='#b196ce'
    ))
