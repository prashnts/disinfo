from cairocffi import ImageSurface, FORMAT_RGB24, FORMAT_ARGB32
from cairosvg.parser import Tree
from cairosvg.surface import PNGSurface
from PIL import Image

from disinfo.components.elements import Frame

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

def load_svg(path: str) -> Frame:
    with open(path, 'rb') as f:
        svg = f.read()
    surface = PNGSurface(Tree(bytestring=svg), None, 1).cairo
    return Frame(to_pil(surface), hash=path)

def load_svg_string(svg: str) -> Frame:
    surface = PNGSurface(Tree(bytestring=svg.encode()), None, 1).cairo
    return Frame(to_pil(surface), hash=svg)
