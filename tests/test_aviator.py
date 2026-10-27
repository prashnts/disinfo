import os
import math

import pytest

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from disinfo.screens.aviator import utils, app, tasks


def plane(x=0, y=0, alt=3000, gs=360, track=0, vr=0, **kw):
    return {'x': x, 'y': y, 'alt': alt, 'gs': gs, 'track': track, 'vr': vr, 'ground': False, **kw}


def test_bearing_and_window(monkeypatch):
    assert utils.bearing(0, 1) == 0
    assert utils.bearing(1, 0) == 90
    assert utils.bearing(-1, 0) == 270
    monkeypatch.setattr(utils.app_config, 'aviator_window', (0, 180))
    assert utils.in_window(90) and utils.in_window(0) and utils.in_window(180)
    assert not utils.in_window(270)
    # Across north.
    monkeypatch.setattr(utils.app_config, 'aviator_window', (300, 60))
    assert utils.in_window(330) and utils.in_window(30) and not utils.in_window(180)

def test_elevation():
    assert utils.elevation(1000, 1) == pytest.approx(45)
    assert utils.elevation(10_000, 0) == pytest.approx(90)

def test_closest_approach():
    # 10 km south, flying north at 360 km/h: over home in 100 s.
    cpa = utils.closest_approach(plane(y=-10), lookahead=150)
    assert cpa['t'] == 100 and cpa['d'] == pytest.approx(0) and cpa['elev'] == pytest.approx(90)
    # Flying away: closest is now.
    assert utils.closest_approach(plane(y=10), 150)['t'] == 0
    # Beyond the lookahead: where it is then.
    assert utils.closest_approach(plane(y=-30), 150)['d'] == pytest.approx(15)

def test_rotated():
    # Facing west, west is up and north is right.
    rot = app.rotated(270)
    assert rot(-1, 0) == pytest.approx((0, 1))
    assert rot(0, 1) == pytest.approx((1, 0))
    assert app.rotated(0)(3, 4) == pytest.approx((3, 4))

def test_fit_and_held(monkeypatch):
    cx, cy, s = app.fit([(0, 0), (10, 20)], 100, 200, margin=0)
    assert (cx, cy, s) == (5, 10, 10)
    fs = type('fs', (), {'config': type('c', (), {'name': 'test'})})()
    monkeypatch.setattr(app, '_held', {})
    clear = (50, 0, 100, 100)
    # Put in the middle of the clear box (75, 50), then held still while it stays in it.
    t = app.held(fs, (0, 0, 10), (0, 0), clear, 100, 100)
    assert 50 + (0 - t[0]) * 10 == pytest.approx(75)
    assert app.held(fs, (0, 0, 10), (1, 0), clear, 100, 100) == t
    # Out of it: back in the middle.
    t = app.held(fs, (0, 0, 10), (5, 0), clear, 100, 100)
    assert 50 + (5 - t[0]) * 10 == pytest.approx(75)

def test_watched_keeps_its_planes(monkeypatch):
    monkeypatch.setattr(utils.app_config, 'aviator_window', (0, 180))
    seen = lambda h, slant: plane(x=slant, alt=5000, hex=h, slant=slant, bearing=90, elev=10, dist=slant)
    monkeypatch.setattr(tasks, 'table', {'a': seen('a', 20), 'b': seen('b', 25)})
    monkeypatch.setattr(tasks, '_watched', [])
    assert tasks.watched(0, 40) == ['a', 'b']
    # A nearer one comes in: the watched ones keep their cards.
    tasks.table['c'] = seen('c', 5)
    assert tasks.watched(0, 40) == ['a', 'b']
    # One leaves the view: the nearest new one takes its place.
    del tasks.table['a']
    assert tasks.watched(0, 40) == ['b', 'c']

def test_the_card_on_top_brings_the_radar(monkeypatch):
    from discore.widget import Widget
    from disinfo.screens import common
    fs = type('fs', (), {'config': type('c', (), {'name': 'test', 'aviator_view': 'map', 'aviator_quiet': []}), 'now': __import__('pendulum').parse('2026-10-20T12:00:00')})()
    monkeypatch.setattr(app, 'view_mode', lambda fs: fs.config.aviator_view)
    monkeypatch.setattr(app, 'quiet', lambda fs: False)
    plane, weather = Widget('aviator.a', background='aviator'), Widget('weather')
    assert common.radar_wanted(fs, [weather, plane])
    assert not common.radar_wanted(fs, [weather, None])
    # The sky's always there; never in the quiet hours.
    fs.config.aviator_view = 'sky'
    assert common.radar_wanted(fs, [weather])
    monkeypatch.setattr(app, 'quiet', lambda fs: True)
    assert not common.radar_wanted(fs, [plane])

def test_motion_is_a_sensor_turning_on(monkeypatch):
    from disinfo.screens import common
    states = {'binary_sensor.a': 'off'}
    monkeypatch.setattr(common, 'get_entity', lambda e: type('s', (), {'state': states[e]}))
    monkeypatch.setattr(common, '_motion', {})
    fs = type('fs', (), {'config': type('c', (), {'name': 'test.motion', 'presence_sensors': ['binary_sensor.a']})})()
    assert not common.motion(fs)
    states['binary_sensor.a'] = 'on'
    assert common.motion(fs)
    # Still on: nothing new.
    assert not common.motion(fs)

