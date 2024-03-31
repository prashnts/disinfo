from .drawer import draw_loop
from .colors import gray
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.widget import Widget
from ..data_structures import FrameState

dishwasher_icon = StillImage('assets/raster/dishwasher.png')

def composer(fs: FrameState):
    schedules = hstack([dishwasher_icon], gap=2)

    return div(
        schedules,
        style=DivStyle(padding=1, radius=2, background=gray.darken(0.4).hex)
    ).tag('dishwasher')

def widget(fs: FrameState):
    return Widget('dishwasher', composer(fs), priority=0.5)

draw = draw_loop(composer)
