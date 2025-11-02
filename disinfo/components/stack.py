import random

from typing import Optional
from dataclasses import dataclass

from disinfo.data_structures import FrameState, UniqInstance
from disinfo.config import app_config

from .elements import Frame
from .layouts import vstack
from .layers import div, DivStyle
from .widget import Widget
from .scroller import VScroller

@dataclass(frozen=True)
class StackStyle:
    size: int = app_config.height
    offset_top: int = 8
    speed: float = 0.0001
    scroll_delta: int = 3
    reverse_delta: int = 10
    scrollbar: bool = False
    static_if_small: bool = False

class Stack(metaclass=UniqInstance):
    def __init__(self, name: str, style: StackStyle = StackStyle):
        self.name = name
        self.style = style
        self._widgets = []
        self._prev_widgets = []

        self.last_step = 0
        self.pos = 0

        self.scroller = VScroller(
            size=self.style.size,
            speed=self.style.speed,
            delta=self.style.scroll_delta,
            static_if_small=self.style.static_if_small,
            scrollbar=self.style.scrollbar)

    def mut(self, widgets: list[Widget]) -> 'Stack':
        self._prev_widgets = self._widgets
        self._widgets = sorted(widgets, key=lambda w: w.priority, reverse=True)
        return self

    def surface(self, fs: FrameState):
        frames = [w.draw(fs, active=i == self.pos and self.scroller.on_target) for i, w in enumerate(self._widgets)]
        pos = self.style.size - self.style.offset_top + sum([f.height for f in frames[0:self.pos] if f]) + (self.pos - 1 * 2)
        return div(vstack(frames, gap=2), DivStyle(padding=(0, 0, 0, 2))), pos
    
    def next_widget(self):
        self.pos += 1
        self.pos %= len(self._widgets)

    def tick(self, step: float):
        curr_widget = self._widgets[self.pos]
        items_in_focus = [w for w in self._widgets if w.frame and w.focus]
        items_just_added = [w for w in self._widgets if w.frame and w not in self._prev_widgets]

        if len(items_in_focus) == 1:
            self.pos = [i for i, w in enumerate(self._widgets) if w.frame and w.focus][0]
            return
        
        if len(items_just_added) == 1:
            self.pos = [i for i, w in enumerate(self._widgets) if w.frame and w == items_just_added[0]][0]
            self.last_step = step
            return

        if not self.scroller.on_target:
            return

        if step - self.last_step > curr_widget.wait_time + 1:
            if not any ([w.frame for w in self._widgets]):
                self.pos = 0
            elif len([w for w in self._widgets if w.frame]) == 1:
                self.pos = [i for i, w in enumerate(self._widgets) if w.frame][0]
            else:
                pos = self.pos
                while True:
                    # pos = random.randint(0, len(self._widgets) - 1)
                    pos += 1
                    pos %= len(self._widgets)
                    if self._widgets[pos].frame and pos != self.pos:
                        self.pos = pos
                        break
            self.scroller.on_target = False
            self.last_step = step

    def draw(self, fs: FrameState) -> Optional[Frame]:
        self.tick(fs.tick)
        surface, pos = self.surface(fs)
        delta = self.style.scroll_delta
        if self.scroller.direction < 0:
            delta = self.style.reverse_delta

        return self.scroller.set_frame(surface, reset=False).set_delta(delta).set_target(pos).draw(fs.tick)
