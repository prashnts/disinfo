from PIL import Image
from dataclasses import dataclass, replace as dc_replace
from typing import Optional

from disinfo.data_structures import FrameState

from .elements import Frame
from .layers import DivStyle, div


@dataclass
class Widget:
    name: str
    frame: Optional[Frame] = None
    priority: int = 1
    active: bool = True
    style: DivStyle = DivStyle(padding=1, radius=2, background='#000000cf', border=1)

    def draw(self, fs: FrameState, active: bool = False) -> Optional[Frame]:
        if self.frame:
            style = dc_replace(self.style, border_color='#0E8E47' if active else '#000000cf')
            return div(self.frame, style)
