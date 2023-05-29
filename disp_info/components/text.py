from PIL import Image, ImageDraw
from PIL.ImageFont import FreeTypeFont
from typing import TypedDict, Optional
from typing_extensions import Unpack

from .elements import Frame
from . import fonts


class TextVars(TypedDict):
    value: Optional[str]
    fill: Optional[str]
    font: Optional[FreeTypeFont]

class Text(Frame):
    def __init__(self, value: Optional[str] = None, font: FreeTypeFont = fonts.tamzen__rs, fill: str = '#fff'):
        self.font = font
        self.fill = fill
        self.value = value

        self._init_str()

    def _init_str(self):
        value = self.value
        if not value:
            return

        _, _, w, h = self.font.getbbox(value, anchor='lt')
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((0, 0), value, fill=self.fill, font=self.font, anchor='lt')
        self.image = im
        self.width = w
        self.height = h

    def update(self, **kwargs: Unpack[TextVars]) -> bool:
        dirty = False

        for prop in ['value', 'fill', 'font']:
            if new_value := kwargs.get(prop):
                prev_value = getattr(self, prop)
                if new_value != prev_value:
                    setattr(self, prop, new_value)
                    dirty = True

        if dirty:
            self._init_str()

        return dirty

class MultiLineText(Text):
    def _init_str(self):
        value = self.value
        if not value:
            return

        # create a dummy image in order to get the bbox.
        _imd = Image.new('RGBA', (0, 0))
        _dd = ImageDraw.Draw(_imd)
        l, t, r, b = _dd.multiline_textbbox((0, 0), value, font=self.font, spacing=2)
        w = r + l
        h = b + t
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.multiline_text((0, 0), value, fill=self.fill, font=self.font, spacing=2)
        self.image = im
        self.width = w
        self.height = h
