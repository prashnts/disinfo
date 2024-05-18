import os
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


class KlipperState(AppBaseModel):
    bed_temp: Optional[float] = None
    extruder_temp: Optional[float] = None
    progress: Optional[float] = None
    state: Optional[str] = None
    filename: Optional[str] = None
    thumbnail: Optional[str] = None

    eta: Optional[str] = None

    completion_time: Optional[str] = ''
    time_left: Optional[str] = ''

    is_on: bool = False
    is_visible: bool = False
    is_done: bool = False
    is_printing: bool = False


class KlipperStateManager(PubSubStateManager[KlipperState]):
    model = KlipperState
    channels = ('di.pubsub.klipper',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            self.state = KlipperState(**data.payload)
            self.state.is_on = self.state.state in ('printing', 'paused', 'standby')
            self.state.is_printing = self.state.state == 'printing'
            self.state.is_done = self.state.state == 'complete'
            self.state.is_visible = self.state.state in ('printing', 'paused', 'standby', 'complete')

            if data.payload.get('eta'):
                self.state.completion_time = pendulum.parse(data.payload['eta'], tz='UTC').in_tz(tz='local').strftime('%H:%M')

@cache
def thumbnail_image(filename: str = None):
    if not filename:
        return None
    size = (300, 300)
    thumb_url = f"http://{app_config.klipper_host}/server/files/gcodes/.thumbs/{os.path.splitext(filename)[0]}-{size[0]}x{size[1]}.png"

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

@throttle(1061)
def get_state(fs: FrameState):
    try:
        print_state = get_dict(rkeys['octoprint_printing'])
        tool_temp = get_dict(rkeys['octoprint_toolt'])
        bed_temp = get_dict(rkeys['octoprint_bedt'])

        time_left = print_state['progress']['printTimeLeft']
        progress = print_state['progress']['completion'] or -1
        flags = print_state['state']['flags']
        last_update = arrow.get(print_state['_timestamp'], tzinfo='local')
    except KeyError:
        return None

    is_printing = flags['printing']
    is_on = flags['operational'] or is_printing
    is_done = is_on and progress == 100

    now = arrow.now()

    is_visible = (is_on or is_done) and (last_update + timedelta(minutes=45)) > now

    completion_time = now.shift(seconds=time_left).strftime('%H:%M') if time_left else 'Idle'

    try:
        filename = print_state['job']['file']['display'] or ''
    except (KeyError, TypeError):
        filename = 'No file selected'

    filename = py_.human_case(filename.replace('.aw', '').replace('.gcode', ''))

    # day_delta = completion_time.timetuple().tm_mday - now.timetuple().tm_mday
    # if day_delta:
        # completion_str = f'+{day_delta} {completion_str}'

    time_left = print_state['progress']['printTimeLeftFormatted'] or '--:--'

    return dict(
        is_on=is_on,
        is_visible=is_visible,
        is_done=is_done,
        is_printing=is_printing,
        progress=progress,
        time_left=time_left,
        completion_time=completion_time,
        file_name=filename,
        toolt_current=tool_temp['actual'],
        toolt_target=tool_temp['target'],
        bedt_current=bed_temp['actual'],
        bedt_target=bed_temp['target'],
    )

def composer(fs: FrameState):
    state = KlipperStateManager().get_state(fs)

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
        temp_detail,
    ]

    return div(vstack(elements, gap=1, align='left'), style=DivStyle(padding=1))

def full_screen_composer(fs: FrameState):
    state = KlipperStateManager().get_state(fs)


    if not state.is_visible:
        return

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
        file_detail,
        temp_detail,
    ]

    return div(vstack(elements, gap=1, align='left'), style=DivStyle(padding=1, background='#00003f31'))

def widget(fs: FrameState):
    frame = composer(fs)
    return Widget('octoprint', frame=frame, priority=15 if frame else 0, wait_time=90 if frame else 0)


draw = draw_loop(composer, sleepms=10)
draw_full_screen = draw_loop(full_screen_composer, sleepms=10)
