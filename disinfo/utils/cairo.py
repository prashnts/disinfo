from functools import cache

from cairocffi import ImageSurface, FORMAT_RGB24, FORMAT_ARGB32
from cairosvg.parser import Tree
from cairosvg.surface import PNGSurface
from PIL import Image

from disinfo.components.elements import Frame
from disinfo.components.layers import styled_div

def to_pil(surface: ImageSurface) -> Image.Image:
    format = surface.get_format()
    size = (surface.get_width(), surface.get_height())
    stride = surface.get_stride()
    buffer = surface.get_data()

    if format == FORMAT_RGB24:
        return Image.frombuffer(
            "RGB", size, buffer,
            'raw', "BGRX", stride)
    elif format == FORMAT_ARGB32:
        return Image.frombuffer(
            "RGBA", size, buffer,
            'raw', "BGRa", stride)
    else:
        raise NotImplementedError(repr(format))

def load_svg(path: str, scale: float = 1) -> Frame:
    with open(path, 'rb') as f:
        svg = f.read()
    surface = PNGSurface(Tree(bytestring=svg), None, 1, scale=scale).cairo
    return Frame(to_pil(surface), hash=path)

@cache
def load_svg_string(svg: str) -> Frame:
    surface = PNGSurface(Tree(bytestring=svg.encode()), None, 1).cairo
    return Frame(to_pil(surface), hash=svg)


def render_emoji(text: str, size: int = 14):
    fontsize = size * 0.8
    w = size * 1
    h = size * 1
    template = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{w}px" height="{h}px" viewBox="0 0 {w} {h}" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <title>Artboard</title>
    <g id="Artboard" stroke="none" stroke-width="1" fill="none" fill-rule="evenodd" font-family="AppleColorEmoji, Apple Color Emoji" font-size="{fontsize}" font-weight="normal" line-spacing="{fontsize}">
        <text id="" fill="#000000">
            <tspan x="0" y="{size * 0.8}">{text}</tspan>
        </text>
    </g>
</svg>'''
    # div = styled_div(border=1, border_color='#FF0000', padding=1, radius=2, margin=1)
    div = styled_div()
    return div(load_svg_string(template))