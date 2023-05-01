#!/usr/bin/env python
import time
import math
import random
import requests
import io
import arrow

from PIL import Image, ImageDraw
from functools import cache

from .weather_icons import render_icon, cursor
from .redis import get_dict, rkeys
from .state_proxy import should_turn_on_display
from .components.text import Text
from .components.elements import Frame
from .components.layouts import stack_horizontal, stack_vertical, composite_at
from .components.scroller import ScrollableText
from .components import fonts

from .screens import date_time, octoprint, weather, twenty_two
from . import config


def draw_sin_wave(step, draw, yoffset, amp, divisor, color, width=1):
    AMP = amp
    OFFSET = 10
    DIVISOR = divisor # 1.5

    y_step = lambda x: round(math.sin(step + x / DIVISOR) * AMP + OFFSET)
    xys = [(x + 0, y_step(x) + yoffset) for x in range(128)]

    draw.line(xys, fill=color, width=width, joint='curve')


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


def draw_frame(st, st_detail, st_music):
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

    twenty_two_frame = twenty_two.draw()

    octoprint_info = octoprint.draw()

    right_widget = [date_time.draw()]

    if octoprint_info:
        right_widget.append(octoprint_info)

    composite_at(stack_vertical(right_widget, gap=1, align='right'), image, 'tr')
    composite_at(weather.draw(tick), image, 'tl')
    image = draw_currently_playing(image, draw, st_music, tick)

    if twenty_two_frame:
        composite_at(twenty_two_frame, image, 'mm')

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

def get_frame():
    return draw_frame(st, st_detail, st_music)
