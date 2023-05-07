from functools import cache
from PIL import Image, ImageDraw

from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import composite_at, stack_horizontal


metro_colors = {
    '1': ['#FFCE00', '#000'],
    '4': ['#C04191', '#fff'],
    '6': ['#50a863', '#000'],
    '8': ['#b171b8', '#000'],
    '13': ['#57abbe', '#000'],
}


@cache
def metro_icon(line_name: str) -> Frame:
    size = 9
    background, text_color = metro_colors.get(line_name, ['#C6C6C6', '#000'])

    img = Image.new('RGBA', (size + 1, size + 1))
    draw = ImageDraw.Draw(img)

    start_x = 0 if len(line_name) > 1 else 1

    draw.ellipse([0, 0, size, size], fill=background)
    draw.text(((size / 2) + start_x, size / 2), line_name, fill=text_color, font=fonts.tamzen__rs, anchor='mm')

    return Frame(img)


def draw(tick: float):
    return stack_horizontal([metro_icon(i) for i in metro_colors], gap=2, align='center')
