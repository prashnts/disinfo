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
    monkeypatch.setattr(app.skylook, 'wetness', lambda fs: (0.0, None, 0.0))
    fs = NS(config=NS(name='layers', width=120, height=80, aviator_map_up=0, aviator_zoom=1))
    full = app.radar(fs)
    assert [t.payload['hex'] for t in full.targets] == ['a']
    # Raining at home: a badge by the compass.
    monkeypatch.setattr(app.skylook, 'wetness', lambda fs: (0.5, None, 0.0))
    assert app.radar(fs).image.tobytes() != full.image.tobytes()
    monkeypatch.setattr(app.skylook, 'wetness', lambda fs: (0.0, None, 0.0))
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
    for state, want in (('1', 0.55), ('3', 0.55), ('400', 1.0), ('5000', 1.0), ('unavailable', 1.0)):
        monkeypatch.setattr(skylook, 'get_entity', lambda i, s=state: NS(state=s))
        assert skylook.light_gain(fs) == pytest.approx(want, abs=0.01)
    monkeypatch.setattr(skylook, 'get_entity', lambda i: None)
    assert skylook.light_gain(fs) == 1.0 and skylook.weather_state(NS(config=NS(weather_entity='w'))) is None
    # Rain or snow: the state says when it says something falls, else the temperature; none with the layer off.
    opened = NS(off=[])
    monkeypatch.setattr(skylook, 'OpenedStateManager', lambda: NS(get_state=lambda fs: opened))
    monkeypatch.setattr(skylook.weather, 'sky_profile', lambda kind: (None, 3.0))
    wet = lambda state, t: (monkeypatch.setattr(skylook, 'weather_state', lambda fs: skylook.conditions.get(state)),
                            monkeypatch.setattr(skylook, 'temperature', lambda: t), skylook.wetness(None))[-1]
    assert wet('snowy', 10)[2] == 1 and wet('snowy-rainy', 10)[2] == 0.5 and wet('rainy', -5)[2] == 0
    assert wet('cloudy', -1)[2] == 1 and wet('cloudy', 1)[2] == 0.5 and wet('cloudy', 5)[2] == 0 and wet(None, None)[2] == 0
    assert wet('cloudy', 5)[0] == 0.5           # the radar's 3 mm/h
    opened.off = ['rain']
    assert wet('pouring', 10)[0] == 0


def test_daylight():
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
    envs = {'sensei': None, 'desk': d.envelope(*zip(*day)), 'coef': coef.tolist(), 'rb': None}
    model = {'at': now, 'cloud_cover': 50, 'cloud_cover_low': 50, 'cloud_cover_mid': 0, 'cloud_cover_high': 0,
             'shortwave_radiation': 400, 'direct_radiation': 0}
    at = lambda k: d.estimate([[now - i * 60, None, 0, *(sky(now - i * 60, k) + 40 + lamp).tolist(), 255, 0, 0] for i in range(15)],
                              envs, model, now)
    assert at(1)['cloud'] == 0 and at(1)['sun'] == 1
    assert at(0.05)['cloud'] == 1 and at(0.05)['dark'] > 0.8 and at(0.05)['sun'] == 0
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
