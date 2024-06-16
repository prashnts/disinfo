from disinfo.components.elements import Frame
from disinfo.data_structures import FrameState
from disinfo.components.widget import Widget
from disinfo.components.layers import div, DivStyle
from disinfo.components.layouts import hstack, vstack
from disinfo.components.text import TextStyle, text
from disinfo.components.transitions import text_slide_in
from disinfo.components import fonts
from disinfo.utils.cairo import load_svg, load_svg_string
from disinfo.screens.colors import gray

from .state import ADSBxStateManager


airplane_icon = load_svg('assets/mui-icons/plane.svg')


def airplane_widget(fs: FrameState, plane: dict) -> Widget:
    distance = plane.get('distance') or 9000
    hexname = plane.get('hex') or '000000'
    frame = hstack([
        airplane_icon,
        vstack([
            text_slide_in(fs, f'avi.w.{plane["hex"]}.flight', plane.get('flight').strip(), TextStyle(font=fonts.px_op_mono_8, color='#106822')),
            hstack([
                hstack([
                    text_slide_in(fs, f'avi.w.{plane["hex"]}.alt', f"{plane.get('alt_baro'):0d}", TextStyle(font=fonts.bitocra7, color=gray.darken(0.2).hex)),
                    text('m', TextStyle(font=fonts.bitocra7, color=gray.darken(0.3).hex)),
                ], align='bottom', gap=1),
                hstack([
                    text_slide_in(fs, f'avi.w.{plane["hex"]}.dist', f"{plane.get('distance'):0.1f}", TextStyle(font=fonts.bitocra7, color=gray.darken(0.1).hex)),
                    text('km', TextStyle(font=fonts.bitocra7, color=gray.darken(0.3).hex)),
                ], align='bottom', gap=1),
            ], gap=2),
        ], gap=2),
    ])
    return Widget(name=f'aviator.airplane_widget.{hexname}', frame=frame, priority=2, wait_time=20, focus=distance < 2)


def planes(fs: FrameState):
    planes = ADSBxStateManager().get_state(fs)
    widgets = [airplane_widget(fs, plane) for plane in planes[:2]]
    return widgets