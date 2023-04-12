#!/usr/bin/env python
import time
import sys
import colorsys
import datetime
import math
import random
import json
import redis

from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageOps


# Configuration for the matrix
options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.chain_length = 2
options.parallel = 1
options.brightness = 80
options.pixel_mapper_config = 'Rotate:180'
options.gpio_slowdown = 2
options.drop_privileges = True
# options.show_refresh_rate = 1
options.hardware_mapping = 'regular'

CANVAS_WIDTH = 128
CANVAS_HEIGHT = 64
origin = (CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2)

matrix = RGBMatrix(options = options)

font_tamzen__rs = ImageFont.truetype('TamzenForPowerline5x9r.ttf', 9)
font_tamzen__rm = ImageFont.truetype('Tamzen7x13r.ttf', 13)
font_px_op__r = ImageFont.truetype('PixelOperator8.ttf', 8)
font_px_op_mono_8 = ImageFont.truetype('PixelOperatorMono8.ttf', 8)
font_px_op__l = ImageFont.truetype('PixelOperator.ttf', 16)
font_px_op__xl = ImageFont.truetype('PixelOperator.ttf', 32)
font_px_op__xxl = ImageFont.truetype('PixelOperator.ttf', 48)

db = redis.Redis(host='localhost', port=6379, db=0)

keys = {
    'weather': 'weather.forecast_data'
}

def get_json_key(key: str):
    value = db.get(key)
    return json.loads(value)

# assets are loaded in advance (for now)
asset_clear_day = Image.open('assets/clear-day.png')
asset_testtw = Image.open('assets/test-tw.png')


def draw_sin_wave(step, draw, yoffset, amp, divisor, color, width=1):
    AMP = amp
    OFFSET = 10
    DIVISOR = divisor # 1.5

    y_step = lambda x: int(math.sin(step + x / DIVISOR) * AMP + OFFSET)
    xys = [(x + 0, y_step(x) + yoffset) for x in range(128)]

    # draw.line([(0, OFFSET), (16, OFFSET)], fill='green')

    draw.line(xys, fill=color, width=width, joint='curve')
    # draw.point(xys, fill='green')


def draw_date_time(draw: ImageDraw):
    t = datetime.datetime.now()
    time_str = t.strftime('%H:%M:%S')
    font = font_tamzen__rs
    time_size = draw.textbbox((0, 0), time_str, font=font, anchor='lt')
    # we want to draw the time on right side, so we need to go left from CANVAS_WIDTH
    xpos = CANVAS_WIDTH - time_size[2]
    ypos = 1
    time_color = '#2BBEC9' if t.second % 2 == 0 else '#0E699D'
    draw.text((xpos, ypos), time_str, font=font, fill=time_color, anchor='lt')

    # next we draw the date just below the time.
    date_str = t.strftime('%a %d/%m')
    date_size = draw.textbbox((0, 0), date_str, font=font, anchor='lt')
    xpos = CANVAS_WIDTH - date_size[2]
    ypos = 2 + time_size[3] + 1

    date_color = '#9F4006'
    draw.text((xpos, ypos), date_str, font=font, fill=date_color, anchor='lt')

def draw_22_22(draw: ImageDraw):
    t = datetime.datetime.now()
    # t = datetime.datetime(2022, 2, 1, 22, 22, t.second)

    equal_elements = t.hour == t.minute
    twentytwo = t.hour == t.minute == 22

    if not equal_elements:
        return

    all_twentytwo = t.hour == t.second == 22
    text = t.strftime('%H:%M')
    font = font_px_op__xl
    fill = '#2FB21B'
    if twentytwo:
        fill = '#CF8C13'
        font = font_px_op__xxl
    if all_twentytwo:
        fill = '#CF3F13'

    # draw a rectangle in the background of the text (with padding * 2)
    pad = 2
    tl, tt, tr, tb = draw.textbbox(origin, text, font=font, anchor='mm')
    # draw.rounded_rectangle(
    #     [(tl - pad, tt - pad), (tr + pad, tb + pad)],
    #     radius=3,
    #     fill='#282828')

    # draw time
    draw.text(origin, text, font=font, fill=fill, anchor='mm')

    # glittering colors if it's the magic hour
    if not twentytwo:
        return

    gcols = [
        '#4096D9',
        '#404BD9',
        '#AF4FD7',
        '#D9BC40',
        '#D96140',
        '#1CB751',
    ]

    # draw some shimmering leds everywhere!
    for x in range(CANVAS_WIDTH):
        for y in range(CANVAS_HEIGHT):
            if random.random() < .003:
                pts = [(x, y)]
                if random.random() < 0.2:
                    # "bigger" points (four pixels)
                    pts = [
                        [
                            (x - 1, y - 1),
                            (x, y - 1),
                            (x - 1, y),
                            (x, y),
                            (x + 1, y + 1),
                            (x + 1, y),
                            (x, y + 1),
                        ],
                        [
                            (x, y),
                            (x + 1, y + 1),
                            (x + 1, y),
                            (x, y + 1),
                        ],
                        [
                            (x - 1, y - 1),
                            (x, y - 2),
                            (x, y - 1),
                            (x - 1, y),
                            (x, y),
                            (x + 1, y + 1),
                            (x + 1, y),
                            (x + 2, y),
                            (x, y + 1),
                        ],
                    ]
                draw.point(random.choice(pts), fill=random.choice(gcols))

