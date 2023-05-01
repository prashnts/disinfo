#!/usr/bin/env python
import time
import math
import random
import requests
import io
import arrow

from PIL import Image, ImageDraw, ImageFont
from functools import cache
from colour import Color

from .weather_icons import render_icon, cursor
from .redis import get_dict, rkeys
from .state_proxy import should_turn_on_display
from .sprite_icons import SpriteIcon, SpriteImage
from .components.text import Text
from .components.elements import Frame
from .components.layouts import stack_horizontal, stack_vertical, composite_at
from .components.scroller import ScrollableText
from .components import fonts
from . import config


def draw_sin_wave(step, draw, yoffset, amp, divisor, color, width=1):
    AMP = amp
    OFFSET = 10
    DIVISOR = divisor # 1.5

    y_step = lambda x: round(math.sin(step + x / DIVISOR) * AMP + OFFSET)
    xys = [(x + 0, y_step(x) + yoffset) for x in range(128)]

    draw.line(xys, fill=color, width=width, joint='curve')


def draw_date_time():
    t = arrow.now()
    time_color = '#2BBEC9' if t.second % 2 == 0 else '#0E699D'
    date_color = '#9F4006'

    return stack_vertical([
        Text(t.strftime('%H:%M:%S'), font=fonts.tamzen__rs, fill=time_color),
        stack_horizontal([
            Text(t.strftime('%a'), font=fonts.tamzen__rs, fill=date_color),
            Text(t.strftime('%d/%m'), font=fonts.tamzen__rs, fill=date_color),
        ], gap=2, align='center'),
    ], gap=1, align='right')

def draw_22_22():
    t = arrow.now()
    # t = arrow.get(2022, 2, 1, 21, 21, t.second)
    action = get_dict(rkeys['ha_enki_rmt']).get('action')

    equal_elements = t.hour == t.minute
    twentytwo = t.hour == t.minute == 22
    all_equal = t.hour == t.minute == t.second

    if action == 'scene_1':
        twentytwo == True
        equal_elements = True
        all_equal = True

    if not equal_elements:
        return

    font = fonts.px_op__xl
    fill = '#2FB21B'
    if twentytwo:
        fill = '#CF8C13'
        font = fonts.px_op__xxl
    if all_equal:
        fill = '#CF3F13'

    time_text = Text(t.strftime('%H:%M'), font=font, fill=fill)
    image = Image.new('RGBA', (config.matrix_w, config.matrix_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    composite_at(time_text, image, 'mm')

    # glittering colors if it's the magic hour
    if not (twentytwo or all_equal):
        return Frame(image)

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

    return Frame(image)

@cache
def draw_temp_range(
    t_current: float,
    t_high: float,
    t_low: float,
    font: ImageFont = fonts.tamzen__rs) -> Frame:
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

    # Current temperature and codition + High/Low
    temperature = forecast['currently']['apparentTemperature']
    update_time = arrow.get(forecast['currently']['time'], tzinfo='local')
    condition = forecast['currently']['summary']
    icon_name = forecast['currently']['icon']
    _today = forecast['daily']['data'][0]
    t_high = _today['temperatureHigh']
    t_low = _today['temperatureLow']
    # Sunset info
    sunset_time = arrow.get(_today['sunsetTime'], tzinfo='local')

    now = arrow.now()
    should_show_sunset = sunset_time > now and (sunset_time - now).total_seconds() < 2 * 60 * 60
    is_outdated = (now - update_time).total_seconds() > 30 * 60  # 30 mins.

    weather_icon.set_icon(f'assets/unicorn-weather-icons/{icon_name}.png')

    temp_text = stack_horizontal([
        Text(f'{round(temperature)}', font=fonts.px_op__l, fill=color_temp),
        Text('°', font=fonts.px_op__r, fill=color_deg_c),
    ], gap=0, align='top')

    condition_info = [Text(condition, font=fonts.tamzen__rs, fill=color_condition)]

    if is_outdated:
        condition_info.insert(0, warning_icon)

    weather_info = stack_vertical([
        stack_horizontal([
            weather_icon.draw(step),
            temp_text,
            draw_temp_range(temperature, t_high, t_low, fonts.tamzen__rs),
        ], gap=1, align='center'),
        stack_horizontal(condition_info, gap=2, align='center'),
    ], gap=1, align='left')

    weather_stack = [weather_info]

    if should_show_sunset:
        weather_stack.append(stack_horizontal([
            sunset_arrow.draw(step),
            Text(sunset_time.strftime('%H:%M'), font=fonts.tamzen__rs, fill=color_condition),
        ], gap=1, align='center'))

    return stack_vertical(weather_stack, gap=1, align='left')


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
    draw.text((1, 52), 'i', font=fonts.tamzen__rm)

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

    draw.text((122, 14), '♫', font=fonts.scientifica__r, fill='#1a810e')
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

    draw_sin_wave(step=step, draw=draw, yoffset=24, amp=4, divisor=2, color='#3A6D8C')
    draw_sin_wave(step=(34 + step * .5), draw=draw, yoffset=25, amp=7, divisor=10, color='#5A5A5A')

    image = draw_numbers(image, draw, st, st_detail, tick)

    twenty_two = draw_22_22()

    composite_at(draw_date_time(), image, 'tr')
    composite_at(draw_weather(tick), image, 'tl')
    image = draw_currently_playing(image, draw, st_music, tick)

    if twenty_two:
        composite_at(twenty_two, image, 'mm')

    image = draw_btn_test(image, draw)

    return image

st = ScrollableText(
    '',
    anchor=(9, 55),
    width=(config.matrix_w - 9),
    speed=.001,
    delta=2,
    font=fonts.px_op__r,
    fill='#12cce1'
)
st_detail = ScrollableText(
    '',
    anchor=(2, 45),
    width=(40),
    speed=.001,
    delta=2,
    font=fonts.px_op_mono_8,
    fill='#9bb10d'
)
st_music = ScrollableText(
    '',
    anchor=(83, 16),
    width=(config.matrix_w - 83 - 7),
    speed=.001,
    delta=2,
    font=fonts.tamzen__rs,
    fill='#72be9c'
)
weather_icon = SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=.05)
sunset_arrow = SpriteIcon('assets/sunset-arrow.png', step_time=.2)
warning_icon = SpriteImage('assets/sync.png')[0]

def get_frame():
    return draw_frame(st, st_detail, st_music, weather_icon)
