import arrow

from datetime import timedelta

from .screen import composer_thread
from ..components.elements import StillImage
from ..redis import rkeys, get_dict
from ..utils.func import throttle
from ..data_structures import FrameState

plant_icon = StillImage('assets/raster/plant-9x9.png')

WARNING_THRESHOLD = 1.7

@throttle(11177)
def get_state():
    state = dict(is_visible=False)
    s = get_dict(rkeys['ha_driplant_volts']).get('new_state')

    if not s:
        return state

    last_updated = arrow.get(s['last_updated']).to('local')
    now = arrow.now()

    state['volts'] = float(s['state'])

    state['is_visible'] = all([
        state['volts'] >= WARNING_THRESHOLD,
        (last_updated + timedelta(minutes=45)) > now
    ])

    return state


def composer(fs: FrameState):
    s = get_state()
    if s['is_visible']:
        return plant_icon

draw = composer_thread(composer, sleepms=1000)
