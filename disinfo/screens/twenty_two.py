import random

from PIL import Image, ImageDraw

from ..utils.drawer import draw_loop
from ..components import fonts
from ..components.elements import Frame
from ..components.layouts import composite_at
from ..components.layers import div
from ..components.text import TextStyle, text
from ..components.spriteim import SpriteIcon
from ..data_structures import FrameState
from ..drat.app_states import RuntimeStateManager
from ..config import app_config


nyan_gif = SpriteIcon('assets/raster/nyan.png', step_time=0.1)


def composer(fs: FrameState):
    t = fs.now #.set(hour=21, minute=21, second=2)

    equal_elements = t.hour == t.minute
    twentytwo = t.hour == t.minute == 22
    all_equal = t.hour == t.minute == t.second

    if RuntimeStateManager().get_state(fs).show_twentytwo:
        equal_elements = True

    if not equal_elements:
        return

    font = fonts.mecha_cb
    font = fonts.pix_tall
    fill = '#2FB21B'
    if twentytwo:
        fill = '#CF8C13'
        # font = fonts.px_op__l if app_config.width < 128 else fonts.px_op__l
    if all_equal:
        fill = '#CF3F13'

    text_timestr = text(t.strftime('%H:%M'), style=TextStyle(font=font, color=fill, outline=1))
    content = div(text_timestr, background='#5010A088', padding=2, radius=2)

    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 50))
    draw = ImageDraw.Draw(image)

    composite_at(nyan_gif.draw(fs.tick), image, 'bm', dx=20)
    composite_at(content, image, 'bl', dy=-42, frost=3, vibrant=1)

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
            if random.random() < .001:
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
