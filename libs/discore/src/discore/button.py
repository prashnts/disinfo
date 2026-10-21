'''Buttons: a styled div that a touch on does an action.'''
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops

from .elements import Frame, Target
from .layers import div, DivStyle


@dataclass(frozen=True)
class ButtonStyle:
    normal: DivStyle = DivStyle(padding=(3, 5, 3, 5), radius=3, background='#ffffff1c', border=1, border_color='#ffffff30')
    pressed: DivStyle = DivStyle(padding=(3, 5, 3, 5), radius=3, background='#ffffff55', border=1, border_color='#ffffff90')
    fill: str = '#ffffff50'     # a hold's progress


def button(content: Frame, action: str, payload: Any = None, pressed: bool = False, style: ButtonStyle = ButtonStyle(),
           hold: float = 0, progress: float = 0) -> Frame:
    '''The content in a div, touchable all over. Targets inside it (a button in a button) come after: on top.

    hold: the seconds a touch stays on it to act; progress (0-1) fills it from the left meanwhile.
    '''
    f = div(content, style.pressed if pressed else style.normal)
    img = f.image
    if progress > 0:
        # In the button's shape: where it has any alpha, its antialiased corners kept.
        bar = Image.new('RGBA', f.size, (0, 0, 0, 0))
        bar.paste(style.fill, (0, 0, round(f.width * min(progress, 1)), f.height))
        bar.putalpha(ImageChops.multiply(bar.getchannel('A'), img.getchannel('A').point(lambda a: min(a * 8, 255))))
        img = img.copy()
        img.alpha_composite(bar)
    return Frame(img, hash=('button', action, repr(payload), pressed, hold, round(progress, 2), f.hash),
                 targets=(Target(0, 0, f.width, f.height, action, payload, hold),) + f.targets)