def test_hidden_cards_go_in_the_tile(monkeypatch):
    from types import SimpleNamespace as NS
    from PIL import Image
    from discore.elements import Frame
    from disinfo.screens.aviator import widgets
    from disinfo.screens.aviator.state import AviatorState
    st = AviatorState(planes={h: plane(hex=h) for h in 'abc'}, overhead=['a'], watched=['a', 'b', 'c'])
    runtime = NS(show_planes=True)
    monkeypatch.setattr(widgets, 'ADSBxStateManager', lambda: NS(get_state=lambda fs: st))
    monkeypatch.setattr(widgets, 'OpenedStateManager', lambda: NS(get_state=lambda fs: NS(opened={'b': 0}, light=False)))
    monkeypatch.setattr(widgets, 'RuntimeStateManager', lambda: NS(get_state=lambda fs: runtime))
    monkeypatch.setattr(widgets, 'on_top', lambda fs: None)
    monkeypatch.setattr(widgets, 'view_mode', lambda fs: 'solar')
    tiled = []
    monkeypatch.setattr(widgets, 'card', lambda fs, p, active: Frame(Image.new('RGBA', (2, 2))))
    monkeypatch.setattr(widgets, 'tile', lambda fs, ps: tiled.append([p['hex'] for p in ps]) or Frame(Image.new('RGBA', (2, 2))))
    assert [w.name for w in widgets.planes(None)] == ['aviator.b', 'aviator.a']     # the solar view: cards only
    runtime.show_planes = False
    assert [w.name for w in widgets.planes(None)] == ['aviator-tile'] and tiled == [['b', 'a', 'c']]


def test_overhead_is_reach_not_elevation(monkeypatch):
    # A low plane passing 3 km away (elevation 27 degrees) is near; a cruiser 7 km away at 12 km (60 degrees) is not.
    low = plane(x=3, y=0, alt=1500, gs=0, hex='l', dist=3)
    low['cpa'] = utils.closest_approach(low, 150)
    high = plane(x=7, y=0, alt=12000, gs=0, hex='h', dist=7)
    high['cpa'] = utils.closest_approach(high, 150)
    assert tasks.nearness(low) < tasks.overhead_km < tasks.nearness(high)
    # One right over, however high, counts: reach = altitude / 4.
    over = plane(x=0, y=0, alt=12000, gs=0, hex='o', dist=0)
    over['cpa'] = utils.closest_approach(over, 150)
    assert tasks.nearness(over) == pytest.approx(3) and tasks.nearness(over) <= tasks.overhead_km
    # A table from before 'reach' counts as far.
    assert tasks.nearness({'x': 0, 'y': 0, 'alt': 100, 'dist': 50, 'cpa': {}}) > tasks.overhead_km

def test_the_nearest_overhead_plane_is_framed_when_no_card(monkeypatch):
    from types import SimpleNamespace as NS
    st = NS(planes={h: {} for h in 'abc'}, overhead=['a', 'b'])
    monkeypatch.setattr(app, 'ADSBxStateManager', lambda: NS(get_state=lambda fs: st))
    monkeypatch.setattr(app, 'OpenedStateManager', lambda: NS(get_state=lambda fs: NS(opened={})))
    monkeypatch.setattr(app, '_following', {})
    monkeypatch.setattr(app, '_near', {})
    fs = NS(config=NS(name='t'))
    assert app.following(fs) == 'a'
    # Another becomes the nearest: the one framed stays while it is overhead.
    st.overhead = ['b', 'a']
    assert app.following(fs) == 'a'
    st.overhead = ['b']
    assert app.following(fs) == 'b'
    st.overhead = []
    assert app.following(fs) is None
    # A card on top for a plane overhead wins; a card for one that's not overhead (nor tapped) does not.
    st.overhead = ['a', 'c']
    app._following['t'] = 'c'
    assert app.following(fs) == 'c'
    st.overhead = ['a']
    assert app.following(fs) == 'a'

def test_framing_keeps_home_in_view_when_it_can():
    clear = (0, 0, 100, 100)
    base = (0, 0, 10)       # 10 px a km: 10 km across
    near = app.framed(base, (4, 0), clear, 100, 100)
    assert app.inside(near, (4, 0), clear, 100, 100) and app.inside(near, (0, 0), clear, 100, 100)
    assert near[0] == pytest.approx(2)      # between them
    # Too far to have both: on the plane.
    far = app.framed(base, (30, 0), clear, 100, 100)
    assert far[0] == pytest.approx(30) and not app.inside(far, (0, 0), clear, 100, 100)

