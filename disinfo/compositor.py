import random

from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .utils.func import throttle
from .components.layouts import hstack, vstack, composite_at
from .components.layers import div, DivStyle, rounded_rectangle
from .components.transitions import FadeIn
from .components.elements import Frame
from .components.stack import Stack
from .data_structures import FrameState
from .drat.app_states import CursorStateManager, PresenceSensorStateManager

from . import screens
from .screens.music.shazam import widgets as shazam_widgets
from .screens.music.shazam import indicators as shazam_indicators
from .config import app_config


def should_turn_on_display(fs: FrameState) -> bool:
    sensors = app_config.presence_sensors

    return any([PresenceSensorStateManager(s).get_state().present_at(fs.now) for s in sensors])


def draw_btn_test(image, fs: FrameState):
    s = CursorStateManager().get_state(fs)
    icon = render_icon(cursor)
    image.alpha_composite(icon, (s.x, s.y))
    return image

@throttle(15_000)
def p_time_offset():
    return random.randint(0, 22)

@throttle(15_000)
def p_stack_offset():
    return random.randint(0, 3)



def compose_big_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))

    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    # composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=2)
    # return Frame(image).tag('present')
    # composite_at(screens.demo.draw(fs), image, 'mm')
    # composite_at(screens.aviator.app.radar(fs), image, 'mm')
    composite_at(screens.solar.draw(fs), image, 'mm')

    composite_at(
        vstack([
            vstack([
                screens.date_time.draw(fs),
                screens.weather.persistent_view(fs),
                screens.plant.draw(fs),
            ], gap=3, align='right'),
        ], gap=1, align='right'),
        image, 'tr', dy=p_time_offset())
    stack = Stack('main_cards').mut([
        screens.weather.widgets.weather(fs),
        *screens.aviator.widgets.planes(fs),
        *shazam_widgets(fs),
        screens.now_playing.widget(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.dishwasher.widget(fs),
        screens.washing_machine.widget(fs),
        *screens.klipper.widget(fs),
        screens.trash_pickup.widget(fs),
    ])
    composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset())
    composite_at(shazam_indicators(fs).draw(fs), image, 'br')
    # composite_at(screens.numbers.draw(fs), image, 'bl')

    composite_at(screens.paris_metro.draw(fs), image, 'bm')

    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(screens.debug_info.draw(fs), image, 'mm')

    # image = draw_btn_test(image, fs)

    return Frame(image).tag('present')

def compose_small_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    # composite_at(screens.aviator.app.radar(fs), image, 'mm')
    composite_at(screens.solar.draw(fs), image, 'mm')
    stack = Stack('main_cards').mut([
        *screens.aviator.widgets.planes(fs),
        *shazam_widgets(fs),
        screens.weather.widgets.weather(fs),
        screens.dishwasher.widget(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.now_playing.widget(fs),
        *screens.klipper.widget(fs),
        screens.trash_pickup.widget(fs),
        screens.date_time.calendar_widget(fs),
    ])
    composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset())
    composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=p_time_offset())
    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(shazam_indicators(fs).draw(fs), image, 'br')

    return Frame(image).tag('present')

def compose_3dp_frame(fs: FrameState):
    state = screens.klipper.KlipperStateManager().get_state(fs)
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    # composite_at(screens.solar.draw(fs), image, 'mm')
    # composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=2)
    # stack = Stack('main_cards').mut([
    #     screens.klipper.widget(fs),
    # ])
    background = rounded_rectangle(
        app_config.width,
        app_config.height,
        radius=(3,)*4,
        fill='#08223c00',
        border=1,
        border_color='#91642176')
    composite_at(screens.klipper.thumbnail_image(state.thumbnail), image, 'mr')
    composite_at(screens.klipper.draw_full_screen(fs), image, 'ml')
    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(Frame(background), image, 'mm')

    return Frame(image).tag('present')

def compose_tiny_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    composite_at(screens.date_time.simple(fs), image, 'tr')

    return Frame(image).tag('present')


def compose_frame(fs: FrameState):
    if app_config.name == 'picowpanel':
        frame = compose_small_frame(fs)
    elif app_config.name == 'frekvens':
        frame = compose_tiny_frame(fs)
    elif app_config.name == '3dpanel':
        frame = compose_3dp_frame(fs)
    else:
        frame = compose_big_frame(fs)
    return FadeIn('compose', duration=0.8).mut(frame).draw(fs).image


def compose_epd_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    stack = Stack('main_cards').mut([
        *screens.aviator.widgets.planes(fs),
        *shazam_widgets(fs),
        screens.weather.widgets.weather(fs),
        screens.dishwasher.widget(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.now_playing.widget(fs),
        *screens.klipper.widget(fs),
        screens.trash_pickup.widget(fs),
        screens.date_time.calendar_widget(fs),
    ])
    composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset())

    composite_at(screens.date_time.simple(fs), image, 'tr')

    return Frame(image).tag('present')
