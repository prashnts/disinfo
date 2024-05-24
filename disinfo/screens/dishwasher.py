import pendulum

from pyquery import PyQuery as pq
from functools import cache
from typing import Optional
from datetime import datetime

from .drawer import draw_loop
from .colors import gray, amber_red, minute_green
from ..components import fonts
from ..components.layers import div, DivStyle
from ..components.layouts import hstack
from ..components.widget import Widget
from ..components.text import TextStyle, text
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..data_structures import FrameState, AppBaseModel
from ..utils.time import is_expired
from ..utils.cairo import load_svg, load_svg_string

label_style = TextStyle(font=fonts.cozette, color=minute_green.darken(0.2).hex)

dishwasher_icon = load_svg('assets/dishwasher.svg')

class DishwasherState(AppBaseModel):
    clean: bool = False
    triggered_at: Optional[datetime] = None
    triggers: Optional[list[datetime]] = None

    @property
    def is_triggered(self):
        return not is_expired(self.triggered_at, 5, expired_if_none=True)

class DishwasherStateManager(PubSubStateManager[DishwasherState]):
    model = DishwasherState
    channels = ('di.pubsub.dishwasher',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'trigger':
            self.state.triggered_at = pendulum.now()

            if not self.state.triggers:
                self.state.triggers = []
            self.state.triggers.append(self.state.triggered_at)
            if len(self.state.triggers) == 4:
                now = pendulum.now()
                trigger_secs = [(now - t).seconds for t in self.state.triggers]
                self.state.triggers = []
                if sum(trigger_secs) < 5:
                    self.state.clean = not self.state.clean

@cache
def washer_lcd(letter: str, color: str):
    mapping = {
        '1': ['b2', 'd2'],
        '2': ['a', 'b2', 'c', 'e', 'd1'],
        '3': ['a', 'b2', 'c', 'e', 'd2'],
        '4': ['b1', 'b2', 'c', 'd2'],
        '5': ['a', 'b1', 'c', 'd2', 'e'],
        '6': ['a', 'b1', 'c', 'd1', 'd2', 'e'],
        '7': ['a', 'b2', 'd2'],
        '8': ['a', 'b1', 'b2', 'c', 'd1', 'd2', 'e'],
        '9': ['a', 'b1', 'b2', 'c', 'd2', 'e'],
        '0': ['a', 'b1', 'b2', 'd1', 'd2', 'e'],
        'h': ['b1', 'c', 'd1', 'd2'],
        'c': ['a', 'b1', 'd1', 'e'],
        'l': ['b1', 'd1', 'e'],
        'e': ['a', 'b1', 'c', 'd1', 'e'],
        'a': ['a', 'b1', 'b2', 'c', 'd1', 'd2'],
        'n': ['a', 'b1', 'b2', 'd1', 'd2'],
    }
    with open('assets/dishwasher-segment.svg', 'rb') as f:
        svg = pq(f.read())

    for led in mapping[letter]:
        svg(f'#{led}').attr('stroke', color)
    
    return load_svg_string(str(svg))


def timer_full_cycle(now):
    # The dishwasher should finish by 07:30.
    # Cycle time is about 3h30m, so it should start at 04:00.
    # now = now.replace(hour=23, minute=50)
    next_target = now.replace(hour=4, minute=0, second=0)
    if now > next_target:
        next_target = next_target.add(days=1)
    return next_target.diff(now).in_hours()

def is_visible(fs: FrameState):
    state = DishwasherStateManager().get_state(fs)
    return state.is_triggered
    return (not (3 < fs.now.hour <= 19)) or state.is_triggered

def composer(fs: FrameState):
    state = DishwasherStateManager().get_state(fs)
    if not is_visible(fs):
        return

    next_timer = timer_full_cycle(fs.now)

    display = None

    if state.clean:
        display = div(text('Clean', label_style), DivStyle(padding=[0, 1, 0, 0]))
        display = hstack([washer_lcd(h, minute_green.darken(0.2).hex) for h in 'clean'], align='bottom')
    else:
        color = amber_red.darken(0.1).hex
        display = hstack([*[washer_lcd(h, color) for h in str(next_timer)], washer_lcd('h', color)], align='bottom')

    return div(
        hstack([
            dishwasher_icon,
            display,
        ], gap=3),
        style=DivStyle(padding=1, radius=1, background=gray.darken(0.7).hex)
    ).tag('dishwasher')

def widget(fs: FrameState):
    state = DishwasherStateManager().get_state(fs)
    return Widget('dishwasher', composer(fs), priority=0.5, wait_time=8, focus=state.is_triggered)

draw = draw_loop(composer)
