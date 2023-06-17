import pendulum
import time

from dataclasses import dataclass
from typing import Optional, Protocol
from PIL import Image


@dataclass
class FrameState:
    tick: float
    now: pendulum.DateTime

    rendererdata: Optional[dict] = None

    # Global state for button inputs
    rmt0_action: Optional[str] = None
    rmt1_action: Optional[str] = None

    @classmethod
    def create(cls):
        return cls(tick=time.time(), now=pendulum.now())


class Drawable(Protocol):
    def draw(self, fs: FrameState) -> Image.Image:
        ...
