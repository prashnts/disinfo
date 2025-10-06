import random

from PIL import Image, ImageDraw

from disinfo.utils import ease

from .drawer import draw_loop
from .colors import gray, amber_red, black, light_gray, light_blue, orange_red, minute_green
from ..data_structures import FrameState
from ..components import fonts
from ..components.elements import Frame
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, vstack, composite_at
from ..components.text import TextStyle, text
from ..components.transitions import text_slide_in
from ..components.widget import Widget


s_date      = TextStyle(color=gray.darken(.2).hex, font=fonts.bitocra7)
s_hour      = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_month     = TextStyle(color=gray.hex, font=fonts.px_op__r)
s_day_flip  = TextStyle(color=gray.hex, font=fonts.px_op__r)
s_date_flip = TextStyle(color=gray.hex, font=fonts.catv, trim=(0, 0, 2, 0))
s_time_flip = TextStyle(color=gray.hex, font=fonts.scientifica__r, trim=(0, 0, 1, 0))
s_second_flip = TextStyle(color=light_blue.darken(.1).hex, font=fonts.scientifica__i)
s_minute    = TextStyle(color=gray.hex, font=fonts.px_op__l)
s_seconds   = TextStyle(color=light_blue.darken(.1).hex, font=fonts.bitocra7)
s_sticky    = TextStyle(color=light_blue.darken(.1).hex, font=fonts.bitocra7)
s_sticky_h  = TextStyle(color=minute_green.darken(.2).hex, font=fonts.bitocra7)
s_sticky_s  = TextStyle(color=light_gray.darken(.4).hex, font=fonts.bitocra7)
s_day = {
    'weekend': {
        'text': TextStyle(color=light_gray.darken(.1).hex, font=fonts.tamzen__rs),
        'div': DivStyle(radius=2, background=orange_red.darken(.2).hex, padding=(1, 1, 1, 2)),
    },
    'weekday': {
        'text': TextStyle(color=black.hex, font=fonts.tamzen__rs),
        'div': DivStyle(radius=2, background=gray.darken(.2).hex, padding=(1, 1, 1, 2)),
    },
}
s_colon = [
    TextStyle(color=light_blue.darken(.2).hex, font=fonts.bitocra7),
    TextStyle(color=light_blue.hex, font=fonts.bitocra7),
]
s_colon_2 = [
    TextStyle(color=light_blue.darken(.2).hex, font=fonts.scientifica__r, trim=(0, 0, 1, 0)),
    TextStyle(color=light_blue.hex, font=fonts.scientifica__r, trim=(0, 0, 1, 0)),
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

def _flip_text(fs: FrameState, key: str, value: str, text_style: TextStyle, edge: str, background: str = '#111111', together: bool = False):
    div_style = DivStyle(background=background, padding=(2, 2, 2, 2), radius=2, border=1, border_color='#000000cc')
    content = text_slide_in(fs, key, value, text_style, edge, duration=0.2, easing=ease.linear.linear, div_style=div_style, together=together)
    return content


def flip_info(fs: FrameState, seconds=True):
    t = fs.now
    background = '#992222' if t.day_of_week in (5, 6) else '#111111'
    mon_day = vstack([
        _flip_text(fs, 'dt.fi.mon', t.strftime('%b'), s_month, 'flip-top', together=True),
        _flip_text(fs, 'dt.fi.dow', t.strftime('%a'), s_day_flip, 'flip-top', background, together=True),
    ], gap=1)
    none_day = _flip_text(fs, 'dt.fi.day', t.strftime('%d'), s_date_flip, 'flip-top', together=True)
    return hstack([none_day, mon_day], gap=2, align='top')

def flip_digital_clock(fs: FrameState, seconds=True):
    t = fs.now
    hhmm = hstack([
        _flip_text(fs, 'dt.fd.hr', t.strftime('%H'), s_time_flip, 'flip-top', together=True),
        text(':', s_colon[t.microsecond <= 500_000]).reposition(x=1, y=-1).trim(left=1),
        _flip_text(fs, 'dt.fd.mn', t.strftime('%M'), s_time_flip, 'flip-top', together=True),
        # _flip_text(fs, 'dt.fd.min', t.strftime('%M'), s_time_flip, 'flip-top'),
    ], gap=0)
    if seconds:
        return vstack([
            hhmm,
            _flip_text(fs, 'dt.fd.sec', t.strftime('%S'), s_colon_2[t.second % 2 == 0], 'flip-top', together=True),
        ], gap=0, align='right')
    return hhmm

def world_clock(fs: FrameState):
    t = fs.now.in_tz('Asia/Kolkata')
    return hstack([
        div(text(
                'DEL',
                TextStyle(color=black.hex, font=fonts.tamzen__rs)
            ),
            DivStyle(background=light_blue.darken(.2).hex, radius=2, padding=(1, 1, 1, 2))),
        text_slide_in(fs, 'dt.wc', t.strftime('%H:%M'), TextStyle(color=gray.hex, font=fonts.bitocra7), 'top'),
    ], gap=2)

def day_of_the_week(fs: FrameState):
    t = fs.now
    style = s_day['weekend' if t.day_of_week in (6, 7) else 'weekday']
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

def date_pattern(fs: FrameState):
    t = fs.now
    if t.hour == t.minute == t.second:
        color = green
    # todo: complete this.

def simple(fs: FrameState):
    return div(vstack([
        text_slide_in(fs, 'dt.sm.clk.h', fs.now.strftime('%H'), edge='right'),
        text_slide_in(fs, 'dt.sm.clk.m', fs.now.strftime('%M'), edge='right'),
        text_slide_in(fs, 'dt.sm.clk.s', fs.now.strftime('%S'), edge='right'),
    ]))

def sticky_widget(fs: FrameState):
    return div(
        vstack([
            text_slide_in(fs, 'dt.sk.clk.h', fs.now.strftime('%H'), s_sticky_h, 'right'),
            text_slide_in(fs, 'dt.sk.clk.m', fs.now.strftime('%M'), s_sticky_h, 'right'),
            text_slide_in(fs, 'dt.sk.clk.s', fs.now.strftime('%S'), s_sticky, 'right'),
        ]),
        style=DivStyle(background='#112244', padding=(1, 1, 1, 2), radius=(0, 0, 2, 2)))

def composer(fs: FrameState):
    return div(
        vstack([
            digital_clock(fs),
            # date(fs),
            world_clock(fs),
        ], gap=2, align='center'),
        style=DivStyle(background='#00000000'))

def calendar_widget(fs: FrameState):
    contents = vstack([
        date(fs),
        world_clock(fs),
    ], gap=2)
    return Widget('dt.calendar', contents, priority=0.1)

def flip_clock(fs: FrameState):
    return div(
        flip_info(fs),
        style=DivStyle(background='#00000000', padding=1, radius=2)
    )


draw = draw_loop(composer)
