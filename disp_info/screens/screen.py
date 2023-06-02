import threading

from typing import Optional, Callable

from ..components.elements import Frame
from ..data_structures import FrameState
from ..utils.time import adaptive_delay


DrawerFn = Callable[[FrameState], Optional[Frame]]
ComposerFn = Callable[[FrameState], Optional[Frame]]


def composer_thread(composer: ComposerFn, sleepms: int = 1, use_threads: bool = False) -> DrawerFn:
    '''Creates a daemon thread to executer composer function.

    The goal is not to gain in performance that much, rather it is to ensure
    all the composers are executed based on their own update frequency, and the
    main thread assembles the available frames. It is possible, and okay, that
    some outdated frames are rendered.

    Returns a function which returns the latest frame.

    NOTE: I've disabled the threads for the time being. I notice similar performance
    (if not better)
    '''
    current_state: Optional[FrameState] = None
    previous_state: Optional[FrameState] = None
    current_frame: Optional[Frame] = None

    if not use_threads:
        return composer

    def painter():
        nonlocal current_frame, previous_state
        while True:
            with adaptive_delay(sleepms):
                if current_state and current_state != previous_state:
                    current_frame = composer(current_state)
                    previous_state = current_state

    t = threading.Thread(target=painter, daemon=True)
    t.start()

    def draw(fs: FrameState) -> Optional[Frame]:
        nonlocal current_state
        current_state = fs
        return current_frame

    return draw
