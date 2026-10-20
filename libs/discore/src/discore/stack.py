import random

from typing import Optional
from dataclasses import dataclass

from .data_structures import FrameState, ScopedInstance

from .elements import Frame
from .layouts import vstack, hstack
from .layers import div, DivStyle
from .widget import Widget
from .scroller import VScroller, HScroller

@dataclass(frozen=True)
class StackStyle:
    size: int
    offset_top: int = 8
    speed: float = 0.0001
    scroll_delta: int = 3
    reverse_delta: int = 10
    scrollbar: bool = False
    static_if_small: bool = False
    align: str = 'left'
    horizontal: bool = False
    # Moving on, the widget shown least lately goes next: over time each gets about the same, whatever moved
    # the stack on (its wait, a motion, a press). Lately: the time on top fades by half over this many seconds.
    half_life: float = 600

class Stack(metaclass=ScopedInstance):
    def __init__(self, name: str, style: StackStyle):
        self.name = name
        self.style = style
        self._widgets = []
        self._prev_widgets = []

        self.last_step = 0
        self.pos = 0
        self.shown = {}             # widget name -> seconds on top, lately
        self._shown_at = None

        if self.style.horizontal:
            self.scroller = HScroller(
                name=f'{name}.scroller',
                size=self.style.size,
                speed=self.style.speed,
                delta=self.style.scroll_delta,
                static_if_small=self.style.static_if_small,
                scrollbar=self.style.scrollbar)
        else:
            self.scroller = VScroller(
                name=f'{name}.scroller',
                size=self.style.size,
                speed=self.style.speed,
                delta=self.style.scroll_delta,
                static_if_small=self.style.static_if_small,
                scrollbar=self.style.scrollbar)

    def mut(self, widgets: list[Widget]) -> 'Stack':
        self._prev_widgets = self._widgets
        self._widgets = sorted(widgets, key=lambda w: w.priority, reverse=True)
        # The list can shrink between frames (e.g. a printer goes offline).
        self.pos = min(self.pos, max(len(self._widgets) - 1, 0))
        return self

    @property
    def current(self) -> Optional[Widget]:
        return self._widgets[self.pos] if self._widgets else None

    def surface(self, fs: FrameState):
        curr_widget = self._widgets[self.pos]
        visible_widgets = [(i, w) for i, w in enumerate(self._widgets) if w.frame and (w.frame.width + w.frame.height) > 2]
        _visible = [w for i, w in visible_widgets]
        # frames = [w.draw(fs, active=i == self.pos and self.scroller.on_target) for i, w in enumerate(self._widgets)]
        frames = [self._frames[w] for i, w in enumerate(self._widgets)]
        frames = [f for _, f in enumerate(frames) if (f.width + f.height) > 2]
        pos = _visible.index(curr_widget) if curr_widget in _visible else 0
        # out_frames = frames[:pos]
        # frames += out_frames
        # frames[:pos] = [f.opacity(0) for f in out_frames]
        pos = self.style.size - self.style.offset_top + sum([f.width if self.style.horizontal else f.height for f in frames[0:pos]]) + (pos - 1 * 2)
        if self.style.horizontal:
            align = 'center' if self.style.align == 'left' else self.style.align
            return div(hstack(frames, gap=2, align=align), DivStyle(padding=(0, 0, 2, 0))), pos
        return div(vstack(frames, gap=2, align=self.style.align), DivStyle(padding=(0, 0, 0, 2))), pos
    
    def next_widget(self):
        if self._widgets:
            self.pos = self._least_shown(stay=False)
            self.scroller.on_target = False

    def _visible(self) -> list[int]:
        frames = getattr(self, '_frames', {})
        seen = lambda w: (f := frames.get(w, w.frame)) is not None and (f.width + f.height) > 2
        return [i for i, w in enumerate(self._widgets) if seen(w)]

    def _least_shown(self, stay: bool = True) -> int:
        # The one in view on top the least lately, the stack's order between equals. A short one stays on until
        # it's had its share; moved on (stay=False), another.
        visible = self._visible()
        others = [i for i in visible if stay or i != self.pos] or visible or [0]
        # Between equals, another than the one on top.
        return min(others, key=lambda i: (round(self.shown.get(self._widgets[i].name, 0), 1), i == self.pos, i))

    def _count(self, step: float):
        # The one on top gains the time since the last frame, all fade.
        dt = min(max(step - self._shown_at, 0), 1) if self._shown_at is not None else 0
        k = 0.5 ** (dt / self.style.half_life)
        # The ones gone (a plane's card) are forgotten once they've faded out.
        here = {w.name for w in self._widgets}
        self.shown = {n: t * k for n, t in self.shown.items() if n in here or t * k > 1}
        # A newcomer starts level with the least shown: a turn, not minutes catching up.
        start = min(self.shown.values(), default=0)
        for w in self._widgets:
            self.shown.setdefault(w.name, start)
        name = self._widgets[self.pos].name
        self.shown[name] = self.shown.get(name, 0) + dt
        self._shown_at = step

    def tick(self, fs: FrameState):
        step = fs.tick
        _visible = lambda w: (self._frames[w].width + self._frames[w].height) > 2
        curr_widget = self._widgets[self.pos]
        self._count(step)
        items_in_focus = [w for w in self._widgets if _visible(w) and w.focus]
        # By name: a widget whose picture changed isn't a new one.
        before = {w.name for w in self._prev_widgets}
        items_just_added = [w for w in self._widgets if _visible(w) and w.name not in before]

        if len(items_in_focus) == 1:
            self.pos = [i for i, w in enumerate(self._widgets) if _visible(w) and w.focus][0]
            return
        
        if len(items_just_added) == 1:
            self.pos = [i for i, w in enumerate(self._widgets) if _visible(w) and w == items_just_added[0]][0]
            self.last_step = step
            return

        if not self.scroller.on_target:
            return
        
        # if not _visible(curr_widget):
        #     self.pos = 0
        #     return

        if step - self.last_step > curr_widget.wait_time + 1:
            if not any ([_visible(w) for w in self._widgets]):
                self.pos = 0
            elif len([w for w in self._widgets if _visible(w)]) == 1:
                self.pos = [i for i, w in enumerate(self._widgets) if _visible(w)][0]
            else:
                self.pos = self._least_shown()
            self.scroller.on_target = False
            self.last_step = step

    def draw(self, fs: FrameState) -> Optional[Frame]:
        if not self._widgets:
            return
        self._frames = {w: w.draw(fs, active=i == self.pos and self.scroller.on_target) for i, w in enumerate(self._widgets)}
        surface, pos = self.surface(fs)
        delta = self.style.scroll_delta
        if self.scroller.direction < 0:
            delta = self.style.reverse_delta

        # pin to middle
        # pos = pos - (self.style.size // 3)

        stack_im = self.scroller.set_frame(surface, reset=False).set_delta(delta).set_target(pos).draw(fs.tick)

        self.tick(fs)
        return stack_im