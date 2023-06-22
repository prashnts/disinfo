from dataclasses import dataclass
from functools import cache
from PIL import Image, ImageColor, ImageDraw

from typing import Union

from .elements import Frame


@dataclass(frozen=True)
class DivStyle:
    '''
    The radius is ordered on top-right, bottom-right, bottom-left, and top-left corners.
    The margin and padding are ordered top, right, bottom, and left edges.
    '''
    padding: Union[int, tuple[int]] = 0
    radius: Union[int, tuple[int]] = 0
    margin: Union[int, tuple[int]] = 0
    background: str = '#00000000'
    border: int = 0
    border_color: str = '#00000000'


@cache
def rounded_rectangle(
        width: int,
        height: int,
        radius: list[int],
        fill: str,
        border: int,
        border_color: str,
        scaleup: int = 3,
) -> Image.Image:
    '''
    Creates an Image patch of a rectangle with rounded corners.

    Each corner may have different radius, and optionally a border.
    It is antialiased.
    '''
    w = width * scaleup  # Scale up
    h = height * scaleup
    r = tuple(i * scaleup for i in radius)

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    diam = [i * 2 for i in r]
    xmax = w - 1
    ymax = h - 1

    arc_params = [
        ((             0,              0), diam[3], (180, 270)),
        ((xmax - diam[0],              0), diam[0], (270,  0)),
        ((xmax - diam[1], ymax - diam[1]), diam[1], (  0,  90)),
        ((             0, ymax - diam[2]), diam[2], ( 90, 180)),
    ]
    polygon_coords = [
        (       r[3],           0),
        (xmax - r[0],           0),
        (       xmax,        r[0]),
        (       xmax, ymax - r[1]),
        (xmax - r[1],        ymax),
        (       r[2],        ymax),
        (          0, ymax - r[2]),
        (          0,        r[3]),
        (       r[3],           0),
    ]
    d.polygon(polygon_coords, fill=fill, outline=border_color, width=border * scaleup)

    for ((ax, ay), dim, (start, end)) in arc_params:
        d.pieslice((ax, ay, ax + dim, ay + dim), start=start, end=end, fill=fill)
        d.arc((ax, ay, ax + dim, ay + dim), start=start, end=end, width=border * scaleup, fill=border_color)

    return img.resize((width, height), resample=Image.LANCZOS)


def div(
    frame: Frame,
    style: DivStyle = DivStyle(),
) -> Frame:
    '''
    Acts as a container for other frames.

    Padding and margin can be added to each edge, as well as the corner
    radius.

    Returns a new Frame.
    '''
    pad = style.padding
    margin = style.margin
    radius = style.radius

    if isinstance(style.padding, int):
        pad = (style.padding,) * 4
    if isinstance(style.margin, int):
        margin = (style.margin,) * 4
    if isinstance(style.radius, int):
        radius = (style.radius,) * 4

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
            width=w_inner,
            height=h_inner,
            radius=radius,
            fill=style.background,
            border=style.border,
            border_color=style.border_color)
        i.alpha_composite(bg, (margin[1], margin[0]))

    i.alpha_composite(frame.image, (o_x, o_y))
    return Frame(i)

def styled_div(**kwargs):
    style = DivStyle(**kwargs)
    def div_(frame: Frame):
        return div(frame, style)
    return div_
