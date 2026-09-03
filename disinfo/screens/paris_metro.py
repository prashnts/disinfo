import pendulum

from datetime import datetime
from functools import cache
from typing import Optional
from PIL import ImageDraw

from ..utils.drawer import draw_loop
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
from ..utils.func import throttle
from ..data_structures import FrameState, AppBaseModel
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..drat.idfm import fetch_state
from ..drat import idfm
from ..redis import get_dict, publish
from disinfo.components.widget import Widget

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
    tick: int = 0


@throttle(27_000)
def throttled_fetch_state(force: bool = False):
    if idfm.is_active() or force:
        try:
            return idfm.fetch_state()
        except Exception as e:
            print('Error fetching metro state:', e)

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
            print('Remote message received:', data)
            if data.action == 'show_metro':
                self.toggle()

    def initial_state(self) -> MetroAppState:
        return MetroAppState(data=throttled_fetch_state())

    def toggle(self):
        s = self.state
        show = s.show
        if is_expired(s.toggled_at, seconds=25):
            show = True
        else:
            show = not show
        if show:
            self.state.data = throttled_fetch_state(True)
        self.state.show = show
        self.state.toggled_at = pendulum.now()

    def update_data(self, fs: FrameState):
        s = self.state
        next_state = throttled_fetch_state()
        if next_state:
            self.state.data = next_state

    def get_state(self, fs: FrameState):
        s = self.state
        self.update_data(fs)
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
            font=fonts.microfont_35_reg,
            color='#b9b9b9',
            outline=1,
            outline_color='#181818',
            spacing=1,
            width=69,
        ),
    )


def render_metro_info(fs: FrameState, state: MetroAppState):
    s = state.data

    if not s:
        return

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
                background="#24242485",
                padding=1,
                radius=(2, 2, 0, 0),
            ),
        ))

    return hstack(main_view, gap=2)


def metro_view(fs: FrameState):
    state = MetroAppStateManager().get_state(fs)
    if state.data:
        content = render_metro_info(fs, state)
    else:
        content = div(metro_paris_banner, style=DivStyle(padding=10))

    return content.tag(('metro_view', state.show))


def composer(fs: FrameState):
    state = MetroAppStateManager().get_state(fs)
    if state.show:
        return metro_view(fs)
    return

draw = draw_loop(composer, use_threads=True)

def widgets(fs: FrameState):
    return [
        Widget('di.metro.info', draw(fs), wait_time=14, style=DivStyle(
            background="#05153486",
            padding=3,
            margin=0,
            radius=3,
            border=1,
            border_color="#333435C9",
        ))
    ]

# todo: Refactor this similar to klipper using RuntimeStateManager.