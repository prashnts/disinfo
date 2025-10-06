import time
from dataclasses import replace as dc_replace

from PIL import Image
from typing import Literal, Optional, TypeVar, Generic

from disinfo.data_structures import FrameState, UniqInstance
from disinfo.utils import ease

from .elements import Frame
from .layers import DivStyle, div
from .layouts import hstack, vstack, composite_at, place_at
from .text import TextStyle, text


Edges = Literal['top', 'bottom', 'left', 'right', 'flip-top']
TransitionValue = TypeVar('TransitionValue')


def ensure_unity_int(value: float) -> int:
    if value <= 1:
        return 1
    return int(value)


class TimedTransition(Generic[TransitionValue], metaclass=UniqInstance):
    '''A generic that transitions between pos 0 and 1 over a given duration.

    Transition triggers when TransitionValue changes. Once the transition
    completes, the previous value is set to the new value.
    '''

    def __init__(
            self,
            name: str,
            duration: float,
            easing: ease.EasingFn = ease.linear.linear,
            initial: Optional[TransitionValue] = None,
            reset_on_none: bool = False) -> None:
        self.name = name
        self.duration = duration
        self.easing_fn = easing
        self.reset_on_none = reset_on_none

        self.hash = (self.__class__.__name__, name, duration, easing)

        self.prev_value: Optional[TransitionValue] = initial
        self.curr_value: Optional[TransitionValue] = None

        self.last_step = time.time()
        self.pos = 0
        self.running = False
        self.finished = False

    def mut(self, value: TransitionValue) -> 'TimedTransition':
        if not value:
            return self

        if self.curr_value != value:
            self.pos = 0
            self.running = True
            self.finished = False
        self.curr_value = value
        return self

    def reset(self):
        self.pos = 0
        self.running = True
        self.finished = False
        self.last_step = time.time()
        return self

    def tick(self, step: float):
        if not self.running:
            self.last_step = step
            self.prev_value = self.curr_value
            return

        pos = (step - self.last_step) / self.duration
        pos = max(0, min(1, pos))
        self.pos = self.easing_fn(pos)

        if pos == 1:
            self.pos = 1
            self.last_step = step
            self.prev_value = self.curr_value
            self.running = False
            self.finished = True


class FadeIn(TimedTransition[Frame]):
    def draw(self, fs: FrameState) -> Optional[Frame]:
        self.tick(fs.tick)
        i = Image.new('RGBA', self.curr_value.size, (0, 0, 0, 0))
        composite_at(self.prev_value, i, 'mm')
        return Frame(Image.blend(i, self.curr_value.image, self.pos), hash=self.hash)

class ScaleIn(TimedTransition[Frame]):
    def draw(self, fs: FrameState) -> Optional[Frame]:
        self.tick(fs.tick)
        fw, fh = self.curr_value.size
        new_size = (ensure_unity_int(fw * self.pos), ensure_unity_int(fh * self.pos))
        if new_size[1] == 1 or new_size[0] == 1:
            return None
        return Frame(self.curr_value.image.resize(size=new_size), hash=self.hash)

class ScaleOut(TimedTransition[Frame]):
    def draw(self, fs: FrameState) -> Optional[Frame]:
        self.tick(fs.tick)
        fw, fh = self.curr_value.size
        new_size = (ensure_unity_int(fw * (1 - self.pos)), ensure_unity_int(fh * (1 - self.pos)))
        if new_size[1] == 1 or new_size[0] == 1:
            return None
        return Frame(self.curr_value.image.resize(size=new_size), hash=self.hash)

