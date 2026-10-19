import os
import io
import json
import base64
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from disinfo import transport
from disinfo.transport import pack_raw, unpack_raw, pack_ws2, encode, RGBZ, PNG, RGB565Z

# The client's package imports the matrix hardware: load the module alone.
_spec = importlib.util.spec_from_file_location(
    'ws_frames', Path(__file__).parents[1] / 'clients/websocket-rpi-matrix/src/websocket_rpi_matrix/frames.py')
frames = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frames)


def picture(size=(8, 6), seed=0) -> Image.Image:
    return Image.fromarray(np.random.default_rng(seed).integers(0, 256, (size[1], size[0], 3), dtype=np.uint8))

def same(a: Image.Image, b: Image.Image) -> bool:
    return a.size == b.size and a.tobytes() == b.tobytes()

def message(img: Image.Image, seq: int, base_seq: int = 0, at=(0, 0), enc: int = RGBZ) -> bytes:
    return pack_ws2(seq, base_seq, (*at, *img.size), enc, encode(img.tobytes(), img.size, enc))


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
    assert (frames.RGBZ, frames.PNG) == (RGBZ, PNG)


# Partial updates, on the client.

def test_region_is_pasted_in_place():
    a, patch = picture((8, 6), 1), picture((3, 2), 2)
    f = frames.FrameAssembler()
    assert f.apply(message(a, 1)) and f.apply(message(patch, 2, base_seq=1, at=(4, 3)))
    want = a.copy()
    want.paste(patch, (4, 3))
    assert f.seq == 2 and same(f.frame, want)

def test_regions_chain_on_each_other():
    f = frames.FrameAssembler()
    f.apply(message(picture((8, 6), 1), 1))
    p2, p3 = picture((2, 2), 2), picture((2, 2), 3)
    assert f.apply(message(p2, 2, base_seq=1, at=(0, 0))) and f.apply(message(p3, 3, base_seq=2, at=(6, 4)))
    assert same(f.frame.crop((0, 0, 2, 2)), p2) and same(f.frame.crop((6, 4, 8, 6)), p3)

def test_region_of_another_frame_asks_for_a_whole_one():
    f = frames.FrameAssembler()
    assert not f.apply(message(picture((2, 2)), 2, base_seq=1))     # nothing yet
    a = picture((8, 6), 1)
    f.apply(message(a, 5))
    assert not f.apply(message(picture((2, 2)), 7, base_seq=6))     # missed frame 6
    assert f.seq == 5 and same(f.frame, a)
    assert f.apply(message(picture((4, 4), 9), 8))                  # a whole frame, any size, starts over
    assert f.frame.size == (4, 4)

def test_png_region():
    f = frames.FrameAssembler()
    f.apply(message(picture((8, 6), 1), 1, enc=PNG))
    patch = picture((3, 3), 2)
    assert f.apply(message(patch, 2, base_seq=1, at=(1, 1), enc=PNG)) and same(f.frame.crop((1, 1, 4, 4)), patch)

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

def receive_frame(ws, f):
    msg = ws.receive()
    assert 'bytes' in msg, msg
    assert f.apply(msg['bytes'])

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
    import time, asyncio
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


# The renderer.

def test_renderer_skips_unchanged_frames(monkeypatch):
    from disinfo.renderers import background
    sent, now = [], [100.0]
    monkeypatch.setattr(background, 'db', type('db', (), {'publish': lambda self, ch, data: sent.append(data)})())
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
