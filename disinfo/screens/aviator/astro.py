'''Stars and the moon in the sky view: where they are from home, approximately (a degree is plenty on an LED panel).

The bright stars are real (J2000 right ascension in hours, declination in degrees, magnitude): Orion's belt, the Big
Dipper, Cassiopeia and the brightest others; the faint ones are random, the same every time.
'''
import math
import random
import numpy as np
import cairocffi as cairo

from datetime import datetime, timezone
from suncalc.suncalc import getMoonPosition

bright = [
    (6.752, -16.72, -1.46), (14.261, 19.18, -0.05), (18.616, 38.78, 0.03), (5.278, 45.998, 0.08), (5.242, -8.20, 0.13),
    (7.655, 5.225, 0.34), (5.919, 7.407, 0.5), (19.846, 8.87, 0.77), (4.599, 16.51, 0.85), (16.49, -26.43, 1.06),
    (13.42, -11.16, 0.97), (7.755, 28.03, 1.14), (20.69, 45.28, 1.25), (10.14, 11.97, 1.35), (2.53, 89.26, 2.0), (7.577, 31.89, 1.58),
    (5.679, -1.943, 1.77), (5.603, -1.202, 1.69), (5.533, -0.299, 2.23),                                    # Orion's belt
    (11.062, 61.751, 1.8), (11.031, 56.382, 2.37), (11.897, 53.695, 2.44), (12.257, 57.033, 3.3),
    (12.900, 55.960, 1.77), (13.399, 54.925, 2.27), (13.792, 49.313, 1.86),                                  # the Big Dipper
    (0.675, 56.537, 2.24), (0.153, 59.15, 2.27), (0.945, 60.717, 2.47), (1.43, 60.24, 2.68), (1.907, 63.67, 3.35),   # Cassiopeia
]
faint = 140


def catalog() -> np.ndarray:
    # (ra deg, dec deg, magnitude)
    rnd = random.Random(1609)       # Galileo's telescope
    rows = [(ra * 15, dec, mag) for ra, dec, mag in bright]
    rows += [(rnd.uniform(0, 360), math.degrees(math.asin(rnd.uniform(-1, 1))), rnd.uniform(3, 5)) for _ in range(faint)]
    return np.array(rows, np.float32)

_catalog = catalog()

def sidereal(t: float, lon: float) -> float:
    '''Local sidereal time, degrees.'''
    return (280.46061837 + 360.98564736629 * (t / 86400 + 2440587.5 - 2451545.0) + lon) % 360

def stars_at(t: float, lat: float, lon: float):
    '''(bearing, altitude, magnitude) of the stars over the horizon, degrees.'''
    ra, dec, mag = _catalog.T
    H = np.radians(sidereal(t, lon) - ra)
    d, phi = np.radians(dec), math.radians(lat)
    alt = np.degrees(np.arcsin(np.sin(phi) * np.sin(d) + np.cos(phi) * np.cos(d) * np.cos(H)))
    az = np.degrees(np.arctan2(-np.cos(d) * np.sin(H), np.sin(d) * np.cos(phi) - np.cos(d) * np.sin(phi) * np.cos(H))) % 360
    up = alt > 0
    return az[up], alt[up], mag[up]

def moon_at(t: float, lat: float, lon: float) -> tuple[float, float, float]:
    '''(bearing, altitude, phase) of the moon: phase 0 new, 0.5 full, from the mean synodic month.'''
    p = getMoonPosition(datetime.fromtimestamp(t, timezone.utc), lat, lon)
    age = ((t / 86400 + 2440587.5 - 2451550.1) / 29.530588853) % 1
    return (math.degrees(p['azimuth']) + 180) % 360, math.degrees(p['altitude']), age

def draw_moon(ctx: cairo.Context, x: float, y: float, r: float, phase: float, alpha: float):
    '''A dim disc with its lit part: the right side while waxing, the left while waning (the tilt is not worth it).'''
    f = (1 - math.cos(2 * math.pi * phase)) / 2         # the lit fraction
    glow = cairo.RadialGradient(x, y, r, x, y, r * 5)
    glow.add_color_stop_rgba(0, 0.85, 0.88, 1, 0.14 * alpha * (0.3 + f))
    glow.add_color_stop_rgba(1, 0.85, 0.88, 1, 0)
    ctx.set_source(glow)
    ctx.arc(x, y, r * 5, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_source_rgba(0.55, 0.58, 0.68, 0.22 * alpha)
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.fill()
    if f < 0.02:
        return
    ctx.save()
    ctx.translate(x, y)
    if phase > 0.5:
        ctx.scale(-1, 1)
    ctx.arc(0, 0, r, -math.pi / 2, math.pi / 2)
    ctx.save()
    ctx.scale(max(abs(1 - 2 * f), 0.03), 1)
    if f < 0.5:
        ctx.arc_negative(0, 0, r, math.pi / 2, -math.pi / 2)
    else:
        ctx.arc(0, 0, r, math.pi / 2, 3 * math.pi / 2)
    ctx.restore()
    ctx.close_path()
    ctx.set_source_rgba(0.93, 0.94, 0.98, alpha)
    ctx.fill()
    ctx.restore()

def draw_stars(ctx: cairo.Context, t: float, lat: float, lon: float, to_px, in_view, visible: float):
    '''visible: 0..1, how dark the sky is (and how clear). Twinkles a little, once a second.'''
    if visible <= 0.02:
        return
    az, alt, mag = stars_at(t, lat, lon)
    for i, (b, e, m) in enumerate(zip(az, alt, mag)):
        if not in_view(float(b), 0):
            continue
        px, py = to_px(float(b), float(e))
        a = min(max(1.35 - 0.22 * float(m), 0.25), 1) * visible * (0.82 + 0.18 * math.sin(t * 1.7 + i * 2.3))
        ctx.set_source_rgba(1, 0.97, 0.92, a)
        ctx.rectangle(round(px), round(py), 2 if m < 1 else 1, 2 if m < 1 else 1)
        ctx.fill()
