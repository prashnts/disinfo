import arrow

from datetime import timedelta

from .drawer import draw_loop
from .colors import gray
from ..components import fonts
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.text import text, TextStyle
from ..redis import rkeys, get_dict
from ..utils.func import throttle
from ..data_structures import FrameState

trash_bin_green = StillImage('assets/raster/trash-bin-green-10x14.png')
trash_bin_yellow = StillImage('assets/raster/trash-bin-yellow-10x14.png')

WARNING_THRESHOLD = 1.7
SCHEDULE = [
    {
        'type': 'green',
        'label': '1',
        'label_color': '#fff',
        'color': '#42a459',
        'icon': StillImage('assets/raster/trash-bin-green-10x14.png'),
        'days': [0, 1, 2, 3, 4, 5, 6],
    },
    {
        'type': 'yellow',
        'label': '2',
        'label_color': '#000',
        'color': '#f8f644',
        'icon': StillImage('assets/raster/trash-bin-yellow-10x14.png'),
        'days': [1, 2, 4, 6],
    },
    {
        'type': 'white',
        'label': '3',
        'label_color': '#000',
        'color': '#fff',
        'icon': StillImage('assets/raster/trash-bin-white-10x14.png'),
        'days': [1, 3],
    },
]

def todays_trash_schedule(fs: FrameState):
    today = fs.now.day_of_week
    sch = [s for s in SCHEDULE if today in s['days']]
    for s in SCHEDULE:
        yield s['icon'].opacity(0.6 if today not in s['days'] else 1)
        # yield div(
        #     text(s['label'], style=TextStyle(font=fonts.bitocra7, color=s['label_color'])),
        #     style=DivStyle(background=s['color'], radius=2, padding=(0, 0, 0, 1)))

def composer(fs: FrameState):
    schedules = vstack([
        # text('Coll.', style=TextStyle(font=fonts.bitocra7)),
        hstack(list(todays_trash_schedule(fs)), gap=2),
    ], gap=2, align='left')
    # schedules = hstack([s['icon'] for s in todays_trash_schedule(fs)])

    return div(hstack([schedules], gap=1, align='bottom'), style=DivStyle(padding=1, radius=2, background=gray.darken(0.3).hex))

draw = draw_loop(composer)