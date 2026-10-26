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
         tof={'distance_mm': [1], 'updated_at': 900.0})
    send(m, light_sensor={'rgbc': [1, 1, 1, 20], 'updated_at': 3.0}, remote={'encoder': {'position': 0, 'updated_at': 3.0}, 'updated_at': 3.0},
         tof={'distance_mm': [2], 'updated_at': 3.0})
    s = m.state
    assert s.light_sensor.rgbc[3] == 20 and s.light_sensor.received_at > 0
    assert s.remote.encoder.position == 0 and s.tof.distance_mm == [2]


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
