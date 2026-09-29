import time
import typer

from rich.progress import track, Progress, SpinnerColumn, TextColumn

from ..compositor import compose_frame
from discore.data_structures import FrameState
from ..config import app_config
from discore.imops import enlarge_pixels


def main(filename: str = 'assets/disinfo-export.gif', nframe: int = 60, scale: int = 5, fps: int = 25, warmup: float = 0):
    '''Renders the disinfo canvas to a GIF file.

    Each frame is shown for as long as it took on the wall clock. GIF delays are in
    10ms steps and browsers slow anything under 20ms down to 100ms: keep fps <= 50.
    `warmup` draws (and drops) frames for that many seconds first, so the cards have data.
    '''
    frames = []
    raw_frames = []
    durations = []
    _tf = 1 / fps
    print('GIF Renderer started')

    t_warm = time.time() + warmup
    while time.time() < t_warm:
        compose_frame(FrameState.create(app_config))
        time.sleep(_tf)

    t_begin = time.time()
    t_prev = t_begin

    for i in track(range(nframe), description='Rendering'):
        fs = FrameState.create(app_config)
        img = compose_frame(fs)
        raw_frames.append(img)
        time.sleep(max(_tf - (time.time() - t_prev), 0))
        t_now = time.time()
        durations.append(round((t_now - t_prev) * 100) * 10)
        t_prev = t_now

    t_end = time.time()

    for img in raw_frames:
        frames.append(enlarge_pixels(img, scale=scale, outline_color='#00000055', gap=0).convert('RGB'))

    mean_fps = nframe / (t_end - t_begin)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Creating GIF...", total=None)
        frames[0].save(filename, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)

    print(f'[i] Saved as {filename}, {t_end - t_begin:0.1f}s at {mean_fps:0.1f} fps.')


if __name__=='__main__':
    typer.run(main)
