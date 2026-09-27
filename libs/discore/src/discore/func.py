import inspect
from pathlib import Path


def uname(level: int = 4):
    finfo = ''
    for fi in inspect.stack(context=0)[1:level]:
        finfo += f'<{fi.function}@{fi.lineno}!{Path(fi.filename).name}>'
    return finfo