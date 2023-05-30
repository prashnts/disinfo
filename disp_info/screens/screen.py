import threading
import time

from typing import Optional, Callable
from ..components.elements import Frame
from ..data_structures import FrameState


DrawerFn = Callable[[FrameState], Optional[Frame]]
ComposerFn = Callable[[FrameState], Optional[Frame]]

def composer_thread(composer: ComposerFn, sleepms: int = 1, after = None) -> DrawerFn:
    current_state: Optional[FrameState] = None
    previous_state: Optional[FrameState] = None
    current_frame: Optional[Frame] = None
    started: bool = False

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
        nonlocal current_state, started
        current_state = fs
        if not started and after:
            after()
        started = True
        return current_frame

    return draw
