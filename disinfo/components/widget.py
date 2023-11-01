from PIL import Image
from dataclasses import dataclass
from typing import Optional

from disinfo.data_structures import FrameState

from .elements import Frame
from .layers import DivStyle, div


@dataclass
class Widget:
    name: str
    frame: Optional[Frame] = None
    priority: int = 0
    active: bool = True
    style: DivStyle = DivStyle(padding=1, radius=2, background='#000000cf')

    def draw(self, fs: FrameState) -> Optional[Frame]:
        if self.frame:
            return div(self.frame, self.style)
        return Frame(Image.new('RGBA', (1, 1), (0, 0, 0, 0)))
