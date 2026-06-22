import random
import numpy as np
import time

from PIL import Image, ImageDraw

from ..utils.drawer import draw_loop
from ..components import fonts
from ..components.elements import Frame
from ..components.layouts import composite_at, place_at, hstack, mosaic
from ..components.layers import div
from ..components.text import TextStyle, text
from ..components.spriteim import SpriteIcon
from ..data_structures import FrameState
from ..drat.app_states import RuntimeStateManager
from ..config import app_config


nyan_gif = SpriteIcon('assets/raster/nyan-cat2.gif', step_time=0.1, resize=(42, 42))
nyan_rainbow = SpriteIcon('assets/raster/nyan-rainbow.gif', step_time=0.1, resize=(128, 42))

def _gen_path():
    xmax = app_config.width
    ymax = app_config.height
    vmax = 10
    velocity = 3
    pos = np.array([0., 64.])
    dirn = np.array([2., 2.])

    get_angle = lambda a, b: -np.angle(a + b * 1j, deg=True) + 0

    angle = get_angle(dirn[0], dirn[1])

    def _get_anchor(pos):
        return 'mm'

    while True:        
        if random.random() > 0.95:
            dirn[0] += random.choice(np.arange(-.2, .2, .01))
        if random.random() > 0.95:
            dirn[1] += random.choice(np.arange(-.2, .2, .01))
        if random.random() > 0.8:
            velocity = random.choice(np.arange(0, 0.6, 0.05))

        pnext = pos + (velocity * dirn)
        if pnext[0] >= xmax or pnext[0] <= 0:
            dirn[0] *= -1
        if pnext[1] >= ymax or pnext[1] <= 0:
            dirn[1] *= -1

        pos = pos + (velocity * dirn)
        angle = get_angle(dirn[0], dirn[1])
        yield pos, angle, _get_anchor(pos)

next_pos = _gen_path()

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

    text_timestr = text(t.strftime('%H:%M:%S'), style=TextStyle(font=font, color=fill, outline=1))
    content = div(text_timestr, background='#5010A088', padding=2, radius=2)


    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    content = hstack([content, nyan_gif.draw(fs.tick)])

    content = composite_at(nyan_rainbow.draw(fs.tick), content, behind=True, dx=-40, anchor='tr')
    pos, angle, anchor = next(next_pos)
    place_at(content.rotate(angle), image, x=int(pos[0]), y=int(pos[1]), anchor=anchor)

    # composite_at(content, image, 'bl', dy=-42, frost=3, vibrant=1)

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
