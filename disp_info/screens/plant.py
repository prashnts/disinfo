import arrow

from functools import cache
from PIL import Image, ImageDraw
from datetime import timedelta

from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import composite_at, stack_horizontal, stack_vertical
from disp_info.sprite_icons import SpriteImage
from disp_info.redis import rkeys, get_dict
from disp_info.utils import throttle

plant_icon = SpriteImage('assets/raster/plant-9x9.png')[0]

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


def draw(tick: float):
    s = get_state()
    if s['is_visible']:
        return plant_icon
