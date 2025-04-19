import time
import typer
import base64

from io import BytesIO

from ..compositor import compose_frame
from ..data_structures import FrameState
from ..redis import publish

def publish_frame(img):
    with BytesIO() as buffer:
        img.save(buffer, format='png')
        encoded_img = base64.b64encode(buffer.getvalue()).decode()

    publish('di.pubsub.frames', action='new-frame', payload=dict(img=encoded_img))


def main(fps: int = 60, stats: bool = False):
    _tf = 1 / fps

    while True:
        t_start = time.monotonic()
        fs = FrameState.create()
        frame = compose_frame(fs)
        publish_frame(frame)
        t_draw = time.monotonic() - t_start

        delay = max(_tf - t_draw, 0)
        _fps = (1 / (t_draw + delay))

        if stats:
            print(f't draw: {t_draw:0.4}')
            print(f'fps:    \033[34m{_fps:0.4}\033[0m')
            print('\033[3A')
        time.sleep(delay)



if __name__ == '__main__':
    typer.run(main)
