from fastapi import FastAPI, WebSocket
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from disinfo.drat.app_states import PubSubManager, PubSubMessage
from ..redis import db

pubsub = db.pubsub(ignore_subscribe_messages=True)
pubsub.subscribe('di.pubsub.frames')

app = FastAPI()

frame = None

def load_frame(channel_name, message: PubSubMessage):
    global frame
    if message.action == 'new-frame':
        frame = message.payload['img']

PubSubManager().attach('frames', ('di.pubsub.frames',), load_frame)

@app.get('/')
async def index() -> RedirectResponse:
    return RedirectResponse('/web/index.html')

@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    while True:
        await websocket.receive_text()
        if frame:
            await websocket.send_text(frame)

app.mount('/web', StaticFiles(directory='web'), name='web')
