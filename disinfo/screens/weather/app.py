from dataclasses import replace as dc_replace
import numpy as np

from colour import Color
from functools import cache
from PIL import Image, ImageDraw

from disinfo import fonts
from discore.elements import Frame, StillImage
from discore.text import TextStyle, text
from discore.layers import div, DivStyle, shapes
from discore.scroller import HScroller
from discore.layouts import hstack, vstack, composite_at, place_at, Spacer
from discore.spriteim import SpriteIcon
from discore.data_structures import FrameState
from discore.elements import Box
from disinfo.screens.colors import light_gray

from . import vigilance, graphs
from disinfo.screens.aviator import skystate
from .state import get_weather_data
from .assets import temperature_color


weather_icon = SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=.05)
moon_icon = StillImage('assets/moon/moon08.png', resize=(25, 25))
sunset_arrow = SpriteIcon('assets/sunset-arrow.png', step_time=.2)
warning_icon = StillImage('assets/sync.png')
# sunset_icon = StillImage('assets/raster/sunset-11x5.png')
sunset_icon = StillImage('assets/raster/sunset-7x9.png')
sunrise_icon = StillImage('assets/raster/sunrise-7x7.png')

s_temp_value = TextStyle(font=fonts.px_op__l, color=light_gray.darken(0.1).hex)
s_condition = TextStyle(font=fonts.tamzen__rs, color='@fg3')
s_sunset_time = TextStyle(font=fonts.bitocra7, color='@fg3')
s_moon_phase = TextStyle(font=fonts.bitocra7, color='#818284')
s_deg_c = TextStyle(font=fonts.px_op__r, color=light_gray.darken(0.1).hex)
s_forecast = TextStyle(font=fonts.bitocra7, color='#7fb5e8')
vigil_colors = {2: '#e0b400', 3: '#f7a401', 4: '#e03030'}      # yellow, orange, red: a warning is a pill of its colour
s_vigil = TextStyle(font=fonts.bitocra7, color='#000000')



@cache
def moon_phase_image(phase: int) -> StillImage:
    return StillImage(f'assets/moon/moon{phase:02d}.png', resize=(15, 15))


def astronomical_info(fs: FrameState):
    if not (state := get_weather_data(fs)):
        return
    s = state.data
    phase_value = div(text(f'{s.moon_phase}%', style=s_moon_phase), DivStyle(background='@scrim'))
    infos = []

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
    return hstack([
        composite_at(phase_value, moon_phase_image(s.moon_phase), 'br'),
        vstack(infos, gap=1),
    ], gap=2, align='center')

@cache
def range_graph(t_current: float, t_high: float, t_low: float, width: int) -> Frame:
    '''Gradient from min to max temperature, a pointer at the current one.'''
    span = width - 1
    range_graph = Image.new('RGBA', (width, 5), (0, 0, 0, 0))
    d = ImageDraw.Draw(range_graph)

    if t_high > t_low:
        current_pos = (t_high - t_current) * (span / (t_high - t_low))
    else:
        current_pos = span // 2
    current_pos = min(max(current_pos, 1), span - 1)

    gradient = [temperature_color(x) for x in np.linspace(t_low, t_high, span - 1)]
    for x, c in enumerate(gradient):
        d.point([(x + 1, 0), (x + 1, 1)], fill=c.hex)

    # Pointer at the current temperature.
    cp = span - current_pos
    d.point([(cp, 3), (cp - 1, 4), (cp, 4), (cp + 1, 4)], fill='#ffffff')
    return Frame(range_graph, hash=('range-graph', t_current, t_high, t_low, width))

class RangeBar(Box):
    '''The range graph, as wide as its row lets it be.'''
    grow = 1

    def __init__(self, t_current: float, t_high: float, t_low: float, min_width: int = 13):
        self.t = (t_current, t_high, t_low)
        self.min_width = min_width
        self.hash = ('RangeBar', self.t, min_width)

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        return min(self.min_width, max_w), 5

    def render(self, w: int, h: int) -> Frame:
        return range_graph(*self.t, max(w, 3))

def temp_range(t_current: float, t_high: float, t_low: float) -> Frame:
    '''Min and max temperatures, the range graph between them.'''
    # HA sometimes collapses today's forecast (high == low), keep the current temp in range.
    t_low, t_high = min(t_low, t_high, t_current), max(t_low, t_high, t_current)
    value = lambda t: text(f'{round(t)}', style=TextStyle(font=fonts.ttpixels, color=temperature_color(t).hex)).trim(upper=0)
    return hstack([value(t_low), RangeBar(t_current, t_high, t_low), value(t_high)], gap=2, align='bottom')


def vigil_lines(now: float, tick: float, width: int) -> Frame | None:
    '''What Météo-France warns of (rain, cold first), then the next rain and the lowest temperature: one line, scrolled
    in the card's own width, so the card does not change.'''
    parts = [div(text(t, style=s_vigil), dc_replace(shapes.pill, background=vigil_colors[c]))
             for c, t in vigilance.lines(now)]
    parts += [text(t, style=s_forecast) for t in vigilance.forecast_lines(now)]
    if not parts:
        return None
    line = hstack(parts, gap=6, align='center')
    return HScroller(size=width, pause_at_loop=True, name='weather.vigil').set_frame(line).draw(tick)

def composer(fs: FrameState):
    if not (state := get_weather_data(fs)):
        return
    s = state.data

    weather_icon.set_icon(f'assets/unicorn-weather-icons/{s.icon_name}.png')

    # Temperature centered, range graph across.
    card = vstack([
        hstack([
            Spacer(),
            composite_at(warning_icon if state.is_outdated else None, weather_icon.draw(fs.tick), 'br'),
            hstack([
                text(f'{s.temperature}', style=s_temp_value),
                text('°', style=s_deg_c),
            ], gap=0, align='top'),
            Spacer(),
        ], gap=2, align='bottom'),
        temp_range(s.temperature, s.t_high, s.t_low),
    ], gap=3, align='hstretch')
    if warn := vigil_lines(fs.now.timestamp(), fs.tick, card.width):
        card = vstack([card, warn], gap=3, align='hstretch')
    # The graphs under it while the metro has the bottom stack; a touch opens them (or shuts them).
    on, where = graphs.shown(fs)
    more = graphs.graphs(fs, skystate.doc(), card.width, on and where == 'side', 'side')
    base = card.hash
    if more:
        card = vstack([card, more], gap=3, align='hstretch')
    return Frame(card.image, hash=('weather.card', base), targets=(graphs.toggle(fs, on)(card.width, card.height),))

def extended(fs: FrameState) -> Frame | None:
    '''The graphs in a card of their own (the bottom stack's), the metro down. A touch shuts it.'''
    on, where = graphs.shown(fs)
    if not on or where != 'bottom':
        return None
    w = min(fs.config.width - 16, graphs.max_width)
    if not (f := graphs.graphs(fs, skystate.doc(), w, True, 'bottom')):
        return None
    return Frame(f.image, hash=('weather.graphs', w), targets=(graphs.toggle(fs, on)(f.width, f.height),))
