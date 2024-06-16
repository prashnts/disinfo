from disinfo.components.elements import Frame
from disinfo.data_structures import FrameState
from disinfo.components.widget import Widget
from disinfo.components.layers import div, DivStyle
from disinfo.components.layouts import hstack, vstack
from disinfo.components.text import TextStyle, text
from disinfo.components.transitions import text_slide_in
from disinfo.components import fonts
from disinfo.utils.cairo import load_svg, load_svg_string

from .state import ADSBxStateManager


airplane_icon = load_svg('assets/mui-icons/plane.svg')


def airplane_widget(fs: FrameState, plane: dict) -> Widget:
    frame = hstack([
        airplane_icon,
        vstack([
            text_slide_in(fs, f'avi.w.{plane["hex"]}.flight', plane.get('flight').strip(), TextStyle(font=fonts.px_op_mono_8, color='#106822')),
            hstack([
                text_slide_in(fs, f'avi.w.{plane["hex"]}.alt', f"{plane.get('alt_baro'):0d}", TextStyle(font=fonts.cozette, color='#106822')),
                text('m', TextStyle(font=fonts.bitocra7, color='#b27853')),
            ]),
        ]),
    ])
    return Widget(name='aviator.airplane_widget', frame=frame, priority=2, wait_time=10)


def planes(fs: FrameState):
    planes = ADSBxStateManager().get_state(fs)
    widgets = [airplane_widget(fs, plane) for plane in planes[:1]]
    return widgets