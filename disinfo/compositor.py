#!/usr/bin/env python
import arrow

from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .components.layouts import hstack, vstack, composite_at
from .components.layers import div, DivStyle
from .data_structures import FrameState
from .drat.app_states import CursorStateManager, MotionSensorStateManager

from . import config, screens


def should_turn_on_display() -> bool:
    sensors = ['ha_pir_salon', 'ha_pir_kitchen']
    return any([MotionSensorStateManager(s).get_state().detected for s in sensors])


def draw_btn_test(image, fs: FrameState):
    s = CursorStateManager().get_state(fs)
    icon = render_icon(cursor)
    image.alpha_composite(icon, (s.x, s.y))
    return image


def compose_frame(fs: FrameState):
    image = Image.new('RGBA', (config.matrix_w, config.matrix_h), (0, 0, 0, 255))

    if not should_turn_on_display():
        # do not draw if nobody is there.
        return image

    # composite_at(screens.demo.draw(fs), image, 'mm')

    octoprint_info = screens.octoprint.draw(fs)
    composite_at(screens.solar.draw(fs), image, 'mm')

    composite_at(
        vstack([
            vstack([
                screens.date_time.draw(fs),
                screens.plant.draw(fs),
            ], gap=2, align='right'),
            octoprint_info,
        ], gap=1, align='right'),
        image, 'tr')
    composite_at(
        div(vstack([
            screens.weather.draw(fs),
            screens.now_playing.draw(fs),
        ]), DivStyle(padding=2)),
        image, 'ml')
    composite_at(screens.numbers.draw(fs), image, 'bl')

    composite_at(screens.paris_metro.draw(fs), image, 'bm')

    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(screens.debug_info.draw(fs), image, 'mm')

    image = draw_btn_test(image, fs)

    return image

