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

    def set_icon(self, filename: str):
        if filename == self.filename:
            return

        self.init_sprite(filename)
        self.current_frame = 0
        self.last_step = 0

    def get_frame(self, frame: int = 0) -> Image:
        # make a crop rectangle in original image for the frame.
        croprect = (
            0,
            self.sprite.width * frame,
            self.sprite.width,
            self.sprite.width * (frame + 1),
        )
        return self.sprite.crop(croprect)

    def draw(self, step: int, image: Image) -> Image:
        if (step - self.last_step) >= self.step_time:
            self.current_frame += 1
            self.current_frame %= self.nframes
            self.last_step = step

        frame = self.get_frame(self.current_frame)

        image.alpha_composite(frame, self.anchor)
        return image
