from .drawer import draw_loop
from .colors import gray
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.widget import Widget
from ..data_structures import FrameState

SCHEDULE = [
    # https://www.paris.fr/pages/la-collecte-44
    {
        'type': 'green',
        'icon': StillImage('assets/raster/trash-bin-green-10x14.png'),
        'days': [0, 1, 2, 3, 4, 5, 6],
    },
    {
        'type': 'yellow',
        'icon': StillImage('assets/raster/trash-bin-yellow-10x14.png'),
        'days': [2, 4, 6],
    },
    {
        'type': 'white',
        'icon': StillImage('assets/raster/trash-bin-white-10x14.png'),
        'days': [3],
    },
]

def todays_trash_schedule(fs: FrameState):
    today = fs.now.day_of_week
    for s in SCHEDULE:
        yield s['icon'].opacity(0.4 if today not in s['days'] else 1)

def composer(fs: FrameState):
    schedules = hstack(list(todays_trash_schedule(fs)), gap=2)

    return div(
        schedules,
        style=DivStyle(padding=1, radius=2, background=gray.darken(0.4).hex)
    ).tag('trash_pickup')

def widget(fs: FrameState):
    return Widget('trash_pickup', composer(fs))

draw = draw_loop(composer)
