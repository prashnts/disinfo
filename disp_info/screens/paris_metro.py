from functools import cache
from PIL import Image, ImageDraw

from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import composite_at, stack_horizontal


metro_colors = {
    '1': ['#FFCE00', '#000'],
    '4': ['#C04191', '#fff'],
    '6': ['#83C491', '#000'],
    '8': ['#CEADD2', '#000'],
    '13': ['#98D4E2', '#000'],
}


@cache
def metro_icon(line_name: str) -> Frame:
    size = 10
    background, text_color = metro_colors.get(line_name, ['#C6C6C6', '#000'])

    img = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(img)
    text_line = Text(line_name, font=fonts.bitocra, fill=text_color)

    draw.ellipse([0, 0, size - 1, size - 1], fill=background)

    return Frame(composite_at(text_line, img, 'mm'))


def draw(tick: float):
    return stack_horizontal([metro_icon(i) for i in metro_colors], gap=2, align='center')
