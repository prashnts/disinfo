from PIL import Image
from dataclasses import dataclass, replace as dc_replace
from typing import Optional

from disinfo.data_structures import FrameState
from disinfo.utils import ease

from .elements import Frame
from .transitions import ScaleIn, ScaleOut
from .layers import DivStyle, div


@dataclass
class Widget:
    name: str
    frame: Optional[Frame] = None
    priority: int = 1
    active: bool = True
    focus: bool = False
    wait_time: float = 2
    transition_duration: float = 1
    style: DivStyle = DivStyle(padding=1, radius=2, background='#000000ca', border=1)

    def draw(self, fs: FrameState, active: bool = False) -> Optional[Frame]:
        enter = ScaleIn(f'{self.name}.scalein', self.transition_duration, ease.cubic.cubic_in)
        if self.frame:
            style = dc_replace(self.style, border_color='#155598a9' if active else '#000000cf')
            return enter.mut(div(self.frame, style).tag(self.frame.hash)).draw(fs)
        else:
            exit = ScaleOut(f'{self.name}.scaleout', self.transition_duration, ease.cubic.cubic_out)
            enter.reset()
            if enter.curr_value and not exit.finished:
                return exit.mut(enter.curr_value).draw(fs)