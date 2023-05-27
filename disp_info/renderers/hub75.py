'''
HW interface with `rgbmatrix` library to drive HUB75 LED Panels.
         ┌──────────┐┌──────────┐
┌───┐    │          ││          │
│Pi ╞═══╗│   64x64  ││   64x64  │
│   │ P1║│          ││          │
└───┘   ╚╪═▍▶1     ▕╪╪═▍▶2     ▕│
         └──────────┘└──────────┘
═▍▶ HUB75 IN
  ▕ HUB75 OUT

P1: Matrix Parallel 1 (/3)
Chain Length: 2
'''
import time
import typer

from rgbmatrix import RGBMatrix, RGBMatrixOptions

from ..compositor import get_frame
from ..utils.func import throttle
from ..redis import rkeys, get_dict


# Configuration for the matrix
options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.chain_length = 2
options.parallel = 1
options.brightness = 80
options.pwm_bits = 11   # 1..11
options.scan_mode = 0   # 0: progressive, 1: interlaced
options.pixel_mapper_config = 'Rotate:180'
options.gpio_slowdown = 2
options.drop_privileges = True
options.hardware_mapping = 'regular'


def lux_to_brightness(lux: float) -> int:
    if lux <= 0.5:
        return 5
    if lux <= 1.5:
        return 8
    if lux <= 2:
        return 12
    if lux <= 3:
        return 16
    if lux <= 4:
        return 20
    if lux <= 10:
        return 30
    if lux <= 20:
        return 50
    if lux <= 30:
        return 55
    if lux <= 60:
        return 60
    return 80


@throttle(50)
def get_state():
    try:
        s = get_dict(rkeys['ha_enviomental_lux'])
        lux = float(s['new_state']['state'])
    except KeyError:
        lux = 50
    return { 'lux': lux }


def main(fps: int = 0, show_refresh_rate: bool = False, stats: bool = False):
    if show_refresh_rate:
        options.show_refresh_rate = 1
    if fps > 0:
        options.limit_refresh_rate_hz = fps

    matrix = RGBMatrix(options=options)
    double_buffer = matrix.CreateFrameCanvas()


    print('Matrix Renderer started')

    while True:
        state = get_state()
        t_a = time.time()
        img = get_frame()
        t_b = time.time()
        double_buffer.SetImage(img.convert('RGB'))
        double_buffer = matrix.SwapOnVSync(double_buffer)
        new_brightness = lux_to_brightness(state['lux'])
        print(new_brightness)
        matrix.brightness = new_brightness
        t_c = time.time()

        t_draw = t_b - t_a
        t_matrix = t_c - t_b
        t_frame = t_c - t_a

        _fps = (1 / t_frame)

        if stats:
            print(f'[t draw: {t_draw:0.4}] [fps: {_fps:0.4}]')


if __name__=='__main__':
    typer.run(main)
