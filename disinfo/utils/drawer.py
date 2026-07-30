import threading

from typing import Generic, TypeVar, Callable, Protocol

from ..components.elements import Frame
from ..data_structures import FrameState
from .time import adaptive_delay

T = TypeVar('T')

DrawerFn = Callable[[FrameState], Frame | None]
ComposerFn = Callable[[FrameState], Frame | None]


class DrawerFn(Protocol):
    def __call__(self, fs: FrameState) -> T | None:
        ...


def draw_loop(composer: ComposerFn, sleepms: int = 82, use_threads: bool = False) -> DrawerFn:
    '''Creates a daemon thread to executer composer function.

    The goal is not to gain in performance that much, rather it is to ensure
    all the composers are executed based on their own update frequency, and the
    main thread assembles the available frames. It is possible, and okay, that
    some outdated frames are rendered.

    Returns a function which returns the latest frame.
    '''
    current_args: tuple | None = None
    current_kwargs: dict | None = dict()
    previous_state: FrameState | None = None
    current_frame: Frame | None = None

    if not use_threads:
        return composer

    def painter():
        nonlocal current_frame, previous_state
        while True:
            with adaptive_delay(sleepms):
                if current_args and current_args != previous_state:
                    current_frame = composer(*current_args, **current_kwargs)
                    previous_state = current_args

    t = threading.Thread(target=painter, daemon=True)

    def draw(*args, **kwargs) -> Frame | None:
        if not t.is_alive():
            t.start()

        nonlocal current_args, current_kwargs
        current_args = args
        current_kwargs = kwargs
        return current_frame

    return draw
