import math
import cairocffi as cairo

from functools import cache
from typing import NamedTuple

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
from disinfo.drat.app_states import RuntimeStateManager

from .state import ADSBxStateManager, OpenedStateManager
from .colors import marker_color
from .flags import find_icao_range
from .app import chevron, on_top, pill, number, map_up, view_mode
from . import lookup


card_width = 75
photo_size = (card_width, 38)
# Fixed widths: longer text scrolls, slowly.
callsign_width = card_width - 9 - 7 - 3 * 2    # the icon, the flag, the gaps
airline_width = 34
scroll_speed = 0.1         # s a pixel: slow, and fewer frames changed for the displays
class Look(NamedTuple):
    callsign: TextStyle
    value: TextStyle
    muted: TextStyle
    unit: TextStyle
    tiny: TextStyle
    tiny_dim: TextStyle
    credit: TextStyle
    arrow: TextStyle        # bitocra has no arrows.
    overhead: TextStyle
    widget: DivStyle
    over: str               # the card's bottom over the photo

def look_of(c: dict, widget: DivStyle, over: str) -> Look:
    return Look(
        TextStyle(font=fonts.px_op_mono_8, color=c['callsign']), TextStyle(font=fonts.bitocra7, color=c['value']),
        TextStyle(font=fonts.bitocra7, color=c['muted']), TextStyle(font=fonts.bitocra7, color=c['unit']),
        TextStyle(font=fonts.microfont_35_reg, color=c['muted']), TextStyle(font=fonts.microfont_35_reg, color=c['unit']),
        TextStyle(font=fonts.exsmall, color=c['unit']), TextStyle(font=fonts.scientifica__r, color=c['unit']),
        TextStyle(font=fonts.bitocra7, color=c['overhead']), widget, over)

dark = look_of(
    {'callsign': '#3fa05a', 'value': '#a6a6a6', 'muted': '#808080', 'unit': '#5b5e64', 'overhead': '#b7925e'},
    DivStyle(padding=3, radius=3, background='#0a1a3a50', border=1, border_color='#00000088'), '#0a1a3a60')
# The light map (a medium grey behind): the texts darker, on a paler card.
light = look_of(
    {'callsign': '#12612c', 'value': '#1c1e24', 'muted': '#33363e', 'unit': '#464a52', 'overhead': '#7a4f10'},
    DivStyle(padding=3, radius=3, background='#e6eaf270', border=1, border_color='#00000066'), '#e6eaf2a0')._replace(credit=dark.credit)   # over the photo's dark strip

def looks(fs: FrameState) -> Look:
    return light if OpenedStateManager().get_state(fs).light else dark


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

def value(fs: FrameState, k: Look, v: str, unit: str, name: str, arrow: str = '') -> Frame:
    return hstack([text_slide_in(fs, v, k.value, name=name), text(unit, k.unit), text(arrow, k.arrow) if arrow else None], align='bottom', gap=1)

compass = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

def where(k: Look, p: dict) -> Frame:
    # Where to look from the window: the direction and how high above the horizon. How far from home.
    d = p['dist']
    far = hstack([text(f'{d:.1f}' if d < 10 else f'{d:.0f}', k.value), text('km', k.unit)], gap=1, align='bottom')
    if p['elev'] >= 60:
        return hstack([text('overhead', k.overhead), far], gap=2, align='bottom')
    return hstack([text(compass[round(p['bearing'] / 45) % 8], k.muted), text(f'{round(p["elev"])}', k.value), text('°', k.arrow), far], gap=1, align='bottom')

def photo(k: Look, photo: dict) -> Frame | None:
    # Cropped to photo_size, the photographer in its corner.
    pic = lookup.photo_frame(photo['src'], photo_size) if photo.get('src') else None
    if not pic:
        return None
    w, h = pic.size
    x, y = (w - photo_size[0]) // 2, (h - photo_size[1]) // 2
    pic = Frame(pic.image.crop((x, y, x + photo_size[0], y + photo_size[1])), ('aviator.photo', photo['src'])).brightness(0.85)
    credit = div(text(photo['by'] or '', k.credit, overflow='fit'), padding=(1, 1, 1, 2), background='#00000090')
    return composite_at(credit, pic, 'tr')

def scrolling(fs: FrameState, f: Frame, width: int, name: str) -> Frame:
    return HScroller(size=width, pause_at_loop=True, speed=scroll_speed, name=name).set_frame(f).draw(fs.tick)

