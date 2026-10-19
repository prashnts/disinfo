import os
import io
import json
import time
import base64
import struct
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from disinfo import transport
from disinfo.transport import pack_raw, unpack_raw, pack_ws2, encode, changed_boxes, pack_regions, bounds, REGION, RGBZ, PNG, RGB565Z

# The client's package imports the matrix hardware: load the module alone.
_spec = importlib.util.spec_from_file_location(
    'ws_frames', Path(__file__).parents[1] / 'clients/websocket-rpi-matrix/src/websocket_rpi_matrix/frames.py')
frames = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frames)


def picture(size=(8, 6), seed=0) -> Image.Image:
    return Image.fromarray(np.random.default_rng(seed).integers(0, 256, (size[1], size[0], 3), dtype=np.uint8))

def same(a: Image.Image, b: Image.Image) -> bool:
    return a.size == b.size and a.tobytes() == b.tobytes()

def message(img: Image.Image, seq: int, enc: int = RGBZ) -> bytes:
    return pack_ws2(seq, 0, (0, 0, *img.size), enc, encode(img.tobytes(), img.size, enc))

def regions(seq: int, base_seq: int, parts: list, enc: int = RGBZ) -> bytes:
    # parts: (picture, (x, y))
    payload = struct.pack('<H', len(parts))
    for img, (x, y) in parts:
        data = encode(img.tobytes(), img.size, enc)
        payload += REGION.pack(x, y, *img.size, len(data)) + data
    return pack_ws2(seq, base_seq, bounds([(*at, *img.size) for img, at in parts]), enc, payload)

def changed(a: Image.Image, at: tuple[int, int], size=(3, 3), seed=9) -> Image.Image:
    b = a.copy()
    b.paste(picture(size, seed), at)
    return b


def test_raw_roundtrip():
    img = picture()
    name, w, h, rgbz = unpack_raw(pack_raw('distudy', img.size, img.tobytes()))
    assert (name, w, h) == ('distudy', 8, 6) and same(Image.frombytes('RGB', (w, h), transport.zlib.decompress(rgbz)), img)

def test_rgb565():
    img = picture()
    v = np.frombuffer(transport.zlib.decompress(encode(img.tobytes(), img.size, RGB565Z)), '<u2')
    a = np.asarray(img).reshape(-1, 3)
    assert (v >> 11 == a[:, 0] >> 3).all() and ((v >> 5) & 63 == a[:, 1] >> 2).all() and (v & 31 == a[:, 2] >> 3).all()

def test_client_reads_the_server_format():
    assert frames.WS2_HEADER.format == transport.WS2_HEADER.format and frames.WS2_MAGIC == transport.WS2_MAGIC
    assert frames.REGION.format == REGION.format and (frames.RGBZ, frames.PNG) == (RGBZ, PNG)

def test_changed_boxes():
    a = np.zeros((48, 64, 3), np.uint8)
    b = a.copy()
    b[2, 3] = 1
    b[20:40, 40:60] = 9
    b[18, 40] = 9
    assert changed_boxes(a.tobytes(), b.tobytes(), (64, 48)) == [(0, 0, 16, 16), (32, 16, 32, 32)]
    assert changed_boxes(a.tobytes(), a.tobytes(), (64, 48)) == []
    a, b = np.zeros((20, 30, 3), np.uint8), np.zeros((20, 30, 3), np.uint8)
    b[19, 29] = 5
    assert changed_boxes(a.tobytes(), b.tobytes(), (30, 20)) == [(16, 16, 14, 4)]   # cut to the frame

@pytest.mark.parametrize('enc', [RGBZ, PNG])
def test_regions_from_the_server_rebuild_the_frame(enc):
    a = picture((50, 37), 1)                                         # not whole tiles
    b = changed(changed(a, (48, 35), (2, 2)), (3, 20), (20, 5))
    boxes = changed_boxes(a.tobytes(), b.tobytes(), a.size)
    f = frames.FrameAssembler()
    f.apply(message(a, 1, enc))
    assert f.apply(pack_ws2(2, 1, bounds(boxes), enc, pack_regions(b.tobytes(), b.size, boxes, enc)))
    assert same(f.frame, b)


# Partial updates, on the client.

def test_regions_are_pasted_in_place_together():
    a, p, q = picture((8, 6), 1), picture((3, 2), 2), picture((2, 2), 3)
    f = frames.FrameAssembler()
    shown = []
    assert f.apply(message(a, 1))
    shown.append(f.frame)
    assert f.apply(regions(2, 1, [(p, (4, 3)), (q, (0, 0))]))
    want = a.copy()
    want.paste(p, (4, 3))
    want.paste(q, (0, 0))
    assert f.seq == 2 and same(f.frame, want)
    assert same(shown[0], a)        # a new frame, the one shown before is left as it was

