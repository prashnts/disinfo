from typing import Optional

from .elements import Frame
from disinfo.data_structures import FrameState, UniqInstance

class Stack(metaclass=UniqInstance):
    def __init__(self):
        pass

    def draw(self, fs: FrameState) -> Optional[Frame]:
        pass
