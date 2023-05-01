#!/usr/bin/env python
import time
import sys
import colorsys
import datetime
import math
import random
import json
import requests
import io
import arrow
import dateutil

from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageOps, ImageFilter
from functools import cache
from colour import Color


from .weather_icons import get_icon_for_condition, arrow_x, render_icon, cursor
from .redis import get_dict, rkeys
from .state_proxy import should_turn_on_display
from .sprite_icons import SpriteIcon, SpriteImage
from .components.text import Text
from .components.elements import Frame
from .components.layouts import stack_horizontal, stack_vertical
from . import config


origin = (config.matrix_w / 2, config.matrix_h / 2)

font_tamzen__rs = ImageFont.truetype('assets/fonts/TamzenForPowerline5x9r.ttf', 9)
font_tamzen__rm = ImageFont.truetype('assets/fonts/Tamzen7x13r.ttf', 13)
font_px_op__r = ImageFont.truetype('assets/fonts/PixelOperator8.ttf', 8)
font_px_op_mono_8 = ImageFont.truetype('assets/fonts/PixelOperatorMono8.ttf', 8)
font_px_op__l = ImageFont.truetype('assets/fonts/PixelOperator.ttf', 16)
font_px_op__xl = ImageFont.truetype('assets/fonts/PixelOperator.ttf', 32)
font_px_op__xxl = ImageFont.truetype('assets/fonts/PixelOperator.ttf', 48)
font_cd_icon = ImageFont.truetype('assets/fonts/CD-IconsPC.ttf', 22)
font_scientifica__r = ImageFont.truetype('assets/fonts/scientifica.ttf', 11)
font_scientifica__b = ImageFont.truetype('assets/fonts/scientificaBold.ttf', 11)
font_scientifica__i = ImageFont.truetype('assets/fonts/scientificaItalic.ttf', 11)

# assets are loaded in advance (for now)
asset_clear_day = Image.open('assets/clear-day.png')
asset_testtw = Image.open('assets/test-tw.png')


def draw_sin_wave(step, draw, yoffset, amp, divisor, color, width=1):
    AMP = amp
    OFFSET = 10
    DIVISOR = divisor # 1.5

    y_step = lambda x: round(math.sin(step + x / DIVISOR) * AMP + OFFSET)
    xys = [(x + 0, y_step(x) + yoffset) for x in range(128)]

    # draw.line([(0, OFFSET), (16, OFFSET)], fill='green')

    draw.line(xys, fill=color, width=width, joint='curve')
    # draw.point(xys, fill='green')


def draw_date_time(draw: ImageDraw):
    t = datetime.datetime.now()
    time_str = t.strftime('%H:%M:%S')
    font = font_tamzen__rs
    time_size = font.getbbox(time_str, anchor='lt')
    # we want to draw the time on right side, so we need to go left from CANVAS_WIDTH
    xpos = config.matrix_w - time_size[2]
    ypos = 1
    time_color = '#2BBEC9' if t.second % 2 == 0 else '#0E699D'
    draw.text((xpos, ypos), time_str, font=font, fill=time_color, anchor='lt')

    # next we draw the date just below the time.
    date_str = t.strftime('%a %d/%m')
    date_size = font.getbbox(date_str, anchor='lt')
    xpos = config.matrix_w - date_size[2]
    ypos = 2 + time_size[3] + 1

    date_color = '#9F4006'
    draw.text((xpos, ypos), date_str, font=font, fill=date_color, anchor='lt')

def draw_22_22(draw: ImageDraw):
    t = datetime.datetime.now()
    action = get_dict(rkeys['ha_enki_rmt']).get('action')
    # t = datetime.datetime(2022, 2, 1, 22, 22, t.second)

    equal_elements = t.hour == t.minute
    twentytwo = t.hour == t.minute == 22
    all_equal = t.hour == t.minute == t.second

    if action == 'scene_1':
        twentytwo == True
        equal_elements = True
        all_equal = True

    if not equal_elements:
        return

    text = t.strftime('%H:%M')
    font = font_px_op__xl
    fill = '#2FB21B'
    if twentytwo:
        fill = '#CF8C13'
        font = font_px_op__xxl
    if all_equal:
        fill = '#CF3F13'

    # draw time
    draw.text(origin, text, font=font, fill=fill, anchor='mm')

    # glittering colors if it's the magic hour
    if not (twentytwo or all_equal):
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
    for x in range(config.matrix_w):
        for y in range(config.matrix_h):
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

