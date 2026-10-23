'''Weather under the radar: the rain mosaic of Météo-France (Licence Ouverte, credit "Météo-France"), resampled on the radar's
flat grid (km east and north of home) so the renderer only has to lay it with the basemap's matrix.

Clouds: EUMETSAT's EUMETView WMS (infrared, no key, credit EUMETSAT).
Wind: Open-Meteo's Météo-France models (AROME, CC-BY 4.0, non-commercial, no key), a grid of points in one request.
Needs h5py, numpy, pyproj (the mosaic is ODIM HDF5 in polar stereographic). Redis only in store(): decode() is pure.
'''
import io
import json
import time
import cairocffi as cairo
import requests

from .utils import home, km_lat, km_lon

RADAR_URL = 'https://public-api.meteofrance.fr/public/DPRadar/v1/mosaiques/METROPOLE/observations/LAME_D_EAU/produit'
RADAR_KEY = 'di.weather.radar'      # JSON: {at, half_km, px_km, scale, png (base64 L)}; the png is mm/h * scale
half_km = 150       # the box around home, each way
px_km = 1.0
scale = 4           # grey level per mm/h: 255 = 64 mm/h


def fetch_radar(key: str) -> bytes:
    r = requests.get(RADAR_URL, params={'maille': 500}, headers={'apikey': key}, timeout=60)
    r.raise_for_status()
    return r.content

def decode(content: bytes) -> tuple[float, 'numpy.ndarray']:
    '''The mosaic -> (end time of the 5 minutes, uint8 rain rate on the flat grid, row 0 = north).'''
    import h5py
    import numpy as np
    from calendar import timegm
    from pyproj import Proj

    f = h5py.File(io.BytesIO(content), 'r')
    d = f['dataset1']
    w = dict(f['where'].attrs)
    proj = Proj(w['projdef'].decode())
    # The corner pixel's centre -> its x,y; rows go south from the upper left.
    x0, y0 = proj(float(w['UL_lon']), float(w['UL_lat']))
    xs, ys = float(w['xscale']), float(w['yscale'])

    n = int(2 * half_km / px_km)
    east = (np.arange(n) + 0.5) * px_km - half_km
    north = half_km - (np.arange(n) + 0.5) * px_km
    lon = home[1] + east[None, :] / km_lon + 0 * north[:, None]
    lat = home[0] + north[:, None] / km_lat + 0 * east[None, :]
    px, py = proj(lon, lat)
    col = np.floor((px - x0) / xs).astype(int)
    row = np.floor((y0 - py) / ys).astype(int)
    raw = d['data1/data']
    ok = (col >= 0) & (col < raw.shape[1]) & (row >= 0) & (row < raw.shape[0])
    v = np.zeros((n, n), np.float32)
    # Only the rows needed: read the block then index it.
    r0, r1, c0, c1 = row[ok].min(), row[ok].max() + 1, col[ok].min(), col[ok].max() + 1
    block = raw[r0:r1, c0:c1].astype(np.float32)
    what = dict(d['data1/what'].attrs)
    got = block[row[ok] - r0, col[ok] - c0]
    got[got >= what['undetect']] = 0                    # undetect and nodata
    v[ok] = got * what['gain'] + what['offset']         # mm over the 5 minutes
    a = dict(d['what'].attrs)
    t = timegm(time.strptime(a['enddate'].decode() + a['endtime'].decode(), '%Y%m%d%H%M%S'))
    return t, np.clip(v * 12 * scale, 0, 255).astype(np.uint8)

def png_of(grey) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(grey, 'L').save(b, 'PNG', optimize=True)
    return b.getvalue()

def store(at: float, grey):
    import base64
    from disinfo.redis import db, publish
    doc = {'at': at, 'half_km': half_km, 'px_km': px_km, 'scale': scale, 'png': base64.b64encode(png_of(grey)).decode()}
    db.set(RADAR_KEY, json.dumps(doc), ex=900)
    publish('weather', 'radar')

def radar_job():
    from disinfo.config import app_config
    key = app_config.meteo_france_api_key__radar
    if not key:
        return
    at, grey = decode(fetch_radar(key.get_secret_value()))
    store(at, grey)

