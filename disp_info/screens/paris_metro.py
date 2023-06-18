from functools import cache
from PIL import Image, ImageDraw

from .screen import composer_thread
from ..components import fonts
from ..components.elements import Frame, StillImage
from ..components.text import Text, MultiLineText, TextStyle
from ..components.layouts import hstack, vstack, mosaic
from ..components.layers import div, DivStyle, styled_div
from ..components.frame_cycler import FrameCycler
from ..components.scroller import VScroller, HScroller
from ..utils.func import throttle
from ..utils.palettes import metro_colors
from ..data_structures import FrameState
from ..drat.app_states import MetroInfoStateManager

warning_tile = StillImage('assets/raster/warning-tile-3x3.png')
metro_issue_icon = StillImage('assets/raster/metro-issues.png')
metro_paris_banner = StillImage('assets/raster/metro-paris-old-52x16.png')
msg_vscroll = VScroller(size=40, pause_at_loop=True, pause_duration=1.5, speed=0.02)
status_hscroll = HScroller(size=30, pause_at_loop=True, pause_duration=1, speed=0.02)

warning_line = mosaic(
    warning_tile,
    nx=1,
    ny=msg_vscroll.size // warning_tile.height,
    seamless=False)


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

@cache
def timing_text(value: int) -> Text:
    return Text(f'{value}'.rjust(2), style=TextStyle(font=fonts.bitocra, color='#a57a05'))

@cache
def message_text(value: str) -> MultiLineText:
    return MultiLineText(
        value,
        style=TextStyle(
            font=fonts.tamzen__rs,
            color='#b9b9b9',
            outline=1,
            outline_color='#181818',
            spacing=10,
            line_width=12,
        ),
    )

@cache
def loading_screen():
    return div(metro_paris_banner, style=DivStyle(background='#051534e2', radius=2, padding=10))

@throttle(50)
def get_state(fs: FrameState):
    return MetroInfoStateManager().get_state(fs)


def composer(fs: FrameState):
    state = get_state(fs)

    if not state.visible:
        msg_vscroll.reset_position()
        return

    if not state.valid:
        return loading_screen()

    s = state.data

    train_times = []
    status_icons = []
    msg_texts = []

    for info in s.information:
        if info.issues:
            ticon = metro_status_icon(info.line, issues=True)
            status_icons.append(ticon.draw(fs.tick))

            msgs = info.messages
            if msgs:
                msg_texts.append(ticon.draw(fs.tick))
                msg_texts.append(message_text('\n---\n'.join(msgs)))

    visible_timing_count = 3 if msg_texts else 4

    for train in s.trains:
        if not train.timings:
            next_train_times = ['--', '--']
        else:
            next_train_times = [round(t.next_in) for t in train.timings[:visible_timing_count]]
        ticon = metro_status_icon(train.line, issues=train.information.issues)
        timings = hstack([timing_text(t) for t in next_train_times], gap=3)
        time_table = hstack([ticon.draw(fs.tick), timings], gap=3)
        train_times.append(time_table)

    if not (train_times or status_icons):
        return

    list_view = [vstack(train_times, gap=1, align='left')]
    if status_icons:
        status_hscroll.set_frame(hstack(status_icons, gap=2), reset=False)
        list_view.append(hstack([
            metro_issue_icon,
            status_hscroll.draw(fs.tick),
        ], gap=1))

    main_view = [vstack(list_view, gap=2)]

    if msg_texts:
        msg_vscroll.set_frame(vstack(msg_texts, gap=4), False)
        msg_box = hstack([warning_line, msg_vscroll.draw(fs.tick)], gap=1)
        main_view.append(div(
            msg_box,
            style=DivStyle(
                background='#242424',
                padding=1,
                radius=(0, 2, 2, 0),
            ),
        ))

    return div(
        hstack(main_view, gap=2),
        style=DivStyle(
            background='#051534e2',
            padding=2,
            radius=(2, 2, 0, 0),
        ),
    )

draw = composer_thread(composer)
