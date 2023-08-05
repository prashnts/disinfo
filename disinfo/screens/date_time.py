import random

from PIL import Image, ImageDraw

from .drawer import draw_loop
from .colors import gray, amber_red, black, light_gray, light_blue, orange_red
from ..data_structures import FrameState
from ..components import fonts
from ..components.elements import Frame
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack
from ..components.text import TextStyle, text


s_date      = TextStyle(color=gray.darken(.2).hex, font=fonts.bitocra)
s_hour      = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_minute    = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_seconds   = TextStyle(color=light_blue.darken(.1).hex, font=fonts.bitocra)
s_day = {
    'weekend': {
        'text': TextStyle(color=light_gray.darken(.1).hex, font=fonts.tamzen__rs),
        'div': DivStyle(radius=2, background=orange_red.darken(.2).hex, padding=[1, 1, 1, 2]),
    },
    'weekday': {
        'text': TextStyle(color=black.hex, font=fonts.tamzen__rs),
        'div': DivStyle(radius=2, background=gray.darken(.2).hex, padding=[1, 1, 1, 2]),
    },
}
s_colon = [
    TextStyle(color=light_blue.darken(.5).hex, font=fonts.bitocra),
    TextStyle(color=light_blue.hex, font=fonts.bitocra),
]

def digital_clock(fs: FrameState, seconds=True):
    t = fs.now
    hhmm = hstack([
        text(t.strftime('%H'), s_hour),
        text(':', s_colon[t.microsecond <= 500_000]).reposition(x=1, y=-1),
        text(t.strftime('%M'), s_minute),
    ])
    if seconds:
        return hstack([hhmm, text(t.strftime('%S'), s_seconds)], gap=1)
    return hhmm

def day_of_the_week(fs: FrameState):
    t = fs.now
    style = s_day['weekend' if t.day_of_week in (6, 0) else 'weekday']
    return div(text(t.strftime('%a').upper(), style['text']), style['div'])

def date(fs: FrameState):
    t = fs.now
    return hstack([
        day_of_the_week(fs),
        text(t.strftime('%d/%m'), s_date),
    ], gap=2, align='bottom')

def glitterify(frame: Frame):
    # draw some shimmering leds everywhere!
    # todo: WIP
    gcols = [
        '#4096D9',
        '#404BD9',
        '#AF4FD7',
        '#D9BC40',
        '#D96140',
        '#1CB751',
    ]
    img = Image.new('RGBA', (frame.width, frame.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for x in range(frame.width):
        for y in range(frame.height):
            if random.random() < .3:
                pts = [(x, y)]
                if random.random() < 0.2:
                    pts.append((x + 1, y))
                if random.random() < 0.2:
                    pts.append((x, y + 1))
                if random.random() < 0.2:
                    pts.append((x + 1, y + 1))
                draw.point(pts, fill=random.choice(gcols))
    img.alpha_composite(frame.image)

    return Frame(img)

def composer(fs: FrameState):
    return div(
        vstack([
            digital_clock(fs),
            date(fs),
        ], gap=2, align='center'),
        style=DivStyle(background='#000000ac'))

draw = draw_loop(composer, sleepms=200)
