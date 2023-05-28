import pendulum
import time

from dataclasses import dataclass

@dataclass
class FrameState:
    tick: float
    now: pendulum.DateTime

    @classmethod
    def create(cls):
        return cls(tick=time.time(), now=pendulum.now())
