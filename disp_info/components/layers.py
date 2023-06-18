from dataclasses import dataclass
from functools import cache
from PIL import Image, ImageColor, ImageDraw

from typing import Union

from .elements import Frame


@dataclass
class DivStyle:
    padding: Union[int, tuple[int]] = 0
    radius: Union[int, tuple[int]] = 0
    margin: Union[int, tuple[int]] = 0
    background: str = '#00000000'
    border: int = 0
    border_color: str = '#000'


@cache
def rounded_rectangle(w: int, h: int, r: list[int], fill: str, border: int, border_color: str) -> Image.Image:
    '''
    Creates an Image patch of a rectangle with rounded corners.

    Each corner may have different radius, and optionally a border.
    '''
    i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(i)
    diam = [i * 2 for i in r]
    xmax = w - 1
    ymax = h - 1

    arc_params = [
        ((             0,              0), diam[0], (180, 270)),
        ((xmax - diam[1],              0), diam[1], (270,  0)),
        ((xmax - diam[2], ymax - diam[2]), diam[2], (  0,  90)),
        ((             0, ymax - diam[3]), diam[3], ( 90, 180)),
    ]
    polygon_coords = [
        (       r[0],           0),
        (xmax - r[1],           0),
        (       xmax,        r[1]),
        (       xmax, ymax - r[2]),
        (xmax - r[2],        ymax),
        (       r[3],        ymax),
        (          0, ymax - r[3]),
        (          0,        r[1]),
    ]
    d.polygon(polygon_coords, fill=fill, outline=border_color, width=border)

    for ((ax, ay), dim, (start, end)) in arc_params:
        d.pieslice((ax, ay, ax + dim, ay + dim), start=start, end=end, fill=fill)
        d.arc((ax, ay, ax + dim, ay + dim), start=start, end=end, width=border, fill=border_color)

    return i


def div(
    frame: Frame,
    style: DivStyle = DivStyle(),
) -> Frame:
    '''
    Acts as a container for other frames.

    Padding can be added uniformly to each edge, and a corner
    radius can be specified to get rounded corners in the background.
    It is possible to only have rounded corners on specified corners,
    via `corners` argument. The corners are top-left, top-right,
    bottom-right, and bottom-left (in this order).

    Note that this is much faster with radius=0 as we don't need to draw.
    '''
    if isinstance(style.padding, int):
        style.padding = (style.padding,) * 4
    if isinstance(style.margin, int):
        style.margin = (style.margin,) * 4
    if isinstance(style.radius, int):
        style.radius = (style.radius,) * 4

    pad = style.padding
    margin = style.margin
    radius = style.radius

    w = frame.width + (pad[1] + pad[3]) + (margin[1] + margin[3])
    h = frame.height + (pad[0] + pad[2]) + (margin[0] + margin[2])
    w_inner = frame.width + (pad[1] + pad[3])
    h_inner = frame.height + (pad[0] + pad[2])

    o_x = margin[3] + pad[3]    # Origin of the frame in div.
    o_y = margin[0] + pad[0]

    if sum(radius) == 0 and sum(margin) == 0:
        i = Image.new('RGBA', (w, h), ImageColor.getrgb(style.background))
    else:
        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        bg = rounded_rectangle(
            w_inner,
            h_inner,
            r=radius,
            fill=style.background,
            border=style.border,
            border_color=style.border_color)
        i.alpha_composite(bg, (margin[1], margin[0]))

    i.alpha_composite(frame.image, (o_x, o_y))
    return Frame(i)