def test_layers_planes_and_info(monkeypatch):
    from types import SimpleNamespace as NS
    from disinfo.screens.aviator.state import AviatorState
    p = plane(x=2, y=2, hex='a', at=0, lat=48.86, lon=2.41, trail=[[0, 48.85, 2.4, 3000], [1, 48.86, 2.41, 3000]], elev=30, slant=3, bearing=45, cpa={})
    st = AviatorState(planes={'a': p}, watched=['a'], radius=40, trail=180)
    opened = NS(opened={}, off=[], light=False, map_up={}, zoom={}, view=None)
    monkeypatch.setattr(app, 'ADSBxStateManager', lambda: NS(get_state=lambda fs: st))
    monkeypatch.setattr(app, 'OpenedStateManager', lambda: NS(get_state=lambda fs: opened))
    monkeypatch.setattr(app.basemap, 'draw', lambda *a, **k: None)
    monkeypatch.setattr(app, 'following', lambda fs: None)
    monkeypatch.setattr(app, 'drift', lambda t: t)
    monkeypatch.setattr(app, '_cams', {})
    dry = app.skylook.Seen((0.3, 0.2, 0), 0, 0, None, 0, None, None, 0.0, 0.0)
    monkeypatch.setattr(app.skylook, 'seen', lambda fs: dry)
    fs = NS(config=NS(name='layers', width=120, height=80, aviator_map_up=0, aviator_zoom=1))
    full = app.radar(fs)
    assert [t.payload['hex'] for t in full.targets] == ['a']
    # Raining at home: a badge by the compass.
    monkeypatch.setattr(app.skylook, 'seen', lambda fs: dry._replace(wet=0.5))
    assert app.radar(fs).image.tobytes() != full.image.tobytes()
    monkeypatch.setattr(app.skylook, 'seen', lambda fs: dry)
    opened.off = ['planes']
    no_planes = app.radar(fs)
    assert no_planes.targets == ()
    opened.off = ['info']
    no_info = app.radar(fs)
    assert [t.payload['hex'] for t in no_info.targets] == ['a']         # the plane and its trail stay, tappable
    assert no_info.image.tobytes() != full.image.tobytes()
    # Planes and info both off: only the background, the same with or without the plane.
    opened.off = ['planes', 'info']
    bare = app.radar(fs)
    st.planes = {}
    assert bare.image.tobytes() == app.radar(fs).image.tobytes()


def test_stars_and_moon():
    import time
    from disinfo.screens.aviator import astro
    lat, lon = 48.84, 2.39
    t = time.time()
    # Polaris stays at the latitude's height, due north, whenever it is.
    for dt in (0, 3 * 3600, 9 * 3600):
        az, alt, mag = astro.stars_at(t + dt, lat, lon)
        i = list(mag).index(pytest.approx(2.0))
        assert alt[i] == pytest.approx(lat, abs=1.5) and (az[i] < 3 or az[i] > 357)
    # Only what's over the horizon.
    assert (alt > 0).all()
    # The moon: new on 2026-10-10, full around 2026-10-26 (the mean month is good to a day).
    import calendar
    new = calendar.timegm((2026, 10, 10, 16, 0, 0))
    full = calendar.timegm((2026, 10, 26, 4, 0, 0))
    p = astro.moon_at(new, lat, lon)[2]
    assert p < 0.05 or p > 0.95
    assert astro.moon_at(full, lat, lon)[2] == pytest.approx(0.5, abs=0.05)

def test_sky_look(monkeypatch):
    from types import SimpleNamespace as NS
    from disinfo.screens.aviator import skylook
    clear, cloudy = skylook.conditions['sunny'], skylook.conditions['cloudy']
    noon, sunset, night = skylook.look(45, clear), skylook.look(0, clear), skylook.look(-20, clear)
    assert sunset.glow > 0.8 and noon.glow == 0 and night.glow == 0
    # Cloud greys the sky, hides the glow, and a weather cloud can be overridden (the satellite's).
    assert skylook.look(0, cloudy).glow < sunset.glow / 2
    assert skylook.look(45, clear, cloud=1).cloud == 1
    # A day sky is much lighter than a night one; the room's light scales it.
    assert sum(noon.zenith) > 5 * sum(night.zenith)
    assert sum(skylook.look(45, clear, 0.55).zenith) < sum(noon.zenith)
    # The city's light on the cloud: only at night, only with cloud; a cloud is dark and warm then, darker in the rain.
    rainy_night, rainy_noon = skylook.look(-20, skylook.conditions['rainy']), skylook.look(45, skylook.conditions['rainy'])
    assert night.city == 0 and rainy_noon.city == 0 and rainy_night.city > 0.8
    cn, cd = skylook.cloud_color(rainy_night), skylook.cloud_color(rainy_noon)
    assert sum(cn) < sum(cd) / 2 and cn[0] > cn[2] and sum(skylook.cloud_color(rainy_noon, 1)) < sum(cd)
    # The light sensor: dark room 55%, bright room 100%, none (or garbage) 100%.
    fs = NS(config=NS(ambient_light_sensor='x'))
    monkeypatch.setattr(skylook, 'room_counts', lambda fs: None)
    for state, want in (('1', 0.55), ('3', 0.55), ('400', 1.0), ('5000', 1.0), ('unavailable', 1.0)):
        monkeypatch.setattr(skylook, 'get_entity', lambda i, s=state: NS(state=s))
        assert skylook.light_gain(fs) == pytest.approx(want, abs=0.01)
    monkeypatch.setattr(skylook, 'get_entity', lambda i: None)
    assert skylook.light_gain(fs) == 1.0
    # The screen's own sensor first: its counts, dark to bright.
    for counts, want in ((50, 0.55), (10000, 1.0)):
        monkeypatch.setattr(skylook, 'room_counts', lambda fs, c=counts: c)
        assert skylook.light_gain(fs) == pytest.approx(want, abs=0.01)


