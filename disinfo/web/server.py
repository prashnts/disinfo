import io
import base64

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
from ..redis import db, publish

app = FastAPI()

frame = None
frame_pico = None
frame_salon = None

def load_frame(channel_name, message: PubSubMessage):
    global frame, frame_pico, frame_salon
    if message.action == 'new-frame-pico':
        frame_pico = message.payload['img']
    if message.action == 'new-frame':
        frame = message.payload['img']
    if message.action == 'new-frame-salon':
        frame_salon = message.payload['img']

PubSubManager().attach('frames', ('di.pubsub.frames',), load_frame)

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

@app.websocket('/ws-salon')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    while True:
        await websocket.receive_text()
        if frame_salon:
            await websocket.send_text(frame_salon)

@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    while True:
        await websocket.receive_text()
        if frame:
            await websocket.send_text(frame)

@app.websocket('/ws-pico')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    while True:
        await websocket.receive_text()
        if frame_pico:
            await websocket.send_text(frame_pico)

@app.get('/png/salon')
async def get_png_salon():
    fs = FrameState.create()
    image = draw_epd_frame(fs)

    with io.BytesIO() as buffer:
        image.convert("1").save(buffer, format='png')
        bytes_ = buffer.getvalue()

    return Response(content=bytes_, media_type='image/png')

app.mount('/web', StaticFiles(directory='web'), name='web')
