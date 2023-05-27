import sys
import time
import typer

from typing import Optional


from .renderer import get_frame
from .utils import enlarge_pixels


def main(filename: str = 'disinfo-export.gif', nframe: int = 60, scale: int = 5, stats: bool = True):
    frames = []
    print('Matrix Renderer started')

    t_begin = time.time()

    for i in range(nframe):
        img = get_frame()
        frames.append(enlarge_pixels(img, scale=scale))

        if stats:
            print(f'[frame: {i}/{nframe}]')

    t_end = time.time()
    mean_fps = (t_end - t_begin) / nframe

    frames[0].save(filename, save_all=True, append_images=frames[1:], duration=mean_fps * 100, loop=0, optimize=True)
    print(f'[i] Saved at {filename}, at {mean_fps}s per frame.')


if __name__=='__main__':
    typer.run(main)
