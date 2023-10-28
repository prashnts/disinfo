from typing import Callable

from .import bounce, exp, linear, cubic, circle

EasingFn = Callable[[float], float]

__all__ = [
    'EasingFn',
    'bounce',
    'exp',
    'linear',
    'cubic',
    'circle',
]
