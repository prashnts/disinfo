from PIL import Image
from abc import ABCMeta, abstractmethod
from typing import Optional


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

    def reposition(self, x: int = 0, y: int = 0) -> 'Frame':
        # TODO: support extending the frame
        w = self.width
        h = self.height

        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        i.alpha_composite(self.image, (x, y))
        return Frame(i)

    def rotate(self, angle: float) -> 'Frame':
        return Frame(self.image.rotate(angle, expand=True))

class StillImage(Frame):
    def __init__(self, filename: str, resize: Optional[tuple[int, int]] = None):
        img = Image.open(filename).convert('RGBA')
        if resize:
            img = img.resize(resize)
        super().__init__(img)