def draw_weather(draw: ImageDraw, image: Image):
    forecast = get_json_key(keys['weather'])

    color_temp = '#6e7078'
    color_deg_c = '#6E7078'
    color_condition = '#989A9F'

    temperature = forecast['currently']['apparentTemperature']
    condition = forecast['currently']['summary']

    temp_str = f'{round(temperature)}'
    deg_c = '°'

    o_x = 0
    o_y = 1

    _, _, temp_w, temp_h = draw.textbbox((0, 0), temp_str, font=font_px_op__l, anchor='lt')
    _, _, degc_w, _ = draw.textbbox((0, 0), deg_c, font=font_tamzen__rs, anchor='lt')

    draw.text((o_x, o_y + 1), temp_str, font=font_px_op__l, fill=color_temp, anchor='lt')
    draw.text((o_x + temp_w, o_y + 1), deg_c, font=font_tamzen__rs, fill=color_deg_c, anchor='lt')

    draw.text((o_x + 1, o_y + temp_h + 3), condition, font=font_tamzen__rs, fill=color_condition, anchor='lt')

    # high low:
    today = forecast['daily']['data'][0]
    temp_high_label = 'H'
    temp_low_label = 'L'
    label_margin = 2
    temp_high = f'{round(today["temperatureHigh"])}°'
    temp_low = f'{round(today["temperatureLow"])}°'
    high_low_font = font_tamzen__rs

    color_high = '#967b03'
    color_low = '#2d83b4'

    _, _, highl_w, highl_h = draw.textbbox((0, 0), temp_high_label, font=high_low_font, anchor='lt')
    _, _, lowl_w, lowl_h = draw.textbbox((0, 0), temp_low_label, font=high_low_font, anchor='lt')
    _, _, highv_w, highv_h = draw.textbbox((0, 0), temp_high, font=high_low_font, anchor='lt')
    _, _, lowv_w, lowv_h = draw.textbbox((0, 0), temp_low, font=high_low_font, anchor='lt')
    high_line_h = max(highl_h, highv_h) + 1

    draw.text((o_x + temp_w + degc_w + 1, o_y), temp_high_label, font=high_low_font, fill=color_high, anchor='lt')
    draw.text((o_x + temp_w + degc_w + 1 + highl_w + 1, o_y), temp_high, font=high_low_font, fill=color_high, anchor='lt')

    draw.text((o_x + temp_w + degc_w + 1, o_y + high_line_h), temp_low_label, font=high_low_font, fill=color_low, anchor='lt')
    draw.text((o_x + temp_w + degc_w + 1 + highl_w + 1, o_y + high_line_h), temp_low, font=high_low_font, fill=color_low, anchor='lt')


class ScrollableText:
    def __init__(self,
        message: str,
        width: int=128,
        anchor: tuple=(10, 10),
        speed: int=1,
        font: ImageFont=font_px_op__l,
        fill: str='#e68b1b'
    ):
        self.message = message
        self.width = width
        self.anchor = anchor
        self.font = font
        self.fill = fill

        # make a "base image" which will be scrolled later.
        _qimg = Image.new('RGBA', (0, 0))
        _qdraw = ImageDraw.Draw(_qimg)
        _, _, w, h = _qdraw.textbbox((0, 0), self.message, font=self.font, anchor='lt')
        self.msg_width = w
        self.msg_height = h

        self.im_base = Image.new('RGBA', (w, h))
        base_draw = ImageDraw.Draw(self.im_base)
        base_draw.text((0, 0), self.message, font=self.font, fill=self.fill, anchor='lt')

        # the cursor position
        self.ypos = 0
        self.last_step = 0 # a step is a "second"
        self.speed = speed  # px/s

    def draw(self, step: int, im: Image) -> Image:
        if (step - self.last_step) >= self.speed:
            self.ypos += 2
            self.ypos %= self.msg_width
            self.last_step = step
        # we need to crop the base image by cursor offset.
        crop_rect = (
            self.ypos,
            0,
            min(self.ypos + self.width, self.msg_width),
            self.msg_height
        )
        patch = self.im_base.crop(crop_rect)

        im.paste(patch.convert('RGBA'), box=self.anchor)
        return im


def draw_frame(st):
    tick = time.time()
    step = int(tick * 15)

    image = Image.new('RGBA', (128, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)


    draw_sin_wave(step=(1 + step * .6), draw=draw, yoffset=38, amp=10, divisor=6, color='#98A9D0', width=1)
    draw_sin_wave(step=step, draw=draw, yoffset=30, amp=4, divisor=2, color='#3A6D8C')
    draw_sin_wave(step=step * .5, draw=draw, yoffset=38, amp=7, divisor=14, color='#34424A', width=2)
    draw_sin_wave(step=(3 + step * .2), draw=draw, yoffset=38, amp=7, divisor=10, color='#5A5A5A')

    draw_date_time(draw)
    draw_22_22(draw)
    draw_weather(draw, image)

    image = st.draw(tick, image)


    enchancer = ImageEnhance.Sharpness(image)
    image = enchancer.enhance(.7)

    # image = Image.alpha_composite(asset_testtw, image)

    return image

double_buffer = matrix.CreateFrameCanvas()

msgs = [
    'Bonjour!',
    'Hello',
    '(｡◕‿‿◕｡)',
    'Namaste',
    '(-(-_-(-_(-_(-_-)_-)-_-)_-)_-)-)',
    'World!',
    'This is a public service announcement.',
    'Plese note you must celebrate 22:22.',
    'It is our duty.',
    'So We MUST!',
    'QUESTIONS?',
    '(｡◕‿‿◕｡)'
]

try:
    print("Press CTRL-C to stop.")
    st = ScrollableText(' * '.join(msgs), anchor=(0, 50), speed=.0001)
    while True:
        img = draw_frame(st)
        double_buffer.SetImage(img.convert('RGB'))
        double_buffer = matrix.SwapOnVSync(double_buffer)
        time.sleep(0.01)
except KeyboardInterrupt:
    sys.exit(0)
