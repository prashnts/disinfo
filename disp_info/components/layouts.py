from PIL import Image
from typing import Literal, Optional

from .elements import UIElement, Frame

VerticalAlignment = Literal['center', 'top', 'bottom']
HorizontalAlignment = Literal['center', 'left', 'right']
ComposeAnchor = Literal['tl', 'tm', 'tr', 'ml', 'mm', 'mr', 'bl', 'bm', 'br']


def stack_horizontal(
    elements: list[Optional[UIElement]],
    gap: int = 0,
    align: VerticalAlignment = 'center',
) -> Frame:
    _elems = [e for e in elements if e]

    gap_width = gap * (len(_elems) - 1)
    width = sum([e.width for e in _elems]) + gap_width
    height = max([e.height for e in _elems])
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    x = 0
    for e in _elems:
        if align == 'top':
            y = 0
        elif align == 'center':
            y = (height - e.height) // 2
        elif align == 'bottom':
            y = height - e.height
        img.alpha_composite(e.image, (x, y))
        x += e.width
        x += gap

    return Frame(img)

def stack_vertical(
    elements: list[Optional[UIElement]],
    gap: int = 0,
    align: HorizontalAlignment = 'left',
) -> Frame:
    _elems = [e for e in elements if e]

    gap_width = gap * (len(_elems) - 1)
    width = max([e.width for e in _elems])
    height = sum([e.height for e in _elems]) + gap_width

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    y = 0
    for e in _elems:
        if align == 'left':
            x = 0
        elif align == 'center':
            x = (width - e.width) // 2
        elif align == 'right':
            x = width - e.width
        img.alpha_composite(e.image, (x, y))
        y += e.height
        y += gap

    return Frame(img)

def composite_at(
    frame: Optional[Frame],
    dest: Image,
    anchor: ComposeAnchor = 'tl',
) -> Image:
    # composes the `frame` so that it is at `anchor` corner of `dest`. It modifies the image.
    if not frame:
        return dest

    dw = dest.width
    dh = dest.height
    fw = frame.width
    fh = frame.height

    left = (dw - fw) // 2
    top = (dh - fh) // 2

    if anchor[0] == 't':
        top = 0
    elif anchor[0] == 'm':
        top = (dh - fh) // 2
    elif anchor[0] == 'b':
        top = dh - fh
    else:
        raise ValueError('Wrong value for anchor.')

    if anchor[1] == 'l':
        left = 0
    elif anchor[1] == 'm':
        left = (dw - fw) // 2
    elif anchor[1] == 'r':
        left = dw - fw
    else:
        raise ValueError('Wrong value for anchor.')

    dest.alpha_composite(frame.image, (left, top))
    return dest
