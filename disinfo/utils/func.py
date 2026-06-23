import inspect
import time
from pathlib import Path


def throttle(duration: int):
    '''Throttles the execution of the decorated function.
    - duration: (milliseconds) during which func is cached.
    '''
    def decorator(func):
        last_called_at = 0
        duration_sec = duration / 1000.0
        last_value = None
        def wrapper(*args, **kwargs):
            nonlocal last_called_at, last_value
            if last_called_at and (time.monotonic() - last_called_at) < duration_sec:
                return last_value
            last_value = func(*args, **kwargs)
            last_called_at = time.monotonic()
            return last_value
        return wrapper

    return decorator


def uname(level: int = 4):
    finfo = ''
    for fi in inspect.stack(context=0)[1:level]:
        finfo += f'<{fi.function}@{fi.lineno}!{Path(fi.filename).name}>'
    return finfo