from pyquery import PyQuery as pq
from functools import cache

from .drawer import draw_loop
from .colors import gray, amber_red
from ..components import fonts
from ..components.layers import div, DivStyle
from ..components.layouts import hstack
from ..components.widget import Widget
from ..components.text import TextStyle, text
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..data_structures import FrameState, AppBaseModel
from ..utils.cairo import load_svg, load_svg_string

label_style = TextStyle(font=fonts.bitocra7, color=amber_red.darken(0.2).hex)

dishwasher_icon = load_svg('assets/washing_machine.svg')


class WashingMachineState(AppBaseModel):
    hours: str = ''
    active: bool = False


class WashingMachineStateManager(PubSubStateManager[WashingMachineState]):
    model = WashingMachineState
    channels = ('di.pubsub.washing_machine',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            self.state.hours = data.payload['hours']
            self.state.active = data.payload['active']


@cache
def washer_lcd(letter):
    mapping = {
        1: ['b2', 'd2'],
        2: ['a', 'b2', 'c', 'e', 'd1'],
        3: ['a', 'b2', 'c', 'e', 'd2'],
        4: ['b1', 'b2', 'c', 'd2'],
        5: ['a', 'b1', 'c', 'd2', 'e'],
        6: ['a', 'b1', 'c', 'd1', 'd2', 'e'],
        7: ['a', 'b2', 'd2'],
        8: ['a', 'b1', 'b2', 'c', 'd1', 'd2', 'e'],
        9: ['a', 'b1', 'b2', 'c', 'd2', 'e'],
        0: ['a', 'b1', 'b2', 'd1', 'd2', 'e'],
        'h': ['b1', 'c', 'd1', 'd2'],
    }
    with open('assets/dishwasher-segment.svg', 'rb') as f:
        svg = pq(f.read())

    for led in mapping[letter]:
        svg(f'#{led}').attr('stroke', amber_red.darken(0.1).hex)
    
    return load_svg_string(str(svg))


def composer(fs: FrameState):
    state = WashingMachineStateManager().get_state(fs)

    if not state.active:
        return

    return div(
        hstack([
            dishwasher_icon,
            text(state.hours, style=label_style),
        ], gap=3),
        style=DivStyle(padding=1, radius=1, background=gray.darken(0.7).hex)
    ).tag('washing_machine')

def widget(fs: FrameState):
    return Widget('washing_machine', composer(fs), priority=0.5, wait_time=4)

draw = draw_loop(composer)