def radar_task():
    '''The scheduled one: no key, no h5py/numpy/pyproj or a failed fetch leaves the last mosaic (it expires after 15 min).'''
    try:
        radar_job()
    except ImportError as e:
        print(f'weather radar off, missing {e.name}')
    except Exception as e:
        print(f'weather radar: {e!r}')


# The rain on the map: transparent under 0.25 mm/h, then light blue -> violet -> pink with the rate; deeper in the light mode.
rain_colors = {
    False: [(0, (0.45, 0.75, 1.0)), (40, (0.55, 0.45, 1.0)), (128, (1.0, 0.45, 0.85))],
    True: [(0, (0.10, 0.35, 0.90)), (40, (0.35, 0.15, 0.85)), (128, (0.80, 0.10, 0.55))],
}
rain_alpha = (0.12, 0.60)       # from a drizzle to 16 mm/h
read_every = 20                 # s between two looks at redis

_rain = {'read': 0.0, 'doc': None}
_rain_surfaces = {}             # (at, light) -> (surface, the pixels it points at)

def rain_doc() -> dict | None:
    now = time.monotonic()
    if now - _rain['read'] > read_every:
        from disinfo.redis import db
        _rain['read'] = now
        try:
            _rain['doc'] = json.loads(db.get(RADAR_KEY) or 'null')
        except ValueError:
            _rain['doc'] = None
    return _rain['doc']

def rain_surface(doc: dict, light: bool) -> cairo.ImageSurface:
    key = doc['at'], light
    if key not in _rain_surfaces:
        import base64
        import numpy as np
        from PIL import Image
        g = np.asarray(Image.open(io.BytesIO(base64.b64decode(doc['png']))).convert('L'), dtype=np.float32)
        stops = rain_colors[light]
        levels = [l for l, _ in stops]
        rgb = [np.interp(g, levels, [c[i] for _, c in stops]) for i in range(3)]
        a = np.interp(g, [1, 64], rain_alpha) * (g >= 1)
        out = np.empty(g.shape + (4,), np.uint8)       # cairo's ARGB32 is B, G, R, A premultiplied on a little-endian machine
        for i, c in enumerate((2, 1, 0)):
            out[..., i] = np.round(rgb[c] * a * 255)
        out[..., 3] = np.round(a * 255)
        _rain_surfaces.clear()
        h, w = g.shape
        data = np.ascontiguousarray(out)
        _rain_surfaces[key] = cairo.ImageSurface.create_for_data(memoryview(data).cast('B'), cairo.FORMAT_ARGB32, w, h), data
    return _rain_surfaces[key][0]

def paint_rain(ctx: cairo.Context, light: bool):
    '''Over the map in km (the view's matrix already applied): north at the top row, 1 px = px_km.'''
    doc = rain_doc()
    if not doc:
        return
    try:
        surface = rain_surface(doc, light)
    except ImportError:
        return
    ctx.save()
    ctx.translate(-doc['half_km'], doc['half_km'])
    ctx.scale(doc['px_km'], -doc['px_km'])
    ctx.set_source_surface(surface)
    ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
    ctx.paint()
    ctx.restore()


WIND_URL = 'https://api.open-meteo.com/v1/meteofrance'
WIND_KEY = 'di.weather.wind'        # JSON: {at, half_km, n, u, v}: the grid's rows from north to south, m/s east and north
wind_n = 7                          # points each way: 7x7 over the box, one request (every 50 km)
wind_half_km = 150

def wind_points() -> list[tuple[float, float]]:
    step = 2 * wind_half_km / (wind_n - 1)
    ks = [wind_half_km - i * step for i in range(wind_n)]
    return [(home[0] + y / km_lat, home[1] + x / km_lon) for y in ks for x in ks[::-1]]

