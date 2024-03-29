import pendulum

from datetime import datetime
from functools import cache
from typing import Optional
from PIL import ImageDraw
from pydantic import BaseModel

from .drawer import draw_loop
from ..components import fonts
from ..components.elements import Frame, StillImage
from ..components.text import Text, MultiLineText, TextStyle
from ..components.layouts import hstack, vstack, mosaic
from ..components.layers import div, DivStyle, rounded_rectangle
from ..components.frame_cycler import FrameCycler
from ..components.scroller import VScroller, HScroller
from ..components.transitions import VisibilitySlider
from ..utils.palettes import metro_colors
from ..utils.time import is_expired
from ..data_structures import FrameState, AppBaseModel
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..drat import idfm
from ..redis import get_dict, publish, rkeys

warning_tile = StillImage('assets/raster/warning-tile-3x3.png')
metro_issue_icon = StillImage('assets/raster/metro-issues.png')
metro_paris_banner = StillImage('assets/raster/metro-paris-old-52x16.png')
msg_vscroll = VScroller(size=40, pause_at_loop=True, pause_duration=1.5, speed=0.02)
status_hscroll = HScroller(size=30, pause_at_loop=True, pause_duration=1, speed=0.02)
visibility_slider = VisibilitySlider(edge='bottom', duration=0.3)

warning_line = mosaic(
    warning_tile,
    nx=1,
    ny=msg_vscroll.size // warning_tile.height,
    seamless=False)


class MetroAppState(AppBaseModel):
    show: bool = False
    visible: bool = False
    valid: bool = False
    toggled_at: Optional[datetime] = None
    data: Optional[idfm.MetroData] = None

class MetroAppStateManager(PubSubStateManager[MetroAppState]):
    model = MetroAppState
    channels = ('di.pubsub.metro', 'di.pubsub.remote')

    # TODO support intializing the inner states.

    def process_message(self, channel: str, data: PubSubMessage):
        if channel.endswith('.metro'):
            if data.action == 'update':
                self.update_data()
            if data.action == 'toggle':
                self.toggle()
        if channel.endswith('.remote'):
            if data.action == 'btn_metro':
                self.toggle()

    def initial_state(self) -> MetroAppState:
        return MetroAppState(data=self.load_timing())

    def toggle(self):
        s = self.state
        show = s.show
        if is_expired(s.toggled_at, seconds=25):
            show = True
        else:
            show = not show
        if show:
            publish('di.pubsub.dataservice', action='fetch_metro')
        self.state.show = show
        self.state.toggled_at = pendulum.now()

    def load_timing(self):
        if timing := get_dict(rkeys['metro_timing']):
            return idfm.MetroData(**timing)

    def update_data(self):
        self.state.data = self.load_timing()

    def get_state(self, fs: FrameState):
        s = self.state
        if not s.data:
            s.visible = False
            s.valid = False
        else:
            shown = s.show and not is_expired(s.toggled_at, seconds=25, now=fs.now)
            s.visible = idfm.is_active() or shown
            s.valid = not is_expired(s.data.timestamp, minutes=1, seconds=20, now=fs.now)

        return s


@cache
def metro_icon(line_name: str, outline: bool = False, has_problems: bool = False) -> Frame:
    size = 9
    start_x = 0 if len(line_name) > 1 else 1
    background, text_color = metro_colors.get(line_name, ['#C6C6C6', '#000'])

    img = rounded_rectangle(
        width=size + 1,
        height=size,
        radius=(4,) * 4,
        fill=background,
        border=1 if outline else 0,
        border_color='#ba1c11' if has_problems else '#000')

    draw = ImageDraw.Draw(img)
    draw.text(
        ((size / 2) + start_x, size / 2),
        line_name,
        fill=text_color,
        font=fonts.tamzen__rs.font,
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
    return Text(f'{value}'.rjust(2), style=TextStyle(font=fonts.bitocra7, color='#a57a05'))

@cache
def message_text(value: str) -> MultiLineText:
    return MultiLineText(
        value,
        style=TextStyle(
            font=fonts.tamzen__rs,
            color='#b9b9b9',
            outline=1,
            outline_color='#181818',
            spacing=1,
            line_width=12,
        ),
    )


def render_metro_info(fs: FrameState, state: MetroAppState):
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
        status_icon_ticker = (status_hscroll
            .set_frame(hstack(status_icons, gap=2), reset=False)
            .set_size(visible_timing_count * 10)
            .draw(fs.tick))
        list_view.append(hstack([
            metro_issue_icon,
            status_icon_ticker,
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
                radius=(2, 2, 0, 0),
            ),
        ))

    return hstack(main_view, gap=2)


def metro_view(fs: FrameState, state: MetroAppState):
    if state.valid:
        content = render_metro_info(fs, state)
    else:
        content = div(metro_paris_banner, style=DivStyle(padding=10))

    return div(
        content,
        style=DivStyle(
            background='#051534',
            padding=2,
            radius=(3, 0, 0, 3),
            border=1,
            border_color='#333435',
        ),
    )


def composer(fs: FrameState):
    state = MetroAppStateManager().get_state(fs)

    return (visibility_slider
        .set_frame(metro_view(fs, state))
        .visibility(state.visible)
        .draw(fs.tick))

draw = draw_loop(composer)
