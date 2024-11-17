from PIL import Image
from dataclasses import dataclass, replace as dc_replace
from typing import Optional

from disinfo.data_structures import FrameState

from .elements import Frame
from .transitions import ScaleIn
from .layers import DivStyle, div


@dataclass
class Widget:
    name: str
    frame: Optional[Frame] = None
    priority: int = 1
    active: bool = True
    focus: bool = False
    wait_time: float = 2
    style: DivStyle = DivStyle(padding=1, radius=2, background='#000000ca', border=1)

    def draw(self, fs: FrameState, active: bool = False) -> Optional[Frame]:
        transition = ScaleIn(f'{self.name}.scalein', 2, reset_on_none=True)
        if self.frame:
            style = dc_replace(self.style, border_color='#155598a9' if active else '#000000cf')
            return transition.mut(div(self.frame, style).tag('static')).draw(fs)
        else:
            transition.mut(None)