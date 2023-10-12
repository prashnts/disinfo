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
import io
import base64
import typer

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions   # type: ignore
except ImportError:
    from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions

from ..compositor import compose_frame
from ..redis import publish
from ..config import app_config
from ..drat.app_states import LightSensorStateManager
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


def publish_frame(img):
    with io.BytesIO() as buffer:
        img.save(buffer, format='png')
        encoded_img = base64.b64encode(buffer.getvalue()).decode()

    publish('di.pubsub.frames', action='new-frame', payload=dict(img=encoded_img))


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
        state = LightSensorStateManager(app_config.ambient_light_sensor).get_state()
        fs = FrameState.create()
        fs.rendererdata = { **state.model_dump(), 'draw_time': last_draw_time }

        t_a = time.monotonic()
        img = compose_frame(fs)
        publish_frame(img)
        t_b = time.monotonic()
        double_buffer.SetImage(img.convert('RGB'))
        double_buffer = matrix.SwapOnVSync(double_buffer)
        matrix.brightness = state.brightness
        t_c = time.monotonic()

        t_draw = t_b - t_a
        t_frame = t_c - t_a

        _fps = (1 / t_frame)

        last_draw_time = t_draw

        if stats:
            print(f'[t draw: {t_draw:0.4}] [fps: {_fps:0.4}]')


if __name__=='__main__':
    typer.run(main)
