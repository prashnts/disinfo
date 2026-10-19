import os
import sys


def uname(level: int = 4):
    # A name from where it's called: the caller and the frames above it, level - 1 of them.
    # Calls from the same lines share it (a loop, a helper used twice): give those a name.
    finfo = ''
    f = sys._getframe(1)
    for _ in range(level - 1):
        if f is None:
            break
        finfo += f'<{f.f_code.co_name}@{f.f_lineno}!{os.path.basename(f.f_code.co_filename)}>'
        f = f.f_back
    return finfo
