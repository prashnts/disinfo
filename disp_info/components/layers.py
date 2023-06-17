from dataclasses import dataclass, field
from PIL import Image, ImageColor, ImageDraw

from typing import Union

from .elements import Frame


@dataclass
class DivStyle:
    padding: int = 0
    radius: int = 0
    margin: int = 0
    corners: list[int] = field(default_factory=lambda: [1, 1, 1, 1])
    background: str = '#00000000'
    border: int = 0
    border_color: str = '#000'


def add_background(
    frame: Frame,
    style: DivStyle = DivStyle(),
) -> Frame:
    '''Adds a background to given Frame.

    Padding can be added uniformly to each edge, and a corner
    radius can be specified to get rounded corners in the background.
    It is possible to only have rounded corners on specified corners,
    via `corners` argument. The corners are top-left, top-right,
    bottom-right, and bottom-left (in this order).

    Note that this is much faster with radius=0 as we don't need to draw.
    '''
    w = frame.width + (2 * style.padding)
    h = frame.height + (2 * style.padding)

    background = ImageColor.getrgb(style.background)

    if style.radius == 0:
        i = Image.new('RGBA', (w, h), background)
    else:
        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(i)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=style.radius, fill=background)

        # Draw rounded corners where specified.
        # Selectively fills the corners set to 0. We do this because the
        # pillow version we use does not support selective corners in rounded rect.
        # We are getting around it by filling the colors where we don't need
        # rounded corners.
        coords = [
            (0, 0),                     # top left corner
            (w - style.radius, 0),            # top right
            (w - style.radius, h - style.radius),   # bottom right
            (0, h - style.radius),            # bottom left
        ]
        for corner, box in zip(style.corners, coords):
            if not corner:
                x0, y0 = box
                d.rectangle((x0, y0, x0 + style.radius - 1, y0 + style.radius - 1), fill=background)

    i.alpha_composite(frame.image, (style.padding, style.padding))
    return Frame(i)
