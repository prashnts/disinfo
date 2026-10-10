import random

from PIL import Image, ImageDraw

from .utils.weather_icons import render_icon, cursor
from .utils.func import throttle
from discore.layouts import hstack, vstack, composite_at, place_at
from discore.transitions import FadeIn, Resize
from discore.elements import Frame
from discore.stack import Stack, StackStyle
from discore.data_structures import FrameState, scope
from .drat.app_states import RuntimeStateManager

from . import screens
from .screens.solar import AnalogClockStyle
from .screens.music.shazam import widgets as shazam_widgets
from .screens.music.shazam import indicators as shazam_indicators
from .screens.stream import widget as stream_widget
from .web.telemetry import TelemetryStateManager, act
from disinfo.redis import publish
from disinfo.apps.timer import timer_app
from disinfo.apps.news import news_app
from disinfo.utils.hass import get_entity


def should_turn_on_display(fs: FrameState) -> bool:
    s = RuntimeStateManager().get_state(fs)
    if s.motion_override:
        return True

    sensors = [get_entity(x) for x in fs.config.presence_sensors]
    return any(s and s.state == 'on' for s in sensors)

cursor_f = Frame(render_icon(cursor, 3), hash=('cursor', 'v1'))

def draw_btn_test(image, fs: FrameState):
    s = RuntimeStateManager().get_state(fs)
    return place_at(cursor_f.opacity(0.3), image, s.x % fs.config.width, s.y % fs.config.height, 'tl', frost=1)

@throttle(15_000)
def p_time_offset():
    return random.randint(2, 10)

@throttle(15_000)
def p_stack_offset():
    return random.randint(0, 3)



