import time
import typer

from rich.progress import track, Progress, SpinnerColumn, TextColumn

from ..compositor import compose_frame
from ..data_structures import FrameState
from ..utils.imops import enlarge_pixels


def main(filename: str = 'assets/disinfo-export.gif', nframe: int = 60, scale: int = 5):
    '''Renders the disinfo canvas to a GIF file.'''
    frames = []
    durations = []
    print('GIF Renderer started')

    t_begin = time.time()

    for i in track(range(nframe), description='Rendering'):
        fs = FrameState.create()
        t_a = time.time()
        img = compose_frame(fs)
        frames.append(enlarge_pixels(img, scale=scale, outline_color='#00000055', gap=0).convert('RGB'))
        durations.append((time.time() - t_a) * 100)

    t_end = time.time()
    mean_fps = (t_end - t_begin) / nframe

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Creating GIF...", total=None)
        frames[0].save(filename, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)

    print(f'[i] Saved as {filename}, at {mean_fps}s per frame.')


if __name__=='__main__':
    typer.run(main)
