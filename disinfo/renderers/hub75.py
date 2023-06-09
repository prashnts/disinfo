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

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions   # type: ignore
except ImportError:
    from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions

from scipy.interpolate import interp1d

from ..compositor import compose_frame
from ..utils.func import throttle
from ..redis import rkeys, get_dict
from ..data_structures import FrameState


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
# On Pi 3B+ this was 2. I set it to 5 on Pi 4B.
options.gpio_slowdown = 5
options.drop_privileges = True
options.hardware_mapping = 'regular'


brightness_min: float = 10
brightness_max: float = 100
brightness_curve = [
    # LUX   BRIGHTNESS %
    [0.2,   10],
    [2,     20],
    [5,     40],
    [20,    60],
    [50,    70],
    [200,   95],
    [400,  100],
]
brightness_interpolator = interp1d(
    *zip(*brightness_curve),
    bounds_error=False,
    fill_value=(brightness_min, brightness_max),
)

@throttle(50)
def get_state():
    try:
        s = get_dict(rkeys['ha_enviomental_lux'])
        lux = float(s['new_state']['state'])
    except (KeyError, TypeError, ValueError):
        lux = 50
    return {
        'lux': lux,
        'brightness': int(brightness_interpolator(lux)),
    }


def main(fps: int = 0, show_refresh_rate: bool = False, stats: bool = False):
    if show_refresh_rate:
        options.show_refresh_rate = 1
    if fps > 0:
        options.limit_refresh_rate_hz = fps

    matrix = RGBMatrix(options=options)
    double_buffer = matrix.CreateFrameCanvas()


    print('Matrix Renderer started')
    last_draw_time = 0

    while True:
        state = get_state()
        fs = FrameState.create()
        fs.rendererdata = { **state, 'draw_time': last_draw_time }

        t_a = time.monotonic()
        img = compose_frame(fs)
        t_b = time.monotonic()
        double_buffer.SetImage(img.convert('RGB'))
        double_buffer = matrix.SwapOnVSync(double_buffer)
        matrix.brightness = state['brightness']
        t_c = time.monotonic()

        t_draw = t_b - t_a
        t_frame = t_c - t_a

        _fps = (1 / t_frame)

        last_draw_time = t_draw

        if stats:
            print(f'[t draw: {t_draw:0.4}] [fps: {_fps:0.4}]')


if __name__=='__main__':
    typer.run(main)
