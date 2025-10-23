import random
from dataclasses import replace as dc_replace

from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .utils.func import throttle
from .components.layouts import hstack, vstack, composite_at, place_at
from .components.layers import div, DivStyle, rounded_rectangle
from .components.transitions import FadeIn
from .components.elements import Frame
from .components.stack import Stack
from .data_structures import FrameState
from .drat.app_states import CursorStateManager, PresenceSensorStateManager, RemoteStateManager

from . import screens
from .screens.solar import AnalogClockStyle
from .screens.music.shazam import widgets as shazam_widgets
from .screens.music.shazam import indicators as shazam_indicators
from .screens.stream import widget as stream_widget
from .config import app_config
from .web.telemetry import TelemetryStateManager
from disinfo.redis import publish
from disinfo.apps.timer import timer_app


def should_turn_on_display(fs: FrameState) -> bool:
    sensors = app_config.presence_sensors

    return any([PresenceSensorStateManager(s).state.detected for s in sensors])

cursor_f = Frame(render_icon(cursor, 3), hash=('cursor', 'v1'))

def draw_btn_test(image, fs: FrameState):
    s = CursorStateManager().get_state(fs)
    return place_at(cursor_f.opacity(0.3), image, s.x, s.y, 'tl', frost=1)

@throttle(15_000)
def p_time_offset():
    return random.randint(2, 10)

@throttle(15_000)
def p_stack_offset():
    return random.randint(0, 3)



def compose_big_frame(fs: FrameState):
    rmt_state = RemoteStateManager().get_state(fs)
    telermt = TelemetryStateManager().get_state(fs)
    awake = should_turn_on_display(fs)
    background = telermt.light_sensor.color_hex

    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))

    next_time = fs.now.add(minutes=telermt.remote.encoder.position * 30)
    fs_next = dc_replace(fs, now=next_time)
    gesture = telermt.light_sensor.gesture.read('comp')

    if gesture == 'left':
        publish('di.pubsub.remote', action='btn_debug')
    elif gesture == 'right':
        publish('di.pubsub.remote', action='btn_metro')
    
    if telermt.remote.buttons.select.pressed.read('comp'):
        print("select pressed")
        fs_next = fs

    # composite_at(screens.aviator.app.radar(fs), image, 'mm')
    if awake:
        solar_style = AnalogClockStyle(
            cx=75 + p_stack_offset(),
            cy=42 + p_stack_offset(),
            tick_radius_multiplier=0.40,
            dial_radius_multiplier=0.40,
            needle_radius_multiplier=0.45,
            background=background,
        )
        composite_at(screens.solar.draw(fs_next, solar_style), image, 'mm')
    composite_at(
        screens.date_time.flip_clock(fs_next),
        image,
        'tr',
        dx=-1 * p_stack_offset(),
        dy=p_stack_offset() + 60,
        frost=1)
    # if rmt_state.show_debug:
    #     composite_at(screens.demo.draw(fs), image, 'mm')

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

    if telermt.remote.buttons.down.pressed.read('comp'):
        print("next")
        stack.next_widget()

    if awake:
        composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset(), frost=1.8)
        composite_at(shazam_indicators(fs).draw(fs), image, 'br')
        # composite_at(screens.numbers.draw(fs), image, 'bl')

    if app_config.height > 120:
        composite_at(stream_widget(fs).draw(fs), image, 'bm')

    composite_at(screens.paris_metro.draw(fs), image, 'bm', frost=1.8)

    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(screens.debug_info.widget(fs).draw(fs), image, 'bm', frost=1.8)  
    composite_at(screens.date_time.flip_digital_clock(fs_next), image, 'tr', dy=p_time_offset(), dx=-1, frost=1.8)

    s = CursorStateManager().get_state(fs)
    place_at(cursor_f.opacity(0.4), image, s.x, s.y, 'tl', frost=1)

    composite_at(timer_app(fs).draw(fs), image, 'mm')

    return Frame(image).tag(awake)

def compose_small_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=p_time_offset())
        composite_at(screens.twenty_two.draw(fs), image, 'mm')
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
    composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset(), frost=2)
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
