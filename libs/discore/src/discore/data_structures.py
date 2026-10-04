import os
import pendulum
import time

from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol
from PIL import Image
from lru import LRU


@dataclass(frozen=True)
class FrameState:
    tick: float
    now: pendulum.DateTime

    # Config of the screen being drawn. Read it only while drawing, never at import.
    config: Any = field(default=None, compare=False)
    rendererdata: Optional[dict] = None

    @classmethod
    def create(cls, config: Any = None, **kwargs):
        return cls(tick=time.time(), now=pendulum.now(tz='local'), config=config, **kwargs)


class Drawable(Protocol):
    def draw(self, fs: FrameState) -> Image.Image:
        ...


_scope = ContextVar('scope', default=None)

def current_scope():
    return _scope.get()

@contextmanager
def scope(name):
    '''Separates the animation state of each screen rendered by the process.'''
    token = _scope.set(name)
    try:
        yield
    finally:
        _scope.reset(token)


class UniqInstance(type):
    '''One instance per constructor args, for the whole process (services, connections).'''
    _instances = {}
    _lock = RLock()

    def _key(cls, args, kwargs):
        return (cls, args, tuple(kwargs.items()))

    def __call__(cls, *args, **kwargs):
        key = cls._key(args, kwargs)
        with UniqInstance._lock:
            if key not in cls._instances:
                cls._instances[key] = super().__call__(*args, **kwargs)
            return cls._instances[key]


class ScopedInstance(UniqInstance):
    '''Like UniqInstance but per screen scope, and evictable (animation state).'''
    _instances = LRU(2048)

    def _key(cls, args, kwargs):
        return (_scope.get(), cls, args, tuple(kwargs.items()))


def _after_fork():
    # Threads don't survive a fork (e.g. a PubSubManager listener), so children start fresh.
    UniqInstance._instances.clear()
    ScopedInstance._instances.clear()
    UniqInstance._lock = RLock()

os.register_at_fork(after_in_child=_after_fork)
