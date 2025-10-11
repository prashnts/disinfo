'''Layout utilities for arranging Frames and Images.

Some of the functions are inspired with CSS FlexBoxes. Namely the
horizontal and vertical alignments when differently sized elements
are in the same container.
'''
from PIL import Image, ImageFilter
from typing import Literal, Optional, Type, Union, Sequence
from itertools import product

from .elements import Frame

VerticalAlignment = Literal['center', 'top', 'bottom']
HorizontalAlignment = Literal['center', 'left', 'right']
ComposeAnchor = Literal['tl', 'tm', 'tr', 'ml', 'mm', 'mr', 'bl', 'bm', 'br']


def hstack(
    elements: Sequence[Optional[Frame]],
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
    if not any(elements):
        return Frame(Image.new('RGBA', (1, 1)), hash=('hstack', gap, align, None))

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

    return Frame(img, hash=('hstack', gap, align, tuple(elements)))

def vstack(
    elements: Sequence[Optional[Frame]],
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
    if not any(elements):
        return Frame(Image.new('RGBA', (1, 1)), hash=('vstack', gap, align, None))

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

    return Frame(img, hash=('vstack', gap, align, tuple(elements)))

def composite_at(
    frame: Optional[Frame],
    dest: Union[Image.Image, Frame],
    anchor: ComposeAnchor = 'tl',
    dx: int = 0,
    dy: int = 0,
    frosted: bool = False,
) -> Frame:
    '''Composes the `frame` so that it is at `anchor` corner of `dest`.

    Anchor positions with respect to `dest` are as follows:
        ┌──────────────────┐
        │tl      tm      tr│
        │                  │
        │ml      mm      mr│
        │                  │
        │bl      bm      br│
        └──────────────────┘
    It modifies the destination if it is an Image.
    Returns a Frame.
    '''
    if not frame:
        return dest

    if isinstance(dest, Frame):
        dest = dest.image.copy()

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

    if frosted:
        bg = dest.filter(ImageFilter.GaussianBlur(1.8))
        region = bg.crop((left + dx, top + dy, left + dx + fw, top + dy + fh))

        rg_data = region.getdata()
        fr_data = frame.image.getdata()
        new_data = []

        for (r, g, b, a), (_, _, _, fa) in zip(rg_data, fr_data):
            new_data.append((r, g, b, 0 if fa == 0 else 255))
        
        region.putdata(new_data)
        dest.alpha_composite(region, (left + dx, top + dy))

    dest.alpha_composite(frame.image, (left + dx, top + dy))
    return Frame(dest, hash=('composite_at', anchor, frame))

def mosaic(
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

    return Frame(img, hash=('mosaic', nx, ny, seamless, frame))

def place_at(frame: Frame, dest: Union[Image.Image, Frame], x: int, y: int, anchor: ComposeAnchor='mm') -> Frame:
    '''Places the frame at the given coordinates.
    The anchor is relative to the frame and will be located at the given coordinates.

    Returns a new frame if dest is a Frame, else modifies the dest image.
    '''
    if not frame:
        return dest

    if isinstance(dest, Frame):
        dest = dest.image.copy()

    fw = frame.width
    fh = frame.height

    # calculate the delta between the anchor and the top left corner of the frame.

    if anchor[0] == 't':
        dy = 0
    elif anchor[0] == 'm':
        dy = -fh // 2
    elif anchor[0] == 'b':
        dy = -fh
    else:
        raise ValueError('Wrong value for anchor.')

    if anchor[1] == 'l':
        dx = 0
    elif anchor[1] == 'm':
        dx = -fw // 2
    elif anchor[1] == 'r':
        dx = -fw
    else:
        raise ValueError('Wrong value for anchor.')

    dest.alpha_composite(frame.image, (x + dx, y + dy))
    return Frame(dest, hash=('place_at', anchor, frame))

def tabular(table: list[list[Optional[Frame]]]):
    # convert a 2d list of frames into a tabular grid.
    # we need to find a way to put these irregular elements together.
    ...
