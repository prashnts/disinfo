import pendulum

from functools import cache
from PIL import Image, ImageDraw

from ..components import fonts
from ..components.elements import Frame, StillImage
from ..components.text import Text
from ..components.layouts import composite_at, stack_horizontal, stack_vertical
from ..components.layers import add_background
from ..components.frame_cycler import FrameCycler
from ..redis import rkeys, get_dict
from ..utils.func import throttle
from ..utils.palettes import metro_colors

metro_issue_icon = StillImage('assets/raster/metro-issues.png')


@cache
def status_icon(status_name: str):
    size = 9
    img = Image.new('RGBA', (size + 1, size + 1))
    draw = ImageDraw.Draw(img)
    draw.regular_polygon([size / 2, size / 2 + 1, size / 2 + 1], 3, fill='#e64539')
    draw.text((size / 2 + 1, size / 2 + 1), '!', fill='#fff', font=fonts.tamzen__rs, anchor='mm')

    return Frame(img)


@cache
def metro_icon(line_name: str, outline: bool = False, has_problems: bool = False) -> Frame:
    size = 9
    start_x = 0 if len(line_name) > 1 else 1
    background, text_color = metro_colors.get(line_name, ['#C6C6C6', '#000'])
    outline_color = '#ba1c11' if has_problems else '#000'
    outline_width = 1 if outline else 0

    img = Image.new('RGBA', (size + 1, size))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [0, 0, size, size - 1],
        fill=background,
        radius=2,
        outline=outline_color,
        width=outline_width)
    draw.text(
        ((size / 2) + start_x, size / 2),
        line_name,
        fill=text_color,
        font=fonts.tamzen__rs,
        anchor='mm')

    return Frame(img)

@cache
def metro_status_icon(line_name: str, issues: bool):
    frames = [
        metro_icon(line_name, outline=False),
        metro_icon(line_name, outline=issues, has_problems=issues),
    ]
    return FrameCycler(frames)


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
    status_icons = []

    for train in s['trains']:
        if not train['timings']:
            continue
        ticon = metro_status_icon(train['line'], issues=train['information']['issues'])
        times = [timing_text(round(t['next_in'])) for t in train['timings'][:3]]
        time_table = stack_horizontal([
            ticon.draw(tick),
            stack_horizontal(times, gap=3)
        ], gap=3)
        train_times.append(time_table)

    for info in s['information']:
        if info['issues']:
            ticon = metro_status_icon(info['line'], issues=True)
            status_icons.append(ticon.draw(tick))


    if not (train_times or status_icons):
        return

    list_view = [stack_vertical(train_times, gap=1, align='left')]

    if status_icons:
        list_view.append(stack_horizontal([metro_issue_icon, *status_icons], gap=2))

    return add_background(
        stack_vertical(list_view, gap=2),
        fill='#071e4ac2',
        radius=2,
        padding=2)