@cache
def draw_temp_range(
    t_current: float,
    t_high: float,
    t_low: float,
    font: ImageFont = font_tamzen__rs) -> Frame:
    '''Generates a vertical range graph of temperatures.'''

    color_high = Color('#967b03')
    color_low = Color('#2d83b4')

    text_high = Text(f'{round(t_high)}°', font, color_high.hex)
    text_low = Text(f'{round(t_low)}°', font, color_low.hex)
    span = text_high.height + text_low.height + 1

    # Draw the range graph.
    # todo: this can be refactored.

    range_graph = Image.new('RGBA', (5, span), (0, 0, 0, 0))
    d = ImageDraw.Draw(range_graph)

    span = span - 2
    gradient = color_high.range_to(color_low, span)

    color_current = Color('#ffffff')

    high_span = t_high - t_low
    try:
        current_pos = (t_current - t_low) * (span / high_span)
    except ZeroDivisionError:
        current_pos = span // 2

    if current_pos <= 0:
        current_pos = 0
    elif current_pos >= span - 1:
        current_pos = span - 1

    # "flip" the current pos and move it in frame.
    cp = span - current_pos

    d.line([(3, 1), (4, 1)], fill=color_high.hex)
    d.line([(3, span), (4, span)], fill=color_low.hex)

    for x, c in enumerate(gradient):
        d.point([(3, x + 1)], fill=c.hex)

    d.point([
        (0, cp - 1),
        (0, cp), (1, cp),
        (0, cp + 1),
    ], fill=color_current.hex)

    return stack_horizontal([
        Frame(range_graph),
        stack_vertical([text_high, text_low], gap=1, align='left'),
    ], gap=1, align='center')


def draw_weather(step: int):
    forecast = get_dict(rkeys['weather_data'])

    color_temp = '#9a9ba2'
    color_deg_c = '#6E7078'
    color_condition = '#5b5e64'
    outdated_color = '#a00'

    # Current temperature and codition + High/Low
    temperature = forecast['currently']['apparentTemperature']
    update_time = arrow.get(forecast['currently']['time'], tzinfo='local')
    condition = forecast['currently']['summary']
    icon_name = forecast['currently']['icon']
    today = forecast['daily']['data'][0]
    t_high = today['temperatureHigh']
    t_low = today['temperatureLow']
    # Sunset info
    sunset_time = arrow.get(today['sunsetTime'], tzinfo='local')

    now = arrow.now()
    should_show_sunset = sunset_time > now and (sunset_time - now).total_seconds() < 2 * 60 * 60
    is_outdated = (now - update_time).total_seconds() > 30 * 60  # 30 mins.

    weather_icon.set_icon(f'assets/unicorn-weather-icons/{icon_name}.png')

    temp_text = stack_horizontal([
        Text(f'{round(temperature)}', font=font_px_op__l, fill=color_temp),
        Text('°', font=font_px_op__r, fill=color_deg_c),
    ], gap=0, align='top')

    condition_info = [Text(condition, font=font_tamzen__rs, fill=color_condition)]

    if is_outdated:
        condition_info.insert(0, warning_icon)

    weather_info = stack_vertical([
        stack_horizontal([
            weather_icon.draw(step),
            temp_text,
            draw_temp_range(temperature, t_high, t_low, font_tamzen__rs),
        ], gap=1, align='center'),
        stack_horizontal(condition_info, gap=2, align='center'),
    ], gap=1, align='left')

    weather_stack = [weather_info]

    if should_show_sunset:
        weather_stack.append(stack_horizontal([
            sunset_arrow.draw(step),
            Text(sunset_time.strftime('%H:%M'), font=font_tamzen__rs, fill=color_condition),
        ], gap=1, align='center'))

    return stack_vertical(weather_stack, gap=1, align='left')


class ScrollableText:
    def __init__(self,
        message: str,
        width: int=128,
        anchor: tuple=(10, 10),
        speed: int=1,
        delta: int=1,
        font: ImageFont=font_px_op__l,
        fill: str='#e68b1b',
        gap: int=5,
    ):
        self.width = width
        self.anchor = anchor
        self.font = font
        self.fill = fill
        self.gap = gap
        self.delta = delta

        # the cursor position
        self.ypos = 0
        self.last_step = 0 # a step is a "second"
        self.speed = speed  # px/s

        self.message = ''
        self.set_message(message)

    def set_message(self, msg: str):
        # make a "base image" which will be scrolled later.
        if msg == self.message:
            return
        self.message = msg
        self.ypos = 0
        _, _, w, h = self.font.getbbox(self.message, anchor='lt')
        self.msg_width = w + (self.width * 1)
        self.msg_height = h

        self.im_base = Image.new('RGBA', (self.msg_width, h))
        base_draw = ImageDraw.Draw(self.im_base)
        base_draw.text((self.width, 0), self.message, font=self.font, fill=self.fill, anchor='lt')

    def draw(self, step: int, im: Image) -> Image:
        if (step - self.last_step) >= self.speed:
            self.ypos += self.delta
            self.ypos %= self.msg_width
            self.last_step = step
        # we need to crop the base image by cursor offset.
        yspan = self.ypos + self.width

        crop_rect = (
            self.ypos,
            0,
            min(yspan, self.msg_width),
            self.msg_height
        )
        patch = self.im_base.crop(crop_rect)

        im.alpha_composite(patch, self.anchor)
        return im

