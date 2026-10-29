import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / 'clients/websocket-rpi-matrix/src/websocket_rpi_matrix'))
from tof import ToFTracker, ToFParams, ToFRate, ToFRecorder     # the client's: plain numpy, no hardware


def frames(tr, grid, s, t):
    for _ in range(int(s * 15)):
        tr.update(np.asarray(grid).ravel().tolist(), now=t)
        t += 1 / 15
    return t


def test_present_near_and_rotation(tmp_path):
    room = np.full((8, 8), 2500)
    tr = ToFTracker(ToFParams(rotate=1), tmp_path / 'bg.json')
    t = frames(tr, room, 2, 0)
    assert not tr.present['on'] and not tr.found

    seated = room.copy()
    seated[0:4, 5:8] = 850              # the sensor's rows 0-3, cols 5-7: turned once, the top left
    t = frames(tr, seated, 2, t)
    assert tr.present['on'] and 800 < tr.target['mm'] < 900
    assert tr.target['x'] < 2 and tr.target['y'] < 2 and not tr.near['pressed']

    hand = seated.copy()
    hand[3:6, 3:6] = 120
    t = frames(tr, hand, 1, t)
    assert tr.near['pressed'] and tr.near['mm'] == 120
    t = frames(tr, seated, 1, t)
    assert not tr.near['pressed'] and tr.near['released_at'] > tr.near['pressed_at']

    t = frames(tr, room, 6, t)          # gone: off after the hold-off
    assert not tr.present['on'] and tr.target == {}
    s = tr.serialize()
    assert 'debug' not in s and len(tr.serialize(debug=True)['debug']['grid']) == 64

    tr.save()
    assert ToFTracker(ToFParams(rotate=1), tmp_path / 'bg.json').bg[4, 4] == 2500


def test_still_object_absorbed():
    tr = ToFTracker(ToFParams(absorb_s=60))
    room = np.full((8, 8), 2500)
    t = frames(tr, room, 1, 0)
    chair = room.copy()
    chair[6:8, 0:4] = 700
    t = frames(tr, chair, 30, t)
    assert tr.found
    t = frames(tr, chair, 40, t)        # still past absorb_s: the room now
    assert not tr.found


def seated_tracker():
    tr = ToFTracker(ToFParams())
    room = np.full((8, 8), 2500)
    t = frames(tr, room, 1, 0)
    body = room.copy()
    body[2:8, 1:6] = 650
    t = frames(tr, body, 10, t)     # the body learnt at 0.65 m
    return tr, room, body, t


def test_body_leaning_close_is_no_hand():
    tr, room, body, t = seated_tracker()
    lean = room.copy()
    lean[1:8, 0:6] = 480            # under near_mm, but the body: not 25 cm nearer than it
    t = frames(tr, lean, 3, t)
    assert not tr.near['pressed']


def test_passing_by_and_held_still():
    tr, room, body, t = seated_tracker()
    swipe = body.copy()
    swipe[3:5, 2:4] = 200
    t = frames(tr, swipe, 0.2, t)   # quicker than near_on_s
    t = frames(tr, body, 1, t)
    assert not tr.near['pressed']
    t = frames(tr, swipe, 1, t)
    assert tr.near['pressed']
    t = frames(tr, swipe, tr.params.near_still_s + 1, t)   # not moving: let go, and ignored till it goes
    assert not tr.near['pressed']
    t = frames(tr, body, 1, t)
    t = frames(tr, swipe, 1, t)
    assert tr.near['pressed']


def test_rate_by_ambient():
    r, t = ToFRate(), 0.0
    for amb, hz in ((1, 15), (150, 5), (50, 5), (35, 10), (15, 10), (10, 15)):
        for _ in range(100):
            r.update(amb, False, t)
            t += 0.1
        assert r.hz == hz, (amb, r.hz)
    r.update(150, False, t)
    assert r.update(150, True, t + 0.1) == 15         # a hand: full speed
    for _ in range(100):
        t += 0.1
        r.update(150, False, t)
    assert r.hz == 5


def test_reset_relearns(tmp_path):
    room = np.full((8, 8), 2500)
    tr = ToFTracker(ToFParams(), tmp_path / 'bg.json')
    t = frames(tr, room, 2, 0)
    moved = np.full((8, 8), 1200)                   # the sensor moved: the room nearer, and still
    t = frames(tr, moved, 2, t)
    assert tr.present['on']
    tr.reset()
    t = frames(tr, moved, 7, t)
    assert not tr.present['on'] and not tr.found


def test_recorder_session_writes_its_last_minute(tmp_path, monkeypatch):
    import tof
    clock = [1000.0]
    monkeypatch.setattr(tof.time, 'time', lambda: clock[0])
    rec, tr = ToFRecorder(tmp_path, until=0), ToFTracker(ToFParams())
    rec.add([0] * 64, [0] * 64, [0] * 64, tr)
    assert not rec._rows                            # no session
    rec.until = clock[0] + 20                       # act record:20
    for _ in range(10):
        rec.add([2500] * 64, [5] * 64, [1] * 64, tr, 90.0, 5)
        clock[0] += 1
    clock[0] += 30
    rec.add([2500] * 64, [5] * 64, [1] * 64, tr)
    f, = tmp_path.glob('*.npz')
    z = np.load(f)
    assert len(z['t']) == 10 and z['hz'][0] == 5 and z['amb'][0] == 90
