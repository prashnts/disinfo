from PIL import Image, ImageColor

from .elements import Frame

def add_background(frame: Frame, fill: str, padding: int = 0) -> Frame:
    w = frame.width + (2 * padding)
    h = frame.height + (2 * padding)

    color = ImageColor.getrgb(fill)

    i = Image.new('RGBA', (w, h), color)
    i.alpha_composite(frame.image, (padding, padding))

    return Frame(i)
