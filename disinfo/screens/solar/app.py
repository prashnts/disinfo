import math
import cairo
import pendulum

from functools import cache
from PIL import Image, ImageDraw, ImageFont
from sympy import Ray, Polygon, pi, deg
from suncalc import get_position, get_times
from scipy.interpolate import interp1d

from disinfo.data_structures import FrameState

from disinfo.components.elements import Frame, StillImage
from disinfo.components.layouts import hstack, vstack, composite_at, place_at
from disinfo.components.layers import div, DivStyle
from disinfo.components.text import TextStyle, text
from disinfo.components import fonts
from disinfo.screens.date_time import digital_clock
from disinfo.screens.colors import light_blue, SkyHues, gray
from disinfo import config


s_time_tick = TextStyle(font=fonts.bitocra7, color=SkyHues.label)

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
    times = get_times(t.in_tz('UTC'), config.pw_longitude, config.pw_latitude)
    position = get_position(t.in_tz('UTC'), config.pw_longitude, config.pw_latitude)
    utctimes = {k: pendulum.instance(v).in_tz('local') for k, v in times.items()}
    angles = {k: time_to_angle(v.time()) for k, v in utctimes.items()}
    return angles, utctimes, position

def analog_clock(fs, w: int, h: int):
    t = fs.now
    # t = pendulum.now().set(hour=8, minute=0, month=3)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)

    theta = time_to_angle(t.time())
    solar_angles, solar_times, solar_pos = sun_times(t)

    # print(abs(suntimes['sunset_start'] - suntimes['sunrise_end']))

    sun_path_radius = 22
    sun_radius = 2

    cx = w / 2
    cy = h / 2

    sun_x = cx + sun_path_radius * math.cos(theta)
    sun_y = cy + sun_path_radius * math.sin(theta)

    hyp = math.sqrt(cx ** 2 + cy ** 2)

    ctx = cairo.Context(surface)
    ctx.set_source_rgba(*SkyHues.night_background.rgb, 1)
    ctx.rectangle(0, 0, w, h)
    ctx.fill_preserve()

    # ctx.set_source_rgba(*SkyHues.sky_blue.rgb, clamp(solar_pos['altitude'] + 0.25))
    # ctx.fill_preserve()
    dawn_coords = (cx + hyp * math.cos(solar_angles['dawn']), cy + hyp * math.sin(solar_angles['dawn']))
    dusk_coords = (cx + hyp * math.cos(solar_angles['dusk']), cy + hyp * math.sin(solar_angles['dusk']))

    p1 = p1_interpolator(solar_pos['altitude'])
    ra = cairo.RadialGradient(cx, cy, 1, cx, cy, hyp)
    ra.add_color_stop_rgba(0, *SkyHues.sky_blue.rgb, p1)
    ra.add_color_stop_rgba(1, *SkyHues.sky_blue_b.rgb, p1)
    ctx.set_source(ra)

    # pathorizon = cairo.LinearGradient(0, h, w, 0)
    # pathorizon.add_color_stop_rgba(0, 0, 0, 0, 0)
    # pathorizon.add_color_stop_rgba(.2, *SkyHues.evening_streak_2.rgb, 1)
    # pathorizon.add_color_stop_rgba(.5, *SkyHues.evening_streak.rgb, 1)
    # pathorizon.add_color_stop_rgba(.7, *SkyHues.evening_streak_2.rgb, 1)
    # pathorizon.add_color_stop_rgba(1, 0, 0, 0, 0)

    # ctx.set_source(pathorizon)

    ctx.fill()

    # Sun time sections.
    sections = [
        (solar_angles['sunset_start'], solar_angles['sunrise_end'], SkyHues.civil_twilight, 0.2),
        (solar_angles['dusk'], solar_angles['dawn'], SkyHues.nautical_twilight, 0.4),
        (solar_angles['nautical_dusk'], solar_angles['nautical_dawn'], SkyHues.astronomical_twilight, 0.5),
        (solar_angles['night'], solar_angles['night_end'], SkyHues.night, 0.5),
    ]
    for start, end, color, alpha in sections:
        ctx.set_source_rgba(*color.rgba)
        ctx.arc(cx, cy, hyp, start, end)
        ctx.line_to(cx, cy)
        ctx.close_path()
        ctx.fill()

    # Sun path circle.
    r1 = cairo.RadialGradient(cx, cy, sun_path_radius * 2, sun_x, sun_y, sun_radius)
    r1.add_color_stop_rgba(0.5, *SkyHues.sun_path_a.rgba)
    r1.add_color_stop_rgba(.8, *SkyHues.sun_path_b.rgba)
    r1.add_color_stop_rgba(1, *SkyHues.sun_position.rgba)
    ctx.set_source(r1)
    # ctx.set_source_rgba(1, 1, 1, 1)
    ctx.arc(cx, cy, sun_path_radius, 0, 2 * math.pi)
    ctx.set_line_width(1)
    ctx.stroke()

    # Needle
    needle_radius = 29
    needle_x = cx + needle_radius * math.cos(theta)
    needle_y = cy + needle_radius * math.sin(theta)
    r1 = cairo.RadialGradient(cx, cy, 0, sun_x, sun_y, needle_radius)
    r1.add_color_stop_rgba(0.0, 1, 1, 1, 0)
    r1.add_color_stop_rgba(0.4, 1, 1, 1, 1)
    r1.add_color_stop_rgba(0.6, 1, 1, 1, 1)
    r1.add_color_stop_rgba(0.8, 0, 0, 0, 0)
    ctx.set_source(r1)
    ctx.move_to(cx, cy)
    ctx.line_to(needle_x, needle_y)
    ctx.stroke()

    # Reduce brightness of the background.
    r2 = cairo.RadialGradient(cx, cy, sun_path_radius, cx, cy, hyp)
    r2.add_color_stop_rgba(0, 0, 0, 0, 0)
    r2.add_color_stop_rgba(.4, 0, 0, 0, 0)
    r2.add_color_stop_rgba(.9, 0, 0, 0, 1)
    ctx.set_source(r2)
    ctx.rectangle(0, 0, w, h)
    ctx.fill()

    # Day Sun
    ctx.arc(cx, cy, hyp, solar_angles['sunrise'], solar_angles['sunset'])
    ctx.line_to(cx, cy)
    ctx.clip()

    r1 = cairo.RadialGradient(sun_x, sun_y, 1, sun_x, sun_y, 3 * sun_radius)
    r1.add_color_stop_rgba(0, 1, 1, 1, 0.7)
    r1.add_color_stop_rgba(0.2, 1, 1, 0, 0.5)
    r1.add_color_stop_rgba(1, 1, 0.2, 0, 0)
    r2 = cairo.RadialGradient(sun_x, sun_y, sun_radius * 1, sun_x, sun_y, sun_radius * 6)
    r2.add_color_stop_rgba(0, 1, 1, 1, 0.2)
    r2.add_color_stop_rgba(0.5, 1, 1, 1, 0.1)
    r2.add_color_stop_rgba(1, 1, 1, 1, 0)

    ctx.set_source(r2)
    ctx.arc(sun_x, sun_y, sun_radius * 8, 0, 2 * math.pi)
    ctx.fill()

    ctx.set_source(r1)
    ctx.arc(sun_x, sun_y, sun_radius * 2.4, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_source_rgba(1, 1, 0.9, 1)
    ctx.arc(sun_x, sun_y, sun_radius, 0, 2 * math.pi)
    ctx.fill()

    ctx.reset_clip()

    # Night Sun
    ctx.arc(cx, cy, hyp, solar_angles['sunset'], solar_angles['sunrise'])
    ctx.line_to(cx, cy)
    ctx.clip()
    ctx.set_source_rgba(0, 0, 0, 1)
    ctx.arc(sun_x, sun_y, sun_radius * 1.4, 0, 2 * math.pi)
    ctx.fill_preserve()
    ctx.set_line_width(1)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.stroke()

    i = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    i.alpha_composite(to_pil(surface), (0, 0))

    label_radius = 26
    # Draw ticks
    def draw_label(time, label):
        theta = time_to_angle(time)
        lx = round(cx + label_radius * math.cos(theta))
        ly = round(cy + label_radius * math.sin(theta))
        place_at(text(label, s_time_tick), i, lx, ly, anchor='mm')

    draw_label(pendulum.time(hour=12), '12')
    draw_label(pendulum.time(hour=00), '24')
    draw_label(pendulum.time(hour=6), '6')
    draw_label(pendulum.time(hour=18), '18')

    # i.alpha_composite(Image.composite(to_pil(surface_night), blank.copy(), to_pil(surface_mask_night)), (0, 0))

    return Frame(i)

def composer(fs: FrameState):
    return div(analog_clock(fs, config.matrix_w, config.matrix_h))
