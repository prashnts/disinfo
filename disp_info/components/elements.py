from PIL import Image
from abc import ABCMeta, abstractmethod


Postion = tuple[int, int]


class UIElement(metaclass=ABCMeta):
    width: int
    height: int
    image: Image

class Frame(UIElement):
    def __init__(self, image: Image):
        self.image = image
        self.width = image.width
        self.height = image.height