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
from .skystate import conditions
from . import skystate

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
glow_rgb = (255, 138, 66)
city_rgb = (150, 82, 52)            # the streetlights on the underside of the cloud
cloud_rgb = (0.72, 0.75, 0.82)      # a cloud in daylight
lux_dark, lux_bright = 3, 400       # the room: the sky is 55% as bright when dark, full when bright
room_dark, room_bright = 100, 10000 # the same with the screen's own colour sensor, its clear counts


class Look(NamedTuple):
    zenith: tuple       # 0..1 rgb
    horizon: tuple
    haze: float         # 0..1
    cloud: float
    glow: float         # the sunset's strength, 0..1
    city: float         # the city's light on the cloud, 0..1: night and cloud


def room_counts(fs) -> float | None:
    # The screen's own colour sensor (its telemetry), the last minute's.
    from disinfo.web.telemetry import TelemetryStateManager
    ls = TelemetryStateManager(fs.config.name).get_state(fs).light_sensor
    return ls.rgbc[3] if ls.rgbc and time.time() - ls.received_at < 60 else None

def light_gain(fs) -> float:
    '''The room's light: the screen's own sensor, else the configured one in Home Assistant, else full.'''
    if (v := room_counts(fs)) is not None:
        lo, hi = room_dark, room_bright
    else:
        e = get_entity(fs.config.ambient_light_sensor)
        try:
            v, lo, hi = float(e.state), lux_dark, lux_bright
        except (AttributeError, TypeError, ValueError):
            return 1.0
    k = np.clip((math.log10(max(v, 1)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)), 0, 1)
    return float(0.55 + 0.45 * k)

class Seen(NamedTuple):
    cond: tuple             # (cloud, haze, darker): what look() takes
    deck: float             # the low and mid cloud all around, 0..1
    high: float             # cirrus
    sun: float | None       # the sun out, 0..1; None: nobody knows (night, no source)
    dark: float
    broken: float | None    # the light going up and down
    warmth: float | None    # the light redder (over 0) or bluer than usual
    wet: float              # how hard it rains or snows at home, 0..1 (none with the rain layer off)
    snow: float             # the snow's share of it
    trails: tuple | None = None     # (from what height planes leave trails m, how long they last 0..1, the wind up there u, v m/s)
    wind: float | None = None       # at home, m/s; its gusts; where it comes from (degrees)
    gust: float | None = None
    wind_dir: float | None = None

def seen(fs) -> Seen:
    '''The sky state (skystate.py, made in the data service) for drawing: what's drawn as cloud fades as it's less
    sure. Without it (the data service down), Home Assistant's weather state alone.'''
    d = skystate.doc()
    rain_off = 'rain' in OpenedStateManager().get_state(fs).of('off', fs)
    if d is None:
        e = get_entity(fs.config.weather_entity)
        c = conditions.get(e.state, (0.3, 0.2, 0, 0, 0)) if e else conditions['partlycloudy']
        return Seen(c[:3], 0.0, 0.0, None, c[2], None, None, 0.0 if rain_off else c[3], c[4])
    g = lambda k, default=None: skystate.v(d, k, default)
    sure = lambda k: g(k, 0.0) * min(1.0, 0.4 + ((d['sky'].get(k.split('.')[1]) or {}).get('conf') or 0))
    dark = g('sky.dark', 0.0)
    wet = 0.0 if rain_off else min(g('precip.rate', 0.0) / skystate.rain_home_mm, 1.0)
    trails = None
    if (form := g('air.contrails.form_m')) is not None:
        wind = g('air.wind_high') or {'dir': 0, 'ms': 0}
        r = math.radians(wind['dir'])
        trails = form, g('air.contrails.persist', 0.0), -wind['ms'] * math.sin(r), -wind['ms'] * math.cos(r)
    return Seen((g('sky.cover', 0.3), g('sky.haze', 0.2), 0.6 * dark), sure('sky.deck'), sure('sky.high'), g('sky.sun'),
                dark, g('sky.broken'), g('sky.warmth'), wet, g('precip.snow', 0.0), trails,
                skystate.v(d, 'air.wind', conf=0.3), skystate.v(d, 'air.gust', conf=0.3), g('air.dir'))

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
