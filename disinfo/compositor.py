import random
from dataclasses import replace as dc_replace


from PIL import Image, ImageDraw

from .utils.weather_icons import render_icon, cursor
from .utils.func import throttle
from discore.layouts import hstack, vstack, composite_at, place_at
from discore.transitions import FadeIn, Resize
from discore.elements import Frame
from discore.stack import Stack, StackStyle
from discore.data_structures import FrameState, scope
from discore.color import using
from .palette import palette_for
from discore.screen import Screen, Spot, Option
from .drat.app_states import RuntimeStateManager

from . import screens
from .screens.solar import AnalogClockStyle
from .screens.music.shazam import widgets as shazam_widgets
from .screens.music.shazam import indicators as shazam_indicators
from .screens.stream import widget as stream_widget
from .screens.common import background, side_cards, bottom_cards, motion, focus, heat_store, across
from .web.telemetry import TelemetryStateManager, act
from disinfo.redis import publish
from disinfo.apps.timer import timer_app
from disinfo.apps.news import news_app
from disinfo.apps.design_demo import design_demo_app
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



def below_time(fs: FrameState, app, layout, items: dict, image: Frame, gap: int = 2, min_h: int = 100) -> Frame:
    # The app full width, in the rows the time leaves: below it, above it when it's down.
    # At least min_h tall: on a short screen (the desk) it goes over the time's seconds.
    key = 'timedate' if 'timedate' in layout.positions else 'time'
    if key not in layout.positions:
        return image
    y, h = layout.positions[key][1], items[key].height
    H = fs.config.height
    y0, y1 = (min(y + h + gap, H - min_h), H) if y < H // 2 else (0, max(y - gap, min_h))
    return place_at(app(fs, (fs.config.width, y1 - y0)).draw(fs), image, fs.config.width // 2, y0, 'tm', frost=1.5)

def compose_big_frame(fs: FrameState):
    config = fs.config
    screen = screen_for(config.name)
    rmt_reader = TelemetryStateManager(fs.config.name).remote_reader('comp', fs)
    telermt = TelemetryStateManager(fs.config.name).get_state(fs)
    awake = should_turn_on_display(fs)
    # TODO: the color sensor's reading flickers the whole background (clouds, its own light): redo it, sky color meanwhile.
    sky = screens.solar.app.sky_color(fs)

    # A frame, not an image: it keeps the touch targets, for the web page.
    image = Frame(Image.new('RGBA', (config.width, config.height), (0, 0, 0, 255)))

    gesture = telermt.light_sensor.gesture.read('comp')
    if gesture and gesture != '--':
        print(gesture, telermt)
        act(fs, 'buzzer', 'fmart', 'main')

    if rmt_reader('left'):
        publish('di.pubsub.remote', action='btn_debug')
    elif rmt_reader('right'):
        publish('di.pubsub.remote', action='btn_metro')

    # The stacks first: the background is the one their cards on top bring. Made on the designated side, turned
    # to the side they're on.
    designated = screen.choices[0][0].spots['side'].anchor[1]
    stack_conf = StackStyle(size=config.height, align='right' if designated == 'r' else 'left', horizontal=False, fill=True)
    stack = Stack('main_cards', style=stack_conf).mut(side_cards(fs))
    stack.style = dc_replace(stack_conf, align='right' if screen.spot('side').anchor[1] == 'r' else 'left')
    stack_hor_conf = StackStyle(align='bottom', horizontal=True, offset_top=0, size=config.width)
    stack_hor = Stack('bottom_cards', style=stack_hor_conf).mut(bottom_cards(fs))
    if rmt_reader('down'):
        stack.next_widget()
    # Someone moving by: the next cards, the ones shown least lately. A good time to move things too.
    moved = motion(fs)
    if moved:
        stack.next_widget()
        stack_hor.next_widget()
    screens.aviator.app.follow(fs, stack_hor.current)
    on_top = [stack.current, stack_hor.current]

    align = 'right' if (screen.spot('time') or screen.spot('timedate')).anchor[1] == 'r' else 'left'
    clock, date = screens.date_time.flip_digital_clock(fs, align=align), screens.date_time.flip_clock(fs, align=align)
    items = {
        'time': clock,
        'date': date,
        'side': stack.draw(fs) if awake else None,
        'bottom': stack_hor.draw(fs) if awake else None,
    }
    if config.name in DATE_BESIDE:
        # The date in the time's row: one item instead of two, where the date alone would be under the cards.
        items['timedate'] = hstack([date, clock] if align == 'right' else [clock, date], gap=1, align='top')
    # The solar clock where it's designed, across while the side stack is on its other side. Kept clear.
    def solar_style(spots) -> AnalogClockStyle:
        return AnalogClockStyle(
            cx=across(screen, spots, 75 + p_stack_offset(), config.width),
            cy=42 + p_stack_offset(),
            tick_radius_multiplier=0.40,
            dial_radius_multiplier=0.40,
            needle_radius_multiplier=0.45,
            background=sky,
        )
    # Calm (nobody there, or a plane's card on top): the time may go down.
    calm = not awake or any(w and w.background == 'aviator' for w in on_top)
    layout = screen.arrange(fs, items, focus(fs, on_top, solar_style) if awake else None, when={'calm'} if calm else (), relayout=moved)

    if awake:
        image = composite_at(background(fs, solar_style(screen.spots()), layout.clear, on_top), image, 'mm')
    image = layout.place('date', items['date'], image, frost=1)
    image = layout.place('timedate', items.get('timedate'), image, frost=1.8)
    # if rmt_state.show_debug:
    #     composite_at(screens.demo.draw(fs), image, 'mm')

    if awake:
        image = layout.place('side', items['side'], image, frost=1.8)
        image = layout.place('bottom', items['bottom'], image, frost=1.8)
        image = composite_at(shazam_indicators(fs).draw(fs), image, 'br')
        # composite_at(screens.numbers.draw(fs), image, 'bl')

    image = layout.place('time', items['time'], image, frost=1.8)

    s = RuntimeStateManager().get_state(fs)
    pos = rmt_reader('encoder')
    y = pos % config.width
    x = pos // y if y > 0 else 42

    # place_at(cursor_f.opacity(0.4), image, x, y, 'tl', frost=1)

    if awake:
        image = composite_at(news_app(fs).draw(fs), image, 'bm', frost=1)
        image = below_time(fs, design_demo_app, layout, items, image)
        image = composite_at(screens.debug_info.fonts_demo(fs).draw(fs), image, 'bm', frost=1.8)

        if config.height >= 120:
            image = composite_at(stream_widget(fs).draw(fs), image, 'bm')
    image = composite_at(screens.twenty_two.draw(fs), image, 'mm')
    image = composite_at(timer_app(fs).draw(fs), image, 'br' if screen.spot('side').anchor[1] == 'r' else 'bl', frost=2)
    if (note := screens.note.draw(fs)):
        image = composite_at(note, image, 'bm', dy=-2)

    if config.name == 'distudy':
        # dead pixel on border.
        draw = ImageDraw.Draw(image.image)
        draw.rectangle(((0, 0), (config.width - 1, config.height - 1)), outline=(0, 0, 0), width=1)

    return image.tag(awake)

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
    screen = screen_for(config.name)
    awake = should_turn_on_display(fs)
    image = Frame(Image.new('RGBA', (config.width, config.height), (0, 0, 0, 255)))

    on_top, moved, items = [], False, {}
    if awake:
        stack_conf = StackStyle(size=config.height, align='left', horizontal=False, fill=True)
        stack = Stack('main_cards', style=stack_conf).mut([
            *side_cards(fs),
            screens.date_time.calendar_widget(fs),
        ])
        stack.style = dc_replace(stack_conf, align='right' if screen.spot('side').anchor[1] == 'r' else 'left')
        stack_hor = Stack('bottom_cards', style=StackStyle(align='bottom', horizontal=True, offset_top=0, size=config.width)).mut(bottom_cards(fs))
        if moved := motion(fs):
            stack.next_widget()
            stack_hor.next_widget()
        screens.aviator.app.follow(fs, stack_hor.current)
        on_top = [stack.current, stack_hor.current]
        items = {'side': stack.draw(fs), 'bottom': stack_hor.draw(fs)}
    items['time'] = screens.date_time.flip_digital_clock(fs, align='right' if screen.spot('time').anchor[1] == 'r' else 'left')

    def solar_style(spots) -> AnalogClockStyle:
        return AnalogClockStyle(
            cx=across(screen, spots, config.width // 2 + 22 + p_stack_offset(), config.width),
            cy=config.height // 2 - 8 + p_stack_offset(),
            tick_radius_multiplier=0.36,
            dial_radius_multiplier=0.36,
            needle_radius_multiplier=0.42,
            background=screens.solar.app.sky_color(fs),   # TODO: color sensor, see compose_big_frame
        )
    calm = not awake or any(w and w.background == 'aviator' for w in on_top)
    layout = screen.arrange(fs, items, focus(fs, on_top, solar_style) if awake else None, when={'calm'} if calm else (), relayout=moved)

    if awake:
        # The background is the one their cards on top bring.
        image = composite_at(background(fs, solar_style(screen.spots()), layout.clear, on_top), image, 'mm')
        image = layout.place('side', items['side'], image, frost=1.8)
        image = layout.place('bottom', items['bottom'], image, frost=1.8)
        image = composite_at(shazam_indicators(fs).draw(fs), image, 'br')
        image = composite_at(news_app(fs).draw(fs), image, 'bm', frost=1)
        image = composite_at(stream_widget(fs).draw(fs), image, 'bm')

    image = layout.place('time', items['time'], image, frost=1.8)
    if awake:
        image = below_time(fs, design_demo_app, layout, items, image)
    image = composite_at(screens.twenty_two.draw(fs), image, 'mm')
    image = composite_at(timer_app(fs).draw(fs), image, 'br' if screen.spot('side').anchor[1] == 'r' else 'bl', frost=2)
    return image.tag(awake)


DATE_BESIDE = {'distudy'}      # the date may go in the time's row, when below it the cards would cover it
beside_penalty = 1.2     # over what the burn-in heat gives it (the date as an item of its own wears one more spot)

def big_screen(name: str, side: str, time_side: str | None = None, compose=None) -> Screen:
    '''The salon, the desk and the display: the side stack on its designated side, the time and date in the top
    corner across, the bottom stack along the bottom. The other side costs a little, the time on the stack's side
    too; the time goes down only while calm. time_side: the time kept on that side.'''
    l, r = ('l', 'r') if side == 'left' else ('r', 'l')
    inwards = lambda h: 1 if h == 'l' else -1
    def option(s: str, v: str, h: str, penalty: float, when: str | None = None, beside: bool = False) -> Option:
        time = Spot(f'{v}{h}', dx=inwards(h), dy=2 if v == 't' else -2, jitter=(1, 8))
        spots = {'side': Spot(f'm{s}', jitter=(3, 0))}
        if beside:
            return Option({**spots, 'timedate': time}, penalty + beside_penalty, when)
        return Option({**spots, 'time': time, 'date': Spot(f'{v}{h}', dy=60 if v == 't' else -48, jitter=(6, 3))}, penalty, when)
    options = [option(s, v, h, (0 if s == l else 0.5) + (0 if h != s else 0.3) + (0 if v == 't' else 0.2), None if v == 't' else 'calm', beside)
               for s in (l, r) for v in 'tb' for h in (r, l) if not time_side or h == time_side[0]
               for beside in ((False, True) if name in DATE_BESIDE else (False,))]
    load, save = heat_store(name)
    return Screen(name, [
        sorted(options, key=lambda o: o.penalty),
        [Option({'bottom': Spot('bl', jitter=(0, 3))})],
    ], compose=compose or compose_big_frame, load_heat=load, save_heat=save,
                  covering={'side', 'bottom'}, stacked={'side', 'bottom'}, fading={'time', 'date', 'timedate'})

def compose_entry(fs: FrameState) -> Frame:
    # Dim while nobody's there (the panel's off then, but a touch lights it): it fades up when someone comes.
    frame = screens.entry.compose(fs)
    if (note := screens.note.draw(fs)):
        frame = composite_at(note, frame, 'bm', dy=-2)
    return frame if should_turn_on_display(fs) else frame.brightness(0).tag('entry.asleep')

SCREENS = {
    'disalon': big_screen('disalon', 'left'),
    'distudy': big_screen('distudy', 'right'),
    'di_pcstate': big_screen('di_pcstate', 'left', compose=compose_display_frame),
    'dientry': screens.entry.screen,
}
screens.entry.screen.compose = compose_entry

def screen_for(name: str) -> Screen:
    if name not in SCREENS:
        SCREENS[name] = big_screen(name, 'left')
    return SCREENS[name]


def compose(fs: FrameState) -> Frame:
    '''The screen, with its touch targets.'''
    with scope(fs.config.name), using(palette_for(fs)):
        if fs.config.name == 'picowpanel':
            frame = compose_small_frame(fs)
        elif fs.config.name in ('didial', 'disalon_dial'):     # the fridge's, the salon's (on its Pi's USB)
            frame = screens.dial.compose(fs)
        else:
            frame = screen_for(fs.config.name).compose(fs)
        return FadeIn('compose', duration=0.8).mut(frame).draw(fs)

def compose_frame(fs: FrameState):
    return compose(fs).image
