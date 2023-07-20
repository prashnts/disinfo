import pendulum
import time

from dataclasses import dataclass
from pydantic import BaseModel
from typing import Optional, Protocol
from PIL import Image


class AppBaseModel(BaseModel):
    def __hash__(self):
        return hash((type(self),) + tuple(self.__dict__.values()))

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
