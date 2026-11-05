import time

from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Union, Optional

from discore import clock


@contextmanager
def adaptive_delay(delay: Union[float, int]):
    if isinstance(delay, int):
        # interpret as milliseconds
        delay /= 1000
    t_start = time.perf_counter()
    try:
        yield
    finally:
        t_exec = time.perf_counter() - t_start
        t_delay = max(delay - t_exec, 0)
        time.sleep(t_delay)


def is_expired(
    dt: Union[str, datetime, None],
    seconds: int = 0,
    minutes: int = 0,
    microseconds: int = 0,
    now: Optional[datetime] = None,
    expired_if_none: bool = False,
):
    '''Checks if the given datetime has expired. Returns true if dt + delta <= now => dt has expired.'''
    if not dt:
        return expired_if_none
    dt = clock.parse(dt) if isinstance(dt, str) else clock.aware(dt)
    return dt + timedelta(seconds=seconds, minutes=minutes, microseconds=microseconds) <= (now or clock.now())
