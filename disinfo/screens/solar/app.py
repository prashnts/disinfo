import math
import cairo
import pendulum
import numpy as np

from functools import cache
from pendulum.time import Time
from PIL import Image
from suncalc import get_position, get_times
from scipy.interpolate import interp1d

from disinfo.data_structures import FrameState

from disinfo.components.elements import Frame
from disinfo.components.layouts import place_at
from disinfo.components.layers import div, DivStyle
from disinfo.components.text import TextStyle, text
from disinfo.components import fonts
from disinfo.screens.colors import SkyHues
from disinfo.config import app_config
from disinfo.utils.func import throttle


s_time_tick = [
    TextStyle(font=fonts.bitocra7, color=SkyHues.label),
    TextStyle(font=fonts.bitocra7, color=SkyHues.tick_dark),
]
s_time_tick_div = DivStyle(radius=2, background=SkyHues.black.hex, padding=[1, 1, 1, 1])

altitude_alpha = [
    # ALT   ALPHA
    [-0.5,    0],
    [-0.2,  0.1],
    [0,     0.6],
    [0.5,     0.8],
    [1,     1],
]
p1_interpolator = interp1d(
    *zip(*altitude_alpha),
    bounds_error=False,
    fill_value=(0, 1),
)
p2_interpolator = interp1d(
    *zip(*[
        # ALT   ALPHA
        [-0.8,    0],
        [-0.2,  0.2],
        [0,     0.6],
        [0.5,   0.8],
        [0.8,   0.5],
        [1,     0.4],
    ]),
    bounds_error=False,
    fill_value=(0, 0.8),
)

@throttle(4000)
def apply_noise(img: Image.Image, noise: float = 0.1):
    pat = np.random.rand(img.height, img.width) * noise
    alpha = np.ones_like(pat)
    pat = np.stack([pat, pat, pat, alpha], axis=2)
    img_arr = np.array(img) / 255
    img_arr = np.clip(img_arr + pat, 0, 1)
    return Image.fromarray(np.uint8(img_arr * 255))


def deg_to_rad(deg):
    return deg * (math.pi / 180) % (2 * math.pi)

def rad_to_deg(rad):
    return rad * (180 / math.pi) % 360


def time_to_angle(t):
    # Returns the angle of the current time in radians.

    # 12:00 is 0 degrees
    # 24 hours = 24 * 60 * 60 = 86400 seconds
    phase = 90
    period = 60 * 60 * 24
    elapsed = t.hour * 60 * 60 + t.minute * 60 + t.second
    return deg_to_rad((((elapsed / period) * 360) + phase) % 360)

def to_pil(surface: cairo.ImageSurface) -> Image.Image:
    format = surface.get_format()
    size = (surface.get_width(), surface.get_height())
    stride = surface.get_stride()

    with surface.get_data() as memory:
        if format == cairo.Format.RGB24:
            return Image.frombuffer(
                "RGB", size, memory.tobytes(),
                'raw', "BGRX", stride)
        elif format == cairo.Format.ARGB32:
            return Image.frombuffer(
                "RGBA", size, memory.tobytes(),
                'raw', "BGRa", stride)
        else:
            raise NotImplementedError(repr(format))

def clamp(value, min_value=0, max_value=1):
    return max(min(value, max_value), min_value)

def sun_times(t):
    times = get_times(t.in_tz('UTC'), app_config.longitude, app_config.latitude)
    position = get_position(t.in_tz('UTC'), app_config.longitude, app_config.latitude)
    utctimes = {k: pendulum.instance(v).in_tz('local') for k, v in times.items()}
    angles = {k: time_to_angle(v.time()) for k, v in utctimes.items()}
    return angles, utctimes, position

