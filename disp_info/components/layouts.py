from PIL import Image
from typing import Literal, Optional
from itertools import product

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

def tile_copies(frame: Frame, nx: int = 2, ny: int = 2, seamless: bool = True) -> Frame:
    w = frame.width * nx
    h = frame.height * ny
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    width_steps = [frame.width * i for i in range(nx)]
    height_steps = [frame.height * i for i in range(ny)]
    flip_x_states = [(i + 1) % 2 == 0 for i in range(nx)]
    flip_y_states = [(i + 1) % 2 == 0 for i in range(ny)]

    flip_states = product(flip_x_states, flip_y_states)
    coords = product(width_steps, height_steps)

    l_i = frame.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    l_t = frame.image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    l_ti = l_t.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    for c, f in zip(coords, flip_states):
        if f[0] and f[1]:
            i = l_ti
        elif f[0] and not f[1]:
            i = l_i
        elif not f[0] and f[1]:
            i = l_t
        else:
            i = frame.image
        img.alpha_composite(i, (c[0], c[1]))

    return Frame(img)
