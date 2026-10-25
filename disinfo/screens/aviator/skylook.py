'''The sky's colours from the sun's height, the weather state and the room's light: a gradient by sun altitude (zenith and
horizon colours, in the spirit of the sky gradients of cpt-city: a purple-pink twilight, an orange horizon at sunset),
greyed and darkened by cloud, a haze band on the horizon, and the sunset's glow (with its reflection under the horizon).
At night the city's light comes back from the cloud: an orange-pink glow over the horizon, the lower the cloud, the higher.
'''
import math
import time
import numpy as np
import cairocffi as cairo

from typing import NamedTuple

from disinfo.utils.hass import get_entity

from .state import OpenedStateManager
from . import weather, daylight

# Sun altitude (degrees) -> zenith and horizon colours (0-255), a little darker than a day sky: it's an LED display.
palette = [
    (-18, (4, 6, 16), (8, 10, 24)),
    (-12, (8, 12, 34), (26, 24, 58)),
    (-6, (16, 20, 56), (104, 54, 86)),      # civil twilight: purple towards pink
    (-1, (30, 36, 86), (196, 98, 74)),      # the sun at the horizon: orange
    (3, (40, 64, 128), (226, 150, 100)),
    (10, (48, 92, 164), (150, 182, 214)),
    (30, (36, 88, 176), (130, 176, 222)),
]
# HA weather state -> (cloud 0..1, haze 0..1, darker, rain or snow 0..1, the snow's share 0..1)
conditions = {
    'sunny': (0, 0.1, 0, 0, 0), 'clear-night': (0, 0.1, 0, 0, 0), 'partlycloudy': (0.35, 0.2, 0, 0, 0), 'cloudy': (0.8, 0.35, 0.1, 0, 0),
    'fog': (1, 0.9, 0.1, 0, 0), 'rainy': (0.9, 0.5, 0.25, 0.4, 0), 'pouring': (1, 0.55, 0.35, 0.85, 0), 'snowy': (0.9, 0.6, 0.15, 0.4, 1),
    'snowy-rainy': (0.9, 0.55, 0.2, 0.3, 0.5), 'hail': (1, 0.5, 0.35, 0.5, 0), 'lightning': (0.9, 0.4, 0.35, 0, 0),
    'lightning-rainy': (1, 0.5, 0.4, 0.6, 0), 'windy': (0.3, 0.15, 0, 0, 0), 'windy-variant': (0.5, 0.2, 0.05, 0, 0), 'exceptional': (0.5, 0.3, 0.1, 0, 0),
}
glow_rgb = (255, 138, 66)
city_rgb = (150, 82, 52)            # the streetlights on the underside of the cloud
cloud_rgb = (0.72, 0.75, 0.82)      # a cloud in daylight
rain_home_mm = 6        # mm/h at home that is a downpour
snow_c = (0, 2)         # °C at home: snow under the first, rain over the second, sleet between
lux_dark, lux_bright = 3, 400       # the room: the sky is 55% as bright when dark, full when bright


class Look(NamedTuple):
    zenith: tuple       # 0..1 rgb
    horizon: tuple
    haze: float         # 0..1
    cloud: float
    glow: float         # the sunset's strength, 0..1
    city: float         # the city's light on the cloud, 0..1: night and cloud


def light_gain(fs) -> float:
    e = get_entity(fs.config.ambient_light_sensor)
    try:
        lux = float(e.state)
    except (AttributeError, TypeError, ValueError):
        return 1.0
    k = np.clip((math.log10(max(lux, 1)) - math.log10(lux_dark)) / (math.log10(lux_bright) - math.log10(lux_dark)), 0, 1)
    return float(0.55 + 0.45 * k)

def weather_state(fs) -> tuple[float, float, float] | None:
    '''None: no state from Home Assistant (a state it has no entry for counts as a little cloud).'''
    e = get_entity(fs.config.weather_entity)
    return None if e is None else conditions.get(e.state, (0.3, 0.2, 0, 0, 0))

def temperature() -> float | None:
    # °C at home this hour, from the weather card's forecast (AROME).
    from disinfo.screens.weather.vigilance import forecast_doc
    d = forecast_doc()
    return min(d['hours'], key=lambda r: abs(r[0] - time.time()))[2] if d and d['hours'] else None

def wetness(fs) -> tuple[float, tuple | None, float]:
    '''How hard it rains or snows at home, 0..1 (the radar or the weather state; none with the rain layer off), the
    weather state and the snow's share, 0..1: the state's, else the temperature's.'''
    state = weather_state(fs)
    prof = weather.sky_profile('rain')
    wet = 0.0 if 'rain' in OpenedStateManager().get_state(fs).off else max(min((prof[1] if prof else 0) / rain_home_mm, 1), state[3] if state else 0)
    # The state says what falls when it says something falls; the radar doesn't tell rain from snow.
    if state and state[3] > 0:
        snow = state[4]
    else:
        t = temperature()
        snow = 0.0 if t is None else float(np.clip((snow_c[1] - t) / (snow_c[1] - snow_c[0]), 0, 1))
    return wet, state, snow

