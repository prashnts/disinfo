'''The day's cigarettes in the study, from its PM2.5: each one a burst of spikes by the sensor (the puffs), back to
clean air in ~10 min. One starts on a jump from clean air and ends once the air has stayed clean a while; a longer
session (friends over, one after the other) counts one more each each_s. The neighbour's smoke comes in too: an
estimate, the asterisk says so.

On the desk while its smoker is home alone, up to 8+. The web page has the number (the ✱ button).
'''
import json
import math
import time
import datetime as dt

import requests
from PIL import Image

from disinfo import fonts
from disinfo.config import app_config
from disinfo.redis import db
from discore.elements import Frame
from discore.layers import div, DivStyle
from discore.layouts import hstack
from discore.text import TextStyle, text
from discore.widget import Widget
from discore.data_structures import FrameState
from .colors import gray, light_gray
from .aviator import daylight

KEY = 'di.smokes'
onset = 100         # µg/m³, a jump to this from clean air: one lit
quiet = 60          # clean again below this,
calm_s = 300        # for this long: it's over
each_s = 1200       # a longer session: one more each 20 min
most = 8            # then 8+
ember = '#e8a25c'
ember_red = '#e2553a'
paper = '#b9babf'
filter_color = '#a8743f'
s_count = TextStyle(font=fonts.tamzen__rs, color=light_gray.hex)


def history(entity: str, since: dt.datetime) -> list[tuple[float, float]]:
    headers = {'Authorization': f'Bearer {app_config.ha_token.get_secret_value()}'}
    r = requests.get(f'{app_config.ha_base_url}/api/history/period/{since.isoformat()}', headers=headers, timeout=60, params={
        'end_time': dt.datetime.now(dt.timezone.utc).isoformat(), 'filter_entity_id': entity, 'minimal_response': '1', 'no_attributes': '1'})
    out = []
    for s in r.json():
        for x in s:
            try:
                out.append((dt.datetime.fromisoformat(x['last_changed']).timestamp(), float(x['state'])))
            except ValueError:
                pass
    return sorted(out)

def sessions(pts: list[tuple[float, float]]) -> list[list]:
    '''[start, end] of each, end None while it goes on.'''
    out, start, low = [], None, None
    for t, v in pts:
        if start is None:
            if v >= onset:
                start, low = t, None
        elif v < quiet:
            low = low or t
            if t - low >= calm_s:
                out.append([start, low])
                start = None
        else:
            low = None
    if start is not None:
        out.append([start, None])
    return out

def count(ss: list[list], now: float) -> int:
    return sum(max(1, math.ceil(((end or now) - start) / each_s)) for start, end in ss)

def task():
    now = time.time()
    midnight = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    ss = sessions(history(app_config.smokes_pm25, midnight))
    db.set(KEY, json.dumps({'at': now, 'day': midnight.date().isoformat(), 'count': count(ss, now), 'sessions': ss}), ex=86400)

def doc() -> dict | None:
    '''Today's; None if it's stale (the data service down) or yesterday's.'''
    d = daylight.read(KEY)
    today = dt.date.today().isoformat()
    return d if d and d['day'] == today and time.time() - d['at'] < 900 else None

def alone() -> bool:
    from disinfo.utils.hass import get_entity
    state = lambda e: getattr(get_entity(e), 'state', None)
    return bool(app_config.smokes_home) and state(app_config.smokes_home) == 'home' and all(state(e) != 'home' for e in app_config.smokes_away)

def rgb(color: str) -> tuple:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))

def cigarette() -> Frame:
    # 10x5: the filter, the paper, the ember, a wisp over it.
    im = Image.new('RGBA', (10, 5))
    for x in range(10):
        c = filter_color if x < 3 else ember_red if x == 9 else paper
        for y in (3, 4):
            im.putpixel((x, y), (*rgb(c), 255))
    for x, y, a in [(9, 2, 60), (8, 1, 90), (9, 0, 50)]:
        im.putpixel((x, y), (*rgb(paper), a))
    return Frame(im, ('smokes.cigarette',))

def asterisk(color: str) -> Frame:
    # Six arms, 5x5, the tips a little dimmer.
    im = Image.new('RGBA', (5, 5))
    c = rgb(color)
    for x, y in [(2, 1), (1, 2), (2, 2), (3, 2), (2, 3)]:
        im.putpixel((x, y), (*c, 255))
    for x, y in [(2, 0), (0, 1), (4, 1), (0, 3), (4, 3), (2, 4)]:
        im.putpixel((x, y), (*c, 170))
    return Frame(im, ('smokes.asterisk', color))

_asterisk = asterisk(ember)
_cigarette = cigarette()

def composer(fs: FrameState):
    if fs.config.name not in app_config.smokes_screens or not (d := doc()) or not d['count'] or not alone():
        return None
    n = d['count']
    return div(
        hstack([
            _cigarette,
            hstack([text(f'{n}' if n < most else f'{most}+', s_count), _asterisk], gap=1, align='top'),
        ], gap=2, align='center'),
        style=DivStyle(padding=1, radius=1, background=gray.darken(0.7).hex)
    ).tag('smokes')

def widget(fs: FrameState):
    return Widget('smokes', composer(fs), priority=0.3)
