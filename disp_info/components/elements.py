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

class StillImage(Frame):
    def __init__(self, filename: str):
        img = Image.open(filename)
        super().__init__(img)
