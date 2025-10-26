import io
import base64
import json

from PIL import Image, ImageDraw, ImageEnhance
from typing import Annotated
from fastapi import FastAPI, WebSocket, Body, Response
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from disinfo.drat.app_states import PubSubManager, PubSubMessage
from disinfo.drat.tools import trigger_motion
from disinfo.data_structures import AppBaseModel
from disinfo.config import app_config
from disinfo.data_structures import FrameState
from disinfo.epd.m5paper import draw as draw_epd_frame
from disinfo.utils.imops import dither
from disinfo.redis import db, publish
# from disinfo.web.telemetry import 

app = FastAPI()

frames = {}
acts = None


def load_frame(channel_name, message: PubSubMessage):
    dest = message.action
    payload = {
        'img': message.payload['img'],
        'acts': acts,
        'd': dest,
    }
    frames[dest] = payload

def load_acts(channel_name, message: PubSubMessage):
    global acts
    acts = [message.payload['cmd']]

PubSubManager().attach('frames', ('di.pubsub.frames',), load_frame)
PubSubManager().attach('acts', ('di.pubsub.acts',), load_acts)

@app.get('/')
async def index() -> RedirectResponse:
    return RedirectResponse('/web/index.html')

class RemoteInput(AppBaseModel):
    action: str

@app.post('/remote')
async def trigger_remote(rinput: RemoteInput):
    publish('di.pubsub.remote', action=rinput.action)
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
            if telemetry:
                publish('di.pubsub.telemetry', action='update', payload={'data': telemetry})
        except json.JSONDecodeError:
            pass
        if screen in frames:
            await websocket.send_text(json.dumps(frames[screen]))
            global acts
            acts = None

@app.get('/png/{screen}')
async def get_png_salon(screen: str, scale: int = 1):
    bytes_ = base64.b64decode(frames[screen]['img'])
    with (io.BytesIO(bytes_) as incoming, io.BytesIO() as outgoing):
        bim = Image.open(incoming).convert('RGB')
        bim = bim.resize((bim.width * scale, bim.height * scale), Image.Resampling.NEAREST)
        bim.save(outgoing, format='png')
        img = outgoing.getvalue()

    return Response(content=img, media_type='image/png')

app.mount('/web', StaticFiles(directory='web'), name='web')
