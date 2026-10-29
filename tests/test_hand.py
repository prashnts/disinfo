import os
os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from types import SimpleNamespace as NS

from disinfo.screens.aviator import hand
from disinfo.web.telemetry import DiTelemetryState


def setup(monkeypatch, zen_on=False):
    st, sent, clock = DiTelemetryState(), [], [100.0]
    monkeypatch.setattr(hand, 'TelemetryStateManager', lambda name: NS(get_state=lambda fs: st))
    monkeypatch.setattr(hand, 'publish', lambda ch, action, payload: sent.append((action, payload['on'])))
    monkeypatch.setattr(hand.shown, 'zen', lambda fs: zen_on)
    monkeypatch.setattr(hand.time, 'monotonic', lambda: clock[0])
    hand._pans.clear()
    return NS(config=NS(name='distudy')), st, sent, clock


def test_hand_turns_the_sky_in_zen(monkeypatch):
    fs, st, sent, clock = setup(monkeypatch)
    assert hand.update(fs) is None and hand.yaw(fs, 90) is None

    st.tof.near.pressed, st.tof.near.x = True, 4.0
    assert hand.update(fs) and hand.active(fs) and sent == [('zen', True)]
    assert hand.yaw(fs, 90) == 90          # from where the camera was
    st.tof.near.x = 3.0                    # a zone to the user's right: looks right
    hand.update(fs)
    assert hand.yaw(fs, 0) == 90 + hand.deg_per_zone

    st.tof.near.pressed = False
    clock[0] += hand.linger - 1
    assert hand.update(fs) and hand.active(fs)     # held a while where it was left
    clock[0] += 2
    assert hand.update(fs) is None and not hand.active(fs)
    assert sent == [('zen', True), ('zen', False)]


def test_zen_already_on_stays(monkeypatch):
    fs, st, sent, clock = setup(monkeypatch, zen_on=True)
    st.tof.near.pressed = True
    hand.update(fs)
    st.tof.near.pressed = False
    clock[0] += hand.linger + 1
    hand.update(fs)
    assert sent == []


def test_hand_nearer_zooms_in(monkeypatch):
    fs, st, sent, clock = setup(monkeypatch)
    st.tof.near.pressed, st.tof.near.x, st.tof.near.mm = True, 4.0, 300
    hand.update(fs)
    assert hand.fov(fs, 50) == 50          # from how wide it was
    st.tof.near.mm = 300 - hand.mm_per_half
    hand.update(fs)
    assert hand.fov(fs, 0) == 25
    st.tof.near.mm = 900                   # far out: clamped
    hand.update(fs)
    assert hand.fov(fs, 0) == hand.fov_range[1]
