import os
import json

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from types import SimpleNamespace as NS
from disinfo.web.telemetry import TelemetryStateManager, DiTelemetryState
from disinfo.drat.app_states import PubSubMessage


def manager():
    m = object.__new__(TelemetryStateManager)      # no redis
    m.node, m.state = 'desk', DiTelemetryState()
    return m

def send(m, **data):
    m.process_message('di.pubsub.telemetry', PubSubMessage(action='update', payload={'data': json.dumps({'_node': 'desk', **data})}))


def test_client_restart():
    # The client's clock starts over when it restarts: its readings still come through.
    m = manager()
    send(m, light_sensor={'rgbc': [1, 1, 1, 5000], 'updated_at': 900.0}, remote={'encoder': {'position': 7, 'updated_at': 900.0}, 'updated_at': 900.0},
         tof={'present': {'on': True}, 'target': {'mm': 800}, 'updated_at': 900.0})
    send(m, light_sensor={'rgbc': [1, 1, 1, 20], 'updated_at': 3.0}, remote={'encoder': {'position': 0, 'updated_at': 3.0}, 'updated_at': 3.0},
         tof={'near': {'pressed': True, 'mm': 90}, 'target': {}, 'updated_at': 3.0})
    s = m.state
    assert s.light_sensor.rgbc[3] == 20 and s.light_sensor.received_at > 0
    assert s.remote.encoder.position == 0 and s.tof.near.pressed and s.tof.target is None


def test_timer_encoder_restart(monkeypatch):
    from disinfo.apps import timer
    m = manager()
    monkeypatch.setattr(timer, 'TelemetryStateManager', lambda name: NS(get_state=lambda fs: m.state, remote_reader=lambda *a: lambda b: False))
    monkeypatch.setattr(timer, 'act', lambda *a: None)
    monkeypatch.setattr(timer, 'states', {'desk': timer.State()})
    fs = NS(config=NS(name='desk'), tick=0)
    turn = lambda pos, at: (send(m, remote={'encoder': {'position': pos, 'updated_at': at}, 'updated_at': at}), timer.timer_view(fs))
    st = timer.states['desk']
    # Seen first at 40 (the renderer started after the turns): no turn. Then two clicks.
    turn(40, 100.0)
    assert st.duration == 0
    turn(42, 101.0)
    d = st.duration
    assert d > 0
    # The client restarts: back at 0 with a new clock, the duration stays.
    turn(0, 2.0)
    assert st.duration == d
    turn(1, 3.0)
    assert st.duration > d


def test_nfc_card_to_home_assistant(monkeypatch):
    from disinfo.utils import ha_states
    posts = []
    monkeypatch.setattr(ha_states.requests, 'post', lambda url, **kw: posts.append((url.split('/api/')[1], kw['json'])))
    monkeypatch.setattr(ha_states, '_cards', {})
    tell = lambda **nfc: ha_states.card('didial', nfc, {})
    tell(uid='', last='', updated_at=0.0)                          # what a (re)connect says: no event
    tell(uid='04A1B2C3', last='04A1B2C3', updated_at=12.5)
    tell(uid='04A1B2C3', last='04A1B2C3', updated_at=12.5)         # the same again (a turn's telemetry)
    tell(uid='', last='04A1B2C3', updated_at=14.0)
    assert [p for p, _ in posts] == ['states/sensor.didial_nfc', 'events/tag_scanned', 'states/sensor.didial_nfc', 'states/sensor.didial_nfc']
    assert posts[1][1] == {'tag_id': '04A1B2C3', 'device_id': 'didial'} and posts[3][1]['state'] == 'none'
