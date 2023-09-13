import numpy as np

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
from disinfo.screens.colors import light_gray
from disinfo.redis import publish

from .state import WeatherStateManager, WeatherState
from .assets import temperature_color


weather_icon = SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=.05)
moon_icon = StillImage('assets/moon/moon08.png', resize=(25, 25))
sunset_arrow = SpriteIcon('assets/sunset-arrow.png', step_time=.2)
warning_icon = StillImage('assets/sync.png')
# sunset_icon = StillImage('assets/raster/sunset-11x5.png')
sunset_icon = StillImage('assets/raster/sunset-7x9.png')
sunrise_icon = StillImage('assets/raster/sunrise-7x7.png')

s_temp_value = TextStyle(font=fonts.px_op__l, color=light_gray.darken(0.1).hex)
s_condition = TextStyle(font=fonts.tamzen__rs, color='#5b5e64')
s_sunset_time = TextStyle(font=fonts.bitocra7, color='#5b5e64')
s_moon_phase = TextStyle(font=fonts.px_op__r, color='#58595c', outline=1, outline_color='#000000')
s_deg_c = TextStyle(font=fonts.px_op__r, color=light_gray.darken(0.1).hex)


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
def draw_temp_range(t_current: float, t_high: float, t_low: float) -> Frame:
    '''Generates a horizontal range graph of min/max temperatures.'''
    color_low = temperature_color(t_low)
    color_high = temperature_color(t_high)
    color_current = Color('#ffffff')

    value_high = text(f'{round(t_high)}', style=TextStyle(font=fonts.bitocra7, color=color_high.hex)).trim(upper=1)
    value_low = text(f'{round(t_low)}', style=TextStyle(font=fonts.bitocra7, color=color_low.hex)).trim(upper=1)

    temp_range_stack = hstack([value_low, value_high], gap=9, align='center')

    span = temp_range_stack.width - 2

    range_graph = Image.new('RGBA', (span + 1, 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(range_graph)

    try:
        current_pos = (t_high - t_current) * (span / (t_high - t_low))
    except ZeroDivisionError:
        current_pos = span // 2

    if current_pos <= 0:
        current_pos = 1
    elif current_pos >= span - 1:
        current_pos = span - 1

    # d.line([(1, 0), (1, 1)], fill=color_low.hex)
    # d.line([(span - 1, 0), (span - 1, 1)], fill=color_high.hex)

    g_step = (t_high - t_low) / (span - 1)
    gradient = [temperature_color(x) for x in np.arange(t_low, t_high, g_step)]
    for x, c in enumerate(gradient):
        d.point([(x + 1, 0)], fill=c.hex)

    # Draw a pointer at the current temperature.
    cp = span - current_pos
    d.point([
                     (cp, 2),
        (cp - 1, 3), (cp, 3), (cp + 1, 3),
    ], fill=color_current.hex)

    return vstack([temp_range_stack, Frame(range_graph)], gap=0, align='center')


def composer(fs: FrameState):
    fetch_on_start()
    state = WeatherStateManager().get_state(fs)
    s = state.data

    weather_icon.set_icon(f'assets/unicorn-weather-icons/{s.icon_name}.png')

    weather_info = div(
        vstack([
            hstack([
                weather_icon.draw(fs.tick).rescale(1),
                hstack([
                    text(f'{round(s.temperature)}', style=s_temp_value),
                    text('°', style=s_deg_c),
                ], gap=0, align='top'),
            ], gap=2, align='bottom'),
            draw_temp_range(s.temperature, s.t_high, s.t_low),
            warning_icon if state.is_outdated else None,
        ], gap=3, align='left'),
        style=DivStyle(background='#0000008f', padding=2, radius=2))

    weather_stack = [weather_info] #, astronomical_info(state)]

    return vstack(weather_stack, gap=1, align='left')
