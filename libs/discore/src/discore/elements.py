from PIL import Image, ImageEnhance
from abc import ABCMeta
from collections import namedtuple
from itertools import count
from typing import Optional, Union, Any, NamedTuple


_hash = hash
_tokens = count()

class UIElement(metaclass=ABCMeta):
    width: int
    height: int
    image: Image.Image

TrimParam = namedtuple('TrimParam', ['left', 'upper', 'right', 'lower'])

class Target(NamedTuple):
    '''A touchable box of a frame, in its px, and what a touch on it does.'''
    x: int
    y: int
    w: int
    h: int
    action: str
    payload: Any = None
    hold: float = 0     # s a touch stays on it before the action, 0: on release

class Ink(NamedTuple):
    '''Glyph pixels of a frame, in its px: the mask (L, w x h), the color meant and the stroke width.
    Placed over a picture, the guard recolors them to stay readable.'''
    x: int
    y: int
    w: int
    h: int
    mask: Image.Image
    color: str
    stroke: int = 1

# Marks: the Targets and Inks a frame carries, moved along by the layouts.
Mark = Union[Target, Ink]

def shifted(marks: tuple, dx: int, dy: int) -> tuple:
    return tuple(m._replace(x=m.x + dx, y=m.y + dy) for m in marks) if dx or dy else marks

def scaled(marks: tuple, sx: float, sy: float) -> tuple:
    # Inks don't scale: a resized glyph isn't one.
    return tuple(t._replace(x=round(t.x * sx), y=round(t.y * sy), w=round(t.w * sx), h=round(t.h * sy))
                 for t in marks if isinstance(t, Target))

def clipped(marks: tuple, w: int, h: int) -> tuple:
    '''The marks cut to (0, 0, w, h); what's left outside goes.'''
    out = ()
    for m in marks:
        x0, y0, x1, y1 = max(m.x, 0), max(m.y, 0), min(m.x + m.w, w), min(m.y + m.h, h)
        if x1 <= x0 or y1 <= y0:
            continue
        if isinstance(m, Ink) and (x0, y0, x1, y1) != (m.x, m.y, m.x + m.w, m.y + m.h):
            m = m._replace(mask=m.mask.crop((x0 - m.x, y0 - m.y, x1 - m.x, y1 - m.y)))
        out += (m._replace(x=x0, y=y0, w=x1 - x0, h=y1 - y0),)
    return out