def test_regions_chain_on_each_other():
    f = frames.FrameAssembler()
    f.apply(message(picture((8, 6), 1), 1))
    p2, p3 = picture((2, 2), 2), picture((2, 2), 3)
    assert f.apply(regions(2, 1, [(p2, (0, 0))])) and f.apply(regions(3, 2, [(p3, (6, 4))]))
    assert same(f.frame.crop((0, 0, 2, 2)), p2) and same(f.frame.crop((6, 4, 8, 6)), p3)

def test_no_regions_moves_to_the_frame():
    f = frames.FrameAssembler()
    a = picture((8, 6), 1)
    f.apply(message(a, 1))
    assert f.apply(regions(4, 1, [])) and f.seq == 4 and same(f.frame, a)

def test_regions_of_another_frame_ask_for_a_whole_one():
    f = frames.FrameAssembler()
    assert not f.apply(regions(2, 1, [(picture((2, 2)), (0, 0))]))   # nothing yet
    a = picture((8, 6), 1)
    f.apply(message(a, 5))
    assert not f.apply(regions(7, 6, [(picture((2, 2)), (0, 0))]))   # missed frame 6
    assert f.seq == 5 and same(f.frame, a)
    assert f.apply(message(picture((4, 4), 9), 8))                   # a whole frame, any size, starts over
    assert f.frame.size == (4, 4)

def test_not_a_frame():
    with pytest.raises(ValueError):
        frames.FrameAssembler().apply(b'nope' + bytes(17))


# The server.

@pytest.fixture(scope='module')
def server():
    from fastapi.testclient import TestClient
    from disinfo.web import server
    with TestClient(server.app) as client:
        yield server, client

def publish(server, name: str, img: Image.Image):
    server.load_raw({'data': pack_raw(name, img.size, img.tobytes())})

def next_bytes(ws) -> bytes:
    # Text first ({"display"}, acts, alive): the next frame.
    while 'bytes' not in (msg := ws.receive()):
        pass
    return msg['bytes']

def receive_frame(ws, f):
    assert f.apply(next_bytes(ws))

def test_ws2_whole_frame_on_connect(server):
    srv, client = server
    a = picture((16, 8), 1)
    publish(srv, 't.connect', a)
    f = frames.FrameAssembler()
    with client.websocket_connect('/ws2/t.connect') as ws:
        receive_frame(ws, f)
    assert same(f.frame, a)

def test_ws2_pushes_changes_and_skips_identical(server):
    srv, client = server
    a, b = picture((16, 8), 1), picture((16, 8), 2)
    publish(srv, 't.push', a)
    f = frames.FrameAssembler()
    with client.websocket_connect('/ws2/t.push') as ws:
        receive_frame(ws, f)
        first = f.seq
        publish(srv, 't.push', a)       # the same picture again: not a new frame
        publish(srv, 't.push', b)
        receive_frame(ws, f)
    assert f.seq == first + 1 and same(f.frame, b)

def test_ws2_resync_sends_the_whole_frame_again(server):
    srv, client = server
    a = picture((16, 8), 3)
    publish(srv, 't.resync', a)
    with client.websocket_connect('/ws2/t.resync') as ws:
        receive_frame(ws, frames.FrameAssembler())
        ws.send_text(json.dumps({'resync': 1}))
        f = frames.FrameAssembler()
        receive_frame(ws, f)
    assert same(f.frame, a)

def test_ws2_acts(server):
    from disinfo.drat.app_states import PubSubMessage
    srv, client = server
    publish(srv, 't.acts', picture())
    with client.websocket_connect('/ws2/t.acts') as ws:
        receive_frame(ws, frames.FrameAssembler())
        srv.load_acts('di.pubsub.acts', PubSubMessage(action='act', payload={'dest': 't.acts', 'cmd': ['buzzer', 'boop', 1]}))
        assert json.loads(ws.receive_text()) == {'acts': [['buzzer', 'boop', 1]]}