def test_seen(monkeypatch):
    # What the sky view draws from the sky state: cloud fades as it's less sure; rain off with its layer.
    from types import SimpleNamespace as NS
    from disinfo.screens.aviator import skylook
    opened = NS(off=[])
    monkeypatch.setattr(skylook, 'OpenedStateManager', lambda: NS(get_state=lambda fs: opened))
    q = lambda v, conf=0.6: {'v': v, 'conf': conf, 'by': {}}
    d = {'sky': {'cover': q(0.9), 'deck': q(0.8, 0.6), 'high': q(1.0, 0.1), 'sun': q(0.2), 'dark': q(0.5), 'haze': q(0.3),
                 'broken': None, 'warmth': None}, 'precip': {'rate': q(3.0), 'snow': q(0.0)}}
    monkeypatch.setattr(skylook.skystate, 'doc', lambda: d)
    s = skylook.seen(NS(config=NS(weather_entity='w')))
    assert s.cond == (0.9, 0.3, 0.3) and s.deck == pytest.approx(0.8) and s.high == pytest.approx(0.5)
    assert s.sun == 0.2 and s.broken is None and s.wet == 0.5 and s.snow == 0 and s.wind is None
    opened.off = ['rain']
    assert skylook.seen(NS(config=NS(weather_entity='w'))).wet == 0
    # No sky state (the data service down): Home Assistant's weather state alone.
    opened.off = []
    monkeypatch.setattr(skylook.skystate, 'doc', lambda: None)
    monkeypatch.setattr(skylook, 'get_entity', lambda i: NS(state='snowy'))
    s = skylook.seen(NS(config=NS(weather_entity='w')))
    assert s.cond[0] == 0.9 and s.wet == 0.4 and s.snow == 1 and s.sun is None and s.deck == 0
    monkeypatch.setattr(skylook, 'get_entity', lambda i: None)
    assert skylook.seen(NS(config=NS(weather_entity='w'))).cond == skylook.conditions['partlycloudy'][:3]


def test_fuse():
    from disinfo.screens.aviator import skystate as ss
    # Two sources that agree: between them, nearer the surer, and surer than either.
    a = ss.fuse([('model', 0.8, 0.3, 0), ('light', 0.9, 0.15, 0)], 'unit', 0.2)
    b = ss.fuse([('light', 0.9, 0.15, 0)], 'unit', 0.2)
    assert 0.85 < a['v'] < 0.9 and a['conf'] > b['conf'] and a['by'] == {'model': 0.8, 'light': 0.9}
    # Disagreeing: less sure than either alone.
    c = ss.fuse([('model', 0.1, 0.3, 0), ('light', 0.9, 0.15, 0)], 'unit', 0.2)
    assert c['conf'] < b['conf'] and c['v'] > 0.6
    # Old observations count less, too old not at all.
    d = ss.fuse([('model', 0.1, 0.3, 0), ('light', 0.9, 0.15, 1200)], 'unit', 0.2)
    assert d['v'] < c['v'] and ss.fuse([('light', 0.9, 0.15, 3600)], 'unit', 0.2) is None
    # Rain is fused as log(1 + mm/h): a drizzle and a downpour meet nearer the drizzle.
    assert ss.fuse([('a', 0.0, 0.5, 0), ('b', 8.0, 0.5, 0)], 'mm', 0.3)['v'] == pytest.approx(2.0, abs=0.01)
    assert ss.v({'sky': {'cover': {'v': 0.5, 'conf': 0.3}}}, 'sky.cover') == 0.5
    assert ss.v({'sky': {'cover': {'v': 0.5, 'conf': 0.3}}}, 'sky.cover', 1, conf=0.5) == 1
    assert ss.v({'sky': {'cover': None}}, 'sky.cover', 7) == 7 and ss.v(None, 'a.b') is None


