import io
import base64
import json
import asyncio

from collections import defaultdict
from PIL import Image
from fastapi import FastAPI, WebSocket, Body, Response
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, StreamingResponse

from disinfo.drat.app_states import PubSubManager, PubSubMessage
from disinfo.drat.tools import trigger_motion
from disinfo.data_structures import AppBaseModel
from disinfo.redis import db, publish
from discore.imops import apply_gamma

app = FastAPI()

frames = {}
action_buffer = defaultdict(list)


def load_frame(channel_name, message: PubSubMessage):
    dest = message.action
    payload = {
        'img': message.payload['img'],
        'acts': action_buffer[dest],
        'd': dest,
    }
    frames[dest] = payload

def load_acts(channel_name, message: PubSubMessage):
    action_buffer[message.payload['dest']].append(message.payload['cmd'])

PubSubManager().attach('frames', ('di.pubsub.frames',), load_frame)
PubSubManager().attach('acts', ('di.pubsub.acts',), load_acts)

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
        data = await websocket.receive_text()
        try:
            msg = json.loads(data)
            telemetry = msg.get('telemetry')
            node_id = msg.get('_node')
            if telemetry and node_id:
                action_buffer[screen] = []
                publish('di.pubsub.telemetry', action='update', payload={'data': telemetry, '_node': node_id})
        except json.JSONDecodeError:
            pass
        if screen in frames:
            await websocket.send_text(json.dumps(frames[screen]))

@app.get('/png/{screen}')
async def get_png_salon(screen: str, scale: int = 1, gamma: float = 1, fmt: str = 'png'):
    bytes_ = base64.b64decode(frames[screen]['img'])
    with io.BytesIO(bytes_) as incoming, io.BytesIO() as outgoing:
        bim = Image.open(incoming).convert('RGB')
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
