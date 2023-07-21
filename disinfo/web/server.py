import json
import time
import asyncio

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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    print(websocket.state)


    while True:
        data = await websocket.receive_text()
        if frame:
            await websocket.send_text(frame)
        # time.sleep(0.1)
        print('here')
        continue
        # message = pubsub.get_message()
        # if not message:
            # continue
        print('here2')
        try:
            data = json.loads(message['data'].decode())
            action = data['_action']
            if action == 'new-frame':
                await websocket.send_text(data['img'])
        except KeyError:
            pass

    # try:
    #     results = await subscribe.listen()
    #     for result in results:
    #         await websocket.send_text('test')
    #         print('test send')
    # except Exception as e:
    #     await websocket.close()
    #     raise e

app.mount('/web', StaticFiles(directory='web'), name='web')