def test_ws2_sends_only_what_changed(server):
    srv, client = server
    a = picture((64, 48), 1)
    b = changed(a, (40, 30))
    publish(srv, 't.regions', a)
    f = frames.FrameAssembler()
    with client.websocket_connect('/ws2/t.regions') as ws:
        whole = next_bytes(ws)
        f.apply(whole)
        publish(srv, 't.regions', b)
        msg = next_bytes(ws)
    _, seq, base_seq, x, y, w, h, _ = transport.WS2_HEADER.unpack_from(msg)
    assert base_seq == f.seq and (x, y, w, h) == (32, 16, 16, 32) and len(msg) < len(whole) / 3
    assert f.apply(msg) and same(f.frame, b)

def test_ws2_catches_up_from_the_frame_it_has(server):
    srv, client = server
    a = picture((64, 48), 1)
    publish(srv, 't.behind', a)
    f = frames.FrameAssembler()
    with client.websocket_connect('/ws2/t.behind') as ws:
        receive_frame(ws, f)
        for i in range(5):
            a = changed(a, (i * 9, i * 7), seed=i)
            publish(srv, 't.behind', a)
        last, t = srv.screens['t.behind'].seq, time.monotonic()
        while f.seq != last:
            receive_frame(ws, f)
    assert same(f.frame, a)
    assert time.monotonic() - t < 0.5     # a frame that came during a send isn't left for the 1 s timeout

def test_ws2_mostly_changed_is_sent_whole(server):
    srv, client = server
    publish(srv, 't.most', picture((64, 48), 1))
    with client.websocket_connect('/ws2/t.most') as ws:
        next_bytes(ws)
        publish(srv, 't.most', picture((64, 48), 2))
        assert transport.WS2_HEADER.unpack_from(next_bytes(ws))[2] == 0

def test_too_far_behind_gets_the_whole_frame(server):
    srv, _ = server
    a = picture((32, 32), 1)
    for i in range(srv.HISTORY + 2):
        a = changed(a, (0, 0), (2, 2), seed=i)
        publish(srv, 't.far', a)
    s = srv.screens['t.far']
    assert transport.WS2_HEADER.unpack_from(s.message(s.seq - 1, RGBZ))[2] == s.seq - 1
    assert transport.WS2_HEADER.unpack_from(s.message(s.seq - srv.HISTORY - 1, RGBZ))[2] == 0

def test_ws2_png(server):
    srv, client = server
    a = picture((16, 8), 4)
    publish(srv, 't.png', a)
    f = frames.FrameAssembler()
    with client.websocket_connect('/ws2/t.png?fmt=png') as ws:
        receive_frame(ws, f)
    assert same(f.frame, a)

def test_v1_and_snapshot_from_the_same_frame(server):
    srv, client = server
    a = picture((16, 8), 5)
    publish(srv, 't.v1', a)
    with client.websocket_connect('/ws/t.v1') as ws:
        ws.send_text('{}')
        payload = json.loads(ws.receive_text())
    assert same(Image.open(io.BytesIO(base64.b64decode(payload['img']))).convert('RGB'), a)
    r = client.get('/png/t.v1')
    assert r.status_code == 200 and same(Image.open(io.BytesIO(r.content)).convert('RGB'), a)
    assert client.get('/png/t.none').status_code == 404


def test_frames_keep_coming_after_a_bad_message(server):
    import asyncio
    from disinfo.redis import db
    srv, _ = server
    loop = asyncio.new_event_loop()
    loop.close()
    srv._loop = loop
    srv.notify('t.closed')                  # the server's loop is gone: nothing to wake
    db.publish(transport.RAW_CHANNEL, b'not a frame')
    a = picture((4, 4), 7)
    db.publish(transport.RAW_CHANNEL, pack_raw('t.after', a.size, a.tobytes()))
    t = time.monotonic()
    while 't.after' not in srv.screens and time.monotonic() - t < 3:
        time.sleep(0.02)
    assert same(srv.screens['t.after'].image(), a)


# Touch: the server finds the target under it.

def test_touch_down_and_up_on_a_target_acts(server, monkeypatch):
    srv, _ = server
    acted, pressed = [], []
    monkeypatch.setattr(srv, 'act', lambda action, payload: acted.append((action, payload)))
    monkeypatch.setattr(srv, 'publish', lambda ch, action, payload: pressed.append(payload['pressed']))
    srv.targets['t.touch'] = [[0, 0, 100, 100, 'big', None], [10, 10, 20, 20, 'small', {'n': 1}]]
    srv.touched('t.touch', 15, 15, 'down')
    srv.touched('t.touch', 16, 16, 'move')
    srv.touched('t.touch', 16, 16, 'up')
    assert acted == [('small', {'n': 1})]                    # the one on top
    assert pressed == [['small', {'n': 1}], None]           # held, then let go (a move inside says nothing)

