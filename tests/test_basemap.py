import os
import math

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

import cairocffi as cairo
from discore.color import resolve

from disinfo.screens.aviator import shapes, osm, basemap
from disinfo.config import app_config


def angles_ok(pts, closed=False):
    pairs = list(zip(pts, pts[1:] + (pts[:1] if closed else [])))
    for (ax, ay), (bx, by) in pairs:
        dx, dy = abs(bx - ax), abs(by - ay)
        assert min(dx, dy) < 1e-6 or abs(dx - dy) < 1e-6, ((ax, ay), (bx, by))

def test_simplify_keeps_the_shape():
    line = [(i / 10, 0.01 * (i % 2)) for i in range(50)]
    assert shapes.simplify(line, 0.1) == [line[0], line[-1]]

def test_octilinear_edges_and_ends():
    pts = [(0, 0), (10, 3), (14, 12), (3, 13), (-2, 5)]
    out = shapes.octilinear(pts, closed=True)
    angles_ok(out, closed=True)
    line = shapes.octilinear([(0, 0), (7, 2), (9, 9)])
    angles_ok(line)
    assert line[0] == (0, 0) and line[-1] == (9, 9)

def test_chains_join_ends():
    c = shapes.chains([[(0, 0), (1, 0)], [(2, 0), (1, 0)], [(2, 0), (2, 1)]])
    assert len(c) == 1 and len(c[0]) == 4
    ring = shapes.chains([[(0, 0), (1, 0), (1, 1)], [(1, 1), (0, 1), (0, 0)]])
    assert len(ring) == 1 and ring[0][0] == ring[0][-1]

def test_rounded_path():
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1))
    shapes.rounded(ctx, [(0, 0), (4, 0), (4, 4), (0, 4)], True, 1)
    kinds = [k for k, _ in ctx.copy_path()]
    assert kinds.count(cairo.PATH_CURVE_TO) == 4

def way(kind_tags, pts):
    la, lo = app_config.latitude, app_config.longitude
    return {'type': 'way', 'tags': kind_tags, 'geometry': [{'lat': la + y / 110.574, 'lon': lo + x / 111.32 / math.cos(math.radians(la))} for x, y in pts]}

def test_build_filters_and_classifies():
    big = [(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)]
    tiny = [(0, 0), (0.1, 0), (0.1, 0.1), (0, 0.1), (0, 0)]
    out = osm.build([
        way({'leisure': 'park'}, big), way({'leisure': 'park'}, tiny),
        way({'natural': 'water'}, big), way({'building': 'yes'}, big),
        way({'highway': 'motorway'}, [(0, 0), (3, 0)]), way({'highway': 'motorway'}, [(3, 0), (6, 1)]),
    ])
    kinds = sorted(f['k'] for f in out)
    assert kinds == ['green', 'motorway', 'water']
    road = next(f for f in out if f['k'] == 'motorway')
    assert road['s'] > 5          # the two ways were joined

def test_draw_nothing_and_something(monkeypatch):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
    ctx = cairo.Context(surface)
    f = osm.feature_of({'k': 'green', 's': 25, 'p': [[(-5, -5), (5, -5), (5, 5), (-5, 5)]]})
    monkeypatch.setattr(basemap, 'sources', [lambda now: [f]])
    basemap._order = (0, [])
    basemap._drawn.clear()
    basemap.draw(ctx, 0, (0, 0, 2), 90, 32, 32)
    assert bytes(surface.get_data())[(16 * 32 + 16) * 4 + 3] > 0

def test_rounded_survives_repeated_points():
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_A8, 1, 1))
    shapes.rounded(ctx, [(0, 0), (0, 0), (4, 0), (4, 0), (4, 4), (0, 4)], True, 1)
    shapes.rounded(ctx, [(0, 0), (0, 0), (4, 0)], False, 1)

