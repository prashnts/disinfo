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
from ..components.transitions import text_slide_in


s_date      = TextStyle(color=gray.darken(.2).hex, font=fonts.bitocra7)
s_hour      = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_minute    = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_seconds   = TextStyle(color=light_blue.darken(.1).hex, font=fonts.bitocra7)
s_sticky    = TextStyle(color=light_blue.darken(.1).hex, font=fonts.bitocra7)
s_sticky_h  = TextStyle(color=orange_red.darken(.2).hex, font=fonts.bitocra7)
s_sticky_s  = TextStyle(color=light_gray.darken(.4).hex, font=fonts.bitocra7)
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
    TextStyle(color=light_blue.darken(.2).hex, font=fonts.bitocra7),
    TextStyle(color=light_blue.hex, font=fonts.bitocra7),
]


def digital_clock(fs: FrameState, seconds=True):
    t = fs.now
    hhmm = hstack([
        text_slide_in(fs, 'dt.dc.hr', t.strftime('%H'), s_hour, 'top'),
        text(':', s_colon[t.microsecond <= 500_000]).reposition(x=1, y=-1),
        text_slide_in(fs, 'dt.dc.min', t.strftime('%M'), s_minute, 'top'),
    ])
    if seconds:
        return hstack([
            hhmm,
            text_slide_in(fs, 'dt.dc.sec', t.strftime('%S'), s_seconds, 'top'),
        ], gap=1)
    return hhmm

def world_clock(fs: FrameState):
    t = fs.now.in_tz('Asia/Kolkata')
    return hstack([
        div(text(
                'DEL',
                TextStyle(color=black.hex, font=fonts.tamzen__rs)
            ),
            DivStyle(background=light_blue.darken(.2).hex, radius=2, padding=[1, 1, 1, 2])),
        text_slide_in(fs, 'dt.wc', t.strftime('%H:%M'), TextStyle(color=gray.hex, font=fonts.bitocra7), 'top'),
    ], gap=2)

def day_of_the_week(fs: FrameState):
    t = fs.now
    style = s_day['weekend' if t.day_of_week in (6, 0) else 'weekday']
    return div(text_slide_in(fs, 'dt.dow', t.strftime('%a').upper(), style['text'], 'top'), style['div'])

def date(fs: FrameState):
    t = fs.now
    return hstack([
        day_of_the_week(fs),
        text_slide_in(fs, 'dt.date', t.strftime('%d/%m'), s_date, 'top'),
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

def sticky_widget(fs: FrameState):
    return div(
        vstack([
            text_slide_in(fs, 'dt.sk.clk.h', fs.now.strftime('%H'), s_sticky_h, 'top'),
            text_slide_in(fs, 'dt.sk.clk.m', fs.now.strftime('%M'), s_sticky_h, 'top'),
            text_slide_in(fs, 'dt.sk.clk.s', fs.now.strftime('%S'), s_sticky, 'top'),
        ]),
        style=DivStyle(background='#112244', padding=(1, 0, 1, 2), radius=(0, 0, 2, 2)))

def composer(fs: FrameState):
    return div(
        vstack([
            digital_clock(fs),
            date(fs),
            world_clock(fs),
        ], gap=2, align='center'),
        style=DivStyle(background='#00000000'))

draw = draw_loop(composer)
