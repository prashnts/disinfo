'''Buttons: a styled div that a touch on does an action.'''
from dataclasses import dataclass
from typing import Any

from .elements import Frame, Target
from .layers import div, DivStyle


@dataclass(frozen=True)
class ButtonStyle:
    normal: DivStyle = DivStyle(padding=(3, 5, 3, 5), radius=3, background='#ffffff1c', border=1, border_color='#ffffff30')
    pressed: DivStyle = DivStyle(padding=(3, 5, 3, 5), radius=3, background='#ffffff55', border=1, border_color='#ffffff90')


def button(content: Frame, action: str, payload: Any = None, pressed: bool = False, style: ButtonStyle = ButtonStyle()) -> Frame:
    '''The content in a div, touchable all over. Targets inside it (a button in a button) come after: on top.'''
    f = div(content, style.pressed if pressed else style.normal)
    return Frame(f.image, hash=('button', action, repr(payload), pressed, f.hash),
                 targets=(Target(0, 0, f.width, f.height, action, payload),) + f.targets)
