from PIL import Image
from typing import Literal, Optional

from .elements import Frame


Edges = Literal['top', 'bottom', 'left', 'right']


class VisibilitySlider:
    '''
    Visibility state manager with slide transition.

    This wrapper can be used to transition in or out a Frame.
    Pick one of the four edges and a duration.
    Live frames are supported.
    Frames that change dimensions are generally supported but support is
    currenlty buggy.

    Usage:

    Initialize a static manager:
    >>> slider = VisibilitySlider(edge='top')

    In the draw function, use this call chain.
    >>> slider.set_frame(frame).visibility(True).draw(fs)

    When visibility sets to False, slide out effect occurs.
    '''
    def __init__(self, frame: Optional[Frame] = None, edge: Edges = 'bottom', duration: float = 0.5):
        self.frame = frame
        self.edge = edge
        self.duration = duration

        self.pos = 0
        self.visible = True
        self.last_step = 0
        self.direction = 1

    def visibility(self, visible: bool):
        if self.visible != visible:
            self.direction = -1 if not visible else 1
            self.visible = visible
        return self

    def set_frame(self, frame: Frame):
        self.frame = frame
        if self.direction > 0 and self.pos > self._max_pos:
            self.pos = self._max_pos
        return self

    def _get_crop_rect(self):
        w = self.frame.width
        h = self.frame.height

        if self.edge == 'bottom':
            return (0, 0, w, h)
        elif self.edge == 'top':
            return (0, h - self.pos, w, h)
        elif self.edge == 'left':
            return (w - self.pos, 0, w, h)
        elif self.edge == 'right':
            return (0, 0, w, h)

    def _get_origin(self):
        w = self.frame.width
        h = self.frame.height
        if self.edge in ['top', 'left']:
            return (0, 0)
        elif self.edge == 'bottom':
            return (0, h - self.pos)
        elif self.edge == 'right':
            return (w - self.pos, 0)

    @property
    def _max_pos(self):
        if self.edge in ['top', 'bottom']:
            return self.frame.height
        else:
            return self.frame.width

    def _tick(self, step: float):
        max_pos = self._max_pos

        ssize = max_pos / (self.duration / (step - self.last_step))
        ssize = int(ssize)

        if step - self.last_step >= (self.duration / max_pos):
            if 0 <= self.pos <= max_pos:
                if self.direction > 0:
                    self.pos += ssize
                else:
                    self.pos -= ssize
                # Bounds check.
                self.pos = max(min(max_pos, self.pos), 0)

            self.last_step = step

    def draw(self, step: float) -> Optional[Frame]:
        if not self.frame:
            return

        self._tick(step)
        w = self.frame.width
        h = self.frame.height

        i = Image.new('RGBA', (w, h), (0, 0, 0, 0))

        patch = self.frame.image.crop(self._get_crop_rect())
        i.alpha_composite(patch, self._get_origin())

        return Frame(i)
