import time
import typer

from libsixel import (
    sixel_output_new, sixel_dither_new, sixel_dither_initialize,
    sixel_encode, sixel_dither_unref, sixel_output_unref,
    SIXEL_PIXELFORMAT_RGB888)
from io import BytesIO
from PIL import Image

from ..compositor import get_frame
from ..utils.imops import enlarge_pixels


def encode_sixels(img: Image.Image, optimize: bool = False, scale=4, gap=1) -> str:
    '''Encodes given image to a sixel string.'''
    if optimize:
        img = enlarge_pixels(img, scale, gap)
    buf = BytesIO()
    data = img.convert('RGB').tobytes()
    width = img.width
    height = img.height
    output = sixel_output_new(lambda data, s: s.write(data), buf)
    dither = sixel_dither_new(256)
    sixel_dither_initialize(dither, data, width, height, SIXEL_PIXELFORMAT_RGB888)
    sixel_encode(data, width, height, 1, dither, output)

    sixel = buf.getvalue().decode('ascii')

    sixel_dither_unref(dither)
    sixel_output_unref(output)
    buf.close()

    return sixel


def main(single_frame: bool = False, fps: int = 60, scale: int = 4):
    if not single_frame:
        # First we clear the screen.
        print('\033[2J')

    _tf = 1 / fps

    while True:
        t_a = time.time()
        frame = get_frame()
        t_b = time.time()
        fsixel = encode_sixels(frame, optimize=True, scale=scale)

        # Term Cursor Position x, y ; ref colorama
        print('\033[0;0H')

        # Print sixel at previous location.
        print(fsixel)
        t_c = time.time()

        # Show various times to execute.

        t_draw = t_b - t_a
        t_sixel = t_c - t_b
        t_frame = t_c - t_a

        delay = max(_tf - t_frame, 0)
        _fps = (1 / (t_frame + delay))

        print(f't draw:      {t_draw:0.4}')
        print(f't sixel:     {t_sixel:0.4}')
        print(f'frame delay: {delay}')
        print(f'fps:         \033[34m{_fps:0.4}\033[0m')

        # Limit frame rate
        time.sleep(delay)

        if single_frame:
            break



if __name__ == '__main__':
    typer.run(main)
