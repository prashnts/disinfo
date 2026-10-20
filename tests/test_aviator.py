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
