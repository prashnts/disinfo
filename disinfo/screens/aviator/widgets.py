import math
import cairocffi as cairo

from functools import cache

from discore.cairo import to_pil
from discore.elements import Frame, Target
from discore.data_structures import FrameState
from discore.widget import Widget
from discore.layers import div, DivStyle
from discore.layouts import hstack, vstack, Spacer, composite_at
from discore.text import TextStyle, text
from discore.transitions import text_slide_in
from discore.scroller import HScroller
from discore.cairo import load_svg_string
from disinfo import fonts

from .state import ADSBxStateManager, OpenedStateManager
from .colors import marker_color
from .flags import find_icao_range
from .app import chevron, on_top, pill, number, map_up, view_mode
from . import lookup


card_width = 80
photo_size = (card_width, 48)
# Fixed widths: longer text scrolls, slowly.
callsign_width = card_width - 9 - 7 - 3 * 2    # the icon, the flag, the gaps
airline_width = 34
scroll_speed = 0.1         # s a pixel: slow, and fewer frames changed for the displays
callsign_style = TextStyle(font=fonts.px_op_mono_8, color='#3fa05a')
value_style = TextStyle(font=fonts.bitocra7, color='#a6a6a6')
muted_style = TextStyle(font=fonts.bitocra7, color='#808080')
unit_style = TextStyle(font=fonts.bitocra7, color='#5b5e64')
tiny_style = TextStyle(font=fonts.microfont_35_reg, color='#808080')
tiny_dim_style = TextStyle(font=fonts.microfont_35_reg, color='#5b5e64')
credit_style = TextStyle(font=fonts.exsmall, color='#5b5e64')
# bitocra has no arrows.
arrow_style = TextStyle(font=fonts.scientifica__r, color='#5b5e64')
widget_style = DivStyle(padding=3, radius=3, background='#0a1a3a50', border=1, border_color='#00000088')


@cache
def plane_icon(track: int, color: str) -> Frame:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 9, 9)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*marker_color_rgb(color))
    chevron(ctx, 4.5, 4.5, track, 3)
    ctx.fill()
    return Frame(to_pil(surface), hash=('aviator.icon', track, color))

def marker_color_rgb(hex: str) -> tuple[float, float, float]:
    return tuple(int(hex[i:i + 2], 16) / 255 for i in (1, 3, 5))

@cache
def flag(hexid: str) -> Frame | None:
    cc = find_icao_range(hexid).get('country_code', '').upper()
    if not cc:
        return None
    with open(f'assets/flags/3x2/{cc}.svg', 'r') as fp:
        svg = f'<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 7 7">{fp.read()}</svg>'
    return load_svg_string(svg)

def value(fs: FrameState, v: str, unit: str, name: str, arrow: str = '') -> Frame:
    return hstack([text_slide_in(fs, v, value_style, name=name), text(unit, unit_style), text(arrow, arrow_style) if arrow else None], align='bottom', gap=1)

compass = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

def where(p: dict) -> Frame:
    # Where to look from the window: the direction and how high above the horizon. How far from home.
    d = p['dist']
    far = hstack([text(f'{d:.1f}' if d < 10 else f'{d:.0f}', value_style), text('km', unit_style)], gap=1, align='bottom')
    if p['elev'] >= 60:
        return hstack([text('overhead', TextStyle(font=fonts.bitocra7, color='#b7925e')), far], gap=2, align='bottom')
    return hstack([text(compass[round(p['bearing'] / 45) % 8], muted_style), text(f'{round(p["elev"])}', value_style), text('°', arrow_style), far], gap=1, align='bottom')

def photo(photo: dict) -> Frame | None:
    # Cropped to photo_size, the photographer in its corner.
    pic = lookup.photo_frame(photo['src'], photo_size) if photo.get('src') else None
    if not pic:
        return None
    w, h = pic.size
    x, y = (w - photo_size[0]) // 2, (h - photo_size[1]) // 2
    pic = Frame(pic.image.crop((x, y, x + photo_size[0], y + photo_size[1])), ('aviator.photo', photo['src'])).brightness(0.85)
    credit = div(text(photo['by'] or '', credit_style, overflow='fit'), padding=(1, 1, 1, 2), background='#00000090')
    return composite_at(credit, pic, 'tr')

def scrolling(fs: FrameState, f: Frame, width: int, name: str) -> Frame:
    return HScroller(size=width, pause_at_loop=True, speed=scroll_speed, name=name).set_frame(f).draw(fs.tick)

