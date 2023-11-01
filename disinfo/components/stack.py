import random

from typing import Optional

from disinfo.data_structures import FrameState, UniqInstance
from disinfo.config import app_config

from .elements import Frame
from .layouts import vstack
from .layers import div, DivStyle
from .widget import Widget
from .scroller import VScroller
from .transitions import TimedTransition, NumberTransition

class TransitionList(TimedTransition[float]):
    ...

class Stack(metaclass=UniqInstance):
    def __init__(self, name: str):
        self.name = name
        self._widgets = []

        self.last_step = 0
        self.pos = 0

        self.scroller = VScroller(size=app_config.height)

    def mut(self, widgets: list[Widget]) -> 'Stack':
        self._widgets = sorted(widgets, key=lambda w: w.priority, reverse=True)
        return self

    def surface(self, fs: FrameState):
        frames = [w.draw(fs) for w in self._widgets]
        pos = app_config.height + sum([f.height for f in frames[0:self.pos]]) + (self.pos - 1 * 2)
        return div(vstack(frames, gap=2), DivStyle(padding=1)), pos

    def tick(self, step: float):
        if step - self.last_step > 7:
            self.pos = random.randint(0, len(self._widgets) - 1)
            self.pos %= len(self._widgets)
            self.last_step = step

    def draw(self, fs: FrameState) -> Optional[Frame]:
        self.tick(fs.tick)
        surface, pos = self.surface(fs)

        return self.scroller.set_frame(surface, reset=False).set_target(pos).draw(fs.tick)
