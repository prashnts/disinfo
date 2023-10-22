from PIL import Image
from typing import Literal, Optional

from disinfo.data_structures import FrameState, UniqInstance

from .elements import Frame
from .layouts import hstack, vstack, composite_at, place_at
from .text import TextStyle, text


Edges = Literal['top', 'bottom', 'left', 'right']

class FadeIn(metaclass=UniqInstance):
    def __init__(self, name: str, duration: float) -> None:
        self.name = name
        self.duration = duration
        self._prev_frame = None
        self._curr_frame = None

        self._last_step = 0
        self._alpha = 0

    def mut(self, frame: Frame) -> 'FadeIn':
        if self._curr_frame != frame:
            self._alpha = 0
        self._curr_frame = frame
        return self

    def _tick(self, step: float):
        slen = (self.duration) / 255
        if step - self._last_step >= slen:
            self._alpha += 0.05
            if self._alpha >= 1:
                self._alpha = 1
                self._prev_frame = self._curr_frame
                self._last_step = step

    def draw(self, fs: FrameState) -> Optional[Frame]:
        self._tick(fs.tick)
        i = Image.new('RGBA', self._curr_frame.size, (0, 0, 0, 0))
        if self._prev_frame:
            i.alpha_composite(self._prev_frame.image, (0, 0))
        # Draw the current frame with alpha.
        next_frame = Frame(Image.blend(i, self._curr_frame.image, self._alpha))
        return next_frame

class SlideIn(metaclass=UniqInstance):
    def __init__(self, name: str, duration: float, edge: Edges) -> None:
        self.name = name
        self.duration = duration
        self.edge = edge
        self._prev_frame = None
        self._curr_frame = None

        self._last_step = 0
        self._pos = 0

    def mut(self, frame: Frame) -> 'SlideIn':
        if self._curr_frame != frame:
            self._pos = 0
        self._curr_frame = frame
        return self

    @property
    def _max_pos(self):
        if self.edge in ['top', 'bottom']:
            return self._curr_frame.height
        else:
            return self._curr_frame.width

    @property
    def _slide_frame(self) -> Frame:
        if self._prev_frame:
            prev_frame = self._prev_frame
        else:
            img = Image.new('RGBA', self._curr_frame.size, (0, 0, 0, 0))
            prev_frame = Frame(img)

        if self.edge == 'top':
            return vstack([self._curr_frame, prev_frame])
        elif self.edge == 'bottom':
            return vstack([prev_frame, self._curr_frame])
        elif self.edge == 'left':
            return hstack([self._curr_frame, prev_frame])
        elif self.edge == 'right':
            return hstack([prev_frame, self._curr_frame])

    def _tick(self, step: float):
        slen = (self.duration) / self._max_pos
        if step - self._last_step >= slen:
            self._pos += 1
            if self._pos >= self._max_pos:
                self._pos = self._max_pos
                self._prev_frame = self._curr_frame
                self._last_step = step

    def draw(self, fs: FrameState) -> Optional[Frame]:
        self._tick(fs.tick)
        i = Image.new('RGBA', self._curr_frame.size, (0, 0, 0, 0))

        if self.edge == 'top':
            place_at(self._slide_frame, dest=i, x=0, y=self._pos, anchor='ml')
        elif self.edge == 'bottom':
            place_at(self._slide_frame, dest=i, x=0, y=-self._pos, anchor='tl')
        elif self.edge == 'left':
            place_at(self._slide_frame, dest=i, x=self._pos, y=0, anchor='tm')
        elif self.edge == 'right':
            place_at(self._slide_frame, dest=i, x=-self._pos, y=0, anchor='tl')

        next_frame = Frame(i)
        return next_frame


def text_slide_in(fs: FrameState, name: str, value: str, style: TextStyle = TextStyle(), edge: str = 'top', duration=0.01):
    frames = []
    for i, char in enumerate(value):
        slide = (SlideIn(f'txtslidein.{name}.{i}', duration=duration, edge=edge)
            .mut(text(char, style).tag(char))
            .draw(fs))
        frames.append(slide)
    return hstack(frames)


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
    >>  slider = VisibilitySlider(edge='top')

    In the draw function, use this call chain.
    >>  slider.set_frame(frame).visibility(True).draw(fs)

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
