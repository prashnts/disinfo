import threading

from typing import Generic, TypeVar, Callable, Protocol

from discore.elements import Frame
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
        previous_state = None
        with scope(name):
            while True:
                with adaptive_delay(sleepms):
                    if p['args'] != previous_state:
                        p['frame'] = composer(*p['args'], **p['kwargs'])
                        previous_state = p['args']

    def draw(*args, **kwargs) -> Frame | None:
        name = current_scope()
        if name not in painters:
            painters[name] = p = {'args': args, 'kwargs': kwargs, 'frame': None}
            threading.Thread(target=painter, args=(name, p), daemon=False).start()
        p = painters[name]
        p['args'], p['kwargs'] = args, kwargs
        return p['frame']

    return draw
