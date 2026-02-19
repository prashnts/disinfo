from functools import cache

from disinfo.components.elements import Frame
from disinfo.data_structures import FrameState
from disinfo.components.widget import Widget
from disinfo.components.layers import div, DivStyle
from disinfo.components.layouts import hstack, vstack
from disinfo.components.text import TextStyle, text
from disinfo.components.transitions import text_slide_in
from disinfo.components import fonts
from disinfo.utils.cairo import load_svg_string, load_svg
from disinfo.screens.colors import gray
from disinfo.config import app_config

from .state import ADSBxStateManager
from .markers import shapes, svg_shape_to_svg, get_base_marker
from .colors import marker_color
from .flags import find_icao_range


def flight_icon(category: str, altitude: float, track: float) -> str:
    shape_name, scale = get_base_marker(category, altitude=altitude)
    shape = shapes[shape_name]

    alt = altitude or 0
    alt = 0 if type(alt) == str else alt * 0.3048
    
    svg = svg_shape_to_svg(
        shape,
        fillColor=marker_color(alt).hex,
        strokeColor=marker_color(alt).hex,
        strokeWidth=0,
        scale=0.6*scale,
        angle=track - 90,
    )

    return load_svg_string(svg)

@cache
def flag(hexid: str) -> Frame:
    reg = find_icao_range(hexid)
    country_code = reg.get("country_code", '').upper()

    if not country_code:
        return

    with open(f'assets/flags/3x2/{country_code}.svg', 'r') as fp:
        flag_icon = fp.read()
    
    width = 7
    height = 7
    
    svg = f'<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
    svg += flag_icon
    svg += '</svg>'

    flag_icon = load_svg_string(svg)

    return hstack([
        flag_icon,
        text(reg.get('country_code', '').upper(), TextStyle(font=fonts.bitocra7, color=gray.darken(0.3).hex)),
    ], align='center', gap=1)


def airplane_widget(fs: FrameState, plane: dict) -> Widget:
    distance = plane.get('distance') or 9000
    hexname = plane.get('hex') or '000000'
    alt = plane.get('alt_baro') or -69
    alt = 0 if type(alt) == str else alt * 0.3048
    alt = int(alt)
    frame = hstack([
        flight_icon(plane.get('category', 'A3'), plane.get('alt_baro'), plane.get('track', 0)),
        vstack([
            text_slide_in(fs, plane.get('flight').strip(), name=f'avi.w.{plane["hex"]}.flight', style=TextStyle(font=fonts.px_op_mono_8, color='#106822')),
            hstack([
                flag(hexname),
                hstack([
                    text_slide_in(fs, f"{plane.get('distance'):0.1f}", name=f'avi.w.{plane["hex"]}.dist', style=TextStyle(font=fonts.bitocra7, color=gray.darken(0.1).hex)),
                    text('km', TextStyle(font=fonts.bitocra7, color=gray.darken(0.3).hex)),
                ], align='bottom', gap=1),
                hstack([
                    text_slide_in(fs, f"{alt:0d}", name=f'avi.w.{plane["hex"]}.alt', style=TextStyle(font=fonts.bitocra7, color=gray.darken(0.2).hex)),
                    text('m', TextStyle(font=fonts.bitocra7, color=gray.darken(0.3).hex)),
                ], align='bottom', gap=1),
            ], gap=2),
        ], gap=2),
    ], gap=1)
    return Widget(name=f'aviator.airplane_widget.{hexname}', frame=frame, priority=2, wait_time=10, focus=distance <= 3)

sample_plane = {
    'hex': '4402db',
    'type': 'adsb_icao',
    'flight': 'EJU71TQ ',
    'alt_baro': 5125,
    'alt_geom': 5650,
    'gs': 278.0,
    'ias': 248,
    'tas': 274,
    'mach': 0.42,
    'oat': 14,
    'tat': 24,
    'track': -100.25,
    'track_rate': -0.06,
    'roll': -0.53,
    'mag_heading': 263.5,
    'true_heading': 265.31,
    'baro_rate': -2432,
    'geom_rate': -2240,
    'squawk': '1000',
    'category': 'A3',
    'nav_qnh': 1016.0,
    'nav_altitude_mcp': 4992,
    'lat': 48.900333,
    'lon': 2.175943,
    'nic': 8,
    'rc': 186,
    'seen_pos': 0.6,
    'version': 2,
    'nic_baro': 1,
    'nac_p': 9,
    'nac_v': 1,
    'sil': 3,
    'sil_type': 'perhour',
    'gva': 2,
    'sda': 2,
    'alert': 0,
    'spi': 0,
    'mlat': [],
    'tisb': [],
    'messages': 6512,
    'seen': 0.2,
    'rssi': -24.0,
    'distance': 1.05826323753527
}


def planes(fs: FrameState) -> list[Widget]:
    planes = ADSBxStateManager().get_state(fs)
    # if app_config.devmode:
    #     planes = [sample_plane]
    widgets = [airplane_widget(fs, plane) for plane in planes if plane['distance'] <= 8]
    return widgets
