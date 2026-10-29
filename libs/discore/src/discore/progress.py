from dataclasses import dataclass, replace as dc_replace
from functools import lru_cache

from PIL import Image, ImageDraw

from .elements import Frame
from .layers import rounded_rectangle
from .color import resolve


@dataclass(frozen=True)
class ProgressStyle:
    width: int = 32
    height: int = 2
    color: str = '@ok'
    track: str = '#ffffff1a'
    radius: int = 0


def progress_bar(value: float, style: ProgressStyle = ProgressStyle()) -> Frame:
    '''A bar filled to `value`, from 0 to 1.'''
    filled = round(style.width * min(max(value, 0), 1))
    return _bar(filled, dc_replace(style, color=resolve(style.color), track=resolve(style.track)))

@lru_cache(maxsize=256)
def _bar(filled: int, style: ProgressStyle) -> Frame:
    # Per filled pixel: a slowly moving bar reuses the same frame.
    w, h, r = style.width, style.height, style.radius
    if r:
        img = rounded_rectangle(w, h, (r,) * 4, style.track, 0, '#00000000').copy()   # it's cached, don't draw on it
        if filled:
            img.alpha_composite(rounded_rectangle(max(filled, 2 * r), h, (r,) * 4, style.color, 0, '#00000000'), (0, 0))
    else:
        img = Image.new('RGBA', (w, h), style.track)
        if filled:
            ImageDraw.Draw(img).rectangle((0, 0, filled - 1, h - 1), fill=style.color)
    return Frame(img, ('progress', filled, style))
