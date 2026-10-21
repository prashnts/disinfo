'''Material Design Icons, one svg at a time.

assets/mdi is the cache: an icon not there is downloaded once, in a thread, and saved
(check it in). Can't save (the image's assets are read-only), kept in memory instead.
'''
import re
import threading
import time
from functools import cache
from pathlib import Path

import requests

from discore.cairo import load_svg_string
from discore.elements import Frame

DIR = Path('assets/mdi')
URL = 'https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/{}.svg'
RETRY = 300         # s, after a failed download

_svgs: dict[str, str] = {}
_failed: dict[str, float] = {}
_pending: set[str] = set()


def _fetch(name: str):
    try:
        r = requests.get(URL.format(name), timeout=5)
        r.raise_for_status()
        try:
            (DIR / f'{name}.svg').write_text(r.text)
        except OSError as e:
            print(f'[mdi] {name}: not cached, {e}')
        _svgs[name] = r.text
    except Exception as e:
        print(f'[mdi] {name}: {e}')
        _failed[name] = time.time()
    finally:
        _pending.discard(name)

def svg(name: str) -> str | None:
    '''The icon's svg, None while it downloads (or can't).'''
    if name in _svgs:
        return _svgs[name]
    path = DIR / f'{name}.svg'
    if path.exists():
        _svgs[name] = path.read_text()
        return _svgs[name]
    if name not in _pending and time.time() - _failed.get(name, 0) > RETRY:
        _pending.add(name)
        threading.Thread(target=_fetch, args=(name,), daemon=True).start()
    return None

@cache
def _render(src: str, size: int, color: str) -> Frame:
    src = re.sub(r'<svg ', f'<svg width="{size}" height="{size}" ', src, count=1)
    return load_svg_string(src.replace('<path ', f'<path fill="{color}" '))

def icon(name: str | None, size: int, color: str = '#e0e0e0') -> Frame | None:
    '''The icon at size x size px, None until it's there.'''
    src = svg(name) if name else None
    return _render(src, size, color) if src else None
