import arrow

from datetime import timedelta

from .drawer import draw_loop
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..redis import rkeys, get_dict
from ..utils.func import throttle
from ..data_structures import FrameState

trash_icon = StillImage('assets/raster/trash-bin-green-10x14.png')

WARNING_THRESHOLD = 1.7

@throttle(11177)
def get_state():
    state = dict(is_visible=False)
    s = get_dict(rkeys['ha_driplant_volts']).get('new_state')

    if not s:
        return state

    last_updated = arrow.get(s['last_updated']).to('local')
    now = arrow.now()

    try:
        state['volts'] = float(s['state'])
    except ValueError:
        state['volts'] = 0.0

    state['is_visible'] = all([
        state['volts'] >= WARNING_THRESHOLD,
        (last_updated + timedelta(minutes=45)) > now
    ])

    return state


def composer(fs: FrameState):
    return trash_icon

draw = draw_loop(composer)