def measured(state: tuple | None, cloud: float | None) -> tuple[tuple, float | None, dict | None]:
    '''The weather state and the cloud over home, with what the light by the window says (daylight.py) over them:
    it dims the sky as much as the cloud dims the light. Its doc when it says something (not at night, shutter down).'''
    cond = state or conditions['partlycloudy']
    dl = daylight.doc()
    if not dl or dl['source'] != 'light':
        return cond, cloud, None
    return (cond[0], cond[1], max(cond[2], 0.5 * dl['dark']), *cond[3:]), dl['cloud'], dl

def look(sun_alt: float, cond: tuple, gain: float = 1.0, cloud: float | None = None, warmth: float | None = None) -> Look:
    '''cloud overrides the weather state's (the satellite's, when there is no state, or the light's). warmth: the light's
    colour, redder (over 0) or bluer than usual: a stronger or weaker sunset.'''
    at = [a for a, _, _ in palette]
    zen = np.array([np.interp(sun_alt, at, [z[i] for _, z, _ in palette]) for i in range(3)])
    hor = np.array([np.interp(sun_alt, at, [h[i] for _, _, h in palette]) for i in range(3)])
    c, haze, dark, *_ = cond
    c = c if cloud is None else cloud
    grey = lambda v: np.full(3, v @ [0.3, 0.59, 0.11])
    # Cloud takes the colour out and the light down; the horizon keeps a little of the sunset through it.
    zen = (zen * (1 - 0.65 * c) + grey(zen) * 0.65 * c) * (1 - 0.3 * dark - 0.1 * c)
    hor = (hor * (1 - 0.5 * c) + grey(hor) * 0.5 * c) * (1 - 0.2 * dark)
    glow = max(0, 1 - abs(sun_alt - 1) / 9) * (1 - 0.75 * c) * (float(np.clip(1 + warmth, 0.5, 1.6)) if warmth else 1)
    city = float(np.clip((-sun_alt - 2) / 8, 0, 1)) * c * gain
    return Look(tuple(np.clip(zen * gain / 255, 0, 1)), tuple(np.clip(hor * gain / 255, 0, 1)), haze, c, glow, city)

def cloud_color(lk: Look, wet: float = 0) -> tuple:
    # A cloud is as bright as the sky behind it: white-grey by day, dark at night with the city's light under it,
    # darker the more it rains.
    day = min(max(max(lk.horizon) * 1.4, 0.12), 1)
    return tuple(min(c * day * (1 - 0.35 * wet) + city_rgb[i] / 255 * 0.45 * lk.city, 1) for i, c in enumerate(cloud_rgb))

def paint(ctx: cairo.Context, lk: Look, w: int, hz: int, h: int, glow_x: float | None, below: bool = True):
    '''The gradient, the haze over the horizon, the sunset glow around glow_x (px, None: out of view) and its reflection.'''
    g = cairo.LinearGradient(0, 0, 0, hz)
    g.add_color_stop_rgb(0, *lk.zenith)
    g.add_color_stop_rgb(1, *lk.horizon)
    ctx.set_source(g)
    ctx.rectangle(0, 0, w, hz)
    ctx.fill()
    if lk.haze > 0.05:
        # Light, desaturated air along the horizon: higher in a fog.
        hc = tuple(0.5 * v + 0.5 * 0.62 for v in lk.horizon)
        top = hz * (1 - 0.3 - 0.6 * lk.haze)
        g = cairo.LinearGradient(0, top, 0, hz)
        g.add_color_stop_rgba(0, *hc, 0)
        g.add_color_stop_rgba(1, *hc, min(0.55 * lk.haze + 0.1, 0.7))
        ctx.set_source(g)
        ctx.rectangle(0, top, w, hz - top)
        ctx.fill()
    if lk.city > 0.03:
        top = hz * (1 - 0.35 - 0.4 * lk.city)
        g = cairo.LinearGradient(0, top, 0, hz)
        g.add_color_stop_rgba(0, *(v / 255 for v in city_rgb), 0)
        g.add_color_stop_rgba(1, *(v / 255 for v in city_rgb), 0.5 * lk.city)
        ctx.set_source(g)
        ctx.rectangle(0, top, w, hz - top)
        ctx.fill()
    if glow_x is not None and lk.glow > 0.02:
        r, gg, b = (v / 255 for v in glow_rgb)
        for sign, alpha, span in ((1, 0.5, 0.35), (-1, 0.22, 0.2)):        # over the horizon, then its reflection under it
            if sign < 0 and not below:
                continue
            ctx.save()
            ctx.translate(glow_x, hz)
            ctx.scale(w * 0.55, hz * span * 1.6)
            rg = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
            rg.add_color_stop_rgba(0, r, gg, b, alpha * lk.glow)
            rg.add_color_stop_rgba(1, r, gg, b, 0)
            ctx.set_source(rg)
            ctx.rectangle(-1, -1 if sign > 0 else 0, 2, 1)
            ctx.fill()
            ctx.restore()
