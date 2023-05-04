from colour import Color
from PIL import Image, ImageDraw, ImageFont

from .elements import UIElement
from . import fonts


class Text(UIElement):
    def __init__(self, value: str = None, font: ImageFont = fonts.tamzen__rs, fill: str = '#fff'):
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

    def update(self, **kwargs) -> bool:
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
