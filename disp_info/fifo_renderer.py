import time
import typer

from .renderer import get_frame

def main(fps: int = 60):
    _tf = 1 / fps

    while True:
        t_a = time.time()
        frame = get_frame()
        t_b = time.time()

        with open('/tmp/ledcat-01', 'wb') as fp:
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
