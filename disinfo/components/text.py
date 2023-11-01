from dataclasses import dataclass
from textwrap import wrap
from typing import Optional
from functools import cache

from PIL import Image, ImageDraw
from PIL.ImageFont import FreeTypeFont

from .elements import Frame
from .fonts import tamzen__rs, TTFFont

@dataclass(frozen=True)
class TextStyle:
    color: str          = '#fff'
    outline: int        = 0
    outline_color: str  = '#000'
    font: TTFFont       = tamzen__rs

    # Following are applicable to mutliline text.
    spacing: int        = 1
    line_width: int     = 20

# Used as a fallback image when the text value is missing.
EmptyTextFallback = Image.new('RGBA', (1, 1), (0, 0, 0, 0))

class Text(Frame):
    def __init__(
        self,
        value: Optional[str] = None,
        style: TextStyle = TextStyle(),
    ):
        self.value = value
        self.style = style
        self.hash = (self.__class__.__name__, self.value, self.style)

        self.draw_text()

    def populate_frame(self, im: Image.Image):
        self.image = im
        self.width = im.width
        self.height = im.height

    def draw_text(self):
        value = self.value
        if not value:
            return self.populate_frame(EmptyTextFallback)

        o = self.style.outline
        # If the text has outline the bounding box needs to be adjusted
        # in both axes. This is because the font has no way of knowing that
        # an outline will be applied while drawing.
        _, _, w, h = self.style.font.font.getbbox(value, anchor='lt')
        im = Image.new('RGBA', (w + (2 * o), h + (2 * o)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text(
            (o, o),
            value,
            fill=self.style.color,
            font=self.style.font.font,
            anchor='lt',
            stroke_width=self.style.outline,
            stroke_fill=self.style.outline_color,
        )
        self.populate_frame(im)

    def update(self, value: Optional[str] = None, style: Optional[TextStyle] = None) -> bool:
        dirty = False

        if value and self.value != value:
            self.value = value
            dirty = True

        if style and self.style != style:
            self.style = style
            dirty = True

        self.hash = (self.__class__.__name__, self.value, self.style)

        if dirty:
            self.draw_text()

        return dirty



class MultiLineText(Text):
    def draw_text(self):
        if not self.value:
            return self.populate_frame(EmptyTextFallback)
        # Wrap the string to fit in the container.
        wrap_paragraph = lambda x: '\n'.join(wrap(x, self.style.line_width))
        value = '\n'.join([wrap_paragraph(l) for l in self.value.splitlines()])

        # create a dummy draw instance in order to get the bbox.
        _dd = ImageDraw.Draw(Image.new('RGBA', (0, 0)))
        l, t, r, b = _dd.multiline_textbbox(
            (0, 0),
            value,
            font=self.style.font.font,
            spacing=self.style.spacing,
            stroke_width=self.style.outline,
        )
        # TODO: add anchor.
        w = r + l
        h = b + t
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.multiline_text(
            (0, 0),
            value,
            fill=self.style.color,
            font=self.style.font.font,
            spacing=self.style.spacing,
            stroke_width=self.style.outline,
            stroke_fill=self.style.outline_color,
        )
        self.populate_frame(im)


@cache
def text(value: str, style: TextStyle = TextStyle(), multiline: bool = False) -> Text:
    if multiline:
        return MultiLineText(value, style)
    return Text(value, style)
