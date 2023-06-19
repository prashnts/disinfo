from pydash import py_


def throttle(duration: int):
    '''Throttles the execution of the decorated function.
    - duration: (milliseconds) during which func is cached.
    '''
    def decorator(func):
        return py_.throttle(func, duration)

    return decorator