def card(fs: FrameState, p: dict, active: bool) -> Frame:
    # Compact. The one on top of the stack has the photo, the callsign and route on frost over its bottom.
    k = looks(fs)
    uname = lambda x: f'avi.{p["hex"]}.{x}'
    route = lookup.route(p) or {}
    pic = photo(k, lookup.photo(p) or {}) if active else None
    color = marker_color(p['alt']).hex
    trend = '↑' if p['vr'] > 120 else '↓' if p['vr'] < -120 else ''

    head = hstack([
        # Its number on the map, or its icon turned like the map is.
        pill(n, color) if (n := number(ADSBxStateManager().get_state(fs), p['hex'])) else plane_icon(round((p['track'] - map_up(fs)) / 15) * 15 % 360, color),
        scrolling(fs, text(route.get('number') or p['flight'] or p['r'] or p['hex'], k.callsign), callsign_width, uname('callsign')),
        Spacer(),
        flag(p['hex']),
    ], gap=1, align='center')
    places = route.get('from'), route.get('to')
    # adsbdb has stale routes, some go nowhere.
    places = places if all(places) and places[0] != places[1] else (None, None)
    trip = hstack([
        hstack([text(places[0]['iata'] or '?', k.value), text('→', k.arrow), text(places[1]['iata'] or '?', k.value)], gap=2, align='bottom') if all(places) else None,
        Spacer(),
        where(k, p),
    ], gap=2, align='bottom')
    stats = hstack([
        value(fs, k, f'{p["alt"]}', 'm', uname('alt'), trend),
        Spacer(),
        value(fs, k, f'{p["gs"]}', 'km/h', uname('gs')),
    ], gap=3, align='bottom')
    kind = hstack([
        text(p['t'] or '', k.tiny),
        text(p['r'] or '', k.tiny_dim),
        Spacer(),
        scrolling(fs, text(route.get('airline') or '', k.tiny_dim), airline_width, uname('airline')) if route.get('airline') else None,
    ], gap=3)

    if pic:
        over = div(vstack([head, trip], gap=2), padding=(2, 2, 1, 2), background=k.over, width=card_width-3)
        top = composite_at(over, pic, 'bl', frost=2)
    else:
        top = vstack([head, trip], gap=3)
    f = div(vstack([top, stats, kind], gap=3), width=card_width)
    # The tag changes when the route comes in or the photo shows, so the widget animates the resize.
    return Frame(f.image, targets=(Target(0, 0, f.width, f.height, 'aviator.close', {'hex': p['hex']}),)).tag(('aviator.card', p['hex'], all(places), bool(pic), k is light))


def tile(fs: FrameState, planes: list[dict]) -> Frame:
    # One line for the planes seen from the window, scrolling: their number on the map, callsign, route, where to look.
    k = looks(fs)
    st = ADSBxStateManager().get_state(fs)
    def item(p: dict) -> Frame:
        route = lookup.route(p) or {}
        places = route.get('from'), route.get('to')
        return hstack([
            pill(number(st, p['hex']) or 0, marker_color(p['alt']).hex),
            text(route.get('number') or p['flight'] or p['r'] or p['hex'], k.value),
            hstack([text(places[0]['iata'] or '?', k.tiny), text('→', k.arrow), text(places[1]['iata'] or '?', k.tiny)], gap=1, align='center') if all(places) and places[0] != places[1] else None,
            where(k, p),
        ], gap=2, align='center')
    line = hstack([item(p) for p in planes], gap=8, align='center')
    return scrolling(fs, line, card_width, 'avi.tile').tag(('aviator.tile', tuple(p['hex'] for p in planes), k is light))

def planes(fs: FrameState) -> list[Widget]:
    # A card for the planes passing overhead and the one tapped, a tile for the others seen from the window.
    k = looks(fs)
    st = ADSBxStateManager().get_state(fs)
    opened = OpenedStateManager().get_state(fs).opened
    carded = [h for h in dict.fromkeys([*opened, *st.overhead]) if h in st.planes]
    seen = [st.planes[h] for h in st.watched if h in st.planes and h not in carded]
    # Cards hidden (the web page's show_planes): theirs first in the tile.
    if not (show := RuntimeStateManager().get_state(fs).show_planes):
        seen, carded = [st.planes[h] for h in carded] + seen, []
    shown = on_top(fs)
    # After the other cards (the printer's, the music's): they take the stack only when tapped.
    # On top of the stack, they bring the radar behind (the map or the sky).
    cards = [Widget(f'aviator.{h}', frame=card(fs, st.planes[h], h == shown), background='aviator', style=k.widget, priority=0.4, focus=h in opened, wait_time=10)
             for h in carded]
    # Not 'aviator.<hex>': the radar follows the cards only.
    # The solar view keeps to the planes passing overhead.
    if not seen or (view_mode(fs) == 'solar' and show):
        return cards
    return cards + [Widget('aviator-tile', frame=tile(fs, seen), background='aviator', style=k.widget, priority=0.3, wait_time=10)]
