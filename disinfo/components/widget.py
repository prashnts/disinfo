from PIL import Image
from dataclasses import dataclass, replace as dc_replace, field
from typing import Optional

from disinfo.data_structures import FrameState
from disinfo.utils import ease
from disinfo.utils.func import uname

from .elements import Frame
from .transitions import ScaleIn, ScaleOut, TimedTransition, Resize
from .layers import DivStyle, div


@dataclass
class Widget:
    name: str = field(default_factory=lambda: uname(5))
    frame: Optional[Frame] = None
    priority: int = 1
    active: bool = True
    focus: bool = False
    wait_time: float = 2
    transition_duration: float = 0.25
    style: DivStyle = DivStyle(padding=3, radius=2, background="#00000085", border=1, border_color="#00000088")
    transition_enter: TimedTransition[Frame] = Resize
    transition_exit: TimedTransition[Frame] = Resize
    ease_in: ease.EasingFn = ease.cubic.cubic_in
    ease_out: ease.EasingFn = ease.cubic.cubic_out

    def draw(self, fs: FrameState, active: bool = False) -> Optional[Frame]:
        style = dc_replace(self.style, border_color='#15559869' if active else '#00000098')
        transition = self.transition_enter(f'{self.name}.resize', self.transition_duration, self.ease_in)
        hash_ = self.frame.hash if self.frame else ('widgetframe', self.name)

        if type(transition) == Resize:
            return transition.mut(div(self.frame, style).tag(hash_)).draw(fs)

        exit = self.transition_exit(f'{self.name}.scaleout', self.transition_duration, self.ease_out)
        if self.frame:
            exit.reset()
            return transition.mut(div(self.frame, style).tag(hash_)).draw(fs)
        else:
            transition.reset()
            if transition.curr_value and not exit.finished:
                return exit.mut(transition.curr_value).draw(fs)