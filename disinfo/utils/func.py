import inspect
from pathlib import Path

from pydash import py_


def throttle(duration: int):
    '''Throttles the execution of the decorated function.
    - duration: (milliseconds) during which func is cached.
    '''
    def decorator(func):
        return py_.throttle(func, duration)

    return decorator


def uname(level: int = 4):
    finfo = ''
    for fi in inspect.stack()[1:level]:
        finfo += f'<{fi.function}@{fi.lineno}!{Path(fi.filename).name}>'
    return finfo