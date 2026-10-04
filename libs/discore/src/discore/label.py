from dataclasses import dataclass
from typing import Optional

from .layers import div, DivStyle
from .text import TextStyle, text
from .layouts import vstack, hstack
from .elements import Frame
from .fonts import TTFFont
from .data_structures import FrameState

@dataclass
class LabelStyle:
    font: Optional[TTFFont] = None
    width: int = 0  # auto

    text_style: TextStyle = TextStyle()
    div_style: DivStyle = DivStyle()

    emoji: Optional[str] = ''
    icon: Optional[Frame] = None




def label(text: str, emoji: str, icon: Frame):
    ...