import sys

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

matrix = RGBMatrix(options = options)
double_buffer = matrix.CreateFrameCanvas()

try:
    print("Press CTRL-C to stop.")

    while True:
        img = get_frame()
        double_buffer.SetImage(img.convert('RGB'))
        double_buffer = matrix.SwapOnVSync(double_buffer)
        # time.sleep(0.005)
except KeyboardInterrupt:
    sys.exit(0)
