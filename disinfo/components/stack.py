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

        self.scroller = VScroller(size=app_config.height, speed=0.001, delta=2)

    def mut(self, widgets: list[Widget]) -> 'Stack':
        self._widgets = sorted(widgets, key=lambda w: w.priority, reverse=True)
        return self

    def surface(self, fs: FrameState):
        frames = [w.draw(fs, active=i == self.pos) for i, w in enumerate(self._widgets)]
        pos = app_config.height + sum([f.height for f in frames[0:self.pos] if f]) + (self.pos - 1 * 2)
        return div(vstack(frames, gap=2), DivStyle(padding=1)), pos

    def tick(self, step: float):
        curr_widget = self._widgets[self.pos]
        if step - self.last_step > curr_widget.priority * 2 + 1:
            if not any ([w.frame for w in self._widgets]):
                self.pos = 0
            else:
                while True:
                    self.pos = random.randint(0, len(self._widgets) - 1)
                    if self._widgets[self.pos].frame:
                        break
            self.last_step = step

    def draw(self, fs: FrameState) -> Optional[Frame]:
        self.tick(fs.tick)
        surface, pos = self.surface(fs)

        return self.scroller.set_frame(surface, reset=False).set_target(pos).draw(fs.tick)
