from PIL import Image
from functools import cached_property

class SpriteIcon:
    # Renders animated sprites
    # Assumes the frames are vertically stacked and that its a square frame.

    def __init__(self, filename: str, anchor: tuple=(0, 0), step_time: float=1):
        self.anchor = anchor
        self.step_time = step_time
        self.current_frame = 0
        self.last_step = 0
        self.init_sprite(filename)

    def init_sprite(self, filename: str):
        img = Image.open(filename)
        self.filename = filename
        self.nframes = img.height // img.width
        self.sprite = img
        self._frames = []
        for i in range(self.nframes):
            croprect = (
                0,
                self.sprite.width * i,
                self.sprite.width,
                self.sprite.width * (i + 1),
            )
            self._frames.append(self.sprite.crop(croprect))

    def set_icon(self, filename: str):
        if filename == self.filename:
            return

        self.init_sprite(filename)
        self.current_frame = 0
        self.last_step = 0

    def draw(self, step: int, image: Image) -> Image:
        if (step - self.last_step) >= self.step_time:
            self.current_frame += 1
            self.current_frame %= self.nframes
            self.last_step = step

        frame = self._frames[self.current_frame]

        image.alpha_composite(frame, self.anchor)
        return image
