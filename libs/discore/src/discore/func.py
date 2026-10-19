import os
import sys


def uname(level: int = 4):
    # Named after the call site. Calls from the same line share it.
    finfo = ''
    f = sys._getframe(1)
    for _ in range(level - 1):
        if f is None:
            break
        finfo += f'<{f.f_code.co_name}@{f.f_lineno}!{os.path.basename(f.f_code.co_filename)}>'
        f = f.f_back
    return finfo
