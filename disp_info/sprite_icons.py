from PIL import Image
from functools import cached_property

from .components.elements import Frame


class SpriteImage:
    def __init__(self, filename: str, vertical_layout=True):
        self._init_sprites(filename)

    def _init_sprites(self, filename: str):
        img = Image.open(filename)
        self.nframes = img.height // img.width
        self.width = img.width
        self.height = img.width
        self._frames = []
        for i in range(self.nframes):
            croprect = (
                0,
                img.width * i,
                img.width,
                img.width * (i + 1),
            )
            self._frames.append(img.crop(croprect))

    def __getitem__(self, index) -> Frame:
        return Frame(self._frames[index])

class SpriteIcon:
    # Renders animated sprites
    # Assumes the frames are vertically stacked and that its a square frame.

    def __init__(self, filename: str, step_time: float = 1):
        self.step_time = step_time
        self.current_frame = 0
        self.last_step = 0
        self.init_sprite(filename)

    def init_sprite(self, filename: str):
        self.sprite = SpriteImage(filename)
        self.filename = filename
        self.nframes = self.sprite.nframes

    def set_icon(self, filename: str):
        if filename == self.filename:
            return

        self.init_sprite(filename)
        self.current_frame = 0
        self.last_step = 0

    def draw(self, step: float) -> Frame:
        if (step - self.last_step) >= self.step_time:
            self.current_frame += 1
            self.current_frame %= self.nframes
            self.last_step = step

        return self.sprite[self.current_frame]
