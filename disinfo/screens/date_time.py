import random

from PIL import Image, ImageDraw

from disinfo.utils import ease

from ..utils.drawer import draw_loop
from .colors import gray, gray_lt, amber_red, black, light_gray, light_blue, orange_red, minute_green
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
s_month     = TextStyle(color=gray.hex, font=fonts.dansk)
s_day_flip  = TextStyle(color=gray.hex, font=fonts.px_op__r)
s_date_flip = TextStyle(color=gray.hex, font=fonts.dansk, trim=(0, 0, 0, 0))
s_time_flip = TextStyle(color=gray_lt.hex, font=fonts.s16x8, trim=(0, 0, 0, 0))
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
    TextStyle(color="#DFD9C98F", font=fonts.dansk, trim=(0, 0, 0, 0)),
    TextStyle(color=gray.hex, font=fonts.dansk, trim=(0, 0, 0, 0)),
]


pastel_digit_colors = {
    0: "#FF8A80",
    1: "#FFB74D",
    2: "#B192EA",
    3: "#7AB3E2",
    4: "#7FCD81",
    5: "#C58DCF",
    6: "#E7A592",
    7: "#5A9FC0",
    8: "#A4CE75",
    9: "#DA8BA6" 
}

def find_sequences(s: str) -> set:
    # nemotron-3-nano
    hh, mm, ss = s.split(':')
    h, m, s_ = int(hh), int(mm), int(ss)

    result = set()

    if h == m:
        for ch in hh:
            result.add(int(ch))
    if h == s_:
        for ch in hh:
            result.add(int(ch))
    if m == s_:
        for ch in mm:
            result.add(int(ch))

    if not (h == m or h == s_ or m == s_):
        digit_set = {int(ch) for ch in hh + mm + ss}
        sorted_digits = sorted(digit_set)

        max_len = 0
        best_start = None

        cur_len = 1
        for i in range(1, len(sorted_digits)):
            if sorted_digits[i] == sorted_digits[i - 1] + 1:
                cur_len += 1
            else:
                if cur_len > max_len:
                    max_len = cur_len
                    best_start = sorted_digits[i - cur_len]
                cur_len = 1

        if cur_len > max_len:
            max_len = cur_len
            best_start = sorted_digits[-cur_len]

        if max_len >= 4 and best_start is not None:
            for v in range(best_start, best_start + max_len):
                result.add(v)

    return result

def digital_clock(fs: FrameState, seconds=True):
    t = fs.now
    hhmm = hstack([
        text_slide_in(fs, t.strftime('%H'), s_hour, 'top'),
        text(':', s_colon[t.microsecond <= 500_000]).reposition(x=1, y=-1),
        text_slide_in(fs, t.strftime('%M'), s_minute, 'top'),
    ])
    if seconds:
        return hstack([
            hhmm,
            text_slide_in(fs, t.strftime('%S'), s_seconds, 'top'),
        ], gap=1)
    return hhmm

def ease_seq(t: float):
    t2 = ease.sin.sin_in(t)
    if t2 <= 0.5:
        return t2
    else:
        d = (t2 - t) / 2
        return ease.bounce.bounce_out(t - d)

def _flip_text(fs: FrameState, value: str, text_style: TextStyle, edge: str, background: str = '#111111', together: bool = False):
    div_style = DivStyle(
        background=background,
        margin=(0, 3, 0, 3),
        padding=3,
        radius=3,
        border=1,
        border_color="#2D2D2DB8")
    content = text_slide_in(fs, value, text_style, edge, duration=0.3, easing=ease_seq, div_style=div_style, together=together)
    content = content.trim(left=2, right=2)
    return content


def flip_info(fs: FrameState, seconds=True, align='right'):
    t = fs.now
    bg = "#2D2D2D6E"
    week_day_bg = {5: '#00883377', 6: '#88003377'}.get(t.day_of_week, bg)
    mon_day = hstack([
        _flip_text(fs, t.strftime('%d'), s_date_flip, 'flip-top', together=True, background=bg),
        _flip_text(fs, t.strftime('%b'), s_month, 'flip-top', together=True, background=bg),
    ], gap=0)
    none_day = _flip_text(fs, t.strftime('%a'), s_day_flip, 'flip-top', week_day_bg, together=True)
    return vstack([mon_day, none_day], gap=2, align=align)

def flip_digital_clock(fs: FrameState, seconds=True, align='right'):
    t = fs.now
    time_str = t.strftime('%H:%M:%S')
    sequence_chars = find_sequences(time_str)
    
    bg = "#5E5E5E4E"  # Default background

    sequenced_chars = []
    
    def get_style_for_char(c, base):
        """Get style based on whether char is part of a sequence."""
        if int(c) in sequence_chars and (int(c) not in sequenced_chars or len(sequence_chars) < 3):
            sequenced_chars.append(int(c))
            return TextStyle(color=pastel_digit_colors[int(c)], font=base.font)  # Red for sequence digits
        return base  # Default style
    
    def styled_text(text_str, base=s_time_flip):
        """Create styled text with individual character styling."""
        return [get_style_for_char(c, base) for c in text_str]
    
    hhmm = hstack([
        _flip_text(fs, t.strftime('%H'), styled_text(t.strftime('%H')), 'flip-top', together=True, background=bg),
        _flip_text(fs, t.strftime('%M'), styled_text(t.strftime('%M')), 'flip-top', together=True, background=bg),
    ], gap=0)
    
    if seconds:
        return vstack([
            hhmm,
            _flip_text(fs, t.strftime('%S'), styled_text(t.strftime('%S'), s_colon_2[0]), 'flip-top', together=True, background=bg),
        ], gap=2, align=align)
    return hhmm

def world_clock(fs: FrameState):
    t = fs.now.in_tz('Asia/Kolkata')
    return hstack([
        div(text(
                'DEL',
                TextStyle(color=black.hex, font=fonts.tamzen__rs)
            ),
            DivStyle(background=light_blue.darken(.2).hex, radius=2, padding=(1, 1, 1, 2))),
        text_slide_in(fs, t.strftime('%H:%M'), TextStyle(color=gray.hex, font=fonts.bitocra7), 'top'),
    ], gap=2)

def day_of_the_week(fs: FrameState):
    t = fs.now
    style = s_day['weekend' if t.day_of_week in (6, 7) else 'weekday']
    return div(text_slide_in(fs, t.strftime('%a').upper(), style['text'], 'top'), style['div'])

def date(fs: FrameState):
    t = fs.now
    return hstack([
        day_of_the_week(fs),
        text_slide_in(fs, t.strftime('%d/%m'), s_date, 'top'),
    ], gap=2, align='bottom')

def simple(fs: FrameState):
    return div(vstack([
        text_slide_in(fs, fs.now.strftime('%H'), edge='right'),
        text_slide_in(fs, fs.now.strftime('%M'), edge='right'),
        text_slide_in(fs, fs.now.strftime('%S'), edge='right'),
    ]))

def sticky_widget(fs: FrameState):
    return div(
        vstack([
            text_slide_in(fs, fs.now.strftime('%H'), s_sticky_h, 'right'),
            text_slide_in(fs, fs.now.strftime('%M'), s_sticky_h, 'right'),
            text_slide_in(fs, fs.now.strftime('%S'), s_sticky, 'right'),
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

def flip_clock(fs: FrameState, align='right'):
    return div(
        flip_info(fs, align=align),
        style=DivStyle(background='#00000000', padding=1, radius=2)
    )


draw = draw_loop(composer)
