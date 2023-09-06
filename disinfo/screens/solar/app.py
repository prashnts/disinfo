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
from disinfo.screens.date_time import digital_clock
from disinfo.screens.colors import light_blue, SkyHues
from disinfo import config


def deg_to_rad(deg):
    return deg * (math.pi / 180) % (2 * math.pi)


def time_to_angle(t):
    # Returns the angle of the current time in radians.

    # 12:00 is 0 degrees
    # 24 hours = 24 * 60 * 60 = 86400 seconds
    time = t.time()
    phase = 90
    period = 60 * 60 * 24
    # period = 60
    elapsed = time.hour * 60 * 60 + time.minute * 60 + time.second
    # elapsed = t.second % period
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
    return {k: time_to_angle(pendulum.instance(v).in_tz('local')) for k, v in times.items()}

def draw_background(fs, w: int, h: int):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)

    theta = time_to_angle(fs.now)
    suntimes = sun_times(fs.now)
    is_day = theta < suntimes['sunset']
    bg_color = SkyHues.day_sky if is_day else SkyHues.night_sky

    sun_path_radius = 22
    sun_radius = 2

    cx = w / 2
    cy = h / 2

    # now_arrow = Ray((w_m, h_m), angle=theta)
    # end = border.intersection(now_arrow)[0]
    sun_x = cx + sun_path_radius * math.cos(theta)
    sun_y = cy + sun_path_radius * math.sin(theta)

    hyp = math.sqrt((cx) ** 2 + (cy) ** 2)

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

    draw_arc(ctx, suntimes['sunset'], suntimes['sunrise_end'], SkyHues.civil_twilight)
    draw_arc(ctx, suntimes['dusk'], suntimes['dawn'], SkyHues.nautical_twilight)
    draw_arc(ctx, suntimes['nautical_dusk'], suntimes['nautical_dawn'], SkyHues.astronomical_twilight)
    draw_arc(ctx, suntimes['night'], suntimes['night_end'], SkyHues.night)


    r1 = cairo.RadialGradient(cx, cy, sun_path_radius * 2, sun_x, sun_y, sun_radius)
    r1.add_color_stop_rgba(0, *SkyHues.sun_path.rgb, 0)
    r1.add_color_stop_rgba(.9, *SkyHues.sun_path.rgb, 1)
    r1.add_color_stop_rgba(1, *SkyHues.sun_position.rgb, 1)
    ctx.set_source(r1)
    # ctx.set_source_rgba(1, 1, 1, 1)
    ctx.arc(cx, cy, sun_path_radius, 0, 2 * math.pi)
    ctx.set_line_width(1)
    ctx.stroke()

    r2 = cairo.RadialGradient(cx, cy, sun_path_radius, cx, cy, hyp)
    r2.add_color_stop_rgba(0, 0, 0, 0, 0)
    r2.add_color_stop_rgba(.8, 0, 0, 0, 1)
    # r1.add_color_stop_rgba(1, *SkyHues.sun_position.rgb, 1)
    ctx.set_source(r2)
    ctx.rectangle(0, 0, w, h)
    ctx.fill()


    # ctx.set_source_rgba(*SkyHues.twilight_blue.rgb, 1)
    # ctx.arc(cx, cy, hyp, sunset_start, sunset_end)
    # ctx.line_to(cx, cy)
    # ctx.close_path()
    # ctx.fill()

    # ctx.set_source_rgba(*SkyHues.dusk_blue.rgb, 1)
    # ctx.arc(cx, cy, hyp, dusk_start, dusk_end)
    # ctx.line_to(cx, cy)
    # ctx.close_path()
    # ctx.fill()

    # ctx.set_source_rgba(*SkyHues.night_blue.rgb, 1)
    # ctx.arc(cx, cy, hyp, ndusk_start, ndusk_end)
    # ctx.line_to(cx, cy)
    # ctx.close_path()
    # ctx.fill()

    def draw_sun(x, y, radius):
        # ctx.set_source_rgba(1, 1, 1, 1)
        r1 = cairo.RadialGradient(x, y, radius, x, y, 3 * radius)
        r1.add_color_stop_rgba(1, 1, 1, 1, 0.7)
        r1.add_color_stop_rgba(0.2, 1, 1, 0, 0.5)
        r1.add_color_stop_rgba(1, 1, 0.2, 0, 0)
        ctx.set_source(r1)
        ctx.arc(x, y, radius * 2, 0, 2 * math.pi)
        ctx.fill()
        ctx.set_source_rgba(1, 1, 0, 1)
        ctx.arc(x, y, radius, 0, 2 * math.pi)
        ctx.fill()

    draw_sun(sun_x, sun_y, sun_radius)
    return Frame(to_pil(surface))

@cache
def generate_angles(w: int, h: int):
    # angles are of 15 deg increments. End coordinate.
    coords = {}
    radius = min(w, h) // 3
    sun_size = 15
    w_m = w // 2
    h_m = h // 2

    border = Polygon((0, 0), (w, 0), (w, h), (0, h))

    for thetadeg in range(0, 360, 1):
        theta = deg_to_rad(thetadeg)
        now_arrow = Ray((w_m, h_m), angle=theta)
        end = border.intersection(now_arrow)[0]
        coords[thetadeg] = (int(end.x), int(end.y))

    return coords


def analog_clock(fs: FrameState, width: int, height: int):
    t = fs.now
    # a clock is a circle with 24 hours.
    # At the top is 12:00.
    # t is the current time.
    # angle = (t.hour * 60 + t.minute) / (24 * 60) * 360
    w = width * 3
    h = height * 3
    radius = min(w, h) // 3
    sun_size = 15
    i = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(i)
    w_m = w // 2
    h_m = h // 2

    # ends = generate_angles(w, h)

    # border = Polygon((0, 0), (w, 0), (w, h), (0, h))
    thetadeg = time_to_angle(t)
    # end = ends[(thetadeg // 15) * 15]
    # end = ends[thetadeg]

    theta = deg_to_rad(time_to_angle(fs.now))

    # now_arrow = Ray((w_m, h_m), angle=theta)
    # end = border.intersection(now_arrow)[0]
    sun_x = int(w_m + radius * math.cos(theta))
    sun_y = int(h_m + radius * math.sin(theta))


    dc = digital_clock(fs).image

    # d.line((w_m, h_m, int(end[0]), int(end[1])), fill=(255, 255, 255, 255), width=3)

    # place_at(draw_sun(sun_size), i, x=sun_x, y=sun_y, anchor='mm')

    img = i.resize((width, height), resample=Image.LANCZOS)
    # img.alpha_composite(dc, (int(end[0]) // 3, int(end[1]) // 3))
    img.alpha_composite(draw_background(fs, width, height).image, (0, 0))

    return Frame(img)

def composer(fs: FrameState):
    return div(analog_clock(fs, config.matrix_w, config.matrix_h))
