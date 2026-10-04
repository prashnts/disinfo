import time
import typer
import base64

from io import BytesIO
from typing import Optional

from ..compositor import compose_frame
from discore.data_structures import FrameState
from ..redis import publish
from disinfo.config import app_config, load_config

def publish_frame(img, name: str):
    with BytesIO() as buffer:
        img.save(buffer, format='png')
        encoded_img = base64.b64encode(buffer.getvalue()).decode()

    publish('di.pubsub.frames', action=name, payload=dict(img=encoded_img))


def main(fps: int = 60, stats: bool = False, n_frames: int = 0, config: Optional[list[str]] = None):
    # --config can be repeated to render several screens, defaults to DI_CONFIG_PATH.
    _tf = 1 / fps
    i = 0
    configs = [load_config(c) for c in config or []] or [app_config]

    while True:
        i += 1
        if n_frames and i > n_frames:
            break
        t_start = time.perf_counter()
        for c in configs:
            fs = FrameState.create(c)
            frame = compose_frame(fs)
            publish_frame(frame, c.name)
        t_draw = time.perf_counter() - t_start

        delay = max(_tf - t_draw, 0.0)
        _fps = (1 / (t_draw + delay))

        if stats:
            print(f't draw: {t_draw:0.4}')
            print(f'fps:    \033[34m{_fps:0.4}\033[0m')
            print(f'delay:  {delay:0.4}')
            print('\033[3A')
        time.sleep(delay)



if __name__ == '__main__':
    typer.run(main)
