from PIL import Image
from dataclasses import dataclass, replace as dc_replace, field
from typing import Optional

from .data_structures import FrameState
from . import ease
from .func import uname

from .elements import Frame
from .transitions import ScaleIn, ScaleOut, TimedTransition, Resize
from .layers import DivStyle, div
from .layouts import vstack


@dataclass
class Widget:
    name: str = field(default_factory=lambda: uname(5))
    frame: Optional[Frame] = None
    priority: int = 1
    active: bool = True
    focus: bool = False
    wait_time: float = 2
    # Its part of the stack's time on top against the others' (1 each): 3, three times a card's time.
    share: float = 1
    transition_duration: float = 0.25
    style: DivStyle = DivStyle(padding=3, radius=2, background="#00000085", border=1, border_color="#00000088")
    transition_enter: TimedTransition[Frame] = Resize
    transition_exit: TimedTransition[Frame] = Resize
    ease_in: ease.EasingFn = ease.cubic.cubic_in
    ease_out: ease.EasingFn = ease.cubic.cubic_out
    # The background it brings while it's on top of its stack (Stack.current): the screen shows it behind.
    background: Optional[str] = None
    # Small cards of their own under it, as wide: each shown while it has a frame (a Box fills the width).
    attached: tuple['Widget', ...] = ()

    def card(self, style: DivStyle) -> Frame:
        # Its div, the attached ones' under it: they come and go with its resize.
        own = div(self.frame, style)
        attached = [a for a in self.attached if a.frame]
        if not attached:
            return own
        sides = lambda v: sum((v,) * 2 if isinstance(v, int) else (v[1], v[3]))
        width = lambda s: own.width - sides(s.padding) - sides(s.margin)
        return vstack([own, *[div(a.frame, a.style, width=width(a.style)) for a in attached]], gap=1)

    def draw(self, fs: FrameState, active: bool = False) -> Optional[Frame]:
        style = dc_replace(self.style, border_color='#15559869' if active else '#00000098')
        transition = self.transition_enter(f'{self.name}.resize', self.transition_duration, self.ease_in)
        hash_ = self.frame.hash if self.frame else ('widgetframe', self.name)
        if self.frame and (more := tuple(a.frame.hash for a in self.attached if a.frame)):
            hash_ = (hash_, *more)

        if type(transition) == Resize:
            return transition.mut(self.card(style).tag(hash_)).draw(fs)

        exit = self.transition_exit(f'{self.name}.scaleout', self.transition_duration, self.ease_out)
        if self.frame:
            exit.reset()
            return transition.mut(self.card(style).tag(hash_)).draw(fs)
        else:
            transition.reset()
            if transition.curr_value and not exit.finished:
                return exit.mut(transition.curr_value).draw(fs)

    def __hash__(self):
        return hash(('widget', self.name))