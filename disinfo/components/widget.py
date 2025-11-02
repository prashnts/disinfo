from PIL import Image
from dataclasses import dataclass, replace as dc_replace
from typing import Optional

from disinfo.data_structures import FrameState
from disinfo.utils import ease

from .elements import Frame
from .transitions import ScaleIn, ScaleOut, TimedTransition
from .layers import DivStyle, div


@dataclass
class Widget:
    name: str
    frame: Optional[Frame] = None
    priority: int = 1
    active: bool = True
    focus: bool = False
    wait_time: float = 2
    transition_duration: float = 0.25
    style: DivStyle = DivStyle(padding=3, radius=2, background="#00000085", border=1, border_color="#00000088")
    transition_enter: TimedTransition[Frame] = ScaleIn
    transition_exit: TimedTransition[Frame] = ScaleOut
    ease_in: ease.EasingFn = ease.cubic.cubic_in
    ease_out: ease.EasingFn = ease.cubic.cubic_out

    def draw(self, fs: FrameState, active: bool = False) -> Optional[Frame]:
        enter = self.transition_enter(f'{self.name}.scalein', self.transition_duration, self.ease_in)
        exit = self.transition_exit(f'{self.name}.scaleout', self.transition_duration, self.ease_out)
        if self.frame:
            style = dc_replace(self.style, border_color='#15559869' if active else '#00000098')
            exit.reset()
            return enter.mut(div(self.frame, style).tag(self.frame.hash)).draw(fs)
        else:
            enter.reset()
            if enter.curr_value and not exit.finished:
                return exit.mut(enter.curr_value).draw(fs)