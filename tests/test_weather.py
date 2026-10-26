import os
import json

import pytest

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from disinfo.screens.weather import stations as st, forecast as fc
from disinfo.screens.aviator import skystate as ss

T0 = 1793037600     # an hour, Monday 2026-10-26 19:00 in Paris


class FakeDB(dict):
    def get(self, k):
        return super().get(k)
    def set(self, k, v, ex=None):
        self[k] = v
    def delete(self, k):
        self.pop(k, None)
    def lpush(self, k, v):
        self.setdefault(k, []).insert(0, v)
    def lrange(self, k, a, b):
        l = super().get(k, [])
        return l[a:] if b == -1 else l[a:b + 1]
    def ltrim(self, k, a, b):
        self[k] = self.lrange(k, a, b)


def station(t, at=T0, **kw):
    return {'at': at, 't': t, 'td': None, 'rh': None, 'dir': None, 'ms': None, 'rr': None, 'vis': None, 'p': None, 'pmer': None, **kw}

def test_home_air():
    # The city's stations count more than the airports; old ones not at all.
    s = {'75114001': station(13, pmer=1016.8, dir=200, ms=3), '75110001': station(13.4), '91027002': station(11, pmer=1017.0, dir=180, ms=3),
         '95088001': station(30, at=T0 - 7200), st.eiffel: station(14)}
    m = {'LFPO': st.parse_metar({'obsTime': T0, 'clouds': [{'cover': 'OVC', 'base': 400}, {'cover': 'FEW', 'base': 25000}],
                                 'wspd': 5, 'wgst': 20, 'visib': '6+', 'wxString': '-DZ'})}
    h = st.home_air(s, m, {}, T0)
    assert 12.8 < h['t'][0] < 13.2 and h['t'][1] < 1 and h['pmer'][0] == pytest.approx(1016.9)
    assert h['dir'] == 190 and h['gust'][0] == pytest.approx(10.3) and h['deck'][0] == 1 and h['ceiling'] == 122
    assert h['wx'] == ['-DZ'] and h['eiffel'] > 0 and m['LFPO']['vis'] == 10000 and h['vis'] is None
    # No stations: the barometers indoors for the pressure.
    assert st.home_air({}, {}, {'b': 1010.0}, T0)['pmer'][0] == 1010
    assert st.tendency([[T0 - 3 * 3600, 0, 0, 1012.0]], 1009.0, T0) == -3

def test_barometers():
    db = FakeDB()
    for _ in range(4):
        assert st.barometers(db, 1016.0, {'s': 1007.0}) == {}
    assert st.barometers(db, 1016.0, {'s': 1007.0})['s'] == pytest.approx(1016)
    assert st.barometers(db, None, {'s': 1006.0})['s'] == pytest.approx(1015)

def run(at, temps, model='a'):
    return {'at': at, 'time': [T0 + 3600 * i for i in range(len(temps))], 'm': {model: {'temp': temps}}}

def test_blend_and_score(monkeypatch):
    monkeypatch.setattr(fc, 'models', {'a': 1.0, 'b': 1.0})
    # Two models, one learnt to be 2 °C too warm: it's taken off, and the surer one weighs more.
    r = {'at': T0, 'time': [T0, T0 + 3600], 'm': {'a': {'temp': [12, 12], 'rain': [0, 1]}, 'b': {'temp': [14, 14], 'rain': [0, 0]}}}
    d = fc.blend(r, {})
    assert d['temp'][0] == 13 and d['spread'][0] == 1 and d['rain_p'] == [0, 0.5]
    d = fc.blend(r, {'b': {'temp': {'3': [2.0, 4.0, 1000]}}})
    assert d['temp'][0] == pytest.approx(12, abs=0.01)
    # Pulled to the stations now, less so ahead.
    a = fc.anchored(d, {'t': [13.0, 0.5]}, T0)
    assert a['temp'][0] == pytest.approx(13, abs=0.01) and 12 < a['temp'][1] < 13
    # Scored: a run 2 h before, 1 °C too warm at the hour the stations saw.
    db = FakeDB()
    db.lpush(fc.RUNS_KEY, json.dumps(run(T0 - 7200, [14, 14])))
    db.set(fc.CHECKED_KEY, T0 - 3600)
    log = [[T0 + 30, 13.0, 10.0, 1016.0, 3.0, 0.0, {}, 15.5]]
    assert fc.check(db, T0 + 3600 + 700, log) == 2
    s = json.loads(db[fc.SKILL_KEY])
    assert s['a']['temp']['3'] == [1.0, 1.0, 1] and s['ha']['temp']['3'][0] == 2.5
    assert fc.error(s, 'a', 'temp', 2)[0] == pytest.approx(1 / 13)
    assert fc.skill_table(s)[1].startswith('a ') and not db.get(fc.RUNS_KEY)

