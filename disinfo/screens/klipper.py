import io
import arrow
import pendulum
import requests

from functools import cache
from datetime import timedelta
from pydash import py_
from typing import Optional
from PIL import Image

from .drawer import draw_loop
from ..components.text import Text, TextStyle, text
from ..components.elements import StillImage, Frame
from ..components.layouts import vstack, hstack
from ..components.layers import div, DivStyle
from ..components.scroller import HScroller
from ..components.spriteim import SpriteIcon
from ..components.widget import Widget
from ..components.transitions import text_slide_in
from ..components import fonts
from ..config import app_config
from ..redis import rkeys, get_dict
from ..utils.func import throttle
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..data_structures import FrameState, AppBaseModel

threed_icon = SpriteIcon('assets/raster/nozzle-alt-9x9.png', step_time=0.1)
done_icon = StillImage('assets/raster/nozzle-9x9-done.png')
file_icon = StillImage('assets/raster/fileicon-5x5.png')
toolt_icon = StillImage('assets/raster/nozzle-5x5.png')
bedt_icon = StillImage('assets/raster/printerbed-5x5.png')

tail_arrow_style = TextStyle(font=fonts.scientifica__r, color='#8c5b3e')
muted_small_style = TextStyle(font=fonts.bitocra7, color='#888888')

tail_arrow_left         = text(f'⤙', style=tail_arrow_style)
tail_arrow_right        = text(f'⤚', style=tail_arrow_style)
text_percent_sign       = Text('%', style=TextStyle(font=fonts.tamzen__rs, color='#888888'))

hscroller_fname = HScroller(size=33, pause_at_loop=True)


class PrinterState(AppBaseModel):
    bed_temp: Optional[float] = None
    extruder_temp: Optional[float] = None
    progress: Optional[float] = None
    state: Optional[str] = None
    filename: Optional[str] = None
    thumbnail: Optional[str] = None

    online: bool = False
    is_definitely_online: bool = False

    eta: Optional[str] = None

    completion_time: Optional[str] = ''
    time_left: Optional[str] = ''
    source_timezone: str = 'UTC'

    is_on: bool = False
    is_visible: bool = False
    is_done: bool = False
    is_printing: bool = False

    def seconds_left(self, now: pendulum.DateTime) -> int:
        if not self.eta:
            return -1

        eta = pendulum.parse(self.eta, tz=self.source_timezone).in_tz(tz='local')
        return (eta - now).total_seconds()

