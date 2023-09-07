import math
import cairo
import pendulum

from functools import cache
from PIL import Image, ImageDraw, ImageFont
from sympy import Ray, Polygon, pi, deg
from suncalc import get_position, get_times

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


def deg_to_rad(deg):
    return deg * (math.pi / 180) % (2 * math.pi)


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

def sun_times(t):
    times = get_times(t.in_tz('UTC'), config.pw_longitude, config.pw_latitude)
    return {k: time_to_angle(pendulum.instance(v).in_tz('local').time()) for k, v in times.items()}

def analog_clock(fs, w: int, h: int):
    t = fs.now
    # t = pendulum.now().set(hour=7, month=3)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    surface_day = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    surface_night = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    surface_mask_day = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    surface_mask_night = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)

    theta = time_to_angle(t.time())
    suntimes = sun_times(t)
    is_day = theta < suntimes['sunset']
    bg_color = SkyHues.day_sky if is_day else SkyHues.night_sky

    sun_path_radius = 22
    sun_radius = 2

    cx = w / 2
    cy = h / 2

    sun_x = cx + sun_path_radius * math.cos(theta)
    sun_y = cy + sun_path_radius * math.sin(theta)

    hyp = math.sqrt(cx ** 2 + cy ** 2)

    ctx = cairo.Context(surface)
    ctx.set_source_rgba(*bg_color.rgb, 1)
    ctx.rectangle(0, 0, w, h)
    ctx.fill()

    def draw_arc(ctx, start, end, color):
        ctx.set_source_rgba(*color.rgb, 1)
        ctx.arc(cx, cy, hyp, start, end)
        ctx.line_to(cx, cy)
        ctx.close_path()
        ctx.fill()

    # Sun time sections.
    draw_arc(ctx, suntimes['sunset'], suntimes['sunrise_end'], SkyHues.civil_twilight)
    draw_arc(ctx, suntimes['dusk'], suntimes['dawn'], SkyHues.nautical_twilight)
    draw_arc(ctx, suntimes['nautical_dusk'], suntimes['nautical_dawn'], SkyHues.astronomical_twilight)
    draw_arc(ctx, suntimes['night'], suntimes['night_end'], SkyHues.night)

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

    # Reduce brightness of the background.
    r2 = cairo.RadialGradient(cx, cy, sun_path_radius, cx, cy, hyp)
    r2.add_color_stop_rgba(0, 0, 0, 0, 0)
    r2.add_color_stop_rgba(.8, 0, 0, 0, 1)
    # r1.add_color_stop_rgba(1, *SkyHues.sun_position.rgb, 1)
    ctx.set_source(r2)
    ctx.rectangle(0, 0, w, h)
    ctx.fill()

    # Create masks
    ctx = cairo.Context(surface_mask_day)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.arc(cx, cy, hyp, suntimes['sunrise'], suntimes['sunset'])
    ctx.line_to(cx, cy)
    ctx.close_path()
    ctx.fill()

    ctx = cairo.Context(surface_mask_night)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.arc(cx, cy, hyp, suntimes['sunset'], suntimes['sunrise'])
    ctx.line_to(cx, cy)
    ctx.close_path()
    ctx.fill()

    # Day Sun
    ctx = cairo.Context(surface_day)
    r1 = cairo.RadialGradient(sun_x, sun_y, sun_radius, sun_x, sun_y, 3 * sun_radius)
    r1.add_color_stop_rgba(1, 1, 1, 1, 0.7)
    r1.add_color_stop_rgba(0.2, 1, 1, 0, 0.5)
    r1.add_color_stop_rgba(1, 1, 0.2, 0, 0)
    ctx.set_source(r1)
    ctx.arc(sun_x, sun_y, sun_radius * 2, 0, 2 * math.pi)
    ctx.fill()
    ctx.set_source_rgba(1, 1, 0, 1)
    ctx.arc(sun_x, sun_y, sun_radius, 0, 2 * math.pi)
    ctx.fill()

    # Night Sun
    ctx = cairo.Context(surface_night)
    ctx.set_source_rgba(0, 0, 0, 1)
    ctx.arc(sun_x, sun_y, sun_radius * 1.4, 0, 2 * math.pi)
    ctx.fill_preserve()
    ctx.set_line_width(1)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.stroke()

    i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    blank = i.copy()
    i.alpha_composite(to_pil(surface), (0, 0))
    # i.alpha_composite(to_pil(surface_mask_night), (0, 0))
    i.alpha_composite(Image.composite(to_pil(surface_day), blank.copy(), to_pil(surface_mask_day)), (0, 0))
    i.alpha_composite(Image.composite(to_pil(surface_night), blank.copy(), to_pil(surface_mask_night)), (0, 0))
    # i.alpha_composite(text('12').image, (int(cx), int(cy)))

    label_radius = 25
    # Draw ticks
    def draw_label(time, label):
        theta = time_to_angle(time)
        lx = int(cx + label_radius * math.cos(theta))
        ly = int(cy + label_radius * math.sin(theta))
        place_at(text(label, s_time_tick), i, lx, ly, anchor='mm')

    draw_label(pendulum.time(hour=12), '12')
    draw_label(pendulum.time(hour=00), '24')
    draw_label(pendulum.time(hour=6), '6')
    draw_label(pendulum.time(hour=18), '18')

    return Frame(i)

def composer(fs: FrameState):
    return div(analog_clock(fs, config.matrix_w, config.matrix_h))