def draw_numbers(image, draw, st, st_detail, tick):
    numbers = get_dict(rkeys['random_msg'])
    num_str = f'#{numbers["number"]}'
    st.set_message(numbers['text'])
    st_detail.set_message(num_str)
    _, _, num_w, _ = st_detail.font.getbbox(num_str, anchor='lt')
    if num_w < 42:
        # draw static text
        draw.rounded_rectangle([(-2, 43), (num_w + 1, config.matrix_h - 10)], radius=2, fill='#013117')
        draw.text((1, 45), num_str, font=st_detail.font, fill='#9bb10d', anchor='lt', stroke_width=1, stroke_fill='black')
    else:
        draw.rounded_rectangle([(-2, 43), (43, config.matrix_h - 10)], radius=2, fill='#013117')
        image = st_detail.draw(tick, image)


    draw.rounded_rectangle([(0, 53), (config.matrix_w - 1, config.matrix_h - 1)], radius=0, fill='#010a29')
    image = st.draw(tick, image)
    draw.text((1, 52), 'i', font=font_tamzen__rm)

    return image

pos_x = 64
pos_y = 32

def draw_btn_test(image, draw):
    global pos_x, pos_y

    action = get_dict(rkeys['ha_enki_rmt']).get('action')
    if action == 'color_saturation_step_up':
        pos_y -= 1
    if action == 'color_saturation_step_down':
        pos_y += 1
    if action == 'color_hue_step_up':
        pos_x += 1
    if action == 'color_hue_step_down':
        pos_x -= 1

    pos_x %= config.matrix_w
    pos_y %= config.matrix_h

    # draw.text((pos_x, pos_y), '↖', font=font_scientifica__r)
    icon = render_icon(cursor)

    image.alpha_composite(icon, (pos_x, pos_y))
    return image

@cache
def get_album_art(fragment: str):
    try:
        r = requests.get(f'http://{config.ha_base_url}{fragment}')
        r.raise_for_status()
        fp = io.BytesIO(r.content)
        img = Image.open(fp)
        return img.resize((25, 25))
    except requests.RequestException:
        return None

def draw_currently_playing(image, draw, st_music, tick):
    state = get_dict(rkeys['ha_sonos_beam'])

    if not state.get('new_state'):
        return image

    state = state['new_state']
    media_info = ''

    if state['state'] == 'playing':
        media_title = state['attributes'].get('media_title')
        media_album = state['attributes'].get('media_album_name')
        media_artist = state['attributes'].get('media_artist')
        elements = [media_title, media_album, media_artist]
        media_info = ' >> '.join([e for e in elements if e])
    else:
        return image

    if not media_info or media_title == 'TV':
        return image

    art = get_album_art(state['attributes'].get('entity_picture'))

    draw.text((122, 14), '♫', font=font_scientifica__r, fill='#1a810e')
    st_music.set_message(media_info)
    image = st_music.draw(tick, image)

    if art:
        image.paste(art, (config.matrix_w - 25 - 2, 24))
    return image


def draw_frame(st, st_detail, st_music, weather_icon):
    tick = time.time()
    step = tick * 15

    image = Image.new('RGBA', (128, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if not should_turn_on_display():
        # do not draw if nobody is there.
        return image

    # draw_sin_wave(step=(1 + step * .6), draw=draw, yoffset=38, amp=10, divisor=6, color='#98A9D0', width=1)
    draw_sin_wave(step=step, draw=draw, yoffset=24, amp=4, divisor=2, color='#3A6D8C')
    # draw_sin_wave(step=step * .5, draw=draw, yoffset=38, amp=7, divisor=14, color='#34424A', width=2)
    draw_sin_wave(step=(34 + step * .5), draw=draw, yoffset=25, amp=7, divisor=10, color='#5A5A5A')

    draw_date_time(draw)



    image = draw_numbers(image, draw, st, st_detail, tick)

    draw_22_22(draw)

    #enchancer = ImageEnhance.Sharpness(image)
    #image = enchancer.enhance(.7)
    #draw = ImageDraw.Draw(image)
    try:
        weather_frame = draw_weather(tick)
        image.alpha_composite(weather_frame.image, (0, 0))
    except Exception as e:
        raise
        print(e)

    image = draw_currently_playing(image, draw, st_music, tick)
    image = draw_btn_test(image, draw)

    # icon = render_icon(arrow_x, scale=1)
    # image.alpha_composite(icon, (50, 30))
    # draw.text((30, 42), '→ ← ₨ ♥  ⮀ ♡  卐', font=font_scientifica__r)

    return image

st = ScrollableText(
    '',
    anchor=(9, 55),
    width=(config.matrix_w - 9),
    speed=.001,
    delta=2,
    font=font_px_op__r,
    fill='#12cce1'
)
st_detail = ScrollableText(
    '',
    anchor=(2, 45),
    width=(40),
    speed=.001,
    delta=2,
    font=font_px_op_mono_8,
    fill='#9bb10d'
)
st_music = ScrollableText(
    '',
    anchor=(83, 16),
    width=(config.matrix_w - 83 - 7),
    speed=.001,
    delta=2,
    font=font_tamzen__rs,
    fill='#72be9c'
)
weather_icon = SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=.05)
sunset_arrow = SpriteIcon('assets/sunset-arrow.png', step_time=.2)
warning_icon = SpriteImage('assets/warning.7x7.png')[0]
sunrise_sunset_icon = SpriteImage('assets/sunrise-sunset.png')

def get_frame():
    return draw_frame(st, st_detail, st_music, weather_icon)
