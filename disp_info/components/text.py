from PIL import Image, ImageDraw
from PIL.ImageFont import FreeTypeFont
from typing import TypedDict, Optional
from typing_extensions import Unpack
from textwrap import wrap

from .elements import Frame
from . import fonts


class TextVars(TypedDict):
    value: Optional[str]
    fill: Optional[str]
    font: Optional[FreeTypeFont]

class Text(Frame):
    def __init__(
        self,
        value: Optional[str] = None,
        font: FreeTypeFont = fonts.tamzen__rs,
        fill: str = '#fff',
        outline: int = 0,
        outline_color: str = '#000',
    ):
        self.font = font
        self.fill = fill
        self.value = value
        self.outline = outline
        self.outline_color = outline_color

        self._init_str()

    def _init_str(self):
        value = self.value
        if not value:
            return

        o = self.outline
        _, _, w, h = self.font.getbbox(value, anchor='lt')
        im = Image.new('RGBA', (w + (2 * o), h + (2 * o)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text(
            (o, o),
            value,
            fill=self.fill,
            font=self.font,
            anchor='lt',
            stroke_width=self.outline,
            stroke_fill=self.outline_color,
        )
        self.image = im
        self.width = im.width
        self.height = im.height

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
    def __init__(self, *args, line_width: int, **kwargs):
        self.line_width = line_width
        super().__init__(*args, **kwargs)

    def _init_str(self):
        if not self.value:
            return
        # Wrap the string to fit in the container.
        wrap_paragraph = lambda x: '\n'.join(wrap(x, self.line_width))
        value = '\n'.join([wrap_paragraph(l) for l in self.value.splitlines()])

        # create a dummy draw instance in order to get the bbox.
        _dd = ImageDraw.Draw(Image.new('RGBA', (0, 0)))
        l, t, r, b = _dd.multiline_textbbox((0, 0), value, font=self.font, spacing=1)
        # TODO: add anchor.
        w = r + l
        h = b + t
        im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.multiline_text((0, 0), value, fill=self.fill, font=self.font, spacing=1)
        self.image = im
        self.width = w
        self.height = h
