import time
import typer

from itertools import cycle

from ..compositor import compose_frame
from ..data_structures import FrameState

fifos = [
    '/tmp/ledcat-01',
    '/tmp/ledcat-02',
    '/tmp/ledcat-03',
    '/tmp/ledcat-04',
]

def main(fps: int = 60):
    _tf = 1 / fps

    _fifos = cycle(fifos)

    while True:
        fs = FrameState.create()
        t_a = time.time()
        frame = compose_frame(fs)
        t_b = time.time()

        with open(next(_fifos), 'wb') as fp:
            fp.write(frame.convert('RGB').tobytes())

        t_c = time.time()

        # Show various times to execute.

        t_draw = t_b - t_a
        t_write = t_c - t_b
        t_frame = t_c - t_a

        delay = max(_tf - t_frame, 0)
        _fps = (1 / (t_frame + delay))

        print(f't draw:      {t_draw:0.4}')
        print(f't write:     {t_write:0.4}')
        print(f'frame delay: {delay}')
        print(f'fps:         \033[34m{_fps:0.4}\033[0m')

        # Limit frame rate
        time.sleep(delay)


if __name__ == '__main__':
    typer.run(main)
