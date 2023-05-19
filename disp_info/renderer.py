#!/usr/bin/env python
import time

from PIL import Image

from .weather_icons import render_icon, cursor
from .redis import get_dict, rkeys
from .state_proxy import should_turn_on_display
from .components.layouts import stack_horizontal, stack_vertical, composite_at
from .utils import throttle

from . import config, screens


pos_x = 64
pos_y = 42

@throttle(40)
def get_remote_action():
    return get_dict(rkeys['ha_enki_rmt']).get('action')


def draw_btn_test(image):
    global pos_x, pos_y

    action = get_remote_action()
    if action == 'color_saturation_step_up':
        pos_y -= 1
    if action == 'color_saturation_step_down':
        pos_y += 1
    if action == 'color_hue_step_up':
        pos_x += 1
    if action == 'color_hue_step_down':
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
            stack_horizontal([
                screens.plant.draw(tick),
                screens.date_time.draw(tick),
            ], gap=2, align='top'),
            octoprint_info,
        ], gap=1, align='right'),
        image, 'tr')
    composite_at(screens.weather.draw(tick), image, 'tl')
    composite_at(screens.numbers.draw(tick), image, 'bl')

    # composite_at(paris_metro.draw(tick), image, 'ml')

    if not octoprint_info:
        composite_at(screens.now_playing.draw(tick), image, 'mr')

    composite_at(screens.twenty_two.draw(tick), image, 'mm')

    image = draw_btn_test(image)

    return image


def get_frame():
    return draw_frame()
