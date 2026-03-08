import io
import time
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
from disinfo.utils.hass import HaWS
from disinfo.screens import stream
from disinfo.utils.imops import image_from_url

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
    current_stage: Optional[str] = None
    filename: Optional[str] = None
    thumbnail: Optional[str] = None
    cover_image: Optional[str] = None
    pick_image: Optional[str] = None

    online: bool = False
    is_definitely_online: bool = False
    printer_name: str | None = None

    eta: Optional[str] = None

    completion_time: Optional[str] = ''
    time_left: Optional[str] = ''
    source_timezone: str = 'local'

    is_on: bool = False
    is_visible: bool = False
    is_done: bool = False
    is_printing: bool = False

    _id: str = 'klipper'

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


def get_moonraker_state():
    ...

def get_bambulab_state(printer_id: str):
    cam = HaWS().get_entity(f'camera.{printer_id}_camera')
    cover = HaWS().get_entity(f'image.{printer_id}_cover_image')
    pick_img = HaWS().get_entity(f'image.{printer_id}_pick_image')
    cachebuster = int(time.time()) # change every minute
    thumburl = (app_config.ha_base_url + cam.attributes.get('entity_picture', '') + f'&t={cachebuster}') if cam else None
    coverurl = (app_config.ha_base_url + cover.attributes.get('entity_picture', '') + f'&t={cachebuster}') if cover else None
    pickurl = (app_config.ha_base_url + pick_img.attributes.get('entity_picture', '') + f'&t={cachebuster}') if pick_img else None
    get_sensor = lambda sensor: x.state if (x := HaWS().get_entity(f'sensor.{printer_id}_{sensor}')) and x.state != 'unavailable' else None

    state = PrinterState(
        bed_temp=float(get_sensor('bed_temperature') or '-42'),
        extruder_temp=float(get_sensor('nozzle_temperature') or '-42'),
        progress=int(get_sensor('print_progress') or '0'),
        state=get_sensor('print_status'),
        filename=get_sensor('task_name'),
        thumbnail=thumburl,
        online=True,
        is_on=get_sensor('print_status') not in ('offline', 'unknown'),
        is_printing=get_sensor('print_status') in ('printing', 'pause', 'running'),
        is_done=get_sensor('print_status') == 'finish',
        completion_time=pendulum.parse(x).strftime('%H:%M') if (x := get_sensor('end_time')) else None,
        time_left=get_sensor('remaining_time'),
        eta=get_sensor('end_time'),
        printer_name=get_sensor('printer_name'),
        cover_image=coverurl,
        pick_image=pickurl,
        current_stage=get_sensor('current_stage'),
    )
    state.is_visible=get_sensor('print_status') not in ('offline', 'unknown') and state.state is not None,
    return state

def get_state():
    printers = []
    for printer in app_config.printer_ids:
        model, printer_id = printer.split(':')
        if model == 'bambu':
            printers.append(get_bambulab_state(printer_id))
        elif model == 'moonraker':
            printers.append(get_moonraker_state())
    return printers


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
        *[hstack([text_slide_in(fs, f'{int(s)}', muted_small_style, name=f'kl.tr.{state._id}.{l}'), text(f'{l}', muted_small_style)], gap=1) for s, l in segments]
    ], gap=2).tag(('klipper.eta', eta))


