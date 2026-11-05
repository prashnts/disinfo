'''Malow's feeder: a chime on the buzzer as it drops the food, then her card a while, 'fed hh:mm'.'''
from collections import defaultdict
from datetime import timedelta
from dataclasses import replace as dc_replace

from discore.text import text, TextStyle
from discore.layouts import hstack, vstack
from discore.layers import div, shapes
from discore.data_structures import FrameState
from disinfo import fonts
from disinfo.web.telemetry import act
from disinfo.screens.twenty_two import cat, cat_step

MEALS = ['00:30', '08:30', '12:30', '16:30', '20:30']
DELAY = 10          # s after the minute turns: the machine drops it then
SHOW = 20 * 60      # s the card stays
LATE = 60           # s: a renderer (re)started later than that stays quiet
BUZZ = {'distudy'}  # the screens that chime

s_small = TextStyle(font=fonts.tamzen__rs, color='#DFD9C9')
s_time = TextStyle(font=fonts.tamzen__rs, color='#FFB000')
chimed = defaultdict(set)   # screen -> the meals it chimed for


def meal(fs: FrameState) -> tuple[str, float] | None:
    '''The meal served lately: (hh:mm, seconds since the food dropped).'''
    for m in MEALS:
        h, mi = map(int, m.split(':'))
        at = fs.now.replace(hour=h, minute=mi, second=DELAY, microsecond=0)
        for t in (at, at - timedelta(days=1)):
            since = (fs.now - t).total_seconds()
            if 0 <= since < SHOW:
                return m, since
    return None


def feeder_app(fs: FrameState):
    served = meal(fs)
    if not served:
        return None
    m, since = served
    name, key = fs.config.name, f'{fs.now.date()}.{m}'
    if name in BUZZ and key not in chimed[name] and since < LATE:
        act(fs, 'buzzer', 'feed', f'feed.{key}')
        chimed[name] = {key}
    # She runs the first minute, then sits.
    i = int(fs.tick / cat_step) if since < 60 else 0
    card = hstack([cat(i, 1), vstack([text('fed', s_small), text(m, s_time)], gap=1, align='center')], gap=2, align='center')
    return div(card, style=dc_replace(shapes.card, background='@scrim', padding=2))
