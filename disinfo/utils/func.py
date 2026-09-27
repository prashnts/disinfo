import time

from discore.data_structures import current_scope


def throttle(duration: int):
    '''Throttles the execution of the decorated function.
    - duration: (milliseconds) during which func is cached.
    The cache is per screen scope, arguments are ignored.
    '''
    def decorator(func):
        duration_sec = duration / 1000.0
        last = {}   # scope -> (called_at, value)
        def wrapper(*args, **kwargs):
            key = current_scope()
            if key in last and (time.perf_counter() - last[key][0]) < duration_sec:
                return last[key][1]
            value = func(*args, **kwargs)
            last[key] = (time.perf_counter(), value)
            return value
        return wrapper

    return decorator
