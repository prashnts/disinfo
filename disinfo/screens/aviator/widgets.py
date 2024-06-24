from disinfo.components.elements import Frame
from disinfo.data_structures import FrameState
from disinfo.components.widget import Widget
from disinfo.components.layers import div, DivStyle
from disinfo.components.layouts import hstack, vstack
from disinfo.components.text import TextStyle, text
from disinfo.components.transitions import text_slide_in
from disinfo.components import fonts
from disinfo.utils.cairo import load_svg, load_svg_string
from disinfo.screens.colors import gray

from .state import ADSBxStateManager
from .markers import shapes, svg_shape_to_svg, get_base_marker

icons = {
    'plane': load_svg('assets/mui-icons/plane.svg'),
    'helicopter': load_svg('assets/mui-icons/helicopter.svg'),
}

category_mapping = {
    'A7': 'helicopter',
}


def flight_icon(plane: dict) -> str:

    shape_name, scale = get_base_marker(plane.get('category', 'A3'), altitude=plane.get('alt_baro', 0))
    shape = shapes[shape_name]

    return load_svg_string(svg_shape_to_svg(shape, fillColor='#225679', strokeColor='#229649', strokeWidth=0.1, scale=0.8*scale, angle=plane.get('track', 0)))


def airplane_widget(fs: FrameState, plane: dict) -> Widget:
    distance = plane.get('distance') or 9000
    kind = category_mapping.get(plane.get('category')) or 'plane'
    hexname = plane.get('hex') or '000000'
    alt = plane.get('alt_baro') or -69
    alt = 0 if type(alt) == str else alt
    frame = hstack([
        # icons[kind],
        flight_icon(plane),
        vstack([
            text_slide_in(fs, f'avi.w.{plane["hex"]}.flight', plane.get('flight').strip(), TextStyle(font=fonts.px_op_mono_8, color='#106822')),
            hstack([
                hstack([
                    text_slide_in(fs, f'avi.w.{plane["hex"]}.alt', f"{alt:0d}", TextStyle(font=fonts.bitocra7, color=gray.darken(0.2).hex)),
                    text('m', TextStyle(font=fonts.bitocra7, color=gray.darken(0.3).hex)),
                ], align='bottom', gap=1),
                hstack([
                    text_slide_in(fs, f'avi.w.{plane["hex"]}.dist', f"{plane.get('distance'):0.1f}", TextStyle(font=fonts.bitocra7, color=gray.darken(0.1).hex)),
                    text('km', TextStyle(font=fonts.bitocra7, color=gray.darken(0.3).hex)),
                ], align='bottom', gap=1),
            ], gap=2),
        ], gap=2),
    ])
    return Widget(name=f'aviator.airplane_widget.{hexname}', frame=frame, priority=2, wait_time=20, focus=distance <= 3)

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
    'track': 265.25,
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
    'distance': 17.05826323753527
}


def planes(fs: FrameState) -> list[Widget]:
    planes = ADSBxStateManager().get_state(fs)
    widgets = [airplane_widget(fs, plane) for plane in planes if plane['distance'] <= 80]
    return widgets
