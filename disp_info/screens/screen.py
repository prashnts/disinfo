import threading
import time

from typing import Optional
from ..components.elements import Frame
from ..data_structures import FrameState


def composer_thread(composer, sleepms: int = 1):
    current_state: Optional[FrameState] = None
    previous_state: Optional[FrameState] = None
    current_frame: Optional[Frame] = None

    def painter():
        nonlocal current_frame, previous_state
        while True:
            if current_state and current_state != previous_state:
                current_frame = composer(current_state)
                previous_state = current_state
            time.sleep(sleepms / 1000)

    t = threading.Thread(target=painter, daemon=True)
    t.start()

    def draw(fs: FrameState) -> Optional[Frame]:
        nonlocal current_state
        current_state = fs
        return current_frame

    return draw
