from PIL import Image
from functools import cached_property

from .elements import Frame


class SpriteImage:
    def __init__(self, filename: str, resize: tuple[int, int] = None):
        self.resize = resize
        self._init_sprites(filename)
        self._init_frames()

    def _init_sprites(self, filename: str):
        img = Image.open(filename).convert('RGBA')
        self.filename = filename
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
    
    def _init_frames(self):
        resize = self.resize if self.resize else (self.width, self.height)
        hash_ = (self.__class__.__name__, self.filename, resize)
        self._frames = [Frame(f, hash=hash_).resize(resize, ratio_fn=max, pixel=True) for f in self._frames]

    def __getitem__(self, index) -> Frame:
        return self._frames[index % self.nframes]

class GifImage(SpriteImage):
    def _init_sprites(self, filename: str):
        img = Image.open(filename).convert('RGBA')
        frames = []
        with Image.open(filename) as img:
            try:
                while True:
                    # Copy the current frame (otherwise it will be modified by next loop)
                    frame = img.copy().convert('RGBA')
                    frames.append(frame)

                    # Advance to next frame
                    img.seek(len(frames))

            except EOFError:
                # End of GIF sequence
                pass
        
        self.filename = filename
        self.nframes = len(frames)
        self.width = frames[0].width
        self.height = frames[0].height
        self._frames = frames

class SpriteIcon:
    # Renders animated sprites
    # Assumes the frames are vertically stacked and that its a square frame.

    def __init__(self, filename: str, step_time: float = 1, resize: tuple[int, int] = None):
        self.step_time = step_time
        self.current_frame = 0
        self.last_step = 0
        self.init_sprite(filename, resize)

    def init_sprite(self, filename: str, resize: tuple[int, int] = None):
        if filename.lower().endswith('.gif'):
            self.sprite = GifImage(filename, resize=resize)
        else:
            self.sprite = SpriteImage(filename, resize=resize)
        self.filename = filename
        self.nframes = self.sprite.nframes

    def set_icon(self, filename: str):
        if filename == self.filename:
            return self

        self.init_sprite(filename)
        self.current_frame = 0
        self.last_step = 0
        return self

    def draw(self, step: float) -> Frame:
        if (step - self.last_step) >= self.step_time:
            self.current_frame += 1
            self.current_frame %= self.nframes
            self.last_step = step

        return self.sprite[self.current_frame]
