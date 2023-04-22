import time
import sys

from libsixel import (sixel_output_new, sixel_dither_new, sixel_dither_initialize,
    sixel_encode, sixel_dither_unref, sixel_output_unref, SIXEL_PIXELFORMAT_RGB888)
from io import BytesIO
from PIL import Image, ImageEnhance, ImageDraw

from .renderer import get_frame

def draw_panel(img, scale=5, gap=1):
    # turn the img into a mosaic with gap between px.
    outline_color = '#000000'
    radius = 2
    w, h = img.width, img.height
    iw, ih = w * scale, h * scale
    i = Image.new('RGBA', (iw, ih))
    d = ImageDraw.Draw(i)

    for x in range(w):
        for y in range(h):
            px = img.getpixel((x, y))

            # draw a rect.
            rx, ry = x * scale, y * scale
            ex, ey = rx + (scale - 1), ry + (scale - 1)
            d.rounded_rectangle([(rx, ry), (ex, ey)], radius, fill=px, outline=outline_color, width=gap)

    enhancer = ImageEnhance.Brightness(i)
    return enhancer.enhance(2)


try:
    while True:
        img = draw_panel(get_frame())
        buf = BytesIO()
        data = img.convert('RGB').tobytes()
        width = img.width
        height = img.height
        output = sixel_output_new(lambda data, s: s.write(data), buf)
        dither = sixel_dither_new(256)
        sixel_dither_initialize(dither, data, width, height, SIXEL_PIXELFORMAT_RGB888)
        sixel_encode(data, width, height, 1, dither, output)
        # print('\033c')
        print(buf.getvalue().decode('ascii'))

        time.sleep(0.01)
except KeyboardInterrupt:
    sixel_dither_unref(dither)
    sixel_output_unref(output)
    sys.exit(0)