def composer(fs: FrameState, state: PrinterState):
    if not state.is_visible:
        return

    if not state.is_done:
        completion_time = text_slide_in(fs, f'{state.completion_time}', style=TextStyle(font=fonts.bitocra7, color='#888888'), name='op.eta')
        time_left = text_slide_in(fs, f'{state.time_left}', muted_small_style, name='op.time_left')
    else:
        completion_time = None
        time_left = text('Done!', style=muted_small_style)


    completion_text = hstack([tail_arrow_right, time_left], gap=2, align='center')
    completion_eta = hstack([tail_arrow_left, completion_time], gap=2, align='center') if completion_time else None

    info_elem = hstack([
        threed_icon.draw(fs.tick) if state.is_printing else done_icon,
        hstack([
            text_slide_in(fs, f'{int(state.progress)}', TextStyle(font=fonts.cozette, color='#888888'), name='op.progress'),
            text_percent_sign,
        ], gap=1, align='top'),
    ], gap=4)

    file_detail = hstack([
        file_icon,
        hscroller_fname.set_frame(text(state.filename, muted_small_style)).draw(fs.tick),
    ], gap=2)

    temp_detail = hstack([
        hstack([toolt_icon, text_slide_in(fs, f'{round(state.extruder_temp)}', muted_small_style, name='op.toolt')], gap=2),
        hstack([bedt_icon, text_slide_in(fs, f'{round(state.bed_temp)}', muted_small_style, name='op.bedt')], gap=2),
    ], gap=4)
    printer_name = text(state.printer_name or '', TextStyle(font=fonts.bitocra7, color='#888888'))

    elements = [
        file_detail,
        text(state.state),
        text(state.current_stage),
    ]
    bg = div(image_from_url(state.thumbnail, resize=(120, 90)), radius=3).tag(('klipper.thumb', state.printer_name))
    covimg = div(image_from_url(state.cover_image, resize=(42, 42)).crop_even(5, 10), radius=3, background="#cccccc3f").tag(('klipper.coverimg', state.printer_name))
    pickimg = div(image_from_url(state.pick_image, resize=(42, 42)).crop_even(5, 10), radius=3, background="#cccccc3f").tag(('klipper.pickimg', state.printer_name))

    card = div(
        vstack([covimg, vstack(elements, gap=1, align='left')], align='left', gap=4),
        width=95,
        padding=(10, 0, 2, 2),
        margin=0,
        radius=3,
        background_frame=bg)
    
    top_info = hstack([
        vstack([info_elem, time_remaining(fs, state)], gap=4, align='left'),
        vstack([printer_name, temp_detail, completion_eta], gap=2, align='left'),
    ], gap=6, align='bottom')

    return vstack([top_info, card], gap=4)

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

        offline_info = text_slide_in(fs, verb, TextStyle(font=fonts.creep, color='#888888'), name='op.offline')
        return div(vstack([let_s, offline_info], gap=3, align='center'), style=DivStyle(padding=1, background='#00003f51'))

    info_elem = hstack([
        threed_icon.draw(fs.tick) if state.is_printing else done_icon,
        hstack([
            text_slide_in(fs, f'{state.progress:0.1f}', TextStyle(font=fonts.cozette, color='#888888'), name='op.progress'),
            text_percent_sign,
        ], gap=1, align='top'),
    ], gap=4)

    file_detail = hstack([
        file_icon,
        hscroller_fname.set_frame(text(state.filename, muted_small_style)).draw(fs.tick),
    ], gap=2)

    temp_detail = hstack([
        hstack([toolt_icon, text_slide_in(fs, f'{round(state.extruder_temp)}', muted_small_style, name='op.toolt')], gap=2),
        hstack([bedt_icon, text_slide_in(fs, f'{round(state.bed_temp)}', muted_small_style, name='op.bedt')], gap=2),
    ], gap=4)

    elements = [
        info_elem,
        time_remaining(fs, state) if state.eta else None,
        file_detail if state.online else None,
        temp_detail if state.online else None,
    ]

    return div(vstack(elements, gap=1, align='left'), style=DivStyle(padding=1, background='#00103f71'))

widget_style = DivStyle(padding=3, radius=3, background="#0455233D", border=1, border_color="#00000088")

draw = draw_loop(composer, use_threads=True)

def widget(fs: FrameState):
    printers = get_state()
    widgets = []
    for i, state in enumerate(printers):
        if not state.is_visible:
            continue
        widget = Widget(f'printer_{i}', frame=draw(fs, state), style=widget_style, wait_time=15)
        widgets.append(widget)
    return widgets

draw_full_screen = draw_loop(full_screen_composer, sleepms=10)