def test_stations_in_sky(monkeypatch):
    home = st.home_air({'75114001': station(-1, td=-2, pmer=1020.0, ms=5, dir=0, vis=800)},
                       {'LFPO': st.parse_metar({'obsTime': T0, 'clouds': [], 'visib': 0.5, 'wxString': 'SN'})}, {}, T0)
    at, q, notes = ss.stations_obs({'at': T0, 'home': home}, T0)
    assert q['temp'] == (-1, 0.6) and q['snow'][0] == 1 and q['haze'][0] > 0.9 and notes['vis'] == 800
    monkeypatch.setattr(ss, 'next_rain', lambda now, fc=None: None)
    d = ss.state(T0, {'stations': (at, q, notes)})
    a = d['air']
    assert a['temp']['v'] == -1 and a['rh'] == 93 and a['feels'] < -5 and a['pressure']['v'] == 1020 and a['dir'] == 0
    assert ss.stations_obs({'at': T0 - 7200, 'home': home}, T0) is None

def test_next_rain_and_outlook(monkeypatch):
    f = {'at': T0, 'time': [T0 + 3600 * i for i in range(4)], 'rain': [0, 0.5, 2, 0.5], 'rain_p': [0, 0.2, 0.8, 0.6]}
    assert ss.next_rain(T0, f) == {'begin': T0 + 3600, 'end': T0 + 3 * 3600, 'mm': 2, 'p': 0.8}
    monkeypatch.setattr(st, 'doc', lambda: None)
    f |= {k: [10, 12, 9, 8] for k in ('temp', 'dew', 'wind', 'gust', 'pressure', 'cloud', 'spread')}
    o = ss.outlook(f, [[T0 - 600, 14.0], [T0 - 86400, 30.0]], T0 + 60)
    assert o['today'] == {'high': 14, 'low': 8} and len(o['hours']) == 4

def test_card_from_sky():
    from disinfo.screens.weather import state, vigilance
    q = lambda v, conf=0.9: {'v': v, 'conf': conf, 'by': {}}
    d = {'time': {'sun': {'alt': 20}}, 'sky': {'cover': q(0.1)}, 'precip': {'rate': q(0.0), 'snow': q(0.0)},
         'air': {'temp': q(-2.04), 'feels': -7, 'gust': q(16.0), 'tendency': -4, 'vis': 9000, 'wx': []},
         'sources': {'stations': 60}, 'forecast': {'today': {'high': 1, 'low': -5},
                                                   'hours': [[T0 + 3600, -2, 0, 0, 0, 0, 1.5, 0.6, 1, 0.5]]}}
    assert state.from_sky(d) == {'temperature': -2.0, 'icon_name': 'wind', 't_high': 1, 't_low': -5, 'outdated': False}
    d['air']['gust'] = q(5.0)
    assert state.icon_of(d) == 'clear-day'
    d['precip']['rate'] = q(1.0)
    assert state.icon_of(d) == 'rain'
    d['air']['temp'] = q(-2.04, 0.5)
    assert state.from_sky(d)['temperature'] == -2
    assert vigilance.forecast_lines(T0, sky=d) == ["Pluie jusqu'à 20h 2mm/h 60%", 'Min -2C à 20h', 'Ressenti -7C', 'Pression -4hPa/3h']
    assert state.from_sky({'air': {}}) is None

