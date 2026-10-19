import time
import typer

from typing import Optional

from ..compositor import compose_frame
from discore.data_structures import FrameState
from ..redis import db
from ..transport import RAW_CHANNEL, pack_raw
from disinfo.config import app_config, load_config

_published = {}     # name -> (rgb, at)

def publish_frame(img, name: str):
    # Unchanged frames are skipped, but sent every second for a server that just started.
    rgb = img.convert('RGB').tobytes()
    prev, at = _published.get(name, (None, 0))
    if rgb == prev and time.monotonic() - at < 1:
        return
    _published[name] = (rgb, time.monotonic())
    db.publish(RAW_CHANNEL, pack_raw(name, img.size, rgb))


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
