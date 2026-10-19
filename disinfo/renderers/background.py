import time
import typer

from typing import Optional

from ..compositor import compose, should_turn_on_display
from discore.data_structures import FrameState
from ..redis import db, publish
from ..transport import RAW_CHANNEL, pack_raw
from disinfo.config import app_config, load_config

_published = {}     # name -> (rgb, (targets, awake), at)

def publish_frame(img, name: str, targets: tuple = (), awake: bool = True):
    # Unchanged frames are skipped, but sent every second for a server that just started. The touch targets and
    # whether someone's there (a display's backlight) too.
    rgb = img.convert('RGB').tobytes()
    state = ([list(t) for t in targets], awake)
    prev, prev_state, at = _published.get(name, (None, None, 0))
    fresh = time.monotonic() - at < 1
    if rgb == prev and state == prev_state and fresh:
        return
    _published[name] = (rgb, state, time.monotonic())
    if rgb != prev or not fresh:
        db.publish(RAW_CHANNEL, pack_raw(name, img.size, rgb))
    if state != prev_state or not fresh:
        publish('di.pubsub.targets', action=name, payload={'targets': state[0], 'awake': awake})


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
            frame = compose(fs)
            publish_frame(frame.image, c.name, frame.targets, should_turn_on_display(fs))
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