def test_touch_slid_off_or_let_go_elsewhere_does_nothing(server, monkeypatch):
    srv, _ = server
    acted = []
    monkeypatch.setattr(srv, 'act', lambda action, payload: acted.append(action))
    monkeypatch.setattr(srv, 'publish', lambda *a, **k: None)
    srv.targets['t.off'] = [[10, 10, 20, 20, 'small', None]]
    srv.touched('t.off', 15, 15, 'down')
    srv.touched('t.off', 50, 50, 'move')                    # slid off: cancelled
    srv.touched('t.off', 15, 15, 'up')
    srv.touched('t.off', 15, 15, 'down')
    srv.touched('t.off', 90, 90, 'up')                      # let go elsewhere
    srv.touched('t.off', 90, 90, 'down')                    # nothing there
    srv.touched('t.off', 90, 90, 'up')
    assert acted == []

def test_touch_comes_over_ws2(server, monkeypatch):
    srv, client = server
    seen = []
    monkeypatch.setattr(srv, 'touched', lambda *a: seen.append(a))
    publish(srv, 't.wstouch', picture())
    with client.websocket_connect('/ws2/t.wstouch') as ws:
        next_bytes(ws)
        ws.send_text(json.dumps({'touch': [3, 4, 'down']}))
        t = time.monotonic()
        while not seen and time.monotonic() - t < 2:
            time.sleep(0.01)
    assert seen == [('t.wstouch', 3, 4, 'down')]


def test_display_sensors_go_to_home_assistant(server, monkeypatch):
    from disinfo.utils import ha_states
    srv, client = server
    posted = []
    monkeypatch.setattr(ha_states.app_config, 'ha_token', type('t', (), {'get_secret_value': lambda self: 'x'})())
    monkeypatch.setattr(ha_states.requests, 'post', lambda url, **k: posted.append((url, k['json'])))
    publish(srv, 't.sensors', picture())
    with client.websocket_connect('/ws2/t.sensors') as ws:
        next_bytes(ws)
        ws.send_text(json.dumps({'_node': 'dientry', 'telemetry': json.dumps({'temperature': 22.5, 'lux': 120.0, 'odd': 1})}))
        t = time.monotonic()
        while len(posted) < 2 and time.monotonic() - t < 3:
            time.sleep(0.02)
    states = {url.rsplit('/', 1)[1]: j for url, j in posted}
    assert sorted(states) == ['sensor.guiton_bme680_temperature', 'sensor.guiton_dientry_lux']     # ESPHome's ids
    t = states['sensor.guiton_bme680_temperature']
    assert t['state'] == 21.5 and t['attributes']['unit_of_measurement'] == '°C' and t['attributes']['device_class'] == 'temperature'
    ha_states.publish('elsewhere', {'lux': 3})
    assert posted[-1][0].endswith('/api/states/sensor.elsewhere_lux')


def test_display_goes_dark_when_no_one_is_there(server):
    from disinfo.drat.app_states import PubSubMessage
    srv, client = server
    publish(srv, 't.dark', picture())
    srv.load_targets('di.pubsub.targets', PubSubMessage(action='t.dark', payload={'targets': [], 'awake': True}))
    with client.websocket_connect('/ws2/t.dark') as ws:
        assert abs(json.loads(ws.receive_text())['time'] - time.time()) < 5      # the clock, for displays without NTP
        assert json.loads(ws.receive_text()) == {'display': {'on': True}}
        next_bytes(ws)
        srv.load_targets('di.pubsub.targets', PubSubMessage(action='t.dark', payload={'targets': [], 'awake': False}))
        assert json.loads(ws.receive_text()) == {'display': {'on': False}}


# The renderer.

def test_renderer_skips_unchanged_frames(monkeypatch):
    from disinfo.renderers import background
    sent, now = [], [100.0]
    monkeypatch.setattr(background, 'db', type('db', (), {'publish': lambda self, ch, data: sent.append(data)})())
    monkeypatch.setattr(background, 'publish', lambda *a, **k: None)
    monkeypatch.setattr(background, 'time', type('clock', (), {'monotonic': staticmethod(lambda: now[0])}))
    a, b = picture(seed=1), picture(seed=2)
    background.publish_frame(a, 't.render')
    background.publish_frame(a, 't.render')
    assert len(sent) == 1
    background.publish_frame(b, 't.render')
    assert len(sent) == 2
    now[0] += 1.5                       # unchanged, but resent every second
    background.publish_frame(b, 't.render')
    assert len(sent) == 3 and unpack_raw(sent[-1])[0] == 't.render'
