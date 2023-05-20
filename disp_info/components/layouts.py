'''Layout utilities for arranging Frames and Images.

Some of the functions are inspired with CSS FlexBoxes. Namely the
horizontal and vertical alignments when differently sized elements
are in the same container.
'''
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
    '''Stacks the given elements horizontally with specified gap.

    Alignment is relative to the tallest element:
    T─┬──┬┬─┬┬─┬┬──┬─        ┌─┐   ┌──┐        ┌─┐
      │  ││ ││ ││  │     ┌──┐│ │┌─┐│* │        │ │   ┌──┐
      └──┘│ │└─┘│  │   C─┼──┼┼─┼┼─┼┼──┼─   ┌──┐│ │┌─┐│  │
          │ │   └──┘     └──┘│ │└─┘└──┘    │  ││ ││ ││  │
          └─┘                └─┘         B─┴──┴┴─┴┴─┴┴──┴─

    Returns a new frame.
    '''
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
    '''Stacks the given elements vertically with specified gap.

    Alignment is relative to widest element:
    ├───┐        ┌─┼─┐        ┌───┤
    ├───┘        └─┼─┘        └───┤
    ├─────┐     ┌──┼──┐     ┌─────┤
    ├─────┘     └──┼──┘     └─────┤
    ├───┐        ┌─┼─┐        ┌───┤
    │   │        │ │ │        │   │
    ├───┘        └─┼─┘        └───┤
    L              C              R

    Returns a new frame.
    '''
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
    '''Composes the `frame` so that it is at `anchor` corner of `dest`.

    Anchor positions with respect to `dest` are as follows:
        ┌──────────────────┐
        │tl      tm      tr│
        │                  │
        │ml      mm      mr│
        │                  │
        │bl      bm      br│
        └──────────────────┘
    It modifies the destination image.
    '''
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

def tile_copies(
    frame: Frame,
    nx: int = 2,
    ny: int = 2,
    seamless: bool = True,
) -> Frame:
    '''Tiles the frame in a grid.

    If `seamless` is enabled the frame is flipped in x and y axes to
    create a seamless tiling (illustrated below).

                ┌───┬───┐         ┌───┬───┐
    ┌───┐       │ ◢ │ ◢ │         │ ◢ │ ◣ │
    │ ◢ │  ->   ├───┼───┤         ├───┼───┤
    └───┘       │ ◢ │ ◢ │         │ ◥ │ ◤ │
                └───┴───┘         └───┴───┘
    Frame    Natural Tiling    Seamless Tiling

    Returns a new frame.
    '''
    w = frame.width * nx
    h = frame.height * ny
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    width_steps = [frame.width * i for i in range(nx)]
    height_steps = [frame.height * i for i in range(ny)]

    coords = product(width_steps, height_steps)

    if seamless:
        flip_x_states = [(i + 1) % 2 == 0 for i in range(nx)]
        flip_y_states = [(i + 1) % 2 == 0 for i in range(ny)]
        flip_states = product(flip_x_states, flip_y_states)
        i_lr = frame.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        i_tb = frame.image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        i_tblr = i_tb.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        for c, f in zip(coords, flip_states):
            if f[0] and f[1]:
                i = i_tblr
            elif f[0] and not f[1]:
                i = i_lr
            elif not f[0] and f[1]:
                i = i_tb
            else:
                i = frame.image
            img.alpha_composite(i, (c[0], c[1]))
    else:
        for cx, cy in coords:
            img.alpha_composite(frame.image, (cx, cy))

    return Frame(img)
