'''The land under the radar: what the map is made of, drawn in layers, the more significant over the less.

A source gives features (osm.Feature: a kind, a size, shapes in km east and north of home). styles says how a kind
looks and where it goes. Another source (metro lines...) adds its features and its styles.
'''
import math
import cairocffi as cairo

from cairocffi.context import _encode_path

from typing import NamedTuple

from . import osm
from .shapes import rounded


class Style(NamedTuple):
    rank: int       # drawn in this order, then the bigger ones first: the small ones on top
    color: tuple
    width: float | None = None      # px for a line, None for a fill

styles = {
    'builtup': Style(0, (0.62, 0.62, 0.72, 0.10)),
    'green': Style(1, (0.30, 0.65, 0.40, 0.20)),
    'water': Style(2, (0.25, 0.50, 0.90, 0.30)),
    'coast': Style(3, (0.25, 0.50, 0.90, 0.40), 1),
    'river': Style(3, (0.25, 0.50, 0.90, 0.35), 1.5),
    'motorway': Style(4, (0.72, 0.74, 0.78, 0.18), 1),
    'metro': Style(5, (0.72, 0.74, 0.78, 0.30), 0.6),
    'rer': Style(5, (0.72, 0.74, 0.78, 0.35), 0.8),
}
# The light mode: the same kinds, deeper and more saturated, to show on a medium grey.
light_styles = {
    'builtup': Style(0, (0.18, 0.18, 0.30, 0.14)),
    'green': Style(1, (0.10, 0.50, 0.20, 0.45)),
    'water': Style(2, (0.05, 0.30, 0.85, 0.50)),
    'coast': Style(3, (0.05, 0.30, 0.85, 0.65), 1),
    'river': Style(3, (0.05, 0.30, 0.85, 0.60), 1.5),
    'motorway': Style(4, (0.15, 0.16, 0.20, 0.28), 1),
    'metro': Style(5, (0.15, 0.16, 0.20, 0.38), 0.6),
    'rer': Style(5, (0.15, 0.16, 0.20, 0.42), 0.8),
}
# What the web page switches: layer -> its kinds.
layers = {
    'builtup': ('builtup',),
    'green': ('green',),
    'water': ('water', 'river', 'coast'),
    'roads': ('motorway',),
    'transit': ('metro', 'rer'),
}
tiny_px = 1.5
round_km = 0.5          # the corners' radius
sources = [osm.features]

_paths = {}             # id of the feature's parts -> its cairo path
_order = (0, [])        # ((how many features, the layers off), sorted)
_drawn = {}             # (screen, w, h) -> (view, the drawing)


def path_of(f) -> tuple:
    # Built once, in km: cairo keeps a path in user space, so it's drawn under any view.
    if (p := _paths.get(id(f.parts))) is None:
        ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1))
        closed = styles[f.kind].width is None   # the same in both modes
        for part in f.parts:
            if len(part) > 2 or not closed:
                rounded(ctx, part, closed, round_km)
        # Encoded once for cairo: append_path would do it again at every frame, most of the drawing's time.
        p = _paths[id(f.parts)] = _encode_path(ctx.copy_path())
    return p

def ordered(now: float, off: frozenset = frozenset()) -> list:
    # off: the layers switched off.
    global _order
    hidden = {k for layer in off for k in layers.get(layer, ())}
    feats = [f for source in sources for f in source(now) if f.kind in styles and f.kind not in hidden]
    if _order[0] != (len(feats), off):
        _order = (len(feats), off), sorted(feats, key=lambda f: (styles[f.kind].rank, -f.size))
    return _order[1]

def view_matrix(cx: float, cy: float, s: float, up: float, w: int, h: int) -> cairo.Matrix:
    # km east and north of home to px: turned so the bearing up is up, (cx, cy) in the middle, s px per km.
    c, sn = math.cos(math.radians(up)), math.sin(math.radians(up))
    return cairo.Matrix(s * c, -s * sn, -s * sn, -s * c, w / 2 - cx * s, h / 2 + cy * s)

def draw(ctx: cairo.Context, now: float, view: tuple[float, float, float], up: float, w: int, h: int, light: bool = False, off: frozenset = frozenset(), name: str = ''):
    # The same view as last time (the camera at rest, the planes moving) is painted from the last drawing.
    feats = ordered(now, off)
    key = (*(round(v, 3) for v in view), up, len(feats), light, off)
    if (cached := _drawn.get((name, w, h))) is None or cached[0] != key:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        paint(cairo.Context(surface), feats, view, up, w, h, light_styles if light else styles)
        cached = _drawn[name, w, h] = key, surface
    ctx.set_source_surface(cached[1])
    ctx.paint()

def paint(ctx: cairo.Context, feats: list, view: tuple[float, float, float], up: float, w: int, h: int, look: dict):
    cx, cy, s = view
    m = view_matrix(cx, cy, s, up, w, h)
    ctx.transform(m)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    for f in feats:
        x0, y0, x1, y1 = f.bbox
        # Where its box falls on the screen: the transformed center, the half sizes turned.
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        hw, hh = (x1 - x0) / 2, (y1 - y0) / 2
        ex, ey = abs(m.xx) * hw + abs(m.xy) * hh, abs(m.yx) * hw + abs(m.yy) * hh
        cpx, cpy = m.xx * mx + m.xy * my + m.x0, m.yx * mx + m.yy * my + m.y0
        if cpx + ex < 0 or cpx - ex > w or cpy + ey < 0 or cpy - ey > h:
            continue
        st = look[f.kind]
        # Under a pixel and a half across, an area is a speck: the small parks are most of the features.
        if st.width is None and ex * 2 < tiny_px and ey * 2 < tiny_px:
            continue
        ctx.new_path()
        cairo.cairo.cairo_append_path(ctx._pointer, path_of(f)[0])
        # A line may have its own colour (the metro's), the style's alpha.
        ctx.set_source_rgba(*(f.color or st.color[:3]), st.color[3])
        if st.width is None:
            ctx.fill()
        else:
            ctx.set_line_width(st.width / s)
            ctx.stroke()
            for x, y in f.ends:
                ctx.new_path()
                ctx.arc(x, y, max(st.width * 1.4, 1.2) / s, 0, 2 * math.pi)
                ctx.fill()
