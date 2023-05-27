from typing import Optional

from .elements import Frame


class FrameCycler:
    def __init__(self, frames: Optional[list[Frame]] = None, delay: float = 1):
        self.frames = frames
        self.delay = delay
        self.last_step = 0
        self.current_frame = 0

    def _tick(self, step: float):
        if step - self.last_step >= self.delay:
            self.current_frame += 1
            self.current_frame %= len(self.frames)
            self.last_step = step

    def draw(self, step: float):
        self._tick(step)
        return self.frames[self.current_frame]
