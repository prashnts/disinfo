import os
import json

from datetime import datetime

import pytest

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from disinfo.config import MetroData, MetroStop, MetroWindow
from disinfo.drat import idfm

T0 = datetime(2026, 10, 26, 8, 0, tzinfo=idfm.tz).timestamp()     # a monday, 8:00
stop = MetroStop(line='1', line_id='C01371', stop='Reuilly - Diderot', stop_id='44637', direction='Charles de Gaulle - Etoile')


def visit(at, direction='Charles de Gaulle-Étoile', status='onTime', line='C01371'):
    return {'MonitoredVehicleJourney': {'LineRef': {'value': f'STIF:Line::{line}:'},
        'DirectionName': [{'value': direction}], 'DestinationName': [{'value': direction}],
        'MonitoredCall': {'ExpectedDepartureTime': at, 'DepartureStatus': status}}}

def stops_doc(*visits):
    return {'Siri': {'ServiceDelivery': {'StopMonitoringDelivery': [{'MonitoredStopVisit': list(visits)}]}}}

@pytest.fixture
def conf(monkeypatch):
    c = MetroData(walk_min=5, stops=[stop], schedule=[MetroWindow(days=[1, 2, 3, 4, 5], start='07:00', end='09:00'),
                                                       MetroWindow(days=[4], start='15:00', end='16:30', month_days=(1, 14))])
    monkeypatch.setattr(idfm, 'conf', lambda: c)
    return c


def test_trains():
    doc = stops_doc(
        visit('2026-10-26T07:06:00.5Z'),
        visit('2026-10-26T07:03:00Z'),          # no fraction
        visit('2026-10-26T07:04:00Z', direction='Château de Vincennes'),
        visit('2026-10-26T07:09:00Z', status='cancelled'),
        visit('2026-10-26T07:05:00Z', line='C01378'))
    assert idfm.parse_trains(doc, stop.line_id, stop.direction) == [T0 + 180, T0 + 360.5]

def test_reports():
    period = lambda b, e: {'begin': datetime.fromtimestamp(b, idfm.tz).strftime('%Y%m%dT%H%M%S'), 'end': datetime.fromtimestamp(e, idfm.tz).strftime('%Y%m%dT%H%M%S')}
    dis = lambda i, b, e, tags=None: {'id': i, 'tags': tags, 'status': 'active', 'severity': {'effect': 'NO_SERVICE'}, 'updated_at': 'x',
                                      'application_periods': [period(b, e)], 'messages': [
                                          {'channel': {'name': 'titre'}, 'text': f'Métro 1 : {i}'},
                                          {'channel': {'name': 'moteur'}, 'text': '<p>Trafic&nbsp;interrompu<br>Bus</p>'}]}
    day = 86400
    ids = ('now', 'lift', 'cut', 'ended', 'far')
    doc = {'disruptions': [dis('now', T0 - 60, T0 + 60), dis('lift', T0 - 60, T0 + 60, ['Ascenseur']),
                           dis('cut', T0 - day / 2, T0 - day / 2 + 1), dis('ended', T0 - 3600, T0 - 60), dis('far', T0 + 30 * day, T0 + 31 * day)],
           'line_reports': [{'line': {'code': l}, 'pt_objects': [{'links': [{'type': 'disruption', 'id': i}]} for i in ids]} for l in ('1', '2', '3')]}
    rs = idfm.parse_reports(doc, {'1', '3'}, T0)
    # A period cut short (a second) stays a day: its text may say more.
    assert [(r['id'], r['lines']) for r in rs] == [('now', ['1', '3']), ('cut', ['1', '3'])]
    assert rs[0]['text'] == 'Trafic interrompu Bus'

def test_schedule_and_press(conf):
    at = lambda *a: datetime(*a, tzinfo=idfm.tz)
    assert idfm.scheduled(at(2026, 10, 26, 7, 30))
    assert not idfm.scheduled(at(2026, 10, 25, 7, 30))      # sunday
    assert idfm.scheduled(at(2026, 10, 8, 15, 30)) and not idfm.scheduled(at(2026, 10, 22, 15, 30))     # thursdays, first two weeks
    now = at(2026, 10, 26, 7, 30)
    assert not idfm.visible(now, {'show': False, 'until': now.timestamp() + 1})
    assert idfm.visible(now, {'show': False, 'until': now.timestamp() - 1})
    assert idfm.visible(at(2026, 10, 26, 12), {'show': True, 'until': now.timestamp() + 5 * 3600})

def test_walk_and_health(conf):
    times = [T0 + m * 60 for m in (2, 6, 9, 13)]
    assert idfm.catchable(stop, times, T0) == [6, 9, 13]
    assert idfm.catchable(stop.model_copy(update={'walk_min': 10}), times, T0) == [13]
    assert idfm.health(times, T0) == 'ok'
    assert idfm.health([T0 + 60, T0 + 15 * 60], T0) == 'slow'
    assert idfm.health([T0 + 60], T0) == 'slow'
    assert idfm.health([], T0) == 'none'


class FakeDB(dict):
    def get(self, k):
        return super().get(k)
    def set(self, k, v, ex=None):
        self[k] = v

def test_no_overfetch(conf, monkeypatch):
    calls, clock = [], [T0]
    def get(path, **params):
        calls.append(path)
        return stops_doc() if path == 'stop-monitoring' else {}
    monkeypatch.setattr(idfm, 'db', FakeDB())
    monkeypatch.setattr(idfm, 'get', get)
    monkeypatch.setattr(idfm, 'publish', lambda *a: None)
    monkeypatch.setattr(idfm, 'summarize', lambda doc: None)
    monkeypatch.setattr(idfm.time, 'time', lambda: clock[0])
    monkeypatch.setattr(idfm, 'datetime', type('dt', (datetime,), {'now': staticmethod(lambda tz=None: datetime.fromtimestamp(clock[0], tz))}))

    # 8:00 monday: the trains and the messages, then nothing until they're due.
    assert idfm.task() and len(calls) == 2
    clock[0] += 30
    assert not idfm.task() and len(calls) == 2
    clock[0] += 30
    assert idfm.task() and calls[2:] == ['stop-monitoring']
    # A press: fresher, but not every time.
    clock[0] += 5
    assert not idfm.task(pressed=True)
    clock[0] += 15
    assert idfm.task(pressed=True) and len(calls) == 4
    # Out of the schedule: nothing, unless shown.
    clock[0] = T0 + 3 * 3600
    assert not idfm.task() and len(calls) == 4
    idfm.db.set(idfm.PRESS_KEY, json.dumps({'show': True, 'until': clock[0] + 60}))
    assert idfm.task() and len(calls) == 6

def test_note_overlap():
    r = {'id': 'a', 'lines': ['13'], 'title': 'Métro 13 : Travaux - Trafic interrompu', 'effect': 'NO_SERVICE',
         'periods': [[T0 - 3600, T0 - 3599]]}        # cut to a second, the text says until noon
    assert idfm.note(r, {}, T0) is None
    llm = {'a': {'text': 'Travaux, trafic interrompu', 'when': "jusqu'à 12h", 'level': 'stop', 'doubt': 'période fausse',
                 'spans': [[T0 - 3600, T0 + 4 * 3600]]}}
    n = idfm.note(r, llm, T0)
    assert n['now'] and n['lines'] == ['13'] and n['when'] == "jusqu'à 12h"
    later = idfm.note({**r, 'periods': [[T0 + 86400, T0 + 2 * 86400]]}, {}, T0)
    assert not later['now'] and later['when'] == '27/10' and later['text'] == 'Travaux - Trafic interrompu' and later['level'] == 'stop'
