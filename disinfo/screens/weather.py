import pendulum

from colour import Color
from functools import cache
from pydantic import BaseModel
from typing import Optional
from pydash import once
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

from .screen import draw_loop
from ..components import fonts
from ..components.elements import Frame, StillImage
from ..components.text import TextStyle, text
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.spriteim import SpriteIcon
from ..data_structures import FrameState
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..redis import publish


weather_icon = SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=.05)
sunset_arrow = SpriteIcon('assets/sunset-arrow.png', step_time=.2)
warning_icon = StillImage('assets/sync.png')
sunset_icon = StillImage('assets/raster/sunset-11x5.png')

s_temp_value = TextStyle(font=fonts.px_op__l, color='#9a9ba2')
s_condition = TextStyle(font=fonts.tamzen__rs, color='#5b5e64')
s_sunset_time = TextStyle(font=fonts.bitocra, color='#5b5e64')
s_deg_c = TextStyle(font=fonts.px_op__r, color='#6E7078')


fetch_on_start = once(lambda: publish('di.pubsub.dataservice', action='fetch_weather'))

class WeatherData(BaseModel):
    temperature: float = 25.0
    condition: str = 'Sunny'
    icon_name: str = 'clear-day'
    t_high: float = 30.0
    t_low: float = 20.0
    sunset_time: Optional[datetime]
    updated_at: Optional[datetime]

class WeatherState(BaseModel):
    data: WeatherData = WeatherData()
    valid: bool = False
    should_show_sunset: bool = False
    is_outdated: bool = True

class WeatherStateManager(PubSubStateManager[WeatherState]):
    model = WeatherState
    channels = ('di.pubsub.weather',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            forecast = data.payload
            _today = forecast['daily']['data'][0]
            self.state.data = WeatherData(
                temperature=forecast['currently']['apparentTemperature'],
                condition=forecast['currently']['summary'],
                icon_name=forecast['currently']['icon'],
                t_high=_today['temperatureHigh'],
                t_low=_today['temperatureLow'],
                sunset_time=pendulum.from_timestamp(_today['sunsetTime'], tz='local'),
                updated_at=pendulum.from_timestamp(forecast['currently']['time'], tz='local'),
            )
            self.state.valid = True

    def get_state(self, fs: FrameState) -> WeatherState:
        if not self.state.valid:
            return self.state
        s = self.state.data
        self.state.should_show_sunset = s.sunset_time > fs.now and (s.sunset_time - fs.now).total_seconds() < 2 * 60 * 60
        self.state.is_outdated = (fs.now - s.updated_at).total_seconds() > 30 * 60  # 30 mins.
        return self.state



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

    condition_info = [
        warning_icon if state.is_outdated else None,
        text(s.condition, style=s_condition),
    ]

    main_info = [
        hstack([
            weather_icon.draw(fs.tick),
            hstack([
                text(f'{round(s.temperature)}', style=s_temp_value),
                text('°', style=s_deg_c),
            ], gap=0, align='top'),
            draw_temp_range(s.temperature, s.t_high, s.t_low, fonts.tamzen__rs),
        ], gap=1, align='center'),
    ]

    if state.should_show_sunset:
        sunset_info = hstack([
            sunset_icon,
            text(s.sunset_time.strftime('%H:%M'), style=s_sunset_time),
        ], gap=1, align='center')
        main_info.append(sunset_info)

    weather_info = vstack([
        div(
            hstack(main_info, gap=2, align='top'),
            style=DivStyle(background='#000000ac'),
        ),
        div(
            hstack(condition_info, gap=2, align='center'),
            style=DivStyle(background='#000000ac'),
        ),
    ], gap=1, align='left')

    weather_stack = [weather_info]

    return vstack(weather_stack, gap=1, align='left')


draw = draw_loop(composer, sleepms=100)
