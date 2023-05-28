#!/usr/bin/env python
import arrow

from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .redis import get_dict, rkeys
from .components.layouts import stack_horizontal, stack_vertical, composite_at
from .utils.func import throttle
from .data_structures import FrameState

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



def draw_btn_test(image, fs: FrameState):
    global pos_x, pos_y
    a0 = fs.rmt0_action
    a1 = fs.rmt1_action

    if a0 == 'color_saturation_step_up' or a1 == 'brightness_up_click':
        pos_y -= 1
    if a0 == 'color_saturation_step_down' or a1 == 'brightness_down_click':
        pos_y += 1
    if a0 == 'color_hue_step_up' or a1 == 'arrow_right_click':
        pos_x += 1
    if a0 == 'color_hue_step_down' or a1 == 'arrow_left_click':
        pos_x -= 1

    pos_x %= config.matrix_w
    pos_y %= config.matrix_h

    icon = render_icon(cursor)

    image.alpha_composite(icon, (pos_x, pos_y))
    return image


def draw_frame(fs: FrameState):
    image = Image.new('RGBA', (config.matrix_w, config.matrix_h), (0, 0, 0, 0))

    if not should_turn_on_display():
        # do not draw if nobody is there.
        return image

    # While not ideal, this allows us to avoid fetching state multiple times.
    rmt_action = get_remotes_action()
    fs.rmt0_action = rmt_action['enki']
    fs.rmt1_action = rmt_action['ikea']

    composite_at(screens.demo.draw(fs), image, 'mm')

    octoprint_info = screens.octoprint.draw(fs)

    composite_at(
        stack_vertical([
            stack_vertical([
                screens.date_time.draw(fs),
                screens.plant.draw(fs),
            ], gap=2, align='right'),
            octoprint_info,
        ], gap=1, align='right'),
        image, 'tr')
    composite_at(screens.weather.draw(fs), image, 'tl')
    composite_at(screens.numbers.draw(fs), image, 'bl')

    composite_at(screens.paris_metro.draw(fs), image, 'ml')

    if not octoprint_info:
        composite_at(screens.now_playing.draw(fs), image, 'mr')

    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(screens.debug_info.draw(fs), image, 'mm')

    image = draw_btn_test(image, fs)

    return image


def get_frame(fs: FrameState):
    return draw_frame(fs)
