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

def shifted(targets: tuple, dx: int, dy: int) -> tuple:
    return tuple(t._replace(x=t.x + dx, y=t.y + dy) for t in targets) if dx or dy else targets

def scaled(targets: tuple, sx: float, sy: float) -> tuple:
    return tuple(t._replace(x=round(t.x * sx), y=round(t.y * sy), w=round(t.w * sx), h=round(t.h * sy)) for t in targets)

class Frame(UIElement):
    '''An image and its hash: equal hashes, same picture.

    Without a hash it gets a token, equal only to itself. Frame.of_pixels hashes the pixels.
    '''
    __slots__ = ('image', 'width', 'height', 'hash', '_targets')

    def __init__(self, image: Image.Image, hash: Any = None, targets: tuple = ()):
        self.image = image
        self.width = image.width
        self.height = image.height
        self.hash = ('frame', next(_tokens)) if hash is None else hash
        self._targets = targets

    @classmethod
    def of_pixels(cls, image: Image.Image) -> 'Frame':
        return cls(image, ('pixels', image.size, _hash(image.tobytes())))

    @property
    def targets(self) -> tuple:
        '''Touchable boxes (Target), carried by the layouts. Subclasses drawing themselves have none.'''
        return getattr(self, '_targets', ())

    def reposition(self, x: int = 0, y: int = 0) -> 'Frame':
        # TODO: support extending the frame
        w = self.width
        h = self.height

        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        i.alpha_composite(self.image, (x, y))
        return Frame(i, hash=('reposition', (x, y), self.hash), targets=shifted(self.targets, x, y))

    def rotate(self, angle: float) -> 'Frame':
        return Frame(self.image.rotate(angle, expand=True), hash=('rotate', angle, self))

    def trim(self, left: int = 0, upper: int = 0, right: int = 0, lower: int = 0) -> 'Frame':
        return Frame(self.image.crop((left, upper, self.width - right, self.height - lower)), hash=('trim', (left, upper, right, lower), self.hash),
                     targets=shifted(self.targets, -left, -upper))
    
    def crop_even(self, horizontal: int = 0, vertical: int = 0) -> 'Frame':
        return Frame(self.image.crop((horizontal, vertical, self.width - horizontal, self.height - vertical)), hash=('crop_even', (horizontal, vertical), self.hash),
                     targets=shifted(self.targets, -horizontal, -vertical))

    def rescale(self, ratio: Union[float, tuple[float, float]]) -> 'Frame':
        if not isinstance(ratio, tuple):
            ratio = (ratio, ratio)
        width = self.width * ratio[0]
        height = self.height * ratio[1]
        return Frame(self.image.resize((int(width), int(height))), hash=('rescale', ratio, self.hash),
                     targets=scaled(self.targets, int(width) / self.width, int(height) / self.height))

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
        return Frame(img, hash=('resize', size, self.hash), targets=scaled(self.targets, img.width / self.width, img.height / self.height))

    def opacity(self, opacity: float) -> 'Frame':
        img = Image.new('RGBA', self.image.size, (0, 0, 0, 0))
        return Frame(Image.blend(img, self.image, opacity), hash=('opacity', opacity, self.hash), targets=self.targets)

    def brightness(self, factor: float = 1) -> 'Frame':
        img = self.image.copy()
        enhance = ImageEnhance.Brightness(img)
        img = enhance.enhance(factor)
        return Frame(img, hash=('brightness', factor, self.hash), targets=self.targets)

    def contrast(self, factor: float = 1) -> 'Frame':
        img = self.image.copy()
        enhance = ImageEnhance.Contrast(img)
        img = enhance.enhance(factor)
        return Frame(img, hash=('contrast', factor, self.hash), targets=self.targets)

    def color_(self, factor: float = 1) -> 'Frame':
        img = self.image.copy()
        enhance = ImageEnhance.Color(img)
        img = enhance.enhance(factor)
        return Frame(img, hash=('color', factor, self.hash), targets=self.targets)

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
    targets = property(lambda self: self.natural.targets)
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