def compose_big_frame(fs: FrameState):
    config = fs.config
    rmt_reader = TelemetryStateManager(fs.config.name).remote_reader('comp', fs)
    telermt = TelemetryStateManager(fs.config.name).get_state(fs)
    awake = should_turn_on_display(fs)
    background = telermt.light_sensor.color_hex
    _leftward = config.name == 'distudy'
    _clock_align = 'left' if _leftward else 'right'

    image = Image.new('RGBA', (config.width, config.height), (0, 0, 0, 255))

    gesture = telermt.light_sensor.gesture.read('comp')
    if gesture and gesture != '--':
        print(gesture, telermt)
        act(fs, 'buzzer', 'fmart', 'main')

    if rmt_reader('left'):
        publish('di.pubsub.remote', action='btn_debug')
    elif rmt_reader('right'):
        publish('di.pubsub.remote', action='btn_metro')
    
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
        solar_frame = screens.solar.draw(fs, solar_style)
        
        composite_at(FadeIn('solar', duration=0.3).mut(solar_frame).draw(fs), image, 'mm')
    composite_at(
        screens.date_time.flip_clock(fs, align=_clock_align),
        image,
        'tl' if _leftward else 'tr',
        dx=p_stack_offset() * (1 if _leftward else -2),
        dy=p_stack_offset() + 60,
        frost=1)
    # if rmt_state.show_debug:
    #     composite_at(screens.demo.draw(fs), image, 'mm')

    stack_conf = StackStyle(size=config.height, scrollbar=_leftward, align='right' if _leftward else 'left', horizontal=False)
    stack = Stack('main_cards', style=stack_conf).mut([
        screens.weather.widgets.weather(fs),
        # *screens.aviator.widgets.planes(fs),
        *shazam_widgets(fs),
        screens.now_playing.slideshow_widget(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.dishwasher.widget(fs),
        screens.washing_machine.widget(fs),
        # *screens.klipper.widget(fs),
        screens.trash_pickup.widget(fs),
    ])

    stack_hor_conf = StackStyle(align='bottom', horizontal=True, offset_top=0, size=config.width)
    stack_hor = Stack('bottom_cards', style=stack_hor_conf).mut([
        screens.now_playing.widget(fs),
        *screens.klipper.widget(fs),
        *screens.debug_info.widgets(fs),
        # *screens.paris_metro.widgets(fs),
    ])

    if rmt_reader('down'):
        stack.next_widget()

    if awake:
        composite_at(stack.draw(fs), image, 'mr' if _leftward else 'ml', dx=p_stack_offset(), frost=1.8)
        composite_at(stack_hor.draw(fs), image, 'bl', dy=p_stack_offset() * -1, frost=1.8)
        composite_at(shazam_indicators(fs).draw(fs), image, 'br')
        # composite_at(screens.numbers.draw(fs), image, 'bl')

    composite_at(screens.date_time.flip_digital_clock(fs, align=_clock_align), image, 'tl' if _leftward else 'tr', dy=p_time_offset(), dx=1 if _leftward else -1, frost=1.8)

    s = RuntimeStateManager().get_state(fs)
    pos = rmt_reader('encoder')
    y = pos % config.width
    x = pos // y if y > 0 else 42

    # place_at(cursor_f.opacity(0.4), image, x, y, 'tl', frost=1)

    if awake:
        composite_at(news_app(fs).draw(fs), image, 'bm', frost=1)
        composite_at(screens.debug_info.fonts_demo(fs).draw(fs), image, 'bm', frost=1.8)

        if config.height >= 120:
            composite_at(stream_widget(fs).draw(fs), image, 'bm')
    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(timer_app(fs).draw(fs), image, 'br' if _leftward else 'bl', frost=2)

    if config.name == 'distudy':
        # dead pixel on border.
        draw = ImageDraw.Draw(image)
        draw.rectangle(((0, 0), (config.width - 1, config.height - 1)), outline=(0, 0, 0), width=1)

    return Frame(image).tag(awake)

def compose_small_frame(fs: FrameState):
    image = Image.new('RGBA', (fs.config.width, fs.config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=p_time_offset())
        composite_at(screens.twenty_two.draw(fs), image, 'mm')
        return Frame(image).tag('not_present')

    # composite_at(screens.aviator.app.radar(fs), image, 'mm')
    composite_at(screens.solar.draw(fs), image, 'mm')
    stack = Stack('main_cards', StackStyle(size=fs.config.height)).mut([
        # *screens.aviator.widgets.planes(fs),
        *shazam_widgets(fs),
        screens.weather.widgets.weather(fs),
        screens.dishwasher.widget(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.now_playing.widget(fs),
        screens.now_playing.slideshow_widget(fs),
        *screens.klipper.widget(fs),
        screens.trash_pickup.widget(fs),
        screens.date_time.calendar_widget(fs),
    ])
    composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset(), frost=2)
    composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=p_time_offset())
    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(shazam_indicators(fs).draw(fs), image, 'br')

    return Frame(image).tag('present')


def compose_display_frame(fs: FrameState):
    # esp-displays' T4-S3 over USB: 200x150, shown at 3x (600x450). Buttons on the display press the remote.
    config = fs.config
    telermt = TelemetryStateManager(config.name).get_state(fs)
    awake = should_turn_on_display(fs)
    image = Image.new('RGBA', (config.width, config.height), (0, 0, 0, 255))

    if awake:
        solar_style = AnalogClockStyle(
            cx=config.width // 2 + 22 + p_stack_offset(),
            cy=config.height // 2 - 8 + p_stack_offset(),
            tick_radius_multiplier=0.36,
            dial_radius_multiplier=0.36,
            needle_radius_multiplier=0.42,
            background=telermt.light_sensor.color_hex,
        )
        composite_at(FadeIn('solar', duration=0.3).mut(screens.solar.draw(fs, solar_style)).draw(fs), image, 'mm')

        stack = Stack('main_cards', style=StackStyle(size=config.height, align='left', horizontal=False)).mut([
            screens.weather.widgets.weather(fs),
            *shazam_widgets(fs),
            screens.now_playing.slideshow_widget(fs),
            screens.weather.widgets.moon_phase(fs),
            screens.dishwasher.widget(fs),
            screens.washing_machine.widget(fs),
            screens.trash_pickup.widget(fs),
            screens.date_time.calendar_widget(fs),
        ])
        stack_hor = Stack('bottom_cards', style=StackStyle(align='bottom', horizontal=True, offset_top=0, size=config.width)).mut([
            screens.now_playing.widget(fs),
            *screens.klipper.widget(fs),
            *screens.debug_info.widgets(fs),
        ])
        if RuntimeStateManager().get_state(fs).show_metro:
            stack.mut([*screens.paris_metro.widgets(fs)])
        composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset(), frost=1.8)
        composite_at(stack_hor.draw(fs), image, 'bl', dy=-p_stack_offset(), frost=1.8)
        composite_at(shazam_indicators(fs).draw(fs), image, 'br')
        composite_at(news_app(fs).draw(fs), image, 'bm', frost=1)
        composite_at(stream_widget(fs).draw(fs), image, 'bm')

    composite_at(screens.date_time.flip_digital_clock(fs, align='right'), image, 'tr', dy=p_time_offset(), dx=-1, frost=1.8)
    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(timer_app(fs).draw(fs), image, 'bl', frost=2)
    return Frame(image).tag(awake)


def compose_frame(fs: FrameState):
    with scope(fs.config.name):
        if fs.config.name == 'picowpanel':
            frame = compose_small_frame(fs)
        elif fs.config.name == 'di_pcstate':
            frame = compose_display_frame(fs)
        else:
            frame = compose_big_frame(fs)
        return FadeIn('compose', duration=0.8).mut(frame).draw(fs).image
