#!/usr/bin/env python
import arrow

from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .components.layouts import hstack, vstack, composite_at
from .components.layers import div, DivStyle
from .components.transitions import FadeIn
from .components.elements import Frame
from .data_structures import FrameState
from .drat.app_states import CursorStateManager, PresenceSensorStateManager

from . import screens
from .config import app_config


def should_turn_on_display(sensors: list[str]) -> bool:
    return any([PresenceSensorStateManager(s).get_state().detected for s in sensors])


def draw_btn_test(image, fs: FrameState):
    s = CursorStateManager().get_state(fs)
    icon = render_icon(cursor)
    image.alpha_composite(icon, (s.x, s.y))
    return image


def compose_big_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))

    if not any([PresenceSensorStateManager(s).get_state().present for s in app_config.presence_sensors]):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    # composite_at(screens.demo.draw(fs), image, 'mm')
    composite_at(screens.solar.draw(fs), image, 'mm')

    composite_at(
        vstack([
            vstack([
                screens.date_time.draw(fs),
                screens.plant.draw(fs),
            ], gap=2, align='right'),
        ], gap=1, align='right'),
        image, 'tr')
    composite_at(
        div(vstack([
            screens.weather.draw(fs),
            screens.now_playing.draw(fs),
            screens.octoprint.draw(fs),
        ], gap=1), DivStyle(padding=2)),
        image, 'ml')
    # composite_at(screens.numbers.draw(fs), image, 'bl')

    composite_at(screens.paris_metro.draw(fs), image, 'bm')

    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(screens.debug_info.draw(fs), image, 'mm')

    image = draw_btn_test(image, fs)

    return Frame(image).tag('present')

def compose_small_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not any([PresenceSensorStateManager(s).get_state().present for s in app_config.presence_sensors]):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    composite_at(screens.solar.draw(fs), image, 'mm')
    composite_at(
        div(vstack([
            screens.weather.draw(fs),
            # screens.date_time.draw(fs),
            screens.now_playing.draw(fs),
            screens.octoprint.draw(fs),
        ], gap=1, align='center'), DivStyle(padding=2)),
        image, 'mm')
    composite_at(screens.twenty_two.draw(fs), image, 'mm')

    return Frame(image).tag('present')


def compose_frame(fs: FrameState):
    if app_config.name == 'picowpanel':
        frame = compose_small_frame(fs)
    else:
        frame = compose_big_frame(fs)
    return FadeIn('compose', duration=0.2).mut(frame).draw(fs).image
