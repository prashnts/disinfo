import cairocffi as cairo
import geopy.distance
import math
from pyquery import PyQuery as pq
from functools import cache

from cairosvg.parser import Tree
from cairosvg.surface import PNGSurface

from disinfo.components.elements import Frame
from disinfo.data_structures import FrameState
from disinfo.components.widget import Widget
from disinfo.components.layers import div, DivStyle
from disinfo.components.layouts import hstack, vstack, composite_at
from disinfo.components.text import TextStyle, text
from disinfo.components.transitions import text_slide_in
from disinfo.components import fonts
from disinfo.utils.cairo import load_svg_string, load_svg, to_pil
from disinfo.screens.colors import gray
from disinfo.config import app_config

from .state import ADSBxStateManager
from .markers import shapes, svg_shape_to_svg, get_base_marker
from .colors import marker_color
from .flags import find_icao_range
from .utils import lat_long_zoom_to_xy, bbox, scale_xy_to_screen



@cache
def load_map() -> cairo.ImageSurface:
    w = app_config.width
    h = app_config.height

    with open('out/map.svg', 'r') as f:
        mapsvg = f.read()

    dom = pq(mapsvg.encode())
    dom.attr('id', 'map')

    svg = f'<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
    svg += f'<defs>{dom.outer_html()}</defs>'
    svg += f'<g><use href="#map" x="0" y="0"  width="{w}" height="{h}"/></g>'
    svg += '</svg>'
    
    surface = PNGSurface(Tree(bytestring=svg.encode()), None, 1).cairo
    return surface


@cache
def flight_icon(category: str, altitude: float, track: float, scalefactor: float = 0.6) -> cairo.ImageSurface:
    shape_name, scale = get_base_marker(category, altitude=altitude)
    shape = shapes[shape_name]

    alt = altitude or 0
    alt = 0 if type(alt) == str else alt * 0.3048
    
    svg = svg_shape_to_svg(
        shape,
        fillColor=marker_color(alt).hex,
        strokeColor=marker_color(alt).hex,
        strokeWidth=0.5,
        scale=scalefactor*scale,
        angle=track,
    )

    with open(f'assets/{shape_name}.svg', 'w') as fp:
        fp.write(svg)

    surface = PNGSurface(Tree(bytestring=svg.encode()), None, 1).cairo
    return surface


class RadarSurface:
    def __init__(self):
        ...


def radar(fs: FrameState) -> Frame:
    state = ADSBxStateManager().get_state(fs)
    w = app_config.width
    h = app_config.height

    center = 48.993, 2.515

    span = 16_000, 22_000
    box = bbox(center, span)
    cx, cy = scale_xy_to_screen(*lat_long_zoom_to_xy(*center), box)
    cx = w - cx
    cy = h - cy

    latlonxy = lambda lat, lon: scale_xy_to_screen(*lat_long_zoom_to_xy(lat, lon), box)

    rmax = max(w, h)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    nrings = 5

    # ctx.set_source_surface(load_map(), 0, 0)
    # ctx.paint()

    # for i in range(10):
    #     ...

   
    # for i in range(nrings):
    #     radius = i * rmax / nrings
    #     thick_mul = i * 1.9 / nrings

    #     pattern = cairo.RadialGradient(cx, cy, radius * 0.5, cx, cy, radius)
    #     pattern.add_color_stop_rgba(1, 0, 0.6, 0.1, 1)
    #     pattern.add_color_stop_rgba(0.95, 0, 0.6, 0.1, 0.6)
    #     pattern.add_color_stop_rgba(0.5 * thick_mul, 0, 0.6, 0.1, 0.1)
    #     pattern.add_color_stop_rgba(0, 1, 0.6, 1, 0)

    #     ctx.set_source(pattern)
    #     ctx.arc(cx, cy, radius, 0, 2 * math.pi)
    #     ctx.fill()

    for plane in state:
        if geopy.distance.distance(center, (plane['lat'], plane['lon'])).m > max(span) + 1_000:
            continue
        if plane['alt_baro'] == 'ground':
            plane['alt_baro'] = 0

        try:
            # flight = flight_icon(plane['category'], 1000, plane['track'])
            flight = flight_icon(plane['category'], plane['alt_baro'], plane['track'], 0.3 if plane['alt_baro'] > 15000 else 0.5)
            iw = flight.get_width()
            ih = flight.get_height()
        except KeyError:
            continue
        sx, sy = scale_xy_to_screen(*lat_long_zoom_to_xy(plane['lat'], plane['lon']), box)

        positions = []
        max_pos = 400
        positions = plane['positions'][-max_pos:]

        if plane['alt_baro'] < 25000:
            for i, (lat, lon, alt, track) in enumerate(positions):
                if alt is None:
                    continue
                alt *= 0.3048
                x, y = scale_xy_to_screen(*lat_long_zoom_to_xy(lat, lon), box)
                if i == 0:
                    ctx.move_to(x, y)
                else:
                    prev_pos = positions[i - 1]
                    px, py = scale_xy_to_screen(*lat_long_zoom_to_xy(prev_pos[0], prev_pos[1]), box)
                    ctx.move_to(px, py)
                ctx.set_source_rgba(*marker_color(alt).darken(0.2).rgb, 255)#max_pos - i / max_pos)
                # positions.append((x, y, marker_color(alt).rgba))
                ctx.line_to(x, y)
                ctx.set_line_width(1)
                # ctx.arc(x, y, 0.5, 0, 2 * math.pi)
                ctx.stroke()

        ctx.set_source_surface(flight, sx - iw / 2, sy - ih / 2)
        ctx.paint()
    
    return Frame(to_pil(surface)).tag('radar')