def fetch_wind() -> dict:
    import math
    pts = wind_points()
    r = requests.get(WIND_URL, timeout=30, params={
        'latitude': ','.join(f'{la:.4f}' for la, _ in pts), 'longitude': ','.join(f'{lo:.4f}' for _, lo in pts),
        'current': 'wind_speed_10m,wind_direction_10m', 'wind_speed_unit': 'ms'})
    r.raise_for_status()
    u, v = [], []
    for loc in r.json():
        speed, frm = loc['current']['wind_speed_10m'], math.radians(loc['current']['wind_direction_10m'])
        # The direction is where it comes from: it blows toward the opposite.
        u.append(round(-speed * math.sin(frm), 2))
        v.append(round(-speed * math.cos(frm), 2))
    return {'at': time.time(), 'half_km': wind_half_km, 'n': wind_n, 'u': u, 'v': v}

def wind_job():
    from disinfo.redis import db, publish
    db.set(WIND_KEY, json.dumps(fetch_wind()), ex=3 * 3600)
    publish('weather', 'wind')

def wind_task():
    try:
        wind_job()
    except Exception as e:
        print(f'weather wind: {e!r}')

_wind = {'read': 0.0, 'doc': None}

def wind_doc() -> dict | None:
    now = time.monotonic()
    if now - _wind['read'] > read_every:
        from disinfo.redis import db
        _wind['read'] = now
        try:
            _wind['doc'] = json.loads(db.get(WIND_KEY) or 'null')
        except ValueError:
            _wind['doc'] = None
    return _wind['doc']

def wind_at(doc: dict, x: float, y: float) -> tuple[float, float] | None:
    '''(east, north) m/s at x, y km from home, bilinear in the grid; None outside it.'''
    n, half = doc['n'], doc['half_km']
    fx, fy = (x + half) / (2 * half) * (n - 1), (half - y) / (2 * half) * (n - 1)     # row 0 is north
    if not (0 <= fx <= n - 1 and 0 <= fy <= n - 1):
        return None
    i, j = min(int(fx), n - 2), min(int(fy), n - 2)
    tx, ty = fx - i, fy - j
    def at(k):
        a, b, c, d = (doc[k][(j + dj) * n + i + di] for dj in (0, 1) for di in (0, 1))
        return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
    return at('u'), at('v')

wind_color = {False: (0.85, 0.92, 1.0), True: (0.10, 0.20, 0.45)}
wind_alpha = 0.25
wind_gap_px = 34        # between two arrows on the screen
wind_px_per_ms = 1.6    # an arrow's length
wind_max_px = 26

