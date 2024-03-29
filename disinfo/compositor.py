from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .components.layouts import hstack, vstack, composite_at
from .components.layers import div, DivStyle
from .components.transitions import FadeIn
from .components.elements import Frame
from .components.stack import Stack
from .data_structures import FrameState
from .drat.app_states import CursorStateManager, PresenceSensorStateManager

from . import screens
from .config import app_config


def should_turn_on_display(fs: FrameState) -> bool:
    sensors = app_config.presence_sensors

    # return any([PresenceSensorStateManager(s).get_state().present_at(fs.now) for s in sensors])
    return any([PresenceSensorStateManager(s).get_state().present_at(fs.now) for s in sensors])


def draw_btn_test(image, fs: FrameState):
    s = CursorStateManager().get_state(fs)
    icon = render_icon(cursor)
    image.alpha_composite(icon, (s.x, s.y))
    return image


def compose_big_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))

    if not should_turn_on_display(fs):
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
    stack = Stack('main_cards').mut([
        screens.weather.widgets.weather(fs),
        screens.now_playing.widget(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.octoprint.widget(fs),
        screens.trash_pickup.widget(fs),
    ])
    composite_at(stack.draw(fs), image, 'ml')
    # composite_at(screens.numbers.draw(fs), image, 'bl')

    composite_at(screens.paris_metro.draw(fs), image, 'bm')

    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(screens.debug_info.draw(fs), image, 'mm')

    image = draw_btn_test(image, fs)

    return Frame(image).tag('present')

def compose_small_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    composite_at(screens.solar.draw(fs), image, 'mm')
    composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=2)
    stack = Stack('main_cards').mut([
        screens.weather.widgets.weather(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.now_playing.widget(fs),
        screens.octoprint.widget(fs),
        screens.trash_pickup.widget(fs),
        screens.date_time.calendar_widget(fs),
    ])
    composite_at(stack.draw(fs), image, 'ml')
    composite_at(screens.twenty_two.draw(fs), image, 'mm')

    return Frame(image).tag('present')


def compose_frame(fs: FrameState):
    if app_config.name == 'picowpanel':
        frame = compose_small_frame(fs)
    else:
        frame = compose_big_frame(fs)
    return FadeIn('compose', duration=0.8).mut(frame).draw(fs).image
