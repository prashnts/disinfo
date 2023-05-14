import sys
import time
import typer

from rgbmatrix import RGBMatrix, RGBMatrixOptions

from .renderer import get_frame


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
# options.show_refresh_rate = 1
options.hardware_mapping = 'regular'


def main(fps: int = 60, stats: bool = False):
    matrix = RGBMatrix(options = options)
    double_buffer = matrix.CreateFrameCanvas()

    print('Matrix Renderer started')
    _tf = 1 / fps

    while True:
        t_a = time.time()
        img = get_frame()
        t_b = time.time()
        double_buffer.SetImage(img.convert('RGB'))
        double_buffer = matrix.SwapOnVSync(double_buffer)
        t_c = time.time()

        t_draw = t_b - t_a
        t_matrix = t_c - t_b
        t_frame = t_c - t_a

        delay = max(_tf - t_frame, 0)
        _fps = (1 / (t_frame + delay))

        if stats:
            print('\033[2J')
            print(f't draw:      {t_draw:0.4}')
            print(f't sixel:     {t_matrix:0.4}')
            print(f'frame delay: {delay}')
            print(f'fps:         \033[34m{_fps:0.4}\033[0m')

        time.sleep(delay)

if __name__=='__main__':
    typer.run(main)
