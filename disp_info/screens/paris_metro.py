import pendulum

from functools import cache
from PIL import Image, ImageDraw

from ..components import fonts
from ..components.elements import Frame
from ..components.text import Text
from ..components.layouts import composite_at, stack_horizontal, stack_vertical
from ..components.layers import add_background
from ..redis import rkeys, get_dict
from ..utilities.func import throttle
from ..utilities.palettes import metro_colors


@cache
def status_icon(status_name: str):
    size = 9
    img = Image.new('RGBA', (size + 1, size + 1))
    draw = ImageDraw.Draw(img)

    draw.regular_polygon([size / 2, size / 2 + 1, size / 2 + 1], 3, fill='#e64539')

    draw.text((size / 2 + 1, size / 2 + 1), '!', fill='#fff', font=fonts.tamzen__rs, anchor='mm')

    return Frame(img)


@cache
def metro_icon(line_name: str, problems: bool = False) -> Frame:
    size = 9
    background, text_color = metro_colors.get(line_name, ['#C6C6C6', '#000'])

    img = Image.new('RGBA', (size + 1, size))
    draw = ImageDraw.Draw(img)

    start_x = 0 if len(line_name) > 1 else 1

    draw.rounded_rectangle([0, 0, size, size - 1], fill=background, radius=2)

    draw.text(((size / 2) + start_x, size / 2), line_name, fill=text_color, font=fonts.tamzen__rs, anchor='mm')

    return Frame(img)


@throttle(400)
def get_state():
    payload = get_dict(rkeys['metro_timing'])
    last_updated = pendulum.parse(payload['timestamp'])
    visible = last_updated.add(minutes=1, seconds=20) > pendulum.now()

    return {
        'is_visible': visible,
        **payload,
    }

@cache
def timing_text(value: int):
    return Text(f'{value}'.rjust(2), fonts.bitocra, fill='#a57a05')


def draw(tick: float):
    s = get_state()

    if not s['is_visible']:
        return

    train_times = []

    for train in s['trains']:
        if not train['timings']:
            continue
        ticon = metro_icon(train['line'])
        times = []
        for time in train['timings'][:3]:
            times.append(timing_text(round(time['next_in'])))
        time_table = stack_horizontal([
            ticon,
            stack_horizontal(times, gap=3)
        ], gap=3)
        train_times.append(time_table)

    if not train_times:
        return

    return add_background(
        stack_vertical(train_times, gap=1, align='left'),
        fill='#071e4ac2',
        radius=2,
        padding=2)
