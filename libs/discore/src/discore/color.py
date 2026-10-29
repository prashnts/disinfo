from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields, replace as dc_replace
from functools import cached_property
from typing import Iterator, Union

from colour import Color as _Colour
from PIL import ImageColor


def constrain(value, min_value=0, max_value=1):
    return max(min(value, max_value), min_value)


def linear(c: float) -> float:
    '''sRGB channel 0-1 to linear light.'''
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def gamma(c: float) -> float:
    c = constrain(c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

def lstar(y: float) -> float:
    '''Relative luminance to CIE L* (0-100), how light it looks.'''
    return y * 903.3 if y <= 0.008856 else 116 * y ** (1 / 3) - 16

def luminance(l: float) -> float:
    '''CIE L* back to relative luminance.'''
    return l / 903.3 if l <= 8 else ((l + 16) / 116) ** 3


class AppColor(_Colour):
    def __init__(self, color: str):
        self.__dict__['alpha'] = 1
        if color.startswith('#'):
            if len(color) == 9:
                # contains alpha.
                self.__dict__['alpha'] = int(color[7:9], 16) / 255
                color = color[0:7]
        super().__init__(color)

    def saturate(self, amount: float):
        self.saturation += amount
        return self

    def darken(self, amount: float):
        c = _Colour(self)
        luminance = self.luminance - amount
        c.luminance = constrain(luminance)
        return c

    def clamp(self, minval=0, maxval=1):
        c = _Colour(self)
        # c.saturation = constrain(c.saturation, minval, maxval)
        c.luminance = constrain(c.luminance, minval, maxval)
        return c

    def get_rgba(self):
        return (*self.rgb, self.alpha)

    def get_hexa(self):
        alpha = hex(int(self.alpha * 255))[2:].zfill(2)
        return f'{self.hex_l}{alpha}'

    def set_alpha(self, alpha: float) -> 'AppColor':
        self.__dict__['alpha'] = alpha
        return self

    def get_pil_color(self) -> tuple[int, int, int, int]:
        r, g, b = [int(c * 255) for c in self.rgb]
        a = int(self.alpha * 255)
        return (r, g, b, a)


ColorLike = Union[str, tuple, _Colour]

class Color(str):
    '''A color as its hex, '#rrggbbaa': a string wherever a color string goes (PIL, styles, hashes).

    From a hex, a css name, an (r, g, b[, a]) of 0-255 or a colour.Color (AppColor). A token ('@fg') isn't a
    color: resolve() it against the palette.
    '''

    def __new__(cls, value: ColorLike):
        if isinstance(value, Color):
            return value
        if isinstance(value, AppColor):
            value = value.get_hexa()
        elif isinstance(value, _Colour):
            value = value.hex_l
        rgba = tuple(value) if isinstance(value, tuple) else ImageColor.getrgb(value)
        rgba = (*rgba, 255) if len(rgba) == 3 else rgba
        c = super().__new__(cls, '#%02x%02x%02x%02x' % rgba)
        c.rgba = rgba
        return c

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self.rgba[:3]

    @property
    def alpha(self) -> float:
        return self.rgba[3] / 255

    @property
    def cairo(self) -> tuple[float, float, float, float]:
        return tuple(c / 255 for c in self.rgba)

    @cached_property
    def lum(self) -> float:
        r, g, b = (linear(c / 255) for c in self.rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @cached_property
    def L(self) -> float:
        return lstar(self.lum)

    def a(self, alpha: float) -> 'Color':
        return Color((*self.rgb, round(constrain(alpha) * 255)))

    def mix(self, other: ColorLike, t: float) -> 'Color':
        '''t of the way to other, in linear light.'''
        o = Color(other).rgba
        lin = [linear(c / 255) * (1 - t) + linear(d / 255) * t for c, d in zip(self.rgb, o)]
        return Color((*(round(gamma(c) * 255) for c in lin), round(self.rgba[3] * (1 - t) + o[3] * t)))

    def with_L(self, l: float) -> 'Color':
        '''The same hue at lightness l: scaled in linear light, towards white where a channel is full.'''
        y, cur = luminance(constrain(l, 0, 100)), self.lum
        lin = [linear(c / 255) for c in self.rgb]
        lin = [min(c * y / cur, 1) for c in lin] if cur > 0 else [y] * 3
        got = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
        if got < y < 1:
            t = (y - got) / (1 - got)
            lin = [c + t * (1 - c) for c in lin]
        return Color((*(round(gamma(c) * 255) for c in lin), self.rgba[3]))

    def lift(self, dl: float) -> 'Color':
        return self.with_L(self.L + dl)


# Light × lit area: luminance × stroke stays under it on the LEDs (fg on 1 px, fg2 on 2 px).
glare = 0.5

def capped(color: ColorLike, stroke: int, limit: float = glare) -> Color:
    '''The color, darkened to the glare cap of its stroke width.'''
    c = Color(color)
    return c.with_L(lstar(limit / stroke)) if c.lum * stroke > limit else c


@dataclass(frozen=True)
class Palette:
    '''The color tokens: '@name' in a style resolves to them when it's drawn.

    Core first; the meanings below them are the extension. Swap values, never names: of() for a screen or section.
    '''
    bg: Color = Color('#000000')
    fg: Color = Color('#a6a8ae')        # values, body
    fg2: Color = Color('#83868c')       # labels, display
    fg3: Color = Color('#5b5e64')       # units, ticks
    line: Color = Color('#ffffff30')
    card: Color = Color('#00000088')
    scrim: Color = Color('#000000b0')
    accent: Color = Color('#e0a040')
    ok: Color = Color('#42a459')
    warn: Color = Color('#b7925e')
    bad: Color = Color('#c93f20')
    # Extension
    ink2: Color = Color('#33363e')      # rules, tracks; not for text
    info: Color = Color('#2d83b4')
    active: Color = Color('#8a6cc8')
    live: Color = Color('#3fb8c8')
    done: Color = Color('#5f8a68')
    idle: Color = Color('#6a6d74')
    alert: Color = Color('#e03030')
    # Tints: a section's card, at a3.
    navy: Color = Color('#0a1a3a')
    green: Color = Color('#045523')
    violet: Color = Color('#3a1a6a')
    amber: Color = Color('#40300c')
    # Frost: blur radius, and the dim between its floor and cap solved to keep the text readable.
    frost: float = 1.8
    dim: tuple[float, float] = (0.08, 0.7)
    # The glare cap applies (LEDs bloom, AMOLED and LCD don't).
    glare: bool = True

    def __hash__(self) -> int:
        # Hashed for every cached style: once.
        if (h := self.__dict__.get('_hash')) is None:
            h = hash(tuple(getattr(self, f.name) for f in fields(self)))
            object.__setattr__(self, '_hash', h)
        return h

    def of(self, **kwargs) -> 'Palette':
        '''Another palette, the named tokens changed: colors as any ColorLike.'''
        kinds = {f.name: f.type for f in fields(self)}
        return dc_replace(self, **{k: Color(v) if kinds[k] is Color else v for k, v in kwargs.items()})

    def asdict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def triple(self, meaning: str) -> tuple[Color, Color, Color]:
        '''Ink, fill and line of a meaning: text, pills, borders that don't drift apart.'''
        c = getattr(self, meaning)
        return c, c.a(0.31), c.a(0.69)


_palette: ContextVar[Palette] = ContextVar('palette', default=Palette())

def palette() -> Palette:
    return _palette.get()

@contextmanager
def using(p: Palette) -> Iterator[Palette]:
    '''Draws within with p: the tokens resolve to it.'''
    token = _palette.set(p)
    try:
        yield p
    finally:
        _palette.reset(token)

def resolve(color: ColorLike) -> Color:
    '''A token ('@fg', '@ok/a3' with an alpha step) to its color in the palette in use, anything else as a Color.'''
    if isinstance(color, str) and color.startswith('@'):
        name, _, a = color[1:].partition('/')
        c = getattr(palette(), name)
        return c.a(alpha_steps[a]) if a else c
    return Color(color)

# a1-a6: the alpha steps.
alpha_steps = {'a1': 0x14 / 255, 'a2': 0x30 / 255, 'a3': 0x50 / 255, 'a4': 0x88 / 255, 'a5': 0xb0 / 255,
               'a6': 0xe0 / 255}
