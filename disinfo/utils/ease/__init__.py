from typing import Callable

from .linear import linear as ease_linear
from .exp import exp_in as ease_exp_in, exp_out as ease_exp_out, exp_in_out as ease_exp_in_out
from .bounce import bounce_in as ease_bounce_in, bounce_out as ease_bounce_out, bounce_in_out as ease_bounce_in_out

from .import bounce, exp, linear, cubic

EasingFn = Callable[[float], float]

__all__ = [
    'ease_linear',
    'ease_exp_in', 'ease_exp_out', 'ease_exp_in_out',
    'ease_bounce_in', 'ease_bounce_out', 'ease_bounce_in_out',
    'EasingFn',
]
