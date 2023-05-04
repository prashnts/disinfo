import arrow
import random

from PIL import Image, ImageDraw

from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.layouts import composite_at
from disp_info.components.text import Text
from disp_info.redis import rkeys, get_dict
from disp_info import config

text_timestr = Text()


def draw():
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

    text_timestr.update(
        value=t.strftime('%H:%M'),
        font=font,
        fill=fill)

    image = Image.new('RGBA', (config.matrix_w, config.matrix_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    composite_at(text_timestr, image, 'mm')

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
