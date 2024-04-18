from PIL import Image
from abc import ABCMeta
from typing import Optional, Union, Any


_hash = hash

class UIElement(metaclass=ABCMeta):
    width: int
    height: int
    image: Image.Image

class Frame(UIElement):
    def __init__(self, image: Image.Image, hash: Any = None):
        self.image = image
        self.width = image.width
        self.height = image.height
        self.hash = (self.__class__.__name__, _hash(image.tobytes())) if hash is None else hash

    def reposition(self, x: int = 0, y: int = 0) -> 'Frame':
        # TODO: support extending the frame
        w = self.width
        h = self.height

        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        i.alpha_composite(self.image, (x, y))
        return Frame(i, hash=('reposition', (x, y), self))

    def rotate(self, angle: float) -> 'Frame':
        return Frame(self.image.rotate(angle, expand=True), hash=('rotate', angle, self))

    def trim(self, left: int = 0, upper: int = 0, right: int = 0, lower: int = 0) -> 'Frame':
        return Frame(self.image.crop((left, upper, self.width - right, self.height - lower)), hash=('trim', (left, upper, right, lower), self))

    def rescale(self, ratio: Union[float, tuple[float, float]]) -> 'Frame':
        if not isinstance(ratio, tuple):
            ratio = (ratio, ratio)
        width = self.width * ratio[0]
        height = self.height * ratio[1]
        return Frame(self.image.resize((int(width), int(height))), hash=('rescale', ratio, self))

    def opacity(self, opacity: float) -> 'Frame':
        img = Image.new('RGBA', self.image.size, (0, 0, 0, 0))
        return Frame(Image.blend(img, self.image, opacity), hash=('opacity', opacity, self))

    def __repr__(self) -> str:
        return f'{self.hash}'

    def __hash__(self):
        if self.hash:
            if self.hash[0] == 'tag':
                return hash(self.hash[1])
            return hash(self.hash)
        return hash(self.image.tobytes())

    def __eq__(self, other) -> bool:
        return hash(self) == hash(other)

    def tag(self, value) -> 'Frame':
        self.hash = ('tag', value, self.hash)
        return self

    @property
    def size(self):
        return self.image.size

    def flex(self, width, height) -> 'Frame':
        raise NotImplementedError


class StillImage(Frame):
    def __init__(self, filename: str, resize: Optional[tuple[int, int]] = None):
        img = Image.open(filename).convert('RGBA')
        if resize:
            img = img.resize(resize)
        super().__init__(img, hash=(filename, resize))
