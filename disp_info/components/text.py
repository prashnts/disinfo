from colour import Color
from PIL import Image, ImageDraw, ImageFont

from .elements import UIElement


class Text(UIElement):
    width: int
    height: int

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