class KlipperStateManager(PubSubStateManager[PrinterState]):
    model = PrinterState
    channels = ('di.pubsub.klipper',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            self.state = PrinterState(**data.payload)
            self.state.is_on = self.state.state in ('printing', 'paused', 'standby')
            self.state.is_printing = self.state.state == 'printing'
            self.state.is_done = self.state.state == 'complete'
            self.state.is_visible = self.state.state in ('printing', 'paused', 'complete') and self.state.online
            self.state.is_definitely_online = self.state.online and self.state.bed_temp != 0

            if data.payload.get('eta'):
                eta = pendulum.parse(data.payload['eta'], tz='UTC').in_tz(tz='local')
                self.state.completion_time = eta.strftime('%H:%M')

class BambuStateManager(PubSubStateManager[PrinterState]):
    model = PrinterState
    channels = ('di.pubsub.bambu',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            self.state = PrinterState(**data.payload, source_timezone='local')
            self.state.is_on = self.state.state in ('running', 'printing', 'paused', 'standby') or (2 <= self.state.progress  <= 98)
            self.state.is_printing = self.state.state == 'running'
            self.state.is_done = self.state.state == 'complete'
            self.state.is_visible = self.state.state in ('printing', 'paused', 'complete', 'running') and self.state.online
            self.state.is_definitely_online = self.state.online and self.state.bed_temp != 0

            if data.payload.get('eta'):
                eta = pendulum.parse(data.payload['eta'])
                self.state.completion_time = eta.strftime('%H:%M')

@cache
def thumbnail_image(thumb_url: str = None):
    if not thumb_url:
        return None

    try:
        r = requests.get(thumb_url)
        r.raise_for_status()
        fp = io.BytesIO(r.content)
        img = Image.open(fp)
        # Dithering helps? .quantize()
        frame = Frame(img.resize((150, 150)).quantize().resize((32, 32)).convert('RGBA'))
        return frame
    except requests.RequestException:
        return None


def time_remaining(fs: FrameState, state: PrinterState) -> Frame:
    if not state.eta:
        return None
    
    now = fs.now
    eta = pendulum.parse(state.eta, tz=state.source_timezone).in_tz(tz='local')
    d = (eta - now).total_seconds()
    days = d // (24 * 60 * 60)
    d = d - (days * (24 * 3600))
    hours = d // 3600
    d -= hours * 3600
    minutes = d // 60
    d -= minutes * 60
    seconds = int(d)

    segments = [(days, 'd'), (hours, 'h'), (minutes, 'm'), (seconds, 's')]
    segments = [(s, l) for s, l in segments if s > 0]

    return hstack([
        *[hstack([text(f'{int(s)}', muted_small_style), text(f'{l}', muted_small_style)], gap=1) for s, l in segments]
    ], gap=2).tag(('klipper.eta', eta))


def composer(fs: FrameState, state: PrinterState):
    if not state.is_visible:
        return

    if not state.is_done:
        completion_time = text_slide_in(fs, 'op.eta', f'{state.completion_time}', style=TextStyle(font=fonts.bitocra7, color='#888888'))
        time_left = text_slide_in(fs, 'op.time_left', f'{state.time_left}', muted_small_style)
    else:
        completion_time = None
        time_left = text('Done!', style=muted_small_style)


    completion_text = hstack([tail_arrow_right, time_left], gap=2, align='center')
    completion_eta = hstack([tail_arrow_left, completion_time], gap=2, align='center') if completion_time else None

    info_elem = hstack([
        threed_icon.draw(fs.tick) if state.is_printing else done_icon,
        hstack([
            text_slide_in(fs, 'op.progress', f'{state.progress:0.1f}', TextStyle(font=fonts.cozette, color='#888888')),
            text_percent_sign,
        ], gap=1, align='top'),
    ], gap=4)

    file_detail = hstack([
        file_icon,
        hscroller_fname.set_frame(text(state.filename, muted_small_style)).draw(fs.tick),
    ], gap=2)

    temp_detail = hstack([
        hstack([toolt_icon, text_slide_in(fs, 'op.toolt', f'{round(state.extruder_temp)}', muted_small_style)], gap=2),
        hstack([bedt_icon, text_slide_in(fs, 'op.bedt', f'{round(state.bed_temp)}', muted_small_style)], gap=2),
    ], gap=4)

    elements = [
        info_elem,
        # completion_text,
        file_detail,
        completion_eta,
        time_remaining(fs, state),
        temp_detail,
    ]

    return div(vstack(elements, gap=1, align='left'), style=DivStyle(padding=1))

def compose_klipper_state(fs: FrameState):
    state = KlipperStateManager().get_state(fs)
    return composer(fs, state)

def compose_bambu_state(fs: FrameState):
    state = BambuStateManager().get_state(fs)
    return composer(fs, state)

def full_screen_composer(fs: FrameState):
    state = KlipperStateManager().get_state(fs)


    if not state.is_definitely_online:
        let_s = text('let\'s', TextStyle(font=fonts.bitocra7, color='#888888'))
        verbs = [
            ' print',
            ' make ',
            'create',
            ' build',
            ' craft',
            ' forge',
            ' shape',
            'design',
            '  fab ',
        ]
        verb = verbs[int(fs.tick // 5 % len(verbs))]

        offline_info = text_slide_in(fs, 'op.offline', verb, TextStyle(font=fonts.creep, color='#888888'))
        return div(vstack([let_s, offline_info], gap=3, align='center'), style=DivStyle(padding=1, background='#00003f51'))

    info_elem = hstack([
        threed_icon.draw(fs.tick) if state.is_printing else done_icon,
        hstack([
            text_slide_in(fs, 'op.progress', f'{state.progress:0.1f}', TextStyle(font=fonts.cozette, color='#888888')),
            text_percent_sign,
        ], gap=1, align='top'),
    ], gap=4)

    file_detail = hstack([
        file_icon,
        hscroller_fname.set_frame(text(state.filename, muted_small_style)).draw(fs.tick),
    ], gap=2)

    temp_detail = hstack([
        hstack([toolt_icon, text_slide_in(fs, 'op.toolt', f'{round(state.extruder_temp)}', muted_small_style)], gap=2),
        hstack([bedt_icon, text_slide_in(fs, 'op.bedt', f'{round(state.bed_temp)}', muted_small_style)], gap=2),
    ], gap=4)

    elements = [
        info_elem,
        time_remaining(fs, state) if state.eta else None,
        file_detail if state.online else None,
        temp_detail if state.online else None,
    ]

    return div(vstack(elements, gap=1, align='left'), style=DivStyle(padding=1, background='#00103f71'))

def widget(fs: FrameState):
    klipper_frame = compose_klipper_state(fs)
    bambu_frame = compose_bambu_state(fs)

    return [
        Widget('octoprint', frame=klipper_frame, priority=15 if klipper_frame else 0, wait_time=90 if klipper_frame else 0),
        Widget('bambu', frame=bambu_frame, priority=15 if bambu_frame else 0, wait_time=90 if bambu_frame else 0),
    ]


draw = draw_loop(composer, sleepms=10)
draw_full_screen = draw_loop(full_screen_composer, sleepms=10)
