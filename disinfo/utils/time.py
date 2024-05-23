import time
import pendulum

from datetime import datetime
from contextlib import contextmanager
from typing import Union, Optional


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


def is_expired(
    dt: Union[str, pendulum.DateTime, datetime, None],
    seconds: int = 0,
    minutes: int = 0,
    microseconds: int = 0,
    now: Optional[pendulum.DateTime] = None,
    expired_if_none: bool = False,
):
    '''Checks if the given datetime has expired. Returns true if dt + delta <= now => dt has expired.'''
    if not dt:
        return expired_if_none
    if not now:
        now = pendulum.now()
    if isinstance(dt, str):
        dt = pendulum.parse(dt)
    if isinstance(dt, datetime):
        dt = pendulum.instance(dt)
    return dt.add(seconds=seconds, minutes=minutes, microseconds=microseconds) <= now
