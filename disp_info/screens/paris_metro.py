import random

from functools import cache
from PIL import Image, ImageDraw

from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import composite_at, stack_horizontal, stack_vertical


# Metro colors are taken from wikipedia [1] but some colors
# were adjusted (saturated + darkened) to be better visible on LED Matrix.
# [1]: https://commons.wikimedia.org/wiki/Template:Paris_transit_icons
# First color represents color of metro line and second the text fill.
metro_colors = {
    '1': ['#FFCE00', '#000'],
    '2': ['#0064B0', '#fff'],
    '3': ['#847e14', '#000'],
    '3b': ['#57abbe', '#000'],
    '4': ['#8a2465', '#fff'],
    '5': ['#F28E42', '#000'],
    '6': ['#50a863', '#000'],
    '7': ['#d7829a', '#000'],
    '7b': ['#50a863', '#000'],
    '8': ['#b171b8', '#000'],
    '9': ['#D5C900', '#000'],
    '10': ['#E3B32A', '#000'],
    '11': ['#8D5E2A', '#fff'],
    '12': ['#00814F', '#fff'],
    '13': ['#57abbe', '#000'],
    '14': ['#662483', '#fff'],
    '15': ['#B90845', '#fff'],
    '16': ['#d7829a', '#000'],
    '17': ['#D5C900', '#000'],
    '18': ['#086b5c', '#fff'],
}

@cache
def status_icon(status_name: str):
    size = 9
    img = Image.new('RGBA', (size + 1, size + 1))
    draw = ImageDraw.Draw(img)

    draw.regular_polygon([size / 2, size / 2 + 1, size / 2 + 1], 3, fill='#e64539')

    draw.text((size / 2 + 1, size / 2 + 1), '!', fill='#fff', font=fonts.tamzen__rs, anchor='mm')

    return Frame(img)


@cache
def metro_icon(line_name: str, problems: bool = False) -> Frame:
    size = 9
    background, text_color = metro_colors.get(line_name, ['#C6C6C6', '#000'])

    img = Image.new('RGBA', (size + 1, size + 1))
    draw = ImageDraw.Draw(img)

    start_x = 0 if len(line_name) > 1 else 1

    draw.ellipse([0, 0, size, size], fill=background, outline='#e64539', width=problems)
    draw.text(((size / 2) + start_x, size / 2), line_name, fill=text_color, font=fonts.tamzen__rs, anchor='mm')

    return Frame(img)


def draw(tick: float):
    traffic_ok = ['1', '8']
    has_problems = random.random() > 0.9
    ok_lines = stack_horizontal([metro_icon(i, has_problems) for i in traffic_ok], gap=1, align='center')
    return stack_horizontal([
        status_icon('ok'),
        ok_lines,
    ], gap=1, align='center')