def test_refine_loosens_cached_shapes():
    ring = [(x / 5, 0.05 * (x % 2)) for x in range(50)] + [(10, 10), (0, 10)]
    out = osm.refine(ring, 'builtup')
    assert out and len(out) < len(ring) / 2
    angles_ok(out, closed=True)
    assert osm.refine([(0, 0), (0.1, 0), (0, 0.1)], 'builtup') is None

def test_map_up_and_zoom_are_kept(monkeypatch):
    from disinfo.screens.aviator import state
    kept = {}
    monkeypatch.setattr(state, 'db', type('db', (), {'set': lambda self, k, v: kept.update({k: v}), 'get': lambda self, k: kept.get(k)})())
    d = {}
    state.OpenedStateManager.set_all(d, state.MAP_UP_KEY, 'all', 90)
    state.OpenedStateManager.set_all(d, state.MAP_UP_KEY, 'distudy', 270)
    assert state.read_dict(state.MAP_UP_KEY) == {'*': 90, 'distudy': 270}

def test_widget_texts_are_darker_in_light_mode():
    from disinfo.screens.aviator import widgets
    lum = lambda c: resolve(c).lum
    for name in ('callsign', 'value', 'muted', 'unit', 'tiny', 'tiny_dim'):
        assert lum(getattr(widgets.light, name).color) < lum(getattr(widgets.dark, name).color), name

def test_transit_lines_joined_with_dots_at_the_ends():
    la, lo = app_config.latitude, app_config.longitude
    def g(x0, x1):
        return [{'lat': la, 'lon': lo + x / 111.32 / math.cos(math.radians(la))} for x in (x0, x1)]
    def route(members, **tags):
        return {'type': 'relation', 'id': 1, 'tags': {'route': 'subway', 'ref': '7', 'colour': '#FA9ABA', **tags}, 'members': members}
    way = lambda ref, a, b, role='': {'type': 'way', 'ref': ref, 'role': role, 'geometry': g(a, b)}
    stop = {'type': 'node', 'ref': 9, 'role': 'stop', 'lat': la, 'lon': lo}
    # Two directions share their ways; the platform isn't track.
    out = osm.lines_of([route([way(1, 0, 3), way(2, 3, 6), stop, way(3, 1, 2, 'platform')]), route([way(2, 3, 6), way(1, 0, 3)])])
    assert len(out) == 1 and out[0]['k'] == 'metro' and out[0]['c'] == (0.98, 0.6, 0.73)
    assert len(out[0]['p']) == 1 and len(out[0]['e']) == 2
    assert osm.lines_of([route([way(1, 0, 3)], route='bus')]) == []

def test_layers_switched_off(monkeypatch):
    feats = [osm.feature_of({'k': k, 's': 5, 'p': [[(0, 0), (1, 0), (1, 1)]]}) for k in ('green', 'river', 'water', 'metro')]
    monkeypatch.setattr(basemap, 'sources', [lambda now: feats])
    basemap._order = (0, [])
    assert len(basemap.ordered(0)) == 4
    basemap._order = (0, [])
    assert sorted(f.kind for f in basemap.ordered(0, frozenset({'water', 'transit'}))) == ['green']

def test_resize_blends_one_value_for_another_without_a_dip():
    import time
    from PIL import Image
    from types import SimpleNamespace as NS
    from discore.elements import Frame
    from discore.transitions import Resize
    a = Frame(Image.new('RGBA', (20, 10), (200, 50, 50, 255)), ('a',))
    b = Frame(Image.new('RGBA', (20, 10), (50, 50, 200, 255)), ('b',))
    r, t = Resize('dip', 1.0, lambda x: x), time.time()
    r.mut(a)
    r.draw(NS(tick=t))
    r.draw(NS(tick=t + 2))
    r.mut(b).start_at = t + 2
    mid = r.draw(NS(tick=t + 2.5)).image.getpixel((10, 5))
    assert mid[3] == 255 and mid[1] == 50     # opaque, and not darker than both
