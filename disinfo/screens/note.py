'''A note at the bottom of a screen, for a while: Redis di.note.<screen> (or di.note.all), with a TTL.

Plain text, lines split on '|'. Or JSON {"t0": <epoch>, "steps": [[seconds, "text"], ...]}: the step due now, with its
countdown; before t0 the title and the countdown to the start, after the last step `done` till the key expires.
Set from the web page (view tab), POST /note, or here:
    python -m disinfo.screens.note distudy 'lean in|to the screen' --min 5
    python -m disinfo.screens.note distudy --steps steps.json --start 60     # [[20, "sit"], [15, "lean in"]]
    python -m disinfo.screens.note distudy --clear
'''
import json
import time
from functools import lru_cache

from discore.text import text, TextStyle
from discore.layouts import vstack
from discore.layers import div, DivStyle
from discore.data_structures import FrameState
from disinfo import fonts

_note = {}      # screen -> (looked at, value)
s_line = TextStyle(font=fonts.tamzen__rs, color='#DFD9C9')
s_count = TextStyle(font=fonts.tamzen__rs, color='#FFB000')


def key(screen: str) -> str:
    return f'di.note.{screen}'


def put(screen: str, value: str | None, seconds: int = 600):
    '''screen 'all': every screen, under their own notes. None clears it.'''
    from disinfo.redis import db
    if value:
        db.set(key(screen), value, ex=max(int(seconds), 1))
    else:
        db.delete(key(screen))


def steps(items: list, start: float = 0, title: str = 'starts in', done: str = 'done, thanks!') -> tuple[str, int]:
    '''A timed note: the value and how long it stays (the steps, then a minute for `done`).'''
    t0 = time.time() + start
    return json.dumps({'t0': t0, 'title': title, 'done': done, 'steps': items}), int(start + sum(s for s, _ in items) + 60)


def notes() -> dict:
    from disinfo.redis import db
    out = {}
    for k in db.scan_iter('di.note.*'):
        k = k.decode() if isinstance(k, bytes) else k
        v = db.get(k)
        out[k.removeprefix('di.note.')] = {'value': v.decode() if isinstance(v, bytes) else v, 'ttl': db.ttl(k)}
    return out


def _read(name: str) -> str | None:
    now = time.monotonic()
    seen, value = _note.get(name, (-99, None))
    if now - seen > 2:
        try:
            from disinfo.redis import db
            value = db.get(key(name)) or db.get(key('all'))
            value = value.decode() if isinstance(value, bytes) else value
        except Exception:
            value = None
        _note[name] = now, value
    return value


def _lines(value: str) -> tuple[tuple[str, ...], str | None]:
    if not value.startswith('{'):
        return tuple(value.split('|')), None
    note = json.loads(value)
    left = note['t0'] - time.time()
    if left > 0:
        return tuple(note.get('title', 'starts in').split('|')), f'{left:.0f}s'
    for seconds, line in note['steps']:
        left += seconds
        if left > 0:
            return tuple(line.split('|')), f'{left:.0f}s'
    return tuple(note.get('done', 'done, thanks!').split('|')), None


@lru_cache(maxsize=8)
def _render(lines: tuple[str, ...], count: str | None):
    rows = [text(l, s_line) for l in lines]
    if count:
        rows.append(text(count, s_count))
    return div(vstack(rows, gap=1, align='center'),
               style=DivStyle(background='#000000D0', border=1, border_color='#FFB000', radius=2, padding=2))


def draw(fs: FrameState):
    value = _read(fs.config.name)
    if not value:
        return None
    try:
        return _render(*_lines(value))
    except Exception:
        return None


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='A note at the bottom of a screen.')
    p.add_argument('screen', help="distudy, disalon, dientry, di_pcstate or all")
    p.add_argument('text', nargs='?', help="'|' breaks lines")
    p.add_argument('--min', type=float, default=10, help='how long (plain text)')
    p.add_argument('--steps', help='a JSON file: [[seconds, "text"], ...]')
    p.add_argument('--start', type=float, default=0, help='seconds before the first step')
    p.add_argument('--clear', action='store_true')
    a = p.parse_args()
    if a.clear:
        put(a.screen, None)
    elif a.steps:
        put(a.screen, *steps(json.load(open(a.steps)), a.start))
    else:
        put(a.screen, a.text, a.min * 60)
    print(json.dumps(notes(), indent=1))
