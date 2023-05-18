#!/usr/bin/env python
import time
import math
import requests
import io

from PIL import Image, ImageDraw
from functools import cache

from .weather_icons import render_icon, cursor
from .redis import get_dict, rkeys
from .state_proxy import should_turn_on_display
from .components.layouts import stack_horizontal, stack_vertical, composite_at
from .components import fonts
from .utils import throttle

from .screens import date_time, octoprint, weather, twenty_two, now_playing, numbers, paris_metro, plant, demo
from . import config


pos_x = 64
pos_y = 42

@throttle(40)
def get_remote_action():
    return get_dict(rkeys['ha_enki_rmt']).get('action')


def draw_btn_test(image, draw):
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

    # draw.text((pos_x, pos_y), '↖', font=font_scientifica__r)
    icon = render_icon(cursor)

    image.alpha_composite(icon, (pos_x, pos_y))
    return image


def draw_frame():
    tick = time.time()
    step = tick * 15

    image = Image.new('RGBA', (128, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if not should_turn_on_display():
        # do not draw if nobody is there.
        return image

    composite_at(demo.draw(tick), image, 'mm')

    twenty_two_frame = twenty_two.draw()
    octoprint_info = octoprint.draw(tick)

    plant_info = plant.draw(tick)
    date_time_info = date_time.draw()

    right_widget = []

    if plant_info:
        right_widget.append(stack_horizontal([plant_info, date_time_info], gap=2, align='top'))
    else:
        right_widget.append(date_time_info)

    if octoprint_info:
        right_widget.append(octoprint_info)

    composite_at(stack_vertical(right_widget, gap=1, align='right'), image, 'tr')
    composite_at(weather.draw(tick), image, 'tl')
    composite_at(numbers.draw(tick), image, 'bl')

    # composite_at(paris_metro.draw(tick), image, 'ml')

    now_playing_frame = now_playing.draw()

    if now_playing_frame and not octoprint_info:
        composite_at(now_playing_frame, image, 'mr')


    if twenty_two_frame:
        composite_at(twenty_two_frame, image, 'mm')

    image = draw_btn_test(image, draw)

    return image


def get_frame():
    return draw_frame()