def analog_clock(fs, w: int, h: int):
    t = fs.now
    # t = pendulum.now().set(hour=17, minute=00, month=1)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    surface_sun = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)

    theta = time_to_angle(t.time())
    solar_angles, solar_times, solar_pos = sun_times(t)

    cx = w / 2
    cy = h / 2
    hyp = math.sqrt(cx ** 2 + cy ** 2)

    # full circle radius
    rcontain = min(cx, cy)

    sun_path_radius = rcontain * 0.45
    sun_radius = 2

    sun_x = cx + sun_path_radius * math.cos(theta)
    sun_y = cy + sun_path_radius * math.sin(theta)

    ctx = cairo.Context(surface)
    ctx.set_source_rgba(*SkyHues.night_background.rgb, 1)
    ctx.rectangle(0, 0, w, h)
    ctx.fill_preserve()

    pax = cx + hyp * math.cos(solar_angles['dawn'])
    pay = cy + hyp * math.sin(solar_angles['dawn'])
    pbx = cx + hyp * math.cos(solar_angles['dusk'])
    pby = cy + hyp * math.sin(solar_angles['dusk'])

    # Blue Background
    p1 = p1_interpolator(solar_pos['altitude'])
    ra = cairo.RadialGradient(cx, cy, 1, cx, cy, hyp)
    ra.add_color_stop_rgba(0, *SkyHues.sky_blue.rgb, p1)
    ra.add_color_stop_rgba(1, *SkyHues.sky_blue_b.rgb, p1)
    ctx.set_source(ra)
    ctx.fill_preserve()

    p2 = p2_interpolator(solar_pos['altitude'])
    # Violet Streak
    pathorange = cairo.LinearGradient(pay, pbx, pby, pax)
    pathorange.add_color_stop_rgba(0.2, 0, 0, 0, 0)
    pathorange.add_color_stop_rgba(.5, *SkyHues.evening_streak_3.rgb, p2)
    pathorange.add_color_stop_rgba(0.8, 0, 0, 0, 0)
    ctx.set_source(pathorange)
    ctx.fill_preserve()

    # Yellow Streak
    pathorizon = cairo.LinearGradient(pay, pbx, pby, pax)
    pathorizon.add_color_stop_rgba(0, 0, 0, 0, 0)
    pathorizon.add_color_stop_rgba(.2, *SkyHues.evening_streak_2.rgb, p2 / 2)
    pathorizon.add_color_stop_rgba(.5, *SkyHues.evening_streak.rgb, p2)
    pathorizon.add_color_stop_rgba(.7, *SkyHues.evening_streak_2.rgb, p2 / 2)
    pathorizon.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(pathorizon)
    ctx.fill_preserve()

    ctx.fill()

    # Sun time sections.
    sections = [
        (solar_angles['sunset_start'], solar_angles['sunrise_end'], SkyHues.civil_twilight),
        (solar_angles['dusk'], solar_angles['dawn'], SkyHues.nautical_twilight),
        (solar_angles['nautical_dusk'], solar_angles['nautical_dawn'], SkyHues.astronomical_twilight),
        (solar_angles['night'], solar_angles['night_end'], SkyHues.night),
    ]
    for start, end, color in sections:
        ctx.set_source_rgba(*color.rgba)
        ctx.arc(cx, cy, hyp, start, end)
        ctx.line_to(cx, cy)
        ctx.close_path()
        ctx.fill()

    # Draw hours ticks.
    tick_radius = rcontain * 0.4
    tick_len = [4, 2]

    for hour in range(0, 24):
        time = pendulum.time(hour=hour)
        htheta = time_to_angle(time)
        tick_l = tick_len[hour % 2]

        lx = cx + tick_radius * math.cos(htheta)
        ly = cy + tick_radius * math.sin(htheta)
        mx = cx + (tick_radius + tick_l) * math.cos(htheta)
        my = cy + (tick_radius + tick_l) * math.sin(htheta)

        if htheta < solar_angles['sunset'] and htheta > solar_angles['sunrise']:
            ctx.set_source_rgba(0, 0, 0, 1)
        else:
            ctx.set_source_rgba(1, 1, 1, 1)
        ctx.move_to(mx, my)
        ctx.line_to(lx, ly)
        ctx.set_line_width(0.8)
        ctx.stroke()

    # Reduce brightness of the background.
    pat_dark_ring = cairo.RadialGradient(cx, cy, sun_path_radius, cx, cy, hyp)
    pat_dark_ring.add_color_stop_rgba(0, 0, 0, 0, 0)
    pat_dark_ring.add_color_stop_rgba(.4, 0, 0, 0, 0)
    pat_dark_ring.add_color_stop_rgba(.9, 0, 0, 0, 1)

    ctx.set_source(pat_dark_ring)
    ctx.rectangle(0, 0, w, h)
    ctx.fill()

    ctx = cairo.Context(surface_sun)

    # Needle
    needle_radius = rcontain * 0.6
    needle_x = cx + needle_radius * math.cos(theta)
    needle_y = cy + needle_radius * math.sin(theta)

    pat_needle = cairo.RadialGradient(cx, cy, 0, sun_x, sun_y, needle_radius)
    if theta < solar_angles['sunset'] or theta > solar_angles['sunrise']:
        pat_needle.add_color_stop_rgba(0, 0, 0, 0, 0)
        pat_needle.add_color_stop_rgba(0.4, 0, 0, 0, 1)
        pat_needle.add_color_stop_rgba(0.6, 0, 0, 0, 1)
        pat_needle.add_color_stop_rgba(0.8, 0, 0, 0, 0)
    else:
        pat_needle.add_color_stop_rgba(0, 1, 1, 1, 0)
        pat_needle.add_color_stop_rgba(0.4, 1, 1, 1, 1)
        pat_needle.add_color_stop_rgba(0.6, 1, 1, 1, 1)
        pat_needle.add_color_stop_rgba(0.8, 1, 1, 1, 0)

    ctx.set_source(pat_needle)
    ctx.move_to(cx, cy)
    ctx.line_to(needle_x, needle_y)
    ctx.stroke()


    pat_sun_halo = cairo.RadialGradient(sun_x, sun_y, 1, sun_x, sun_y, 3 * sun_radius)
    pat_sun_halo.add_color_stop_rgba(0, 1, 1, 1, 0.7)
    pat_sun_halo.add_color_stop_rgba(0.2, 1, 1, 0, 0.5)
    pat_sun_halo.add_color_stop_rgba(1, 1, 0.2, 0, 0)

    pat_sun_glow = cairo.RadialGradient(sun_x, sun_y, sun_radius * 1, sun_x, sun_y, sun_radius * 6)
    pat_sun_glow.add_color_stop_rgba(0, 1, 1, 1, 0.2)
    pat_sun_glow.add_color_stop_rgba(0.5, 1, 1, 1, 0.1)
    pat_sun_glow.add_color_stop_rgba(1, 1, 1, 1, 0)

    pat_path_circle_light = cairo.RadialGradient(cx, cy, sun_path_radius * 2, sun_x, sun_y, sun_radius)
    pat_path_circle_light.add_color_stop_rgba(0.5, *SkyHues.sun_path_a.rgba)
    pat_path_circle_light.add_color_stop_rgba(.8, *SkyHues.sun_path_b.rgba)
    pat_path_circle_light.add_color_stop_rgba(1, *SkyHues.sun_position.rgba)

    pat_path_circle_dark = cairo.RadialGradient(cx, cy, sun_path_radius * 2, sun_x, sun_y, sun_radius)
    pat_path_circle_dark.add_color_stop_rgba(0.5, *SkyHues.black.rgb, 0)
    pat_path_circle_dark.add_color_stop_rgba(.8, *SkyHues.black.rgb, 1)
    pat_path_circle_dark.add_color_stop_rgba(1, *SkyHues.black.rgb, 1)

    # --------
    # Day Sun
    ctx.arc(cx, cy, hyp, solar_angles['sunrise'], solar_angles['sunset'])
    ctx.line_to(cx, cy)
    ctx.clip()

    # Day Path circle
    # ctx.set_source(pat_path_circle_dark)
    # ctx.arc(cx, cy, sun_path_radius, 0, 2 * math.pi)
    # ctx.set_line_width(1)
    # ctx.stroke()

    ctx.set_source(pat_sun_glow)
    ctx.arc(sun_x, sun_y, sun_radius * 8, 0, 2 * math.pi)
    ctx.fill()

    ctx.set_source(pat_sun_halo)
    ctx.arc(sun_x, sun_y, sun_radius * 2.4, 0, 2 * math.pi)
    ctx.fill()

    ctx.set_source_rgba(1, 1, 0.9, 1)
    ctx.arc(sun_x, sun_y, sun_radius, 0, 2 * math.pi)
    ctx.fill()

    ctx.reset_clip()

    # --------
    # Night Sun

    ctx.arc(cx, cy, hyp, solar_angles['sunset'], solar_angles['sunrise'])
    ctx.line_to(cx, cy)
    ctx.clip()

    # ctx.set_source(pat_path_circle_light)
    # ctx.arc(cx, cy, sun_path_radius, 0, 2 * math.pi)
    # ctx.set_line_width(1)
    # ctx.stroke()

    ctx.set_source_rgba(0, 0, 0, 1)
    ctx.arc(sun_x, sun_y, sun_radius * 1.4, 0, 2 * math.pi)
    ctx.fill_preserve()

    ctx.set_line_width(1)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.stroke()
    ctx.reset_clip()


    i = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    i.alpha_composite(apply_noise(to_pil(surface), 0.03), (0, 0))

    label_radius = tick_radius + 8

    time_ticks = [0, 6, 12, 18]
    for hour in time_ticks:
        time = pendulum.time(hour=hour)
        theta = time_to_angle(time)
        label = time.format('HH')
        lx = round(cx + label_radius * math.cos(theta))
        ly = round(cy + label_radius * math.sin(theta))

        is_day = theta < solar_angles['sunset'] or theta > solar_angles['sunrise']
        place_at(text(label, s_time_tick[is_day]), i, lx, ly, anchor='mm')

    # Place sunset time
    sunset = solar_times['sunset']
    sunset_theta = time_to_angle(sunset.time())
    sunset_radius = min(rcontain / math.sin(sunset_theta) - 5, rcontain / math.cos(2 * math.pi - sunset_theta))
    sunset_label = sunset.format('HH:mm')
    sunset_x = round(cx + sunset_radius * math.cos(sunset_theta))
    sunset_y = round(cy + sunset_radius * math.sin(sunset_theta))
    place_at(text(sunset_label, s_time_tick[0]), i, sunset_x, sunset_y, anchor='ml')

    i.alpha_composite(to_pil(surface_sun), (0, 0))

    return Frame(i)

def composer(fs: FrameState):
    return div(analog_clock(fs, app_config.width, app_config.height))
