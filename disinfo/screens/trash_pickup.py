from .drawer import draw_loop
from .colors import gray
from ..components import fonts
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
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
        'days': [2, 4, 6],
    },
    {
        'type': 'white',
        'label': '3',
        'label_color': '#000',
        'color': '#fff',
        'icon': StillImage('assets/raster/trash-bin-white-10x14.png'),
        'days': [3],
    },
]

def todays_trash_schedule(fs: FrameState):
    today = fs.now.day_of_week
    for s in SCHEDULE:
        yield s['icon'].opacity(0.6 if today not in s['days'] else 1)

def composer(fs: FrameState):
    schedules = vstack([
        hstack(list(todays_trash_schedule(fs)), gap=2),
    ], gap=2, align='left')

    return div(
        hstack([schedules], gap=1, align='bottom'),
        style=DivStyle(padding=1, radius=2, background=gray.darken(0.4).hex)
    ).tag('trash_pickup')

draw = draw_loop(composer)
