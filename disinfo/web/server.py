import io
import time
import zlib
import base64
import json
import asyncio

from collections import defaultdict
from PIL import Image
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Response
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, StreamingResponse

from disinfo.drat.app_states import PubSubManager, PubSubMessage
from disinfo.drat.tools import trigger_motion
from disinfo.data_structures import AppBaseModel
from disinfo.redis import db, publish
from disinfo.utils.hass import HaWS
from disinfo.utils import ha_states
from disinfo.transport import RAW_CHANNEL, ENCODINGS, PNG, RGBZ, unpack_raw, pack_ws2, encode, changed_boxes, pack_regions, bounds
from discore.imops import apply_gamma

app = FastAPI()

frames = {}     # screen -> JSON payload, from renderers still publishing PNGs
action_buffer = defaultdict(list)


HISTORY = 8     # frames a client can be behind and still get regions

class Screen:
    '''The newest frame of a screen, encoded once per format. prev: the frames before it.'''

    def __init__(self, seq: int, size: tuple[int, int], rgbz: bytes, prev: 'Screen | None' = None):
        self.seq, self.size, self.rgbz, self.prev = seq, size, rgbz, prev
        self.encoded = {RGBZ: rgbz}
        self._rgb = None
        s, n = self, 1
        while s.prev and n < HISTORY:
            s, n = s.prev, n + 1
        s.prev = None

    @property
    def rgb(self) -> bytes:
        if self._rgb is None:
            self._rgb = zlib.decompress(self.rgbz)
        return self._rgb

    def encode(self, encoding) -> bytes:
        if encoding not in self.encoded:
            self.encoded[encoding] = encode(self.rgb, self.size, encoding) if isinstance(encoding, int) else self._jpeg(*encoding[1:])
        return self.encoded[encoding]

    def image(self) -> Image.Image:
        return Image.frombytes('RGB', self.size, self.rgb)

    def message(self, base_seq: int, encoding: int) -> bytes:
        '''What changed since frame base_seq, or the whole frame.'''
        key = ('message', base_seq, encoding)
        if key not in self.encoded:
            self.encoded[key] = self._regions(base_seq, encoding) or pack_ws2(self.seq, 0, (0, 0, *self.size), encoding, self.encode(encoding))
        return self.encoded[key]

    def _regions(self, base_seq: int, encoding: int) -> bytes | None:
        base = self.prev
        while base and base.seq != base_seq:
            base = base.prev
        if not base or base.size != self.size:
            return None
        boxes = changed_boxes(base.rgb, self.rgb, self.size)
        # Mostly changed: the whole frame is as small, and simpler.
        if sum(w * h for _, _, w, h in boxes) > self.size[0] * self.size[1] // 2:
            return None
        return pack_ws2(self.seq, base_seq, bounds(boxes), encoding, pack_regions(self.rgb, self.size, boxes, encoding))

    def _jpeg(self, w: int, h: int, quality: int) -> bytes:
        im = self.image()
        # Largest whole scale that fits: pixels stay square and sharp.
        k = max(1, min(w // im.width, h // im.height)) if w and h else 1
        with io.BytesIO() as out:
            im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST).save(out, format='jpeg', quality=quality)
            return out.getvalue()

screens: dict[str, Screen] = {}
_loop = None
_changed: dict[str, asyncio.Event] = {}

def _wake(screen: str):
    if ev := _changed.pop(screen, None):
        ev.set()

def notify(screen: str):
    # From the pubsub threads. The loop is gone once the server stops.
    if _loop and not _loop.is_closed():
        try:
            _loop.call_soon_threadsafe(_wake, screen)
        except RuntimeError:
            pass

async def changed(screen: str, timeout: float):
    ev = _changed.setdefault(screen, asyncio.Event())
    try:
        await asyncio.wait_for(ev.wait(), timeout)
    except asyncio.TimeoutError:
        pass

def load_raw(message):
    name, w, h, rgbz = unpack_raw(message['data'])
    prev = screens.get(name)
    if prev and prev.rgbz == rgbz:
        return
    screens[name] = Screen((prev.seq if prev else 0) + 1, (w, h), rgbz, prev)
    notify(name)

_raw = db.pubsub(ignore_subscribe_messages=True)
_raw.subscribe(**{RAW_CHANNEL: load_raw})
def _keep_listening(e, pubsub, worker):
    print(f'[frames] {e!r}')

_raw.run_in_thread(sleep_time=0.01, daemon=True, exception_handler=_keep_listening)


def load_frame(channel_name, message: PubSubMessage):
    dest = message.action
    payload = {
        'img': message.payload['img'],
        'acts': action_buffer[dest],
        'd': dest,
    }
    frames[dest] = payload

targets = {}    # screen -> [[x, y, w, h, action, payload], ...] from the renderer, in the frame's px
awake = {}      # screen -> someone's there (its presence sensors): a display's backlight
held = {}       # screen -> the target a touch went down on

def load_targets(channel_name, message: PubSubMessage):
    targets[message.action] = message.payload['targets']
    if awake.get(message.action) != message.payload.get('awake', True):
        awake[message.action] = message.payload.get('awake', True)
        notify(message.action)

def touched(screen: str, x: int, y: int, phase: str):
    '''A touch on a screen's frame: the target under it held on down, its action done on up inside it.'''
    hit = next((t for t in reversed(targets.get(screen, [])) if t[0] <= x < t[0] + t[2] and t[1] <= y < t[1] + t[3]), None)
    if phase == 'down':
        held[screen] = hit
    elif phase == 'move':
        if not held.get(screen) or hit == held[screen]:
            return
        held[screen] = None         # slid off it: no press
    elif phase == 'up':
        t = held.pop(screen, None)
        if t and t == hit:
            act(t[4], t[5])
    t = held.get(screen)
    publish('di.pubsub.touch', action=screen, payload={'pressed': [t[4], t[5]] if t else None})

def act(action: str, payload):
    # ha.call: a Home Assistant service, from here (one server; the renderers are many). Else as the remote's.
    if action == 'ha.call':
        HaWS().call_service(payload['service'], target=payload.get('target', {}), service_data=payload.get('data', {}))
    else:
        publish('di.pubsub.remote', action=action, payload=payload or {})

def load_acts(channel_name, message: PubSubMessage):
    action_buffer[message.payload['dest']].append(message.payload['cmd'])
    notify(message.payload['dest'])

def v1_payload(screen: str) -> dict | None:
    if s := screens.get(screen):
        return {'img': base64.b64encode(s.encode(PNG)).decode(), 'acts': action_buffer[screen], 'd': screen}
    return frames.get(screen)

def screen_image(screen: str) -> Image.Image | None:
    if s := screens.get(screen):
        return s.image()
    if screen in frames:
        with io.BytesIO(base64.b64decode(frames[screen]['img'])) as incoming:
            return Image.open(incoming).convert('RGB')

def publish_telemetry(screen: str, msg: dict):
    telemetry = msg.get('telemetry')
    node_id = msg.get('_node')
    if telemetry and node_id:
        publish('di.pubsub.telemetry', action='update', payload={'data': telemetry, '_node': node_id})

PubSubManager().attach('frames', ('di.pubsub.frames',), load_frame)
PubSubManager().attach('acts', ('di.pubsub.acts',), load_acts)
PubSubManager().attach('targets', ('di.pubsub.targets',), load_targets)

@app.get('/')
async def index() -> RedirectResponse:
    return RedirectResponse('/web/index.html')

class RemoteInput(AppBaseModel):
    action: str
    payload: dict[str, str] | None = None

@app.post('/remote')
async def trigger_remote(rinput: RemoteInput):
    publish('di.pubsub.remote', action=rinput.action, payload=rinput.payload or {})
    return {'status': 'ok'}

class TriggerInput(AppBaseModel):
    endpoint: str

@app.post('/trigger')
async def trigger_actions(tinput: TriggerInput):
    if tinput.endpoint == 'motion':
        trigger_motion(state='on')
    return {'status': 'ok'}

@app.websocket('/ws/{screen}')
async def websocket_endpoint(websocket: WebSocket, screen: str):
    await websocket.accept()

    while True:
        try:
            data = await websocket.receive_text()
        except WebSocketDisconnect:
            return
        try:
            msg = json.loads(data)
            if msg.get('telemetry') and msg.get('_node'):
                action_buffer[screen] = []
            publish_telemetry(screen, msg)
        except json.JSONDecodeError:
            pass
        if payload := v1_payload(screen):
            await websocket.send_text(json.dumps(payload))

@app.websocket('/ws2/{screen}')
async def websocket_v2(websocket: WebSocket, screen: str, fmt: str = 'rgbz'):
    '''Pushes the newest frame as it changes: a slow client skips frames.
    From the client: telemetry, or {"resync": 1} for a whole frame.'''
    global _loop
    _loop = asyncio.get_running_loop()
    encoding = ENCODINGS[fmt]
    await websocket.accept()
    sent = 0

    async def receive():
        nonlocal sent
        while True:
            try:
                msg = json.loads(await websocket.receive_text())
            except json.JSONDecodeError:
                continue
            if msg.get('resync'):
                sent = 0
                _wake(screen)
            if touch := msg.get('touch'):
                touched(screen, *touch)
            publish_telemetry(screen, msg)
            if msg.get('telemetry') and msg.get('_node'):    # an ESP display's sensors: Home Assistant's too
                asyncio.create_task(asyncio.to_thread(ha_states.publish, msg['_node'], json.loads(msg['telemetry'])))

    async def send():
        nonlocal sent
        last, told = time.monotonic(), None
        await websocket.send_text(json.dumps({'time': time.time()}))     # displays without NTP (over USB) set their clock
        while True:
            # After each send, look again: what came during it woke no one.
            s = screens.get(screen)
            if awake.get(screen, True) != told:
                told = awake.get(screen, True)
                await websocket.send_text(json.dumps({'display': {'on': told}}))
            elif s and s.seq != sent:
                await websocket.send_bytes(await asyncio.to_thread(s.message, sent, encoding))
                sent, last = s.seq, time.monotonic()
            elif action_buffer[screen]:
                acts, action_buffer[screen] = action_buffer[screen], []
                await websocket.send_text(json.dumps({'acts': acts}))
                last = time.monotonic()
            elif time.monotonic() - last > 2:
                await websocket.send_text(json.dumps({'alive': sent}))
                last = time.monotonic()
            else:
                await changed(screen, 1)

    tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    finally:
        for t in tasks:
            t.cancel()

@app.get('/png/{screen}')
async def get_png_salon(screen: str, scale: int = 1, gamma: float = 1, fmt: str = 'png'):
    bim = screen_image(screen)
    if bim is None:
        return Response(status_code=404)
    with io.BytesIO() as outgoing:
        bim = apply_gamma(bim, gamma)
        bim = bim.resize((bim.width * scale, bim.height * scale), Image.Resampling.NEAREST)
        bim.save(outgoing, format=fmt)
        img = outgoing.getvalue()

    return Response(content=img, media_type=f'image/{fmt}')

# Displays that pull a screen as MJPEG (esp-displays): the stream, the buttons they show, their presses.
DISPLAY_BUTTONS = [
    {'title': 'Left', 'action': 'left'},
    {'title': 'Right', 'action': 'right'},
    {'title': 'Up', 'action': 'up'},
    {'title': 'Down', 'action': 'down'},
    {'title': 'News', 'action': 'show_news'},
    {'title': 'Metro', 'action': 'show_metro'},
    {'title': 'Sensors', 'action': 'show_sensors'},
    {'title': 'Printers', 'action': 'show_printers'},
    {'title': 'Motion', 'action': 'motion_toggle'},
]

_jpegs = {}     # screen -> (png b64, w, h, quality, jpeg): one encode per frame and size


def screen_jpeg(screen: str, w: int, h: int, quality: int) -> bytes | None:
    if s := screens.get(screen):
        return s.encode(('jpeg', w, h, quality))
    if screen not in frames:
        return None
    b64 = frames[screen]['img']
    key = (b64, w, h, quality)
    if _jpegs.get(screen, (None,))[:4] == key:
        return _jpegs[screen][4]
    with io.BytesIO(base64.b64decode(b64)) as incoming, io.BytesIO() as outgoing:
        im = Image.open(incoming).convert('RGB')
        # Largest whole scale that fits: pixels stay square and sharp.
        k = max(1, min(w // im.width, h // im.height)) if w and h else 1
        im = im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST)
        im.save(outgoing, format='jpeg', quality=quality)
        jpeg = outgoing.getvalue()
    _jpegs[screen] = (*key, jpeg)
    return jpeg


@app.get('/display/{screen}/stream.mjpg')
async def display_stream(screen: str, w: int = 0, h: int = 0, fps: float = 12, quality: int = 85):
    async def frames_():
        last = None
        while True:
            jpeg = screen_jpeg(screen, w, h, quality)
            if jpeg is not None and jpeg is not last:
                last = jpeg
                yield (b'--diframe\r\nContent-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n')
            await asyncio.sleep(1 / min(max(fps, 1), 30))

    return StreamingResponse(frames_(), media_type='multipart/x-mixed-replace; boundary=diframe',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@app.get('/display/{screen}/buttons')
async def display_buttons(screen: str):
    return {'kind': 'disinfo', 'screen': screen, 'buttons': DISPLAY_BUTTONS}


@app.post('/display/{screen}/press')
async def display_press(screen: str, rinput: RemoteInput):
    publish('di.pubsub.remote', action=rinput.action, payload=rinput.payload or {})
    return {'status': 'ok'}


app.mount('/web', StaticFiles(directory='web'), name='web')
