'''The land under the radar: what the map is made of, drawn in layers, the more significant over the less.

A source gives features (osm.Feature: a kind, a size, shapes in km east and north of home). styles says how a kind
looks and where it goes. Another source (metro lines...) adds its features and its styles.
'''
import math
import cairocffi as cairo

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
    'motorway': Style(4, (0.95, 0.75, 0.35, 0.35), 1),
}
# The light mode: the same kinds on a mid grey, a little stronger.
light_styles = {
    'builtup': Style(0, (0.80, 0.82, 0.90, 0.10)),
    'green': Style(1, (0.35, 0.78, 0.45, 0.30)),
    'water': Style(2, (0.30, 0.58, 1.00, 0.42)),
    'coast': Style(3, (0.30, 0.58, 1.00, 0.55), 1),
    'river': Style(3, (0.30, 0.58, 1.00, 0.50), 1.5),
    'motorway': Style(4, (1.00, 0.80, 0.40, 0.45), 1),
}
round_km = 0.5          # the corners' radius
sources = [osm.features]

_paths = {}             # id of the feature's parts -> its cairo path
_order = (0, [])        # (how many features, sorted)
_drawn = {}             # (w, h) -> (view, the drawing)


def path_of(f) -> list:
    # Built once, in km: cairo keeps a path in user space, so it's drawn under any view.
    if (p := _paths.get(id(f.parts))) is None:
        ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1))
        closed = styles[f.kind].width is None   # the same in both modes
        for part in f.parts:
            if len(part) > 2 or not closed:
                rounded(ctx, part, closed, round_km)
        p = _paths[id(f.parts)] = ctx.copy_path()
    return p

def ordered(now: float) -> list:
    global _order
    feats = [f for source in sources for f in source(now) if f.kind in styles]
    if _order[0] != len(feats):
        _order = len(feats), sorted(feats, key=lambda f: (styles[f.kind].rank, -f.size))
    return _order[1]

def view_matrix(cx: float, cy: float, s: float, up: float, w: int, h: int) -> cairo.Matrix:
    # km east and north of home to px: turned so the bearing up is up, (cx, cy) in the middle, s px per km.
    c, sn = math.cos(math.radians(up)), math.sin(math.radians(up))
    return cairo.Matrix(s * c, -s * sn, -s * sn, -s * c, w / 2 - cx * s, h / 2 + cy * s)

def draw(ctx: cairo.Context, now: float, view: tuple[float, float, float], up: float, w: int, h: int, light: bool = False):
    # The same view as last time (the camera at rest, the planes moving) is painted from the last drawing.
    feats = ordered(now)
    key = (*(round(v, 3) for v in view), up, len(feats), light)
    if (cached := _drawn.get((w, h))) is None or cached[0] != key:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        paint(cairo.Context(surface), feats, view, up, w, h, light_styles if light else styles)
        cached = _drawn[w, h] = key, surface
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
        px, py = zip(*(m.transform_point(x, y) for x in (x0, x1) for y in (y0, y1)))
        if max(px) < 0 or min(px) > w or max(py) < 0 or min(py) > h:
            continue
        st = look[f.kind]
        ctx.new_path()
        ctx.append_path(path_of(f))
        ctx.set_source_rgba(*st.color)
        if st.width is None:
            ctx.fill()
        else:
            ctx.set_line_width(st.width / s)
            ctx.stroke()
