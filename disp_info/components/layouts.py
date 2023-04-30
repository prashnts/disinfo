from typing import Literal
from PIL import Image

from .elements import UIElement, Frame

VerticalAlignment = Literal['center', 'top', 'bottom']
HorizontalAlignment = Literal['center', 'left', 'right']


def stack_horizontal(elements: list[UIElement], gap: int = 0, align: VerticalAlignment = 'center') -> Frame:
    gap_width = gap * (len(elements) - 1)
    width = sum([e.width for e in elements]) + gap_width
    height = max([e.height for e in elements])
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    x = 0
    for e in elements:
        # todo: respect alignment
        if align == 'top':
            y = 0
        elif align == 'center':
            # position in height
            y = (height - e.height) // 2
        elif align == 'bottom':
            y = height - e.height
        img.alpha_composite(e.image, (x, y))
        x += e.width
        x += gap

    return Frame(img)

def stack_vertical(elements: list[UIElement], gap: int = 0, align: HorizontalAlignment = 'left') -> Frame:
    gap_width = gap * (len(elements) - 1)
    width = max([e.width for e in elements])
    height = sum([e.height for e in elements]) + gap_width

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    y = 0
    for e in elements:
        # todo: respect alignment
        if align == 'left':
            x = 0
        elif align == 'center':
            # position in height
            x = (width - e.width) // 2
        elif align == 'right':
            x = width - e.width
        img.alpha_composite(e.image, (x, y))
        y += e.height
        y += gap

    return Frame(img)
