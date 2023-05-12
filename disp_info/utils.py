from pydash import py_

def throttle(duration: int):
    def decorator(func):
        return py_.throttle(func, duration)

    return decorator
