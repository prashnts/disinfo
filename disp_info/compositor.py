#!/usr/bin/env python
import time
import arrow

from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .redis import get_dict, rkeys
from .components.layouts import stack_horizontal, stack_vertical, composite_at
from .utils.func import throttle

from . import config, screens


pos_x = 64
pos_y = 42

@throttle(40)
def get_remotes_action():
    return {
        'enki': get_dict(rkeys['ha_enki_rmt']).get('action'),
        'ikea': get_dict(rkeys['ha_ikea_rmt_0x01']).get('action'),
    }

@throttle(500)
def should_turn_on_display() -> bool:
    def is_motion_detected(name: str) -> bool:
        pir_state = get_dict(rkeys[name])
        if not pir_state:
            # Uninitialized state on this sensor. Assume on.
            return True

        occupied = pir_state['occupancy']
        if occupied:
            # when motion is detected, it's on.
            return True

        # When motion is NOT detected, we want to keep the display on
        # for 30 minutes during day (8h -> 23h), otherwise 5 minutes.
        # this time is in local timezone.
        last_change = arrow.get(pir_state['timestamp'])
        now = arrow.now()
        delay = 30 if 8 <= now.timetuple().tm_hour < 23 else 5
        delta = (now - last_change).total_seconds()

        return delta <= 60 * delay

    sensors = ['ha_pir_salon', 'ha_pir_kitchen']
    motion_states = [is_motion_detected(s) for s in sensors]

    # if any sensor reports True we keep the display on.
    return any(motion_states)



def draw_btn_test(image):
    global pos_x, pos_y

    actions = get_remotes_action()
    if actions['enki'] == 'color_saturation_step_up' or actions['ikea'] == 'brightness_up_click':
        pos_y -= 1
    if actions['enki'] == 'color_saturation_step_down' or actions['ikea'] == 'brightness_down_click':
        pos_y += 1
    if actions['enki'] == 'color_hue_step_up' or actions['ikea'] == 'arrow_right_click':
        pos_x += 1
    if actions['enki'] == 'color_hue_step_down' or actions['ikea'] == 'arrow_left_click':
        pos_x -= 1

    pos_x %= config.matrix_w
    pos_y %= config.matrix_h

    icon = render_icon(cursor)

    image.alpha_composite(icon, (pos_x, pos_y))
    return image


def draw_frame():
    tick = time.time()

    image = Image.new('RGBA', (config.matrix_w, config.matrix_h), (0, 0, 0, 0))

    if not should_turn_on_display():
        # do not draw if nobody is there.
        return image

    composite_at(screens.demo.draw(tick), image, 'mm')

    octoprint_info = screens.octoprint.draw(tick)

    composite_at(
        stack_vertical([
            stack_vertical([
                screens.date_time.draw(tick),
                screens.plant.draw(tick),
            ], gap=2, align='right'),
            octoprint_info,
        ], gap=1, align='right'),
        image, 'tr')
    composite_at(screens.weather.draw(tick), image, 'tl')
    composite_at(screens.numbers.draw(tick), image, 'bl')

    composite_at(screens.paris_metro.draw(tick), image, 'ml')

    if not octoprint_info:
        composite_at(screens.now_playing.draw(tick), image, 'mr')

    composite_at(screens.twenty_two.draw(tick), image, 'mm')

    image = draw_btn_test(image)

    return image


def get_frame():
    return draw_frame()