class Frame(UIElement):
    '''An image and its hash: equal hashes, same picture.

    Without a hash it gets a token, equal only to itself. Frame.of_pixels hashes the pixels.
    '''
    __slots__ = ('image', 'width', 'height', 'hash', '_targets', '_inks')

    def __init__(self, image: Image.Image, hash: Any = None, targets: tuple[Mark, ...] = ()):
        self.image = image
        self.width = image.width
        self.height = image.height
        self.hash = ('frame', next(_tokens)) if hash is None else hash
        self._targets = targets

    @classmethod
    def of_pixels(cls, image: Image.Image) -> 'Frame':
        return cls(image, ('pixels', image.size, _hash(image.tobytes())))

    @property
    def marks(self) -> tuple[Mark, ...]:
        '''Its Targets and Inks, carried by the layouts (targets= takes both). Subclasses drawing themselves have none.'''
        return getattr(self, '_targets', ())

    @property
    def targets(self) -> tuple[Target, ...]:
        '''Touchable boxes.'''
        return tuple(m for m in self.marks if isinstance(m, Target))

    @property
    def inks(self) -> tuple[Ink, ...]:
        # Once per marks: asked for at every place.
        marks, known = self.marks, getattr(self, '_inks', None)
        if known is None or known[0] is not marks:
            known = self._inks = (marks, tuple(m for m in marks if isinstance(m, Ink)))
        return known[1]

    def inked(self, color: str = '#ffffff', stroke: int = 1) -> 'Frame':
        '''Marks its opaque pixels as one ink (an icon), meant in color.'''
        ink = Ink(0, 0, self.width, self.height, self.image.getchannel('A'), color, stroke)
        return Frame(self.image, hash=self.hash, targets=self.marks + (ink,))

    def reposition(self, x: int = 0, y: int = 0) -> 'Frame':
        # TODO: support extending the frame
        w = self.width
        h = self.height

        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        i.alpha_composite(self.image, (x, y))
        return Frame(i, hash=('reposition', (x, y), self.hash), targets=clipped(shifted(self.marks, x, y), w, h))

    def rotate(self, angle: float) -> 'Frame':
        return Frame(self.image.rotate(angle, expand=True), hash=('rotate', angle, self))

    def trim(self, left: int = 0, upper: int = 0, right: int = 0, lower: int = 0) -> 'Frame':
        w, h = self.width - right - left, self.height - lower - upper
        return Frame(self.image.crop((left, upper, self.width - right, self.height - lower)),
                     hash=('trim', (left, upper, right, lower), self.hash),
                     targets=clipped(shifted(self.marks, -left, -upper), w, h))
    
    def crop_even(self, horizontal: int = 0, vertical: int = 0) -> 'Frame':
        w, h = self.width - 2 * horizontal, self.height - 2 * vertical
        return Frame(self.image.crop((horizontal, vertical, self.width - horizontal, self.height - vertical)),
                     hash=('crop_even', (horizontal, vertical), self.hash),
                     targets=clipped(shifted(self.marks, -horizontal, -vertical), w, h))

    def rescale(self, ratio: Union[float, tuple[float, float]]) -> 'Frame':
        if not isinstance(ratio, tuple):
            ratio = (ratio, ratio)
        width = self.width * ratio[0]
        height = self.height * ratio[1]
        return Frame(self.image.resize((int(width), int(height))), hash=('rescale', ratio, self.hash),
                     targets=scaled(self.marks, int(width) / self.width, int(height) / self.height))

    def resize(self, size: tuple[int, int], ratio_fn=None, pixel=False) -> 'Frame':
        res_x, res_y = size
        img = self.image
        if ratio_fn:
            ratio = ratio_fn(res_x/img.width, res_y/img.height)
            size = (int(img.width*ratio), int(img.height*ratio))
        resample_mode = Image.Resampling.BICUBIC if not pixel else Image.Resampling.LANCZOS
        img = (img
            .resize(size, resample=resample_mode)
            .convert('RGBA'))
        return Frame(img, hash=('resize', size, self.hash), targets=scaled(self.marks, img.width / self.width, img.height / self.height))

    def opacity(self, opacity: float) -> 'Frame':
        img = Image.new('RGBA', self.image.size, (0, 0, 0, 0))
        return Frame(Image.blend(img, self.image, opacity), hash=('opacity', opacity, self.hash), targets=self.marks)

    def brightness(self, factor: float = 1) -> 'Frame':
        img = self.image.copy()
        enhance = ImageEnhance.Brightness(img)
        img = enhance.enhance(factor)
        return Frame(img, hash=('brightness', factor, self.hash), targets=self.marks)

    def contrast(self, factor: float = 1) -> 'Frame':
        img = self.image.copy()
        enhance = ImageEnhance.Contrast(img)
        img = enhance.enhance(factor)
        return Frame(img, hash=('contrast', factor, self.hash), targets=self.marks)

    def color_(self, factor: float = 1) -> 'Frame':
        img = self.image.copy()
        enhance = ImageEnhance.Color(img)
        img = enhance.enhance(factor)
        return Frame(img, hash=('color', factor, self.hash), targets=self.marks)

    def __repr__(self) -> str:
        return f'{self.hash}'

    def __hash__(self):
        h = self.hash
        return hash(h[1]) if isinstance(h, tuple) and h and h[0] == 'tag' else hash(h)

    def __eq__(self, other) -> bool:
        return hash(self) == hash(other)

    def tag(self, value) -> 'Frame':
        self.hash = ('tag', value)
        return self

    @property
    def size(self):
        return self.image.size

    @classmethod
    def fallback(cls, hash: Any = None, size: tuple[int, int] = (1, 1)) -> 'Frame':
        return Frame(Image.new('RGBA', size, (0, 0, 0, 0)), ('fallback', size) if hash is None else hash)

    def blank(self) -> 'Frame':
        return Frame(Image.new('RGBA', self.size, (0, 0, 0, 0)), hash=('blank', self.hash))

class StillImage(Frame):
    def __init__(self, filename: str, resize: Optional[tuple[int, int]] = None):
        img = Image.open(filename).convert('RGBA')
        if resize:
            img = img.resize(resize)
        super().__init__(img, hash=(filename, resize))


# No limit. Big, but fits an image size.
UNBOUNDED = 1 << 14

class Box(Frame):
    '''A frame sized by its parent: it measures, then renders at the size it gets.
    Used as a Frame, it renders at its natural size.
    '''
    grow: float = 0     # share of the free space it takes, like flex-grow
    shrink: float = 0   # share of the overflow it gives up, like flex-shrink

    # axis: 'x' (row) or 'y' (column).
    def grow_along(self, axis: str) -> float:
        return self.grow

    def shrink_along(self, axis: str) -> float:
        return self.shrink

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        '''Size wanted within max_w x max_h.'''
        raise NotImplementedError

    def render(self, w: int, h: int) -> Frame:
        '''A frame of w x h, the size decided by the parent.'''
        raise NotImplementedError

    @property
    def natural(self) -> Frame:
        if (f := self.__dict__.get('_natural')) is None:
            f = self.__dict__['_natural'] = self.render(*self.measure(UNBOUNDED, UNBOUNDED))
        return f

    # The Frame interface, at the natural size.
    image = property(lambda self: self.natural.image)
    _targets = property(lambda self: self.natural.marks)
    width = property(lambda self: self.natural.width)
    height = property(lambda self: self.natural.height)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} {self.hash}>'

def less(limit: int, n: int) -> int:
    '''limit - n, staying unbounded when limit is.'''
    return limit if limit >= UNBOUNDED else max(limit - n, 0)

def measure(frame: Frame, max_w: int, max_h: int) -> tuple[int, int]:
    return frame.measure(max_w, max_h) if isinstance(frame, Box) else frame.size

def render(frame: Frame, w: int, h: int) -> Frame:
    return frame.render(w, h) if isinstance(frame, Box) else frame
