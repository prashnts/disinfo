import time
import typer
import base64

from libsixel import (
    sixel_output_new, sixel_dither_new, sixel_dither_initialize,
    sixel_encode, sixel_dither_unref, sixel_output_unref,
    SIXEL_PIXELFORMAT_RGB888)
from io import BytesIO
from PIL import Image

from ..compositor import compose_frame
from ..data_structures import FrameState
from ..utils.imops import enlarge_pixels
from ..redis import publish

def publish_frame(img):
    with BytesIO() as buffer:
        img.save(buffer, format='png')
        encoded_img = base64.b64encode(buffer.getvalue()).decode()

    publish('di.pubsub.frames', action='new-frame', payload=dict(img=encoded_img))


def encode_sixels(img: Image.Image, optimize: bool = False, scale=4, gap=1) -> str:
    '''Encodes given image to a sixel string.'''
    if optimize:
        img = enlarge_pixels(img, scale * 2, gap)
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)

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


def main(single_frame: bool = False, fps: int = 60, scale: int = 4, inline: bool = True, dont_draw: bool = False):
    if not single_frame:
        # First we clear the screen.
        print('\033[2J')

    _tf = 1 / fps

    while True:
        fs = FrameState.create()
        t_a = time.monotonic()
        frame = compose_frame(fs)
        t_b = time.monotonic()
        fsixel = encode_sixels(frame, optimize=True, scale=scale, gap=0)

        # Term Cursor Position x, y ; ref colorama
        if inline:
            print('\033[0;0H')

        # Print sixel at previous location.
        if not dont_draw:
            print(fsixel)
        t_c = time.monotonic()

        publish_frame(frame)

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
