from dataclasses import dataclass, replace as dc_replace
from textwrap import wrap
from typing import Literal, Optional, Union
from functools import lru_cache

from PIL import Image, ImageDraw

from .elements import Frame, TrimParam, Box, UNBOUNDED
from .layouts import vstack
from . import fonts
from .fonts import TTFFont

@dataclass(frozen=True)
class TextStyle:
    color: str          = '#fff'
    outline: int        = 0
    outline_color: str  = '#000'
    font: Optional[TTFFont] = None     # fonts.default

    width: int          = -1

    # Following are applicable to mutliline text.
    spacing: int        = 1
    line_width: int     = 20

    # Within a width given by a parent (a Flex, a div with a width):
    # 'fit' cuts the text to it, 'wrap' breaks it into lines, at most max_lines (0: any)
    # and as many as fit the height given.
    overflow: Literal['visible', 'fit', 'wrap'] = 'visible'
    max_lines: int      = 0

    # Hacks to make some fonts look better
    trim: Union[int, TrimParam] = 0

    @property
    def trims(self) -> TrimParam:
        if isinstance(self.trim, int):
            return TrimParam(self.trim, self.trim, self.trim, self.trim)
        return self.trim

    @property
    def ttf(self) -> TTFFont:
        return self.font or fonts.default

    @property
    def line_spacing(self) -> int:
        return max(self.ttf.spacing, self.spacing)

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
        _, _, w, h = self.style.ttf.font.getbbox(value, anchor='lt')
        max_width = self.style.width if self.style.width > 0 else w + (2 * o)
        im = Image.new('RGBA', (max_width, h + (2 * o)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text(
            (o, o),
            value,
            fill=self.style.color,
            font=self.style.ttf.font,
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
            font=self.style.ttf.font,
            spacing=self.style.line_spacing,
            stroke_width=self.style.outline,
        )
        _est_line_width = self.style.width // (r - l)
        value = wrapped_value(_est_line_width // 3)

        for width in range(max(_est_line_width - 5, 1), _est_line_width + 20):
            l, t, r, b = _dd.multiline_textbbox(
                (o, o),
                wrapped_value(width),
                font=self.style.ttf.font,
                spacing=self.style.line_spacing,
                stroke_width=self.style.outline,
            )
            bwidth = r - l
            if bwidth > self.style.width:
                break
            value = wrapped_value(width)

        l, t, r, b = _dd.multiline_textbbox(
            (o, o),
            value,
            font=self.style.ttf.font,
            spacing=self.style.line_spacing,
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
            font=self.style.ttf.font,
            spacing=self.style.line_spacing,
            stroke_width=self.style.outline,
            stroke_fill=self.style.outline_color,
        )
        self.populate_frame(im)


class TextBox(Box):
    '''Text that fits the width its parent gives it, see TextStyle.overflow.'''
    shrink = 1

    def __init__(self, value: Optional[str], style: TextStyle):
        self.value = value or ''
        self.style = style
        self.line_style = dc_replace(style, overflow='visible')
        self.hash = ('TextBox', self.value, style)

    def lines(self, max_w: int, max_h: int = UNBOUNDED) -> list[Frame]:
        # The first line always, the others while they fit max_h. Sized by the lines drawn: any font.
        frames, h = [], -self.style.spacing
        for line in self._wrap(max_w):
            f = text(line, self.line_style)
            if frames and h + self.style.spacing + f.height > max_h:
                break
            frames.append(f)
            h += self.style.spacing + f.height
        return frames

    def _wrap(self, max_w: int) -> list[str]:
        if self.style.overflow == 'fit':
            return [_cut(self.value, self.line_style, max_w)]
        lines = ['']
        for word in self.value.split():
            line = f'{lines[-1]} {word}'.strip()
            if _width(line, self.line_style) <= max_w or not lines[-1]:
                lines[-1] = line
            elif len(lines) < (self.style.max_lines or len(lines) + 1):
                lines.append(word)
            else:
                break
        return [_cut(l, self.line_style, max_w) for l in lines]

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        lines = self.lines(max_w, max_h)
        return max(f.width for f in lines), sum(f.height for f in lines) + self.style.spacing * (len(lines) - 1)

    def render(self, w: int, h: int) -> Frame:
        return vstack(self.lines(w, h), gap=self.style.spacing)

@lru_cache(maxsize=4096)
def _width(value: str, style: TextStyle) -> int:
    return style.ttf.font.getbbox(value, anchor='lt')[2] + 2 * style.outline if value else 0

def _cut(value: str, style: TextStyle, max_w: int) -> str:
    # Longest start of value within max_w.
    lo, hi = 0, len(value)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if _width(value[:mid], style) <= max_w else (lo, mid - 1)
    return value[:lo].rstrip()


@lru_cache(maxsize=1024)
def text(value: str, style: TextStyle = TextStyle(), multiline: bool = False, **kwargs) -> Text:
    style = dc_replace(style, **kwargs)
    if style.overflow != 'visible':
        return TextBox(value, style)
    if multiline:
        return MultiLineText(value, style)
    return Text(value, style)
