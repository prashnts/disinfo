'''The sky's colours from the sun's height, the weather state and the room's light: a gradient by sun altitude (zenith and
horizon colours, in the spirit of the sky gradients of cpt-city: a purple-pink twilight, an orange horizon at sunset),
greyed and darkened by cloud, a haze band on the horizon, and the sunset's glow (with its reflection under the horizon).
'''
import math
import numpy as np
import cairocffi as cairo

from typing import NamedTuple

from disinfo.utils.hass import get_entity

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
# HA weather state -> (cloud 0..1, haze 0..1, darker)
conditions = {
    'sunny': (0, 0.1, 0), 'clear-night': (0, 0.1, 0), 'partlycloudy': (0.35, 0.2, 0), 'cloudy': (0.8, 0.35, 0.1),
    'fog': (1, 0.9, 0.1), 'rainy': (0.9, 0.5, 0.25), 'pouring': (1, 0.55, 0.35), 'snowy': (0.9, 0.6, 0.15),
    'snowy-rainy': (0.9, 0.55, 0.2), 'hail': (1, 0.5, 0.35), 'lightning': (0.9, 0.4, 0.35),
    'lightning-rainy': (1, 0.5, 0.4), 'windy': (0.3, 0.15, 0), 'windy-variant': (0.5, 0.2, 0.05), 'exceptional': (0.5, 0.3, 0.1),
}
glow_rgb = (255, 138, 66)
lux_dark, lux_bright = 3, 400       # the room: the sky is 55% as bright when dark, full when bright


class Look(NamedTuple):
    zenith: tuple       # 0..1 rgb
    horizon: tuple
    haze: float         # 0..1
    cloud: float
    glow: float         # the sunset's strength, 0..1


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
    return None if e is None else conditions.get(e.state, (0.3, 0.2, 0))

def look(sun_alt: float, cond: tuple, gain: float = 1.0, cloud: float | None = None) -> Look:
    '''cloud overrides the weather state's (the satellite's, when there is no state).'''
    at = [a for a, _, _ in palette]
    zen = np.array([np.interp(sun_alt, at, [z[i] for _, z, _ in palette]) for i in range(3)])
    hor = np.array([np.interp(sun_alt, at, [h[i] for _, _, h in palette]) for i in range(3)])
    c, haze, dark = cond
    c = c if cloud is None else cloud
    grey = lambda v: np.full(3, v @ [0.3, 0.59, 0.11])
    # Cloud takes the colour out and the light down; the horizon keeps a little of the sunset through it.
    zen = (zen * (1 - 0.65 * c) + grey(zen) * 0.65 * c) * (1 - 0.3 * dark - 0.1 * c)
    hor = (hor * (1 - 0.5 * c) + grey(hor) * 0.5 * c) * (1 - 0.2 * dark)
    glow = max(0, 1 - abs(sun_alt - 1) / 9) * (1 - 0.75 * c)
    return Look(tuple(np.clip(zen * gain / 255, 0, 1)), tuple(np.clip(hor * gain / 255, 0, 1)), haze, c, glow)

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