def test_graphs(monkeypatch):
    import time
    from types import SimpleNamespace as NS
    from disinfo.screens.weather import graphs as g
    fs = NS(config=NS(name='s'), now=NS(timestamp=lambda: T0), tick=time.time())
    # Open with the metro, under the weather card; a touch decides for a while, then the metro again.
    monkeypatch.setattr(g, 'metro_up', lambda fs: True)
    st = g.GraphsStateManager().get_state(fs)
    st.tapped.clear()
    assert g.shown(fs) == (True, 'side')
    g.GraphsStateManager().process_message('', NS(action='weather.graphs', payload={'screen': 's', 'show': False}))
    assert g.shown(fs) == (False, 'side')
    st.tapped['s'][1] -= g.keep_open + 1
    assert g.shown(fs) == (False, 'side')
    st.tapped['s'][1] -= g.keep_shut
    monkeypatch.setattr(g, 'metro_up', lambda fs: False)
    assert g.shown(fs) == (False, 'bottom')
    # Opened by a touch: gone again after keep_open.
    g.GraphsStateManager().process_message('', NS(action='weather.graphs', payload={'screen': 's', 'show': True}))
    assert g.shown(fs) == (True, 'bottom')
    st.tapped['s'][1] -= g.keep_open + 1
    assert g.shown(fs) == (False, 'bottom')
    assert g.toggle(fs, False)(10, 5) == g.Target(0, 0, 10, 5, 'weather.graphs', {'screen': 's', 'show': True})
    # The stations' 6 h, the forecast's 18: a line, the rain only when there's some.
    seen = [[T0 - 3600 * i, 12.0 + i * 0.2, 0.0] for i in range(6, -1, -1)]
    ahead = [[T0 + 3600 * i, 12.0 + i, 0.5, 2.0 if i == 3 else 0.0, 0.8] for i in range(1, 20)]
    f = g.temp_graph(seen, ahead, T0, 96, 34, 6, 18)
    assert f.size == (96, 34) and f.image.getbbox()
    assert g.temp_graph([], [], T0, 96, 34, 6, 18) is None
    assert g.rain_graph(seen, ahead, T0, 96, 5, 6, 18).image.getbbox()
    assert g.rain_graph(seen, [r[:3] + [0.0, 0.0] for r in ahead], T0, 96, 5, 6, 18) is None

def test_graph_pages():
    import time
    from types import SimpleNamespace as NS
    from disinfo.screens.weather import graphs as g
    q = lambda v: {'v': v, 'conf': 0.9, 'by': {}}
    lt = time.localtime(T0)
    t0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + 1, 0, 0, 0, 0, 0, -1))
    hours = [[t0 + 3600 * i, 8 + i % 8, 0, 3, 16 if i == 14 else 5, 1015, 0.5, 0.6, 1, 0.5] for i in range(1, 25)]
    sky = {'air': {'feels': 9.6, 'dew': q(7.2), 'ceiling': 300, 'vis': 4000}, 'forecast': {'hours': hours}}
    assert g.feel_row(sky, 112).width <= 112 and g.feel_row(sky, 40).width <= 40
    assert g.tomorrow_row(sky, T0, 112) and g.tomorrow_row({'forecast': {'hours': hours[:6]}}, T0, 112) is None
    rows = [g.text(f'{i}', g.s_value) for i in range(3)]
    fs = lambda tick: NS(tick=tick)
    assert g.pages(fs(0), 't', rows[:1]) is rows[0] and g.pages(fs(0), 't', [None]) is None
    assert g.pages(fs(g.page_s * 4 + 1), 't', rows).size == rows[1].size

def test_close_the_windows():
    from disinfo.screens.weather import window as wn
    q = lambda v: {'v': v, 'conf': 0.9, 'by': {}}
    sky = lambda dir, wind, gust=None, rate=0.0, nxt=None: {'air': {'dir': dir, 'wind': q(wind), 'gust': q(gust or wind)},
                                                            'precip': {'rate': q(rate), 'next': nxt}}
    # Facing east, 5° to the south: in from the east, not from the west or along the facade.
    assert wn.into(95) == 1 and wn.into(275) == 0 and wn.into(10) == 0 and 0.5 < wn.into(140) < 0.75
    assert wn.advice(sky(100, 7), T0) and not wn.advice(sky(280, 15), T0) and not wn.advice(sky(100, 3), T0)
    assert wn.advice(sky(80, 4, 12), T0)['gust'] == 12
    # Rain blowing in, now or soon: a lighter wind will do.
    assert wn.advice(sky(90, 3, rate=1.0), T0)['rain'] and not wn.advice(sky(270, 3, rate=1.0), T0)
    assert wn.advice(sky(90, 3, nxt={'begin': T0 + 600, 'end': T0 + 3600, 'p': 0.7}), T0)['rain']
    assert not wn.advice(sky(90, 3, nxt={'begin': T0 + 7200, 'end': T0 + 9000, 'p': 0.7}), T0)
    assert not wn.advice({'air': {}}, T0) and not wn.advice(None, T0)
    # Held a while after: no blinking with the gusts.
    wn._held.update(until=0, why=None)
    assert wn.shown(sky(100, 7), T0) and wn.shown(sky(100, 1), T0 + 60) and not wn.shown(sky(100, 1), T0 + wn.hold_s + 1)