def test_sky_state(monkeypatch):
    import time
    from disinfo.screens.aviator import skystate as ss, daylight
    now = time.time()
    monkeypatch.setattr(ss, 'next_rain', lambda now, fc=None: None)
    alt = daylight.sun_at(now)[0]
    hours = {'time': [now - now % 3600], 'precipitation': [0.0], 'temperature_2m': [1.0], **{
        f'{k}_{p}hPa': [v] for p, t, rh in ((850, -3, 80), (700, -10, 70), (500, -25, 60), (300, -45, 95), (250, -52, 90))
        for k, v in (('temperature', t), ('relative_humidity', rh), ('wind_speed', 20), ('wind_direction', 270))}}
    sky = {'at': now, 'cloud_cover': 100, 'cloud_cover_low': 90, 'cloud_cover_mid': 0, 'cloud_cover_high': 50,
           'shortwave_radiation': 50, 'direct_radiation': 0, 'hours': hours}
    m = ss.model_obs(sky, now, alt)
    sources = {'model': (m[0], m[1], {'levels': m[2]}),
               'light': ss.light_obs({'at': now, 'source': 'light', 'window': True, 'b': 0.1, 'cloud': 1.0, 'dark': 0.4,
                                      'sun': 0.0, 'broken': 0.1, 'warmth': None}),
               'camera': (now - 60, {'cover': (1.0, 0.1)}, {})}
    d = ss.state(now, sources)
    assert d['sky']['cover']['v'] > 0.95 and set(d['sky']['cover']['by']) == {'model', 'light', 'camera'}
    assert d['sky']['deck']['v'] > 0.9 and d['sky']['high']['v'] == 0.5
    # 1 °C at home, freezing a little over the ground: snow, mostly.
    assert d['air']['freezing_m'] is not None and d['air']['freezing_m']['v'] < 600 and d['precip']['snow']['v'] > 0.5
    # -45 °C and 95 % at 300 hPa: trails, and they last (over ice it's well over 100 %).
    assert d['air']['contrails']['form_m'] == round(ss.aloft.pressure_m(300)) and d['air']['contrails']['persist'] == 1
    assert d['air']['wind_high'] == {'dir': 270, 'ms': 20, 'by': 'model'}
    assert d['sources']['camera'] == 60 and d['sources']['sat'] is None
    assert ss.light_obs({'at': now, 'source': 'shutter'})[2]['shutter'] and ss.light_obs({'source': 'night'}) is None
    # Behind the window: the light says only how dark it is (and the deck when it's very dark).
    q = ss.light_obs({'at': now, 'source': 'light', 'window': False, 'b': 0.5, 'cloud': 0, 'dark': 0, 'sun': 1,
                      'broken': None, 'warmth': None})[1]
    assert 'sun' not in q and 'cover' not in q and 'deck' not in q and 'dark' in q


def test_aloft(monkeypatch):
    from disinfo.screens.aviator import aloft
    from disinfo.screens.aviator.utils import home
    monkeypatch.setattr(aloft, '_samples', aloft.deque())
    monkeypatch.setattr(aloft, '_last', {})
    # A standard atmosphere, 15 °C at the sea and 6.5 °C/km, a west wind of 10 m/s; one plane far off the rest.
    planes = []
    for i in range(40):
        ft = 1500 + i * 1000
        planes += [{'hex': f'{i}{k}', 'alt_baro': ft, 'alt_geom': ft + 300, 'lat': home[0], 'lon': home[1],
                    'oat': 15 - 6.5 * ft * 0.3048 / 1000 + (k - 1), 'wd': 270, 'ws': 10 / aloft.kt} for k in range(3)]
    planes[30]['oat'] += 80
    planes += [{'hex': 'odd', 'alt_baro': 5500, 'oat': 60, 'lat': home[0], 'lon': home[1]}]
    aloft.add(1000.0, planes)
    # A plane once a minute only.
    aloft.add(1030.0, [{**planes[0], 'oat': -50}])
    prof = aloft.profile(1031.0)
    assert prof['geom_m'] == round(300 * 0.3048) and len(prof['bins']) == 40
    assert prof['bins'][0][1] == pytest.approx(15 - 6.5 * 0.457, abs=0.2)
    der = aloft.derived(prof)
    assert der['freezing_m'] == pytest.approx(15 / 6.5 * 1000 + 91, abs=60)
    assert der['lapse'] == pytest.approx(6.5, abs=0.2) and der['inversion'] is None
    assert aloft.wind_at(prof['bins'], 3000) == (270, 10.0)
    assert 8000 < der['contrail_m'] < 9500        # about 8.5 km in a standard atmosphere
    assert aloft.profile(1000.0 + aloft.window_s + 60) is None
    assert aloft.pressure_hpa(aloft.pressure_m(300)) == pytest.approx(300)
    assert aloft.contrail_c(300) == pytest.approx(-39.8, abs=0.3)