def paint_wind(ctx: cairo.Context, view: tuple[float, float, float], up: float, w: int, h: int, light: bool):
    '''Wind arrows on a regular screen grid (the same density at any zoom), each along the local wind, turned with the map.
    Still: they are painted in the basemap's cached image.'''
    import math
    from .basemap import view_matrix
    doc = wind_doc()
    if not doc:
        return
    cx, cy, s = view
    # The basemap's matrix is applied on ctx: back to pixels.
    ctx.save()
    ctx.identity_matrix()
    m = view_matrix(cx, cy, s, up, w, h)
    inv = view_matrix(cx, cy, s, up, w, h)
    inv.invert()
    ctx.set_source_rgba(*wind_color[light], wind_alpha)
    ctx.set_line_width(1.2)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for py0 in range(wind_gap_px // 2, h, wind_gap_px):
        for px0 in range(wind_gap_px // 2, w, wind_gap_px):
            ex, ny = inv.transform_point(px0, py0)
            if not (wv := wind_at(doc, ex, ny)):
                continue
            u, v = wv
            sp = math.hypot(u, v)
            if sp < 0.3:
                continue
            # The wind's direction on the screen: the matrix' turn, without its scale.
            dx, dy = (m.xx * u + m.xy * v) / s / sp, (m.yx * u + m.yy * v) / s / sp
            L = min(max(sp * wind_px_per_ms, 6), wind_max_px)
            x0, y0, x1, y1 = px0 - dx * L / 2, py0 - dy * L / 2, px0 + dx * L / 2, py0 + dy * L / 2
            ctx.move_to(x0, y0)
            ctx.line_to(x1, y1)
            hd = min(L * 0.4, 5)
            for a in (2.6, -2.6):
                ang = math.atan2(dy, dx) + a
                ctx.move_to(x1, y1)
                ctx.line_to(x1 + math.cos(ang) * hd, y1 + math.sin(ang) * hd)
    ctx.stroke()
    ctx.restore()


SAT_URL = 'https://view.eumetsat.int/geoserver/wms'
SAT_KEY = 'di.weather.sat'          # JSON: {at, half_km, px_km, png (base64 L)}: the infrared, brighter is colder
sat_layers = ('mtg_fd:ir105_hrfi', 'msg_fes:ir108')      # MTG 1 km every 10 min, then Meteosat's 3 km every 15 min

def fetch_sat() -> bytes:
    n = int(2 * half_km / px_km)
    dlat, dlon = half_km / km_lat, half_km / km_lon
    last = None
    for layer in sat_layers:
        for _ in range(2):      # the WMS answers 503 now and then
            r = requests.get(SAT_URL, timeout=60, params={
                'service': 'WMS', 'version': '1.3.0', 'request': 'GetMap', 'layers': layer, 'styles': '', 'crs': 'EPSG:4326',
                'bbox': f'{home[0] - dlat},{home[1] - dlon},{home[0] + dlat},{home[1] + dlon}',      # 1.3.0: lat first
                'width': n, 'height': n, 'format': 'image/png'})
            last = r
            if r.ok and r.headers.get('content-type', '').startswith('image'):
                return r.content
    last.raise_for_status()
    raise RuntimeError(f'no image from {SAT_URL}')

def sat_job():
    import base64
    from PIL import Image
    from disinfo.redis import db, publish
    im = Image.open(io.BytesIO(fetch_sat())).convert('L')
    b = io.BytesIO()
    im.save(b, 'PNG', optimize=True)
    doc = {'at': time.time(), 'half_km': half_km, 'px_km': px_km, 'png': base64.b64encode(b.getvalue()).decode()}
    db.set(SAT_KEY, json.dumps(doc), ex=3600)
    publish('weather', 'sat')

def sat_task():
    try:
        sat_job()
    except Exception as e:
        print(f'weather satellite: {e!r}')

_sat = {'read': 0.0, 'doc': None}

def sat_doc() -> dict | None:
    now = time.monotonic()
    if now - _sat['read'] > read_every:
        from disinfo.redis import db
        _sat['read'] = now
        try:
            _sat['doc'] = json.loads(db.get(SAT_KEY) or 'null')
        except ValueError:
            _sat['doc'] = None
    return _sat['doc']

sat_color = {False: (0.80, 0.86, 0.95), True: (1.0, 1.0, 1.0)}
sat_alpha = 0.40        # the densest clouds
sat_floor = 90          # the grey under which it's ground or sea: the contrast is stretched from here

def sat_surface(doc: dict, light: bool) -> cairo.ImageSurface:
    key = doc['at'], light
    if key not in _sat_surfaces:
        import base64
        import numpy as np
        from PIL import Image
        g = np.asarray(Image.open(io.BytesIO(base64.b64decode(doc['png']))).convert('L'), dtype=np.float32)
        a = np.clip((g - sat_floor) / (255 - sat_floor), 0, 1) ** 1.3 * sat_alpha
        out = np.empty(g.shape + (4,), np.uint8)
        for i, c in enumerate((2, 1, 0)):
            out[..., i] = np.round(sat_color[light][c] * a * 255)
        out[..., 3] = np.round(a * 255)
        _sat_surfaces.clear()
        h, w = g.shape
        data = np.ascontiguousarray(out)
        _sat_surfaces[key] = cairo.ImageSurface.create_for_data(memoryview(data).cast('B'), cairo.FORMAT_ARGB32, w, h), data
    return _sat_surfaces[key][0]

_sat_surfaces = {}

def paint_sat(ctx: cairo.Context, light: bool):
    '''The clouds, first and under the land: same placing as the rain.'''
    doc = sat_doc()
    if not doc:
        return
    try:
        surface = sat_surface(doc, light)
    except ImportError:
        return
    ctx.save()
    ctx.translate(-doc['half_km'], doc['half_km'])
    ctx.scale(doc['px_km'], -doc['px_km'])
    ctx.set_source_surface(surface)
    ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
    ctx.paint()
    ctx.restore()
