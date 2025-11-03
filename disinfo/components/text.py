from dataclasses import dataclass, replace as dc_replace
from textwrap import wrap
from typing import Optional, Union
from functools import cache

from PIL import Image, ImageDraw
from PIL.ImageFont import FreeTypeFont

from .elements import Frame, TrimParam
from .fonts import bitocra7, TTFFont, small_bars

@dataclass(frozen=True)
class TextStyle:
    color: str          = '#fff'
    outline: int        = 0
    outline_color: str  = '#000'
    font: TTFFont       = bitocra7

    width: int          = -1

    # Following are applicable to mutliline text.
    spacing: int        = 1
    line_width: int     = 20

    # Hacks to make some fonts look better
    trim: Union[int, TrimParam] = 0

    @property
    def trims(self) -> TrimParam:
        if isinstance(self.trim, int):
            return TrimParam(self.trim, self.trim, self.trim, self.trim)
        return self.trim

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
        if self.style.trim:
            trim = self.trim(*self.style.trims)
            self.image = trim.image
            self.width = trim.width
            self.height = trim.height

    def draw_text(self):
        value = self.value
        if not value:
            return self.populate_frame(EmptyTextFallback)

        o = self.style.outline
        # If the text has outline the bounding box needs to be adjusted
        # in both axes. This is because the font has no way of knowing that
        # an outline will be applied while drawing.
        _, _, w, h = self.style.font.font.getbbox(value, anchor='lt')
        max_width = self.style.width if self.style.width > 0 else w + (2 * o)
        im = Image.new('RGBA', (max_width, h + (2 * o)), (0, 0, 0, 0))
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
        wrap_paragraph = lambda x, lwidth: '\n'.join(wrap(x, lwidth))
        wrapped_value = lambda width: '\n'.join([wrap_paragraph(l, width) for l in self.value.splitlines()])

        _dd = ImageDraw.Draw(Image.new('RGBA', (0, 0)))
        o = self.style.outline

        # Basic character width
        l, t, r, b = _dd.multiline_textbbox(
            (0, 0),
            'M',
            font=self.style.font.font,
            spacing=self.style.spacing,
            stroke_width=self.style.outline,
        )
        _est_line_width = self.style.width // (r - l)

        for width in range(max(_est_line_width - 5, 1), _est_line_width + 20):
            l, t, r, b = _dd.multiline_textbbox(
                (o, o),
                wrapped_value(width),
                font=self.style.font.font,
                spacing=self.style.spacing,
                stroke_width=self.style.outline,
            )
            bwidth = r - l
            if bwidth > self.style.width:
                break
            value = wrapped_value(width)

        l, t, r, b = _dd.multiline_textbbox(
            (o, o),
            value,
            font=self.style.font.font,
            spacing=self.style.spacing,
            stroke_width=self.style.outline,
        )
        # TODO: add anchor.
        w = r + l
        h = b + t
        im = Image.new('RGBA', (w + (2 * o), h + (2 * o)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.multiline_text(
            (o, o),
            value,
            fill=self.style.color,
            font=self.style.font.font,
            spacing=self.style.spacing,
            stroke_width=self.style.outline,
            stroke_fill=self.style.outline_color,
        )
        self.populate_frame(im)


@cache
def text(value: str, style: TextStyle = TextStyle(), multiline: bool = False, **kwargs) -> Text:
    style = dc_replace(style, **kwargs)
    if multiline:
        return MultiLineText(value, style)
    return Text(value, style)
