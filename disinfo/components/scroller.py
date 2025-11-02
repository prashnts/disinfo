import bisect
import math

from PIL import Image
from typing import Optional

from disinfo.components.elements import Frame
from disinfo.components.layers import rounded_rectangle

class Scroller:
    _horizontal: bool = False
    _vertical: bool = False

    def __init__(self,
        size: int,
        frame: Optional[Frame] = None,
        delta: int = 1,
        speed: float = 0.01,
        static_if_small: bool = True,
        pause_at_loop: bool = False,
        pause_duration: float = 2,
        pause_offset: int = 5,
        scrollbar: bool = False,
    ):
        self.size = size
        self.delta = delta
        self.speed = speed
        self.pos = 0
        self.direction = 1
        self.last_step = 0
        self.static_if_small = static_if_small
        self.pauses = []
        self.pause_at_loop = pause_at_loop
        self.pause_duration = pause_duration
        self.target = None
        self.on_target = False
        self.scrollbar = scrollbar
        self.pause_offset = pause_offset
        self._last_target = 0
        if frame:
            self._init_scroller(frame, True)

    def set_frame(self, frame: Frame, reset: bool = False, pauses: Optional[list[int]] = None, pause_offset: Optional[int] = None):
        self._init_scroller(frame, reset)
        if pauses is not None:
            self.pauses = [p + self.size for p in pauses]
        if pause_offset is not None:
            self.pause_offset = pause_offset
        return self

    def set_target(self, target: int):
        self.target = target
        return self

    def set_size(self, size: int):
        if self.size == size:
            return self

        self.size = size
        if self.frame:
            self._init_scroller(self.frame, reset=True)
        return self
    
    def set_delta(self, delta: int):
        self.delta = delta
        return self

    def reset_position(self):
        self.pos = 0
        return self

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

    def _get_frame_size(self):
        raise NotImplemented
    
    def _get_scrollbar(self):
        raise NotImplemented

    def _tick(self, step: float):
        delta = step - self.last_step
        prev_pos = self.pos

        if self.pauses:
            try:
                pause_point = bisect.bisect(self.pauses, self.pos + self.pause_offset)
                target = self.pauses[pause_point + 1]
                if target != self._last_target:
                    self.target = target

                    if delta < self.pause_duration:
                        return

                    self._last_target = target
            except IndexError:
                self.target = None

        if all([
            self.pause_at_loop,
            self.pos == self.size,
            delta < self.pause_duration,
        ]):
            # We insert a pause by not incrementing position.
            return
        if delta >= self.speed:
            if self.target is not None:
                if abs(self.pos - self.target) <= self.delta:
                    self.pos = self.target
                elif self.pos < self.target:
                    self.pos += self.delta
                elif self.pos > self.target:
                    self.pos -= self.delta
                else:
                    self.pos = self.target
                self.on_target = False
                if self.pos == self.target:
                    self.on_target = True
            else:
                self.pos += self.delta
            self.pos %= self._get_frame_size()
            self.last_step = step
        self.direction = 0 if prev_pos == self.pos else math.copysign(1, self.pos - prev_pos)

    def draw(self, step: float) -> Frame:
        self._tick(step)
        i = self._get_image()
        patch_img = self.frame.image.crop(self._get_crop_rect())
        i.alpha_composite(patch_img, (0, 0))
        if self.scrollbar:
            ratio = self._get_scroll_ratio()
            thumb = self._get_scrollbar_thumb(5)
            pos = self.pos // (ratio if ratio > 0 else 5)
            if self._vertical:
                i.alpha_composite(thumb, (i.width - thumb.width, pos))
            if self._horizontal:
                i.alpha_composite(thumb, (pos, i.height - thumb.height))
        return Frame(i, hash=(self.__class__.__name__, self.size, self.frame))

class HScroller(Scroller):
    _horizontal = True

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

    def _get_scroll_ratio(self):
        return self._true_w // self.size

    def _get_scrollbar_thumb(self, size: int):
        return rounded_rectangle(
            width=size,
            height=3,
            radius=(1,)*4,
            fill='#ffffff88',
            border=0,
            border_color='#00000000')

    def _get_frame_size(self):
        return self.frame.width

    def _get_frame(self, frame: Frame) -> Frame:
        self._true_w = frame.width
        self._true_h = frame.height
        f = frame
        w = f.width + self.size
        i = Image.new('RGBA', (w, f.height), (0, 0, 0, 0))
        i.alpha_composite(f.image, (self.size, 0))
        return Frame(i)

class VScroller(Scroller):
    _vertical = True

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
    
    def _get_scroll_ratio(self):
        return self._true_h // self.size

    def _get_scrollbar_thumb(self, size: int):
        return rounded_rectangle(
            width=3,
            height=size,
            radius=(1,)*4,
            fill='#ffffff44',
            border=0,
            border_color='#00000000')

    def _get_frame_size(self):
        return self.frame.height

    def _get_frame(self, frame: Frame) -> Frame:
        self._true_w = frame.width
        self._true_h = frame.height
        f = frame
        h = f.height + self.size
        i = Image.new('RGBA', (f.width, h), (0, 0, 0, 0))
        i.alpha_composite(f.image, (0, self.size))
        return Frame(i)
