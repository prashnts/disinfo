from colour import Color
from PIL import Image, ImageDraw, ImageFont

from .elements import UIElement


class Text(UIElement):
    def __init__(self, value: str, font: ImageFont, fill: str):
        self.font = font
        self.fill = fill

        self._init_str(value)

    def _init_str(self, value: str):
        _, _, w, h = self.font.getbbox(value, anchor='lt')
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((0, 0), value, fill=self.fill, font=self.font, anchor='lt')
        self.image = im
        self.value = value
        self.width = w
        self.height = h

    def set_value(self, value: str):
        if self.value != value:
            self._init_str(value)
            return True
        return False

    def set_fill(self, fill: str):
        if self.fill != fill:
            self.fill = fill
            self._init_str(self.value)
            return True
        return False
