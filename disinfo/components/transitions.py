import time

from PIL import Image
from typing import Literal, Optional

from disinfo.data_structures import FrameState, UniqInstance
from disinfo.utils import ease

from .elements import Frame
from .layouts import hstack, vstack, composite_at, place_at
from .text import TextStyle, text


Edges = Literal['top', 'bottom', 'left', 'right']

class TimedTransition(metaclass=UniqInstance):
    def __init__(self, name: str, duration: float, easing: ease.EasingFn = ease.linear.linear) -> None:
        self.name = name
        self.duration = duration
        self.easing_fn = easing

        self._prev_frame = None
        self._curr_frame = None

        self._last_step = time.time()
        self.pos = 0
        self._running = False

    def mut(self, frame: Frame) -> 'TimedTransition':
        if not frame:
            return self
        if self._curr_frame != frame:
            self.pos = 0
            self._running = True
        self._curr_frame = frame
        return self

    def tick(self, step: float):
        if not self._running:
            self._last_step = step
            return

        pos = (step - self._last_step) / self.duration
        pos = max(0, min(1, pos))
        self.pos = self.easing_fn(pos)

        if pos == 1:
            self.pos = 1
            self._last_step = step
            self._prev_frame = self._curr_frame
            self._running = False


class FadeIn(TimedTransition):
    def draw(self, fs: FrameState) -> Optional[Frame]:
        self.tick(fs.tick)
        i = Image.new('RGBA', self._curr_frame.size, (0, 0, 0, 0))
        composite_at(self._prev_frame, i, 'mm')
        return Frame(Image.blend(i, self._curr_frame.image, self.pos))

class SlideIn(TimedTransition):
    def __init__(
            self,
            name: str,
            duration: float,
            easing: ease.EasingFn = ease.linear.linear,
            edge: Edges = 'bottom') -> None:
        super().__init__(name, duration, easing)
        self.edge = edge

    @property
    def max_pos(self):
        if self.edge in ['top', 'bottom']:
            return self._curr_frame.height
        else:
            return self._curr_frame.width

    @property
    def slide_frame(self) -> Frame:
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

    def draw(self, fs: FrameState) -> Frame:
        self.tick(fs.tick)
        i = Image.new('RGBA', self._curr_frame.size, (0, 0, 0, 0))
        pos = int(self.max_pos * self.pos)

        if self.edge == 'top':
            place_at(self.slide_frame, dest=i, x=0, y=pos, anchor='ml')
        elif self.edge == 'bottom':
            place_at(self.slide_frame, dest=i, x=0, y=-pos, anchor='tl')
        elif self.edge == 'left':
            place_at(self.slide_frame, dest=i, x=pos, y=0, anchor='tm')
        elif self.edge == 'right':
            place_at(self.slide_frame, dest=i, x=-pos, y=0, anchor='tl')

        return Frame(i)


class NumberTransition(metaclass=UniqInstance):
    def __init__(self, name: str, duration: float, initial: float) -> None:
        self.name = name
        self.duration = duration

        self._prev_value = initial
        self._curr_value = None

        self._last_step = time.time()
        self.pos = 0
        self._running = False

    def mut(self, num: float) -> 'NumberTransition':
        if self._curr_value != num:
            self.pos = 0
            self._running = True
        self._curr_value = num
        return self

    def tick(self, step: float):
        if not self._running:
            self._last_step = step
            return

        factor = (step - self._last_step) / self.duration
        self.pos = factor

        if self.pos >= 1:
            self.pos = 1
            self._last_step = step
            self._prev_value = self._curr_value
            self._running = False

    def value(self, fs: FrameState) -> float:
        self.tick(fs.tick)
        return self._prev_value + (self._curr_value - self._prev_value) * self.pos


def text_slide_in(fs: FrameState, name: str, value: str, style: TextStyle = TextStyle(), edge: str = 'top', duration=0.3):
    frames = []
    for i, char in enumerate(value):
        slide = (SlideIn(f'txtslidein.{name}.{i}', duration=duration, edge=edge, easing=ease.sin.sin_out)
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
