import time

from PIL import Image

from .elements import Frame

class _Scroller:
    def __init__(self,
        size: int,
        frame: Frame = None,
        delta: int = 1,
        speed: float = 0.01,
        static_if_small: bool = True):
        self.size = size
        self.delta = delta
        self.speed = speed
        self.pos = 0
        self.last_step = 0
        self.static_if_small = static_if_small
        if frame:
            self._init_scroller(frame, True)

    def set_frame(self, frame: Frame, reset: bool = True):
        self._init_scroller(frame, reset)

    def _init_scroller(self, frame: Frame, reset: bool):
        self.frame = self._get_frame(frame)
        if reset:
            self.pos = 0
            self.last_step = 0

    def _get_frame(self, frame: Frame) -> Frame:
        self._true_w = frame.width
        self._true_h = frame.height
        return frame

    def _get_crop_rect(self):
        raise NotImplemented

    def _get_image(self):
        raise NotImplemented

    def _tick(self, step: float = None):
        if not step:
            step = time.time()
        if (step - self.last_step) >= self.speed:
            self.pos += self.delta
            self.pos %= self.frame.width
            self.last_step = step

    def draw(self, step: float = None) -> Frame:
        self._tick(step)
        i = self._get_image()
        patch_img = self.frame.image.crop(self._get_crop_rect())
        i.alpha_composite(patch_img, (0, 0))
        return Frame(i)

class HScroller(_Scroller):
    def _get_crop_rect(self):
        # HACK!
        if self.static_if_small and self._true_w <= self.size:
            return (self.size, 0, self.frame.width, self.frame.height)

        xspan = self.pos + self.size
        return (
            self.pos,
            0,
            min(xspan, self.frame.width),
            self.frame.height,
        )

    def _get_image(self):
        return Image.new('RGBA', (self.size, self.frame.height))

    def _get_frame(self, frame: Frame) -> Frame:
        self._true_w = frame.width
        self._true_h = frame.height
        f = frame
        w = f.width + self.size
        i = Image.new('RGBA', (w, f.height), (0, 0, 0, 0))
        i.alpha_composite(f.image, (self.size, 0))
        return Frame(i)

class VScroller(_Scroller):
    def _get_crop_rect(self):
        if self.static_if_small and self._true_h <= self.size:
            return (0, self.size, self.frame.width, self.frame.height)

        yspan = self.pos + self.size
        return (
            0,
            self.pos,
            self.frame.width,
            min(yspan, self.frame.height),
        )

    def _get_image(self):
        return Image.new('RGBA', (self.frame.width, self.size))

    def _get_frame(self, frame: Frame) -> Frame:
        self._true_w = frame.width
        self._true_h = frame.height
        f = frame
        h = f.height + self.size
        i = Image.new('RGBA', (f.width, h), (0, 0, 0, 0))
        i.alpha_composite(f.image, (0, self.size))
        return Frame(i)
