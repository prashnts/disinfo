from PIL import Image
from abc import ABCMeta, abstractmethod
from typing import Optional, Union


Postion = tuple[int, int]


class UIElement(metaclass=ABCMeta):
    width: int
    height: int
    image: Image.Image

class Frame(UIElement):
    def __init__(self, image: Image.Image, hash: Optional[int] = None):
        self.image = image
        self.width = image.width
        self.height = image.height
        self.hash = hash

    def reposition(self, x: int = 0, y: int = 0) -> 'Frame':
        # TODO: support extending the frame
        w = self.width
        h = self.height

        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        i.alpha_composite(self.image, (x, y))
        return Frame(i)

    def rotate(self, angle: float) -> 'Frame':
        return Frame(self.image.rotate(angle, expand=True))

    def trim(self, left: int = 0, upper: int = 0, right: int = 0, lower: int = 0) -> 'Frame':
        return Frame(self.image.crop((left, upper, self.width - right, self.height - lower)))

    def rescale(self, ratio: Union[float, tuple[float, float]]) -> 'Frame':
        if not isinstance(ratio, tuple):
            ratio = (ratio, ratio)
        width = self.width * ratio[0]
        height = self.height * ratio[1]
        return Frame(self.image.resize((int(width), int(height))))

    def __repr__(self) -> str:
        return f'<Frame hash={self.hash}>'

    def __hash__(self):
        if self.hash:
            return hash(self.hash)
        return hash(self.image.tobytes())

    def __eq__(self, other) -> bool:
        return hash(self) == hash(other)

    def tag(self, value) -> 'Frame':
        self.hash = value
        return self

    @property
    def size(self):
        return self.image.size

class StillImage(Frame):
    def __init__(self, filename: str, resize: Optional[tuple[int, int]] = None):
        img = Image.open(filename).convert('RGBA')
        if resize:
            img = img.resize(resize)
        super().__init__(img)
