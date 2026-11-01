import time
import threading

from typing import Generic, TypeVar, Callable, Protocol

from discore.elements import Frame, measuring, measuring_draw
from discore.data_structures import FrameState, scope, current_scope
from .time import adaptive_delay

T = TypeVar('T')

DrawerFn = Callable[[FrameState], Frame | None]
ComposerFn = Callable[[FrameState], Frame | None]


class DrawerFn(Protocol):
    def __call__(self, fs: FrameState) -> T | None:
        ...


def draw_loop(composer: ComposerFn, sleepms: int = 50, use_threads: bool = False) -> DrawerFn:
    '''Creates a daemon thread to executer composer function.

    The goal is not to gain in performance that much, rather it is to ensure
    all the composers are executed based on their own update frequency, and the
    main thread assembles the available frames. It is possible, and okay, that
    some outdated frames are rendered.

    Returns a function which returns the latest frame.
    Each screen scope gets its own thread and frame.
    '''
    if not use_threads:
        return composer

    painters = {}   # scope -> {'args', 'kwargs', 'frame'}

    def painter(name, p):
        previous_state, composed = None, 0.0
        with scope(name):
            while True:
                with adaptive_delay(sleepms):
                    # While its frame is shown; only measured (a lazy card out of view), every 5 s, to know its size.
                    now = time.monotonic()
                    shown = now - p['asked'] < 1
                    measured = now - p['measured'] < 1 and now - composed > 5
                    if p['args'] != previous_state and (shown or measured):
                        with measuring_draw(not shown):
                            p['frame'] = composer(*p['args'], **p['kwargs'])
                        previous_state, composed = p['args'], now

    def draw(*args, **kwargs) -> Frame | None:
        name = current_scope()
        if name not in painters:
            painters[name] = p = {'args': args, 'kwargs': kwargs, 'frame': None, 'asked': 0.0, 'measured': 0.0}
            threading.Thread(target=painter, args=(name, p), daemon=True).start()
        p = painters[name]
        p['args'], p['kwargs'] = args, kwargs
        p['measured' if measuring() else 'asked'] = time.monotonic()
        return p['frame']

    return draw