def test_daylight(monkeypatch):
    import time
    import numpy as np
    from disinfo.screens.aviator import daylight as d
    # The sun up at noon today, so the bearing is in the envelope.
    now = time.time() - time.time() % 86400 + 12 * 3600
    sky = lambda t, k: np.array([0.3, 0.33, 0.37, 1]) * max(0, np.sin(np.radians(d.sun_at(t)[0]))) * 20000 * k
    lamp = np.array([300, 250, 200, 800])
    rnd = np.random.default_rng(1)
    rows = []
    for i in range(4 * 1440):
        t, on = now - i * 60, int(rnd.choice([0, 255]))
        rows.append([t, None, 0, *(sky(t, 1 if i // 600 % 2 else 0.2) + on / 255 * lamp + 40).tolist(), on, 0, 0])
    # The lamps come off the desk's counts: learnt at night, whatever the day did.
    coef = d.lamp_model(rows)
    assert coef[1] == pytest.approx(lamp, abs=1) and coef[0] == pytest.approx(40, abs=1)
    day = [(r[0], x[3]) for r in rows if (x := d.desk_daylight(r, coef)) is not None]
    # A lamp Home Assistant doesn't know of: its colour gives it away.
    sig = d.signatures(rows)
    assert sig and sig['lamp'][0] > sig['day'][0]
    # One left on all day: the day's colour from the hours it's a small share of the light.
    on = [[*r[:3], *(np.array(r[3:7]) + 0.5 * lamp).tolist(), r[7], 0, 128] for r in rows]
    assert d.signatures(on) is None
    sig_on = d.signatures(on, d.lamp_model(on))
    assert sig_on and sig_on['day'] == pytest.approx([0.3, 0.33, 0.37, 1], abs=0.01)
    row = [now, None, 0, *(sky(now, 1) + 40 + 0.7 * lamp).tolist(), 0, 0, 0]
    assert d.desk_daylight(row, coef)[3] > sky(now, 1)[3] + 400
    assert d.desk_daylight(row, coef, sig)[3] == pytest.approx(sky(now, 1)[3], rel=0.05)
    envs = {'sensei': None, 'desk': d.envelope(*zip(*day)), 'coef': coef.tolist(), 'rb': None}
    model = {'at': now, 'cloud_cover': 50, 'cloud_cover_low': 50, 'cloud_cover_mid': 0, 'cloud_cover_high': 0,
             'shortwave_radiation': 400, 'direct_radiation': 0}
    at = lambda k: d.estimate([[now - i * 60, None, 0, *(sky(now - i * 60, k) + 40 + lamp).tolist(), 255, 0, 0] for i in range(15)],
                              envs, model, now)
    # The sun in the window's view: the light says it all.
    monkeypatch.setattr(d.app_config, 'aviator_window', (0, 360))
    assert at(1)['cloud'] == 0 and at(1)['sun'] == 1
    assert at(0.05)['cloud'] == 1 and at(0.05)['dark'] > 0.8 and at(0.05)['sun'] == 0
    # Behind it, the model says if the sun's out (a clear sky across is no brighter than overcast), unless it's dark.
    monkeypatch.setattr(d.app_config, 'aviator_window', ((d.sun_at(now)[1] + 90) % 360, (d.sun_at(now)[1] + 270) % 360))
    assert at(0.3)['sun'] == 1 and at(0.3)['cloud'] < 0.1
    assert at(0.05)['sun'] < 0.2 and at(0.05)['cloud'] > 0.8
    assert at(0.001)['source'] == 'shutter' and at(0.001)['cloud'] is None
    assert d.estimate([], envs, model, now - 12 * 3600)['source'] == 'night'


def test_clouds_without_the_satellite(monkeypatch):
    # Raining at home, no satellite picture: the cover all around is the rain's.
    import cairocffi as cairo
    from disinfo.screens.aviator import sky
    monkeypatch.setattr(sky.weather, 'sky_profile', lambda kind: None)
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64))
    to_px = lambda b, e: (32 + b, 45 - e)
    assert sky.clouds(ctx, 0, 90, 64, 45, 64, (1, 1, 1), 0.5)(10) == 0.5
    sky.puffs(ctx, 0, 90, 64, to_px, (1, 1, 1), 0.5)
    assert sky.clouds(ctx, 0, 90, 64, 45, 64, (1, 1, 1))(10) == 0

def test_overhead_order_is_stable(monkeypatch):
    now = 1000.0
    def p(dist, hex):
        q = plane(hex=hex, dist=dist, bearing=0, elev=0, slant=dist, overhead_at=now)
        q['cpa'] = {'reach': dist}
        return q
    monkeypatch.setattr(tasks, '_watched', [])
    planes = {'a': p(2, 'a'), 'b': p(3, 'b')}
    assert tasks.watched(now, 40, planes) == ['a', 'b']
    # b gets nearer than a: they don't swap.
    planes = {'a': p(3, 'a'), 'b': p(1, 'b')}
    assert tasks.watched(now, 40, planes) == ['a', 'b']
    # A new one comes in by nearness, after the ones there; one that leaves is gone.
    planes = {'a': p(3, 'a'), 'b': p(1, 'b'), 'c': p(2, 'c'), 'd': p(0.5, 'd')}
    assert tasks.watched(now, 40, planes) == ['a', 'b', 'd', 'c']
    del planes['a']
    assert tasks.watched(now, 40, planes) == ['b', 'd', 'c']
    # Its pass over (30 s after), the plane is no longer overhead.
    assert not tasks.is_overhead({'overhead_at': now}, now + tasks.passed_for + 1)


def test_contrails_and_puffs(monkeypatch):
    import cairocffi as cairo
    from disinfo.screens.aviator import sky
    monkeypatch.setattr(sky.app, 'position', lambda p, now, ahead=0: (0.0, 20.0))
    p = {'ground': False, 'alt': 11000, 'trail': [[90.0, 48.9, 2.3, 11000], [95.0, 48.95, 2.3, 11000]], 'lat': 48.95, 'lon': 2.3}
    def drawn(planes, trails):
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
        sky.contrails(cairo.Context(s), planes, 100.0, lambda b, m=10: True, lambda b, e: (100 + b / 3, 90 - e * 2), (1, 1, 1), trails)
        return max(bytes(s.get_data())) > 0
    # Above the height they form at: a trail; under it, or on the ground, none.
    assert drawn([p], (10000, 0.0, 0, 0)) and not drawn([p], (12000, 1.0, 0, 0)) and not drawn([{**p, 'ground': True}], (10000, 1, 0, 0))
    # Puffs: three heaps when small, tiers when big; drawn without a stray wedge (inside its box only).
    assert len(sky.lobes(4, 0.3)) == 3 and len(sky.lobes(60, 0.3)) > 8
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
    sky.puff(cairo.Context(s), 100, 70, 40, 20, (1, 1, 1), 1, 0.4)
    import numpy as np
    alpha = np.frombuffer(s.get_data(), np.uint8).reshape(100, 200, 4)[:, :, 3]
    assert alpha[80:, :].max() == 0 and alpha[60, 100] > 0
    # The wind's curls: in the sky, over the roofs, never under the horizon.
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
    sky.curls(cairo.Context(s), 200, 20, 70, 1000.0, 90, 8, 14, 270, (1, 1, 1))
    alpha = np.frombuffer(s.get_data(), np.uint8).reshape(100, 200, 4)[:, :, 3]
    assert alpha.max() > 0 and alpha[72:, :].max() == 0


def test_skyline():
    import numpy as np
    from disinfo.screens.aviator import skyline
    # A wall 100 m east, 20 m wide, 10 m over the eye: in the near band around 90 degrees, at its height.
    w = np.array([[100, -10, 100, 10, 60]], np.float32)
    p, d = skyline.profile(w, 50, 0, int(180 / skyline.res))
    at = lambda b: p[:, int(b / skyline.res)]
    assert at(90)[0] == pytest.approx(math.degrees(math.atan(0.1)), abs=0.01) and at(90)[1:].max() == -90
    assert at(80).max() == -90 and at(95)[0] > 0
    # How far: 100 m straight east. Seen from 10 m lower, that roof stands as much higher (the hills don't move).
    assert d[0, int(90 / skyline.res)] == pytest.approx(100, abs=0.5)
    up = skyline.Skyline((0, 0, 50), 0, p, [], [], None, d[:-1]).lifted(-10)
    assert up.p[0, int(90 / skyline.res)] == pytest.approx(math.degrees(math.atan(0.2)), abs=0.01) and (up.p[-1] == p[-1]).all()
    # The columns: each the highest of its bins; out of the profile, nothing.
    sk = skyline.Skyline((0, 0, 50), 0, p, [])
    c = sk.columns(80, 1, 20)
    assert c[0, 10] == pytest.approx(at(90)[0], abs=0.1) and c[0, 0] == -90
    assert (sk.columns(200, 1, 5) == -90).all()
    # The window nudged sideways to see past a wall in front of a place.
    wall = np.array([[0, 200, 30, 200, 90]], np.float32)
    (dx, dy, dz), ms = skyline.fit(wall, 0, 0, 80, [(0, 1000, 85)])
    assert ms[0] > -skyline.seen_tol and (dx != 0 or dz > 0)


def test_skyline_last_meanwhile(monkeypatch):
    import json
    from disinfo.screens.aviator import skyline
    # A new version not built yet: the newest older one is shown meanwhile, the new one built.
    store = {b'di.skyline.2.aa': json.dumps({'eye': [0, 0, 50], 'start': 0, 'p': [[0]], 'seen': []}), b'di.skyline.3.bb': json.dumps(
        {'eye': [0, 0, 60], 'start': 0, 'p': [[0]], 't': [[0]], 'seen': []}), b'di.skyline.3.bb.lock': '1'}
    asked = []
    monkeypatch.setattr(skyline, 'db', type('DB', (), {'get': lambda _, k: store.get(k.encode()), 'scan_iter': lambda _, p: list(store)})())
    monkeypatch.setattr(skyline, 'key', lambda: 'di.skyline.4.cc')
    monkeypatch.setattr(skyline, 'ask', asked.append)
    monkeypatch.setattr(skyline, '_loaded', {})
    monkeypatch.setattr(skyline, '_checked', [0.0])
    sk = skyline.get(100)
    assert sk.eye[2] == 60 and sk.t is not None and asked == ['di.skyline.4.cc']
    store[b'di.skyline.4.cc'] = json.dumps({'eye': [0, 0, 70], 'start': 0, 'p': [[0]], 'seen': []})
    assert skyline.get(110).eye[2] == 60 and skyline.get(130).eye[2] == 70


def test_sky_tour_and_roofs(monkeypatch):
    import cairocffi as cairo
    import numpy as np
    from disinfo.screens.aviator import sky, skyline
    # Every other stop the waypoints; a slow turn between, the shorter way, then still.
    monkeypatch.setattr(sky, '_stops', {})
    period = sky.tour_dwell + sky.tour_glide
    k = 1
    assert sky.tour(90, [300], k * period - 1) == 90 and sky.tour(90, [300], k * period + sky.tour_glide) == 300
    mid = sky.tour(90, [300], k * period + sky.tour_glide / 2)
    assert mid == pytest.approx(15) and sky.tour(90, [None], (k + 2) * period) == 90
    # The roofs all around, trees in front, by day and at night: nothing under the horizon left bare, the sky clear.
    n = int(360 / skyline.res)
    p = np.full((5, n), -90.0, np.float32)
    p[-1], p[0, :n // 2] = -0.2, -3
    t = np.full((4, n), -90.0, np.float32)
    t[0, n // 2:] = -5
    sk = skyline.Skyline((0, 0, 80), 0, p, [], [], t)
    for day, night in ((1, 0), (0, 1)):
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 200)
        to_y = lambda e: np.where(e >= 0, 120 - 120 * np.minimum(e, 90) / 60, 120 + 80 * np.minimum(-e, 20) / 20)
        sky.real_roofs(cairo.Context(s), sk, 270, 60, 400, 200, to_y, None, sky.rim_color, (90, 1), night, day, (0.5, 0.6, 0.8), 2)
        alpha = np.frombuffer(s.get_data(), np.uint8).reshape(200, 400, 4)[:, :, 3]
        assert alpha[120:].min() > 0 and alpha[:118, :250].max() == 0 and alpha[:118, 285:300].max() > 0     # the Eiffel tower, out of reach


def test_sky_camera(monkeypatch):
    from types import SimpleNamespace as NS
    from disinfo.screens.aviator import sky
    monkeypatch.setattr(sky.app_config, 'aviator_window', (0, 180))
    monkeypatch.setattr(sky.app_config.screen_data.aviator, 'landmarks', [])
    st = NS(planes={'a': {'bearing': 40}, 'b': {'bearing': 120}}, watched=['a', 'b'])
    # Wide enough for the planes; narrow without them, pulled back to the window now and then.
    assert sky.aim(st, sky.view_fov) == (80, 95)
    monkeypatch.setattr(sky, 'wide_for', 0)
    assert sky.aim(NS(planes={}, watched=[]), sky.view_fov) == (90, sky.view_fov)
    monkeypatch.setattr(sky, 'wide_for', sky.wide_every)
    assert sky.aim(NS(planes={}, watched=[]), sky.view_fov) == (90, 180)
    # A higher plane: the horizon goes down to look up at it.
    assert sky.tilt[0] <= sky.tilt_to(2, 50) < sky.tilt_to(30, 50) <= sky.tilt[1]


def test_sky_demo():
    from disinfo.screens.aviator import sky
    from disinfo.screens.aviator.state import DEMO_S
    # Each scene's sky in its middle, blending into the next at its end; the clock and the season with it.
    each = DEMO_S / len(sky.demo_scenes)
    (b, e), seen, doy, *clock = sky.demo_at(each * 1.5)
    assert (b, e) == (180, 58) and doy == 180 and clock == [13, 0] and seen.wet == 0
    (_, e), seen, *_ = sky.demo_at(each * 5 - sky.demo_blend / 2)
    assert 12 < e < 20 and 0.6 < seen.wet < 0.7 and 0 < seen.snow < 1


def test_sky_held_from_the_web(monkeypatch):
    from types import SimpleNamespace as NS
    from disinfo.screens.aviator import state
    monkeypatch.setattr(state, 'db', type('DB', (), {'set': lambda *a: None})())
    m = state.OpenedStateManager.__new__(state.OpenedStateManager)
    m.state = state.OpenedState()
    # Turned, then zoomed: both kept, on the sky view; the horizon kept within reach; back to its own.
    m.process_message('', NS(action='aviator.sky', payload={'yaw': 284}))
    m.process_message('', NS(action='aviator.sky', payload={'fov': 30}))
    assert (m.state.sky['yaw'], m.state.sky['fov'], m.state.view) == (284, 30, 'sky')
    m.process_message('', NS(action='aviator.horizon', payload={'h': 0.1}))
    assert m.state.horizon == 0.3
    m.process_message('', NS(action='aviator.sky', payload={}))
    m.process_message('', NS(action='aviator.horizon', payload={'h': None}))
    assert m.state.sky == {} and m.state.horizon is None
    m.process_message('', NS(action='aviator.eye', payload={'floors': '-30'}))
    assert m.state.floors == -12


def test_sky_crane():
    import cairocffi as cairo
    import numpy as np
    from disinfo.screens.aviator import sky
    # A crane 800 m north: its mast from the ground to over the horizon, its jib across, by day; lit at night.
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 200)
    to_y = lambda e: np.where(e >= 0, 120 - 120 * (np.minimum(np.abs(e), 90) / 60) ** 0.5, 120 + 80 * (np.minimum(np.abs(e), 20) / 20) ** 0.5)
    sky.cranes(cairo.Context(s), [(0, 800, 50, 55, 800)], 80, 0, 40, 400, to_y, (1, 0, 0), (1, 1, 1), 1, 1000.0)
    alpha = np.frombuffer(s.get_data(), np.uint8).reshape(200, 400, 4)[:, :, 3]
    cols = np.flatnonzero(alpha[:118].max(0))
    assert alpha[135:145, 200].max() > 0 and cols.max() - cols.min() > 20