class SlideIn(TimedTransition[Frame]):
    def __init__(
            self,
            name: str,
            duration: float,
            easing: ease.EasingFn = ease.linear.linear,
            initial: Optional[Frame] = None,
            edge: Edges = 'bottom') -> None:
        super().__init__(name, duration, easing)
        self.edge = edge

    @property
    def max_pos(self):
        if self.edge in ['top', 'bottom']:
            return self.curr_value.height
        else:
            return self.curr_value.width

    @property
    def slide_frame(self) -> Frame:
        if self.prev_value:
            prev_frame = self.prev_value
        else:
            img = Image.new('RGBA', self.curr_value.size, (0, 0, 0, 0))
            prev_frame = Frame(img)

        if self.edge == 'top':
            return vstack([self.curr_value, prev_frame])
        elif self.edge == 'bottom':
            return vstack([prev_frame, self.curr_value])
        elif self.edge == 'left':
            return hstack([self.curr_value, prev_frame])
        elif self.edge == 'right':
            return hstack([prev_frame, self.curr_value])

    def draw(self, fs: FrameState) -> Frame:
        self.tick(fs.tick)
        i = Image.new('RGBA', self.curr_value.size, (0, 0, 0, 0))
        pos = int(self.max_pos * self.pos)

        if self.edge == 'top':
            place_at(self.slide_frame, dest=i, x=0, y=pos, anchor='ml')
        elif self.edge == 'bottom':
            place_at(self.slide_frame, dest=i, x=0, y=-pos, anchor='tl')
        elif self.edge == 'left':
            place_at(self.slide_frame, dest=i, x=pos, y=0, anchor='tm')
        elif self.edge == 'right':
            place_at(self.slide_frame, dest=i, x=-pos, y=0, anchor='tl')
        elif self.edge == 'flip-top':
            mid_y = self.curr_value.height // 2
            prev = self.prev_value if self.prev_value else Frame(Image.new('RGBA', self.curr_value.size, (0, 0, 0, 0)))
            top_curr = self.curr_value.image.crop((0, 0, self.curr_value.width, mid_y))
            bottom_curr = self.curr_value.image.crop((0, mid_y, self.curr_value.width, self.curr_value.height))
            top_prev = prev.image.crop((0, 0, prev.width, mid_y))
            bottom_prev = prev.image.crop((0, mid_y, prev.width, prev.height))
            line = Image.new('RGBA', (self.curr_value.width, 1), (0, 0, 0, 90))
            if self.pos <= 0.5:
                top_prev = top_prev.resize((top_prev.width, ensure_unity_int((self.pos * 2) * top_curr.height)))
                i.alpha_composite(top_curr, (0, 0))
                i.alpha_composite(bottom_prev, (0, mid_y))
                i.alpha_composite(top_prev, (0, mid_y - top_prev.height))
            else:
                bottom_curr = bottom_curr.resize((bottom_curr.width, ensure_unity_int(((self.pos - 0.5) * 2) * bottom_curr.height)))
                i.alpha_composite(top_curr, (0, 0))
                i.alpha_composite(bottom_prev, (0, mid_y))
                i.alpha_composite(bottom_curr, (0, mid_y))
                i.alpha_composite(line, (0, pos + 1))

        return Frame(i, hash=(*self.hash, self.edge))


class NumberTransition(TimedTransition[float]):
    def value(self, fs: FrameState) -> float:
        self.tick(fs.tick)
        return self.prev_value + (self.curr_value - self.prev_value) * self.pos


def text_slide_in(
    fs: FrameState,
    name: str,
    value: str,
    style=TextStyle(),
    edge='bottom',
    duration=0.25,
    easing=ease.linear.linear,
    div_style=None,
    together=False) -> Frame:
    frames: list[Frame] = []
    if together:
        slide = text(value, style)
        frames.append(slide)
    else:
        for i, char in enumerate(value):
            slide = text(char, style)
            # (SlideIn(f'txtslidein.{name}.{i}', duration=duration, edge=edge, easing=easing)
            #     .mut(text(char, style))
            #     .draw(fs))
            frames.append(slide)
    if div_style and frames:
        h = max(frames, key=lambda f: f.height).height
        padding = div_style.padding if isinstance(div_style.padding, tuple) else (div_style.padding,)*4
        for i, frame in enumerate(frames):
            diff = h - frame.height
            p_top = padding[0] + diff // 2
            p_bottom = padding[2] + diff - (diff // 2)
            div_style = dc_replace(div_style, padding=(p_top, padding[1], p_bottom, padding[3]))
            slide = div(frame, style=div_style)
            frames[i] = slide
    for i, frame in enumerate(frames):
        slide = (SlideIn(f'txtslidein.{name}.{i}', duration=duration, edge=edge, easing=easing)
                .mut(frame)
                .draw(fs))
        frames[i] = slide

    if edge == 'flip-top':
        for i, frame in enumerate(frames):
            line = Frame(Image.new('RGBA', (frame.width, 1), (0, 0, 0, 80)))
            frames[i] = composite_at(line, frame, 'mm')


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
