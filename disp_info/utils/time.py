import time

from contextlib import contextmanager
from typing import Union


@contextmanager
def adaptive_delay(delay: Union[float, int]):
    if isinstance(delay, int):
        # interpret as milliseconds
        delay /= 1000
    t_start = time.monotonic()
    try:
        yield
    finally:
        t_exec = time.monotonic() - t_start
        t_delay = max(delay - t_exec, 0)
        time.sleep(t_delay)