def card(fs: FrameState, p: dict, active: bool) -> Frame:
    # Compact. The one on top of the stack has the photo, the callsign and route on frost over its bottom.
    uname = lambda x: f'avi.{p["hex"]}.{x}'
    route = lookup.route(p) or {}
    pic = photo(lookup.photo(p) or {}) if active else None
    color = marker_color(p['alt']).hex
    trend = '↑' if p['vr'] > 120 else '↓' if p['vr'] < -120 else ''

    head = hstack([
        # Its number on the map, or its icon turned like the map is.
        pill(n, color) if (n := number(ADSBxStateManager().get_state(fs), p['hex'])) else plane_icon(round((p['track'] - map_up(fs)) / 15) * 15 % 360, color),
        scrolling(fs, text(route.get('number') or p['flight'] or p['r'] or p['hex'], callsign_style), callsign_width, uname('callsign')),
        Spacer(),
        flag(p['hex']),
    ], gap=2, align='center')
    places = route.get('from'), route.get('to')
    # adsbdb has stale routes, some go nowhere.
    places = places if all(places) and places[0] != places[1] else (None, None)
    trip = hstack([
        hstack([text(places[0]['iata'] or '?', value_style), text('→', arrow_style), text(places[1]['iata'] or '?', value_style)], gap=2, align='bottom') if all(places) else None,
        Spacer(),
        where(p),
    ], gap=2, align='bottom')
    stats = hstack([
        value(fs, f'{p["alt"]}', 'm', uname('alt'), trend),
        Spacer(),
        value(fs, f'{p["gs"]}', 'km/h', uname('gs')),
    ], gap=3, align='bottom')
    kind = hstack([
        text(p['t'] or '', tiny_style),
        text(p['r'] or '', tiny_dim_style),
        Spacer(),
        scrolling(fs, text(route.get('airline') or '', tiny_dim_style), airline_width, uname('airline')) if route.get('airline') else None,
    ], gap=3)

    if pic:
        over = div(vstack([head, trip], gap=2), padding=(2, 2, 1, 2), background='#0a1a3a60', width=card_width)
        top = composite_at(over, pic, 'bl', frost=2)
    else:
        top = vstack([head, trip], gap=3)
    f = div(vstack([top, stats, kind], gap=3), width=card_width)
    # The tag changes when the route comes in or the photo shows, so the widget animates the resize.
    return Frame(f.image, targets=(Target(0, 0, f.width, f.height, 'aviator.close', {'hex': p['hex']}),)).tag(('aviator.card', p['hex'], all(places), bool(pic)))


def tile(fs: FrameState, planes: list[dict]) -> Frame:
    # One line for the planes seen from the window, scrolling: their number on the map, callsign, route, where to look.
    st = ADSBxStateManager().get_state(fs)
    def item(p: dict) -> Frame:
        route = lookup.route(p) or {}
        places = route.get('from'), route.get('to')
        return hstack([
            pill(number(st, p['hex']) or 0, marker_color(p['alt']).hex),
            text(route.get('number') or p['flight'] or p['r'] or p['hex'], value_style),
            hstack([text(places[0]['iata'] or '?', tiny_style), text('→', arrow_style), text(places[1]['iata'] or '?', tiny_style)], gap=1, align='center') if all(places) and places[0] != places[1] else None,
            where(p),
        ], gap=2, align='center')
    line = hstack([item(p) for p in planes], gap=8, align='center')
    return scrolling(fs, line, card_width, 'avi.tile').tag(('aviator.tile', tuple(p['hex'] for p in planes)))

def planes(fs: FrameState) -> list[Widget]:
    # A card for the planes passing overhead and the one tapped, a tile for the others seen from the window.
    st = ADSBxStateManager().get_state(fs)
    opened = OpenedStateManager().get_state(fs).opened
    carded = [h for h in dict.fromkeys([*opened, *st.overhead]) if h in st.planes]
    seen = [st.planes[h] for h in st.watched if h in st.planes and h not in carded]
    shown = on_top(fs)
    # After the other cards (the printer's, the music's): they take the stack only when tapped.
    # On top of the stack, they bring the radar behind (the map or the sky).
    cards = [Widget(f'aviator.{h}', frame=card(fs, st.planes[h], h == shown), background='aviator', style=widget_style, priority=0.4, focus=h in opened, wait_time=10)
             for h in carded]
    # Not 'aviator.<hex>': the radar follows the cards only.
    # The solar view keeps to the planes passing overhead.
    if not seen or view_mode(fs) == 'solar':
        return cards
    return cards + [Widget('aviator-tile', frame=tile(fs, seen), background='aviator', style=widget_style, priority=0.3, wait_time=10)]
