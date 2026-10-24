from dataclasses import dataclass
from typing import Callable, Optional

from .data_structures import FrameState, ScopedInstance
from .elements import Frame
from .layers import div
from .transitions import Edges, FadeIn, SlideIn
from . import ease


# A slide: draws its frame when it's on screen, and how many seconds it stays.
Slide = tuple[Callable[[], Optional[Frame]], float]

@dataclass(frozen=True)
class SlidesStyle:
    width: Optional[int] = None
    height: Optional[int] = None
    radius: int = 0
    fade: float = 0.4
    # Slides in from this edge instead of fading, over the same time.
    edge: Optional[Edges] = None


class Slides(metaclass=ScopedInstance):
    '''Cycles through slides, each for its own time, fading between them.

    Only the slide on screen is drawn. Which one follows fs.tick, so there's
    no state to keep in sync. A fixed size keeps the card from resizing
    between slides. None in the list is skipped, for slides without content.
    '''

    def __init__(self, name: str, style: SlidesStyle = SlidesStyle()):
        self.name = name
        self.style = style
        self.slides: list[Slide] = []

    def mut(self, slides: list[Optional[Slide]]) -> 'Slides':
        self.slides = [s for s in slides if s]
        return self

    @property
    def duration(self) -> float:
        return sum(seconds for _, seconds in self.slides)

    def index(self, tick: float) -> int:
        t = tick % self.duration
        for i, (_, seconds) in enumerate(self.slides):
            if t < seconds:
                return i
            t -= seconds
        return len(self.slides) - 1

    def draw(self, fs: FrameState) -> Optional[Frame]:
        if not self.slides:
            return None
        i = self.index(fs.tick)
        frame = self.slides[i][0]() or Frame.fallback(('slides.empty', self.name))
        s = self.style
        # Tagged by position: the fade restarts on a new slide, not on each new frame of a live one.
        body = div(frame, width=s.width, height=s.height, anchor='tl', radius=s.radius).tag(('slides', self.name, i, len(self.slides)))
        if s.edge:
            return SlideIn(f'{self.name}.slide', s.fade, ease.cubic.cubic_out, edge=s.edge).mut(body).draw(fs)
        return FadeIn(f'{self.name}.fade', s.fade).mut(body).draw(fs)
