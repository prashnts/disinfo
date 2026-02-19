from dataclasses import dataclass, replace as dc_replace
from functools import cache
from PIL import Image, ImageColor, ImageDraw

from typing import Union, Optional

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
    clip: bool = True
    height: int | None = None
    width: int | None = None


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
        ((xmax - diam[0],              0), diam[0], (270,   0)),
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
    frame: Optional[Frame] = None,
    style: DivStyle = DivStyle(),
    **kwargs,
) -> Frame:
    '''
    Acts as a container for other frames.

    Padding and margin can be added to each edge, as well as the corner
    radius.

    Returns a new Frame.
    '''
    if kwargs:
        style = dc_replace(style, **kwargs)
    if not frame:
        return Frame.fallback(('div', style))

    pad = style.padding
    margin = style.margin
    radius = style.radius

    if isinstance(style.padding, int):
        pad = (style.padding,) * 4
    if isinstance(style.margin, int):
        margin = (style.margin,) * 4
    if isinstance(style.radius, int):
        radius = (style.radius,) * 4

    w = style.width or frame.width + (pad[1] + pad[3]) + (margin[1] + margin[3])
    h = style.height or frame.height + (pad[0] + pad[2]) + (margin[0] + margin[2])
    w_inner = frame.width + (pad[1] + pad[3])
    h_inner = frame.height + (pad[0] + pad[2])

    o_x = margin[3] + pad[3]    # Origin of the frame in div.
    o_y = margin[0] + pad[0]

    if sum(radius) == 0 and sum(margin) == 0:
        i = Image.new('RGBA', (w, h), ImageColor.getrgb(style.background))
        i.alpha_composite(frame.image, (o_x, o_y))
    else:
        frame_div = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        frame_div.alpha_composite(frame.image, (o_x, o_y))

        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        i.alpha_composite(
            rounded_rectangle(
                width=w_inner,
                height=h_inner,
                radius=radius,
                fill=style.background,
                border=style.border,
                border_color=style.border_color),
            (margin[1], margin[0]))
        
        if style.clip:
            mask = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            mask.alpha_composite(
                rounded_rectangle(
                    width=w_inner,
                    height=h_inner,
                    radius=radius,
                    fill='#FFFFFF',
                    border=style.border,
                    border_color='#FFFFFF00'),
                (margin[1], margin[0]))
            masked_frame = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            masked_frame = Image.composite(frame_div, masked_frame, mask)
            i.alpha_composite(masked_frame, (0, 0))
        else:
            i.alpha_composite(frame_div, (0, 0))

    return Frame(i, hash=('div', style, frame))

def styled_div(**kwargs):
    style = DivStyle(**kwargs)
    def div_(frame: Frame, style=style, **moreargs):
        if moreargs:
            style = dc_replace(style, **moreargs)
        return div(frame, style)
    return div_
