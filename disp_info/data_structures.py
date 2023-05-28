import pendulum
import time

from dataclasses import dataclass
from typing import Optional

@dataclass
class FrameState:
    tick: float
    now: pendulum.DateTime

    rendererdata: Optional[dict] = None

    @classmethod
    def create(cls):
        return cls(tick=time.time(), now=pendulum.now())
