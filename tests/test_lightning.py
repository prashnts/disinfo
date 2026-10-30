import os
import time
from types import SimpleNamespace as NS

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from disinfo.screens.aviator import lightning, app, utils
from disinfo.screens.aviator.lightning import LightningState
from disinfo.screens.aviator.state import OpenedState
import disinfo.utils.hass as hass


def strike(t, b=90, km=20, heard=None):
    return [t, t + 4, b, km, heard, 0]

def test_storm_starts_back_while_strikes_kept_coming(monkeypatch):
    now = 10000
    monkeypatch.setattr(lightning, 'state', lambda: LightningState(s=[strike(now - 2000), strike(now - 1500), strike(now - 1000), strike(now - 30)]))
    assert lightning.storm(now) is None         # one recent strike: no storm
    monkeypatch.setattr(lightning, 'state', lambda: LightningState(s=[strike(now - 2000), strike(now - 1500), strike(now - 1000), strike(now - 500), strike(now - 30)]))
    assert lightning.storm(now) == now - 2000
    monkeypatch.setattr(lightning, 'state', lambda: LightningState(hits=[[now - 5, 10, 1, True, True, 0]]))
    assert lightning.storm(now) == now - 5      # Sensei heard a real one

def test_hits_matched_to_strikes(monkeypatch):
    stored = {}
    now = time.time()
    e = lambda t, i: NS(entity_id=f'geo_location.lightning_strike_{i}', last_changed=None,
                        attributes={'source': 'blitzortung', 'latitude': utils.home[0] + 0.1, 'longitude': utils.home[1], 'external_id': i,
                                    'publication_date': time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(t))})
    monkeypatch.setattr(lightning, 'db', NS(get=lambda k: stored.get(k), set=lambda k, v, ex=None: stored.__setitem__(k, v)))
    monkeypatch.setattr(lightning, 'publish', lambda *a, **k: None)
    monkeypatch.setattr(lightning, 'number', lambda name: 8)
    monkeypatch.setattr(lightning, '_listening', True)
    monkeypatch.setattr(lightning, '_doc', None)
    monkeypatch.setattr(hass, 'get_entities', lambda p: [e(round(now) - 10, 'a'), e(round(now) - 60, 'b')])
    monkeypatch.setattr(lightning, '_hits', [round(now) - 9.6, round(now) - 30])
    lightning.task()
    d = lightning._doc
    assert len(d['s']) == 2 and d['s'][0][3] < 12
    assert [s[4] is not None for s in sorted(d['s'])] == [False, True]
    assert [h[3] for h in d['hits']] == [True, False]
    lightning.task()                            # the same entities again: not twice
    assert len(d['s']) == 2

def test_noise_without_strikes(monkeypatch):
    stored = {}
    monkeypatch.setattr(lightning, 'db', NS(get=lambda k: stored.get(k), set=lambda k, v, ex=None: stored.__setitem__(k, v)))
    monkeypatch.setattr(lightning, 'publish', lambda *a, **k: None)
    monkeypatch.setattr(lightning, 'number', lambda name: 5)
    monkeypatch.setattr(lightning, '_listening', True)
    monkeypatch.setattr(lightning, '_doc', None)
    monkeypatch.setattr(hass, 'get_entities', lambda p: [])
    monkeypatch.setattr(lightning, '_hits', [time.time()])
    lightning.task()
    assert lightning._doc['hits'][0][4] is False
    assert lightning.real_live(LightningState(live=[time.time()]), time.time()) == []

def test_storm_brings_the_sky_unless_pressed_since(monkeypatch):
    now = time.time()
    fs = NS(config=NS(name='s', aviator_views=['map', 'sky', 'solar']))
    monkeypatch.setattr(app, 'live', lambda *a, **k: None)
    monkeypatch.setattr(app.link, 'on', lambda fs: False)
    monkeypatch.setattr(lightning, 'storm', lambda t: now - 300)
    m = OpenedState()
    monkeypatch.setattr(app, 'OpenedStateManager', lambda: NS(get_state=lambda fs: m))
    assert app.view_mode(fs) == 'sky'
    m.view = {'*': ['map', now - 600]}          # pressed before the storm
    assert app.view_mode(fs) == 'sky'
    m.view = {'*': ['map', now - 60]}           # pressed during it
    assert app.view_mode(fs) == 'map'
    m.view, m.views_off = {}, {'*': ['storm']}  # unchecked
    assert app.view_mode(fs) != 'sky' or int(now // app.VIEW_TURN) % 3 == 1
    fs.config.aviator_views = ['map', 'solar']  # no sky on this screen
    m.views_off = {}
    assert app.view_mode(fs) != 'sky'

def test_thunder_comes_after_its_flash(monkeypatch):
    t = 1000.0
    monkeypatch.setattr(lightning, 'state', lambda: LightningState(s=[strike(t, km=3.43)]))
    assert lightning.rumble(t + 5) == 0
    assert any(lightning.rumble(t + 10 + k / 25) for k in range(40))
    assert lightning.rumble(t + 20) == 0

def test_cells_and_the_one_sensei_hears(monkeypatch):
    now = 5000
    st = LightningState(s=[strike(now - 60 * i, 90, 20 + i % 3) for i in range(6)] + [strike(now - 60 * i, 200, 70) for i in range(4)],
                        hits=[[now - 100, 17, 1, True, True, 0]])
    cs = lightning.cells(st, now)
    assert sorted(round(c['b'] / 10) * 10 for c in cs) == [90, 200]
    assert round(lightning.heard_cell(cs, lightning.front(st, now))['b']) == 90
    monkeypatch.setattr(lightning, 'state', lambda: st)
    yaw, fov = lightning.aim(now, 50)
    assert 85 < yaw < 200 and fov <= 140
