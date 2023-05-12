from PIL import Image, ImageColor, ImageDraw

from .elements import Frame

def add_background(frame: Frame, fill: str, padding: int = 0, radius: int = 0) -> Frame:
    w = frame.width + (2 * padding)
    h = frame.height + (2 * padding)

    color = ImageColor.getrgb(fill)

    if radius == 0:
        i = Image.new('RGBA', (w, h), color)
    else:
        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(i)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=color)
    i.alpha_composite(frame.image, (padding, padding))
    return Frame(i)
