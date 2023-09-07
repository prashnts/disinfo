from colour import Color
from functools import cache
from pydash import once
from PIL import Image, ImageDraw, ImageFont

from disinfo.components import fonts
from disinfo.components.elements import Frame, StillImage
from disinfo.components.text import TextStyle, text
from disinfo.components.layers import div, DivStyle
from disinfo.components.layouts import hstack, vstack, composite_at
from disinfo.components.spriteim import SpriteIcon
from disinfo.data_structures import FrameState
from disinfo.redis import publish

from .state import WeatherStateManager, WeatherState


weather_icon = SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=.05)
moon_icon = StillImage('assets/moon/moon08.png', resize=(25, 25))
sunset_arrow = SpriteIcon('assets/sunset-arrow.png', step_time=.2)
warning_icon = StillImage('assets/sync.png')
# sunset_icon = StillImage('assets/raster/sunset-11x5.png')
sunset_icon = StillImage('assets/raster/sunset-7x9.png')
sunrise_icon = StillImage('assets/raster/sunrise-7x7.png')

s_temp_value = TextStyle(font=fonts.px_op__l, color='#9a9ba2')
s_condition = TextStyle(font=fonts.tamzen__rs, color='#5b5e64')
s_sunset_time = TextStyle(font=fonts.bitocra7, color='#5b5e64')
s_moon_phase = TextStyle(font=fonts.px_op__r, color='#58595c', outline=1, outline_color='#000000')
s_deg_c = TextStyle(font=fonts.px_op__r, color='#6E7078')


fetch_on_start = once(lambda: publish('di.pubsub.dataservice', action='fetch_weather'))

@cache
def moon_phase_image(phase: int) -> StillImage:
    return StillImage(f'assets/moon/moon{phase:02d}.png', resize=(24, 24))


def astronomical_info(state: WeatherState):
    if not state.show_moon_phase:
        return
    s = state.data
    phase_value = text(f'{s.moon_phase}%', style=s_moon_phase)
    infos = [phase_value]

    if state.show_sunrise:
        sunrise_info = hstack([
            sunrise_icon,
            text(s.sunrise_time.strftime('%H:%M'), style=s_sunset_time),
        ], gap=1, align='center')
        infos.append(sunrise_info)

    if state.show_sunset:
        sunset_info = hstack([
            sunset_icon,
            text(s.sunset_time.strftime('%H:%M'), style=s_sunset_time),
        ], gap=1, align='center')
        infos.append(sunset_info)
    return hstack([moon_phase_image(s.moon_phase), vstack(infos, gap=1)], gap=2, align='center')

@cache
def draw_temp_range(
    t_current: float,
    t_high: float,
    t_low: float,
    font: ImageFont.FreeTypeFont = fonts.tamzen__rs) -> Frame:
    '''Generates a vertical range graph of temperatures.'''

    color_high = Color('#967b03')
    color_low = Color('#2d83b4')

    text_high = text(f'{round(t_high)}°', style=TextStyle(font=font, color=color_high.hex))
    text_low = text(f'{round(t_low)}°', style=TextStyle(font=font, color=color_low.hex))
    span = text_high.height + text_low.height + 1

    # Draw the range graph.
    # todo: this can be refactored.

    range_graph = Image.new('RGBA', (5, span), (0, 0, 0, 0))
    d = ImageDraw.Draw(range_graph)

    span = span - 2
    gradient = color_high.range_to(color_low, span)

    color_current = Color('#ffffff')

    high_span = t_high - t_low
    try:
        current_pos = (t_current - t_low) * (span / high_span)
    except ZeroDivisionError:
        current_pos = span // 2

    if current_pos <= 0:
        current_pos = 0
    elif current_pos >= span - 1:
        current_pos = span - 1

    # "flip" the current pos and move it in frame.
    cp = span - current_pos

    d.line([(3, 1), (4, 1)], fill=color_high.hex)
    d.line([(3, span), (4, span)], fill=color_low.hex)

    for x, c in enumerate(gradient):
        d.point([(3, x + 1)], fill=c.hex)

    d.point([
        (0, cp - 1),
        (0, cp), (1, cp),
        (0, cp + 1),
    ], fill=color_current.hex)

    return hstack([
        Frame(range_graph),
        vstack([text_high, text_low], gap=1, align='left'),
    ], gap=1, align='center')


def composer(fs: FrameState):
    fetch_on_start()
    state = WeatherStateManager().get_state(fs)
    s = state.data

    weather_icon.set_icon(f'assets/unicorn-weather-icons/{s.icon_name}.png')

    condition_info = hstack([
        warning_icon if state.is_outdated else None,
        text(s.condition, style=s_condition),
    ], gap=2, align='center')

    main_info = hstack([
        weather_icon.draw(fs.tick),
        hstack([
            text(f'{round(s.temperature)}', style=s_temp_value),
            text('°', style=s_deg_c),
        ], gap=0, align='top'),
        draw_temp_range(s.temperature, s.t_high, s.t_low, fonts.tamzen__rs),
    ], gap=1, align='center')

    weather_info = vstack([
        div(main_info, style=DivStyle(background='#0000002f')),
        div(condition_info, style=DivStyle(background='#0000002f')),
    ], gap=1, align='left')

    weather_stack = [weather_info] #, astronomical_info(state)]

    return vstack(weather_stack, gap=1, align='left')
