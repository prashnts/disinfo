import random

from PIL import Image, ImageDraw

from .drawer import draw_loop
from ..components import fonts
from ..components.elements import Frame
from ..components.layouts import composite_at
from ..components.text import TextStyle, text
from ..data_structures import FrameState
from ..drat.app_states import RemoteStateManager
from ..config import app_config


def composer(fs: FrameState):
    t = fs.now #.set(hour=21, minute=21, second=2)

    equal_elements = t.hour == t.minute
    twentytwo = t.hour == t.minute == 22
    all_equal = t.hour == t.minute == t.second

    if RemoteStateManager().get_state(fs).action == 'btn_twentytwo':
        twentytwo == True
        equal_elements = True
        all_equal = True

    if not equal_elements:
        return

    font = fonts.px_op__xl
    fill = '#2FB21B'
    if twentytwo:
        fill = '#CF8C13'
        font = fonts.px_op__xl if app_config.width < 128 else fonts.px_op__xxl
    if all_equal:
        fill = '#CF3F13'

    text_timestr = text(t.strftime('%H:%M'), style=TextStyle(font=font, color=fill, outline=1))

    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 0))
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
    for x in range(app_config.width):
        for y in range(app_config.height):
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


draw = draw_loop(composer, sleepms=50)
