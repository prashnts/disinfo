import arrow

from colour import Color
from functools import cache
from PIL import Image, ImageDraw, ImageFont

from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.redis import rkeys, get_dict
from disp_info.sprite_icons import SpriteIcon, SpriteImage
from disp_info.utils import throttle


weather_icon = SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=.05)
sunset_arrow = SpriteIcon('assets/sunset-arrow.png', step_time=.2)
warning_icon = SpriteImage('assets/sync.png')[0]

color_temp = '#9a9ba2'
color_deg_c = '#6E7078'
color_condition = '#5b5e64'

text_temperature_value = Text(font=fonts.px_op__l, fill=color_temp)
text_temperature_degree = Text('°', font=fonts.px_op__r, fill=color_deg_c)
text_condition = Text(font=fonts.tamzen__rs, fill=color_condition)
text_sunset_time = Text(font=fonts.bitocra, fill=color_condition)


@cache
def draw_temp_range(
    t_current: float,
    t_high: float,
    t_low: float,
    font: ImageFont = fonts.tamzen__rs) -> Frame:
    '''Generates a vertical range graph of temperatures.'''

    color_high = Color('#967b03')
    color_low = Color('#2d83b4')

    text_high = Text(f'{round(t_high)}°', font, color_high.hex)
    text_low = Text(f'{round(t_low)}°', font, color_low.hex)
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

    return stack_horizontal([
        Frame(range_graph),
        stack_vertical([text_high, text_low], gap=1, align='left'),
    ], gap=1, align='center')

@throttle(1123)
def get_state():
    forecast = get_dict(rkeys['weather_data'])
    _today = forecast['daily']['data'][0]

    return dict(
        temperature=forecast['currently']['apparentTemperature'],
        update_time=arrow.get(forecast['currently']['time'], tzinfo='local'),
        condition=forecast['currently']['summary'],
        icon_name=forecast['currently']['icon'],
        t_high=_today['temperatureHigh'],
        t_low=_today['temperatureLow'],
        sunset_time=arrow.get(_today['sunsetTime'], tzinfo='local'),
    )


def draw(step: int):
    s = get_state()

    now = arrow.now()
    should_show_sunset = s['sunset_time'] > now and (s['sunset_time'] - now).total_seconds() < 2 * 60 * 60
    is_outdated = (now - s['update_time']).total_seconds() > 30 * 60  # 30 mins.

    # update values
    text_temperature_value.update(value=f'{round(s["temperature"])}')
    text_condition.update(value=s['condition'])
    text_sunset_time.update(value=s['sunset_time'].strftime('%H:%M'))

    weather_icon.set_icon(f'assets/unicorn-weather-icons/{s["icon_name"]}.png')

    temp_text = stack_horizontal([
        text_temperature_value,
        text_temperature_degree,
    ], gap=0, align='top')

    condition_info = [text_condition]

    if is_outdated:
        condition_info.insert(0, warning_icon)

    weather_info = stack_vertical([
        stack_horizontal([
            weather_icon.draw(step),
            temp_text,
            draw_temp_range(s['temperature'], s['t_high'], s['t_low'], fonts.tamzen__rs),
        ], gap=1, align='center'),
        stack_horizontal(condition_info, gap=2, align='center'),
    ], gap=1, align='left')

    weather_stack = [weather_info]

    if should_show_sunset:
        weather_stack.append(stack_horizontal([
            sunset_arrow.draw(step),
            text_sunset_time,
        ], gap=1, align='center'))

    return stack_vertical(weather_stack, gap=1, align='left')