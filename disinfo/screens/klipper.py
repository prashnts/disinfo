import io
import re
import time
import pendulum
import numpy as np

from datetime import datetime

from functools import cache
from typing import Optional

from ..utils.drawer import draw_loop
from ..drat.app_states import RuntimeStateManager
from discore.text import Text, TextStyle, text
from PIL import Image
from discore.elements import StillImage, Frame
from discore.layouts import vstack, hstack, Spacer
from discore.layers import div, DivStyle
from discore.scroller import HScroller
from discore.spriteim import SpriteIcon
from discore.widget import Widget
from discore.transitions import text_slide_in
from discore.slides import Slides, SlidesStyle
from discore.progress import progress_bar, ProgressStyle
from disinfo import fonts
from ..config import app_config
from discore.data_structures import FrameState, UniqInstance
from ..data_structures import AppBaseModel
from disinfo.utils.hass import HaWS
from disinfo.utils.imops import image_from_url
from disinfo.utils.mjpeg import MJPEGStream
from disinfo.utils.moonraker import MoonrakerWS
from disinfo.utils.time import is_expired


threed_icon = SpriteIcon('assets/raster/nozzle-alt-9x9.png', step_time=0.1)
done_icon = StillImage('assets/raster/nozzle-9x9-done.png')
file_icon = StillImage('assets/raster/fileicon-5x5.png')
toolt_icon = StillImage('assets/raster/nozzle-5x5.png')
bedt_icon = StillImage('assets/raster/printerbed-5x5.png')

tail_arrow_style = TextStyle(font=fonts.scientifica__r, color='#8c5b3e')
# LEDs oversaturate and blow out light tones: muted, warm colors read as intended.
muted_small_style = TextStyle(font=fonts.bitocra7, color='#808080')
dim_small_style = TextStyle(font=fonts.bitocra7, color='#5b5e64')
bright_small_style = TextStyle(font=fonts.bitocra7, color='#a6a6a6')
warn_small_style = TextStyle(font=fonts.bitocra7, color='#b7925e')
# Three sizes: cozette for the progress, bitocra7 for values, microfont for names and labels.
tiny_style = TextStyle(font=fonts.microfont_35_reg, color='#808080')
tiny_dim_style = TextStyle(font=fonts.microfont_35_reg, color='#5b5e64')
tiny_bright_style = TextStyle(font=fonts.microfont_35_reg, color='#a6a6a6')

tail_arrow_left         = text(f'⤙', style=tail_arrow_style)
tail_arrow_right        = text(f'⤚', style=tail_arrow_style)
text_percent_sign       = Text('%', style=TextStyle(font=fonts.tamzen__rs, color='#888888'))

widget_style = DivStyle(padding=3, radius=3, background="#0455233D", border=1, border_color="#00000088")
# Content width, the card stays within 128px with the widget padding.
card_width = 80
phase_colors = {
    'printing': '#42a459', 'paused': '#b7925e', 'done': '#2d83b4', 'failed': '#c93f20', 'idle': '#5b5e64',
    'busy': '#42a459', 'active': '#8a6cc8', 'error': '#c93f20', 'starting': '#b7925e',
}
# Dark text on the phase color: unlit pixels read best on the LEDs.
pill_style = TextStyle(font=fonts.bitocra7, color='#000000')
# Seconds per slide: the camera is what's worth watching.
slide_times = {'camera': 14, 'job': 6, 'stats': 5}
focus_seconds = 45

# Raw printer statuses -> phase: offline, idle, printing, paused, done, failed.
bambu_phases = {
    'running': 'printing', 'prepare': 'printing', 'slicing': 'printing', 'init': 'printing',
    'pause': 'paused', 'finish': 'done', 'failed': 'failed', 'idle': 'idle',
}
klipper_phases = {
    'printing': 'printing', 'paused': 'paused', 'complete': 'done',
    'cancelled': 'failed', 'error': 'failed', 'standby': 'idle',
}
# Klipper outside of prints: busy runs gcode (a macro, a move), active is homed and enabled, idle has timed out.
klipper_idle_phases = {'Printing': 'busy', 'Ready': 'active', 'Idle': 'idle'}
# Shown whenever the printer is in them, not only for a while.
live_phases = ('busy', 'active', 'error', 'starting')
phase_names = {'done': 'Done', 'failed': 'Failed', 'idle': 'Idle', 'busy': 'Busy', 'active': 'Ready', 'error': 'Error', 'starting': 'Start'}
# Done/failed cards stay this long after the printer stopped.
recent_minutes = 30

class PrinterState(AppBaseModel):
    printer_id: str

    bed_temp: Optional[float] = None
    extruder_temp: Optional[float] = None
    progress: Optional[float] = None
    state: Optional[str] = None
    current_stage: Optional[str] = None
    current_layer: Optional[int] = None
    total_layers: Optional[int] = None
    bed_target: Optional[float] = None
    extruder_target: Optional[float] = None
    active_tray: Optional[str] = None
    tray_color: Optional[str] = None
    chamber_temp: Optional[float] = None
    weight: Optional[float] = None
    objects: Optional[int] = None
    started_at: Optional[str] = None
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

    phase: str = 'offline'
    phase_at: Optional[datetime] = None
    stream_url: Optional[str] = None

    is_on: bool = False
    is_visible: bool = False
    is_done: bool = False
    is_printing: bool = False

    model: str = 'bambu'
    message: Optional[str] = None
    position: Optional[tuple[float, float, float]] = None

    _id: str = 'klipper'

    def seconds_left(self, now: pendulum.DateTime) -> int:
        if not self.eta:
            return -1

        eta = pendulum.parse(self.eta, tz=self.source_timezone).in_tz(tz='local')
        return (eta - now).total_seconds()

    def set_phase(self, phase: str, changed_at):
        self.phase = phase
        self.phase_at = pendulum.instance(changed_at).in_tz('local') if changed_at else None
        self.is_on = phase != 'offline'
        self.is_printing = phase in ('printing', 'paused')
        self.is_done = phase == 'done'
        recent = not is_expired(changed_at, minutes=recent_minutes, expired_if_none=True)
        self.is_visible = self.is_printing or phase in live_phases or (phase in ('done', 'failed') and recent)
        return self


def get_moonraker_state(printer_id: str, url: Optional[str] = None, api_key: Optional[str] = None):
    cam = HaWS().get_entity(f'camera.{printer_id}_toolcam')
    cachebuster = int(time.time() // 7)
    ignored_states = ['unknown', 'unavailable']
    thumburl = (app_config.ha_base_url + cam.attributes.get('entity_picture', '') + f'&t={cachebuster}') if cam else None
    get_sensor = lambda sensor: x.state if (x := HaWS().get_entity(f'sensor.{printer_id}_{sensor}')) and x.state not in ignored_states else None

    state = PrinterState(
        printer_id=printer_id,
        bed_temp=float(get_sensor('bed_temperature') or '-42'),
        extruder_temp=float(get_sensor('nozzle_temperature') or '-42'),
        progress=int(float(get_sensor('progress') or '0')),
        state=get_sensor('current_print_state'),
        filename=get_sensor('filename'),
        thumbnail=thumburl,
        online=True,
        completion_time=pendulum.parse(x).in_tz('local').strftime('%H:%M') if (x := get_sensor('print_eta')) else None,
        current_layer=int(float(x)) if (x := get_sensor('current_layer')) else None,
        total_layers=int(float(x)) if (x := get_sensor('total_layer')) else None,
        time_left=get_sensor('print_time_left'),
        eta=get_sensor('print_eta'),
        printer_name=printer_id,
    )
    state.model = 'klipper'
    state.message = get_sensor('current_display_message') or get_sensor('current_print_message')
    pos = [get_sensor(f'toolhead_position_{a}') for a in 'xyz']
    state.position = tuple(float(v) for v in pos) if all(pos) else None

    entity = lambda sensor: HaWS().get_entity(f'sensor.{printer_id}_{sensor}')
    printer_state, idle = get_sensor('printer_state'), get_sensor('idle_timeout_state')
    changed_at = lambda sensor: x.last_changed if (x := entity(sensor)) else None

    # Moonraker's websocket when it's up: pushed within ~250ms, HA polls it every few seconds.
    mr = MoonrakerWS(url, api_key) if url else None
    if mr and mr.live:
        printer_state = mr.get('webhooks', 'state') if mr.klippy else 'startup'
        idle = mr.get('idle_timeout', 'state')
        state.state = mr.get('print_stats', 'state')
        state.filename = mr.get('print_stats', 'filename') or None
        state.message = mr.get('display_status', 'message') or mr.get('print_stats', 'message') or None
        state.position = tuple(mr.get('toolhead', 'position', [0, 0, 0])[:3])
        progress, duration = mr.get('virtual_sdcard', 'progress') or 0, mr.get('print_stats', 'print_duration') or 0
        state.progress = int(progress * 100)
        # Like Fluidd's file estimate: the time so far, scaled by the progress.
        eta = pendulum.now('UTC').add(seconds=duration / progress - duration) if state.state in klipper_phases and progress > 0.01 else None
        state.eta = eta.isoformat() if eta else None
        state.completion_time = eta.in_tz('local').strftime('%H:%M') if eta else None
        fields = {'printer_state': ('webhooks', 'state'), 'idle_timeout_state': ('idle_timeout', 'state'), 'current_print_state': ('print_stats', 'state')}
        changed_at = lambda sensor, ha=changed_at: mr.changed_at.get(fields[sensor]) or ha(sensor)

    print_phase = klipper_phases.get(state.state, 'idle')
    if printer_state is None:
        phase, by = 'offline', None
    elif printer_state in ('shutdown', 'error'):
        phase, by = 'error', 'printer_state'
        state.message = (mr.get('webhooks', 'state_message') if mr and mr.live else get_sensor('printer_message')) or state.message
    elif printer_state == 'startup':
        phase, by = 'starting', 'printer_state'
    elif print_phase in ('printing', 'paused'):
        phase, by = print_phase, 'current_print_state'
    elif klipper_idle_phases.get(idle, 'idle') != 'idle':
        phase, by = klipper_idle_phases[idle], 'idle_timeout_state'
    else:
        phase, by = print_phase, 'current_print_state'
    return state.set_phase(phase, changed_at(by) if by else None)

def get_bambulab_state(printer_id: str):
    cam = HaWS().get_entity(f'camera.{printer_id}_camera')
    cover = HaWS().get_entity(f'image.{printer_id}_cover_image')
    pick_img = HaWS().get_entity(f'image.{printer_id}_pick_image')
    cachebuster = int(time.time() // 6)
    thumburl = (app_config.ha_base_url + cam.attributes.get('entity_picture', '') + f'&t={cachebuster}') if cam else None
    coverurl = (app_config.ha_base_url + cover.attributes.get('entity_picture', '') + f'&t={cachebuster}') if cover else None
    pickurl = (app_config.ha_base_url + pick_img.attributes.get('entity_picture', '') + f'&t={cachebuster}') if pick_img else None
    ignored_states = ['unknown', 'unavailable']
    get_sensor = lambda sensor: x.state if (x := HaWS().get_entity(f'sensor.{printer_id}_{sensor}')) and x.state not in ignored_states else None

    state = PrinterState(
        printer_id=printer_id,
        bed_temp=float(get_sensor('bed_temperature') or '-42'),
        extruder_temp=float(get_sensor('nozzle_temperature') or '-42'),
        progress=int(get_sensor('print_progress') or '0'),
        state=get_sensor('print_status'),
        filename=get_sensor('task_name'),
        thumbnail=thumburl,
        online=True,
        completion_time=pendulum.parse(x).in_tz('local').strftime('%H:%M') if (x := get_sensor('end_time')) else None,
        current_layer=int(x) if (x := get_sensor('current_layer')) else None,
        total_layers=int(x) if (x := get_sensor('total_layer_count')) else None,
        bed_target=float(x) if (x := get_sensor('bed_target_temperature')) else None,
        extruder_target=float(x) if (x := get_sensor('nozzle_target_temperature')) else None,
        active_tray=get_sensor('active_tray'),
        tray_color=(x.attributes or {}).get('color') if (x := HaWS().get_entity(f'sensor.{printer_id}_active_tray')) else None,
        chamber_temp=float(x) if (x := get_sensor('chamber_temperature')) else None,
        weight=float(x) if (x := get_sensor('print_weight')) else None,
        objects=int(x) if (x := get_sensor('printable_objects')) else None,
        started_at=pendulum.parse(x).in_tz('local').strftime('%H:%M') if (x := get_sensor('start_time')) else None,
        time_left=get_sensor('remaining_time'),
        eta=get_sensor('end_time'),
        printer_name=get_sensor('printer_name'),
        cover_image=coverurl,
        pick_image=pickurl,
        current_stage=get_sensor('current_stage'),
    )
    status = HaWS().get_entity(f'sensor.{printer_id}_print_status')
    return state.set_phase(bambu_phases.get(state.state, 'offline'), status.last_changed if status else None)

def get_state(fs: FrameState):
    printers = []
    for printer in fs.config.printer_ids:
        model, printer_id = printer.split(':')
        if model == 'bambu':
            state = get_bambulab_state(printer_id)
        elif model == 'klipper':
            key = fs.config.moonraker_api_key
            state = get_moonraker_state(printer_id, fs.config.moonraker_urls.get(printer_id), key.get_secret_value() if key else None)
        else:
            continue
        state.stream_url = fs.config.printer_streams.get(printer_id)
        state.model = model
        printers.append(state)
    return printers


def time_remaining(fs: FrameState, state: PrinterState) -> Frame:
    # Two largest units. Past the eta it counts up as overdue instead of wrapping around.
    if not state.eta:
        return None
    eta = pendulum.parse(state.eta, tz=state.source_timezone).in_tz(tz='local')
    d = int((eta - fs.now).total_seconds())
    overdue = d < 0
    d = abs(d)
    segments = [(d // 86400, 'd'), (d % 86400 // 3600, 'h'), (d % 3600 // 60, 'm'), (d % 60, 's')]
    while len(segments) > 1 and segments[0][0] == 0:
        segments.pop(0)
    style = warn_small_style if overdue else bright_small_style

    return hstack([
        text('+', style) if overdue else None,
        *[hstack([text_slide_in(fs, f'{s}', style, name=f'kl.tr.{state.printer_id}.{l}'), text(l, muted_small_style)], gap=1) for s, l in segments[:2]],
    ], gap=2).tag(('klipper.eta', eta, overdue))


def temp(fs: FrameState, icon: Frame, value: float, target: Optional[float], name: str) -> Frame:
    if value is None or value < 0:
        return None
    heating = target and value < target - 3
    return hstack([icon, text_slide_in(fs, f'{round(value)}', warn_small_style if heating else muted_small_style, name=name)], gap=2)

def stage_text(state: PrinterState) -> str:
    if state.phase == 'paused':
        return 'Paused'
    if state.current_stage and state.current_stage not in ('printing', 'idle'):
        return state.current_stage.replace('_', ' ').capitalize()[:18]
    if state.total_layers:
        return f'L{state.current_layer or 0}/{state.total_layers}'
    return (state.state or '').capitalize()

def parts_of(filename: Optional[str]) -> list[tuple[str, int]]:
    # Bambu names a plate 'A + B (1) + A + C...', HA cuts it with '...'. -> [(A, 2), (B, 1), (C, 1)]
    counts = {}
    for p in (filename or '').split(' + '):
        cut = p.endswith('...')
        p = re.sub(r'\s*\(\d+\)$', '', p.removesuffix('...').strip())
        p = re.sub(r'\.(gcode|3mf|stl|step)$', '', p, flags=re.I).replace('_', ' ').strip()
        if cut:
            p = next((k for k in counts if k.startswith(p)), p + '..')
        if p:
            counts[p] = counts.get(p, 0) + 1
    return list(counts.items())

def title_of(state: PrinterState) -> str:
    parts = parts_of(state.filename)
    if not parts:
        return ''
    n = max(state.objects or 0, sum(c for _, c in parts))
    return parts[0][0] + (f' +{n - parts[0][1]}' if n > parts[0][1] else '')

def ago(fs: FrameState, at: Optional[datetime]) -> str:
    if not at:
        return ''
    m = int((fs.now - at).total_seconds() // 60)
    return f'{m}m' if m < 60 else f'{m // 60}h {m % 60}m' if m < 600 else f'{m // 60}h'

def cover(state: PrinterState, size: int) -> Optional[Frame]:
    # The plate render, cropped to the parts.
    if not state.cover_image:
        return None
    img = image_from_url(state.cover_image, resize=(128, 128), ratio_fn=min).image
    box = img.getbbox()
    if not box:
        return None
    # Bambu's saturated blue glares on the LEDs.
    return Frame(img.crop(box), ('klipper.cover', state.printer_id, box)).resize((size, size), ratio_fn=min).color_(0.6).brightness(0.8)


class ObjectFinder(metaclass=UniqInstance):
    '''Where the prints are in the camera: pixels of the filament color.

    Looks at a 1/8 scale decode every few seconds, the box eases towards it.
    Grey, white or black filament can't be told from the bed, so it gives up on those.
    '''
    every = 2

    def __init__(self, printer_id: str):
        self.box = None
        self.at = 0

    def find(self, jpeg: bytes, color: Optional[str]):
        r, g, b = Image.new('RGB', (1, 1), (color or '#000000')[:7]).getpixel((0, 0))
        th, ts, _ = Image.new('RGB', (1, 1), (r, g, b)).convert('HSV').getpixel((0, 0))
        if ts < 80:
            return None
        img = Image.open(io.BytesIO(jpeg))
        img.draft('RGB', (img.width // 8, img.height // 8))
        hsv = np.asarray(img.convert('HSV'), dtype=np.int16)
        dh = np.abs(hsv[..., 0] - th)
        mask = (np.minimum(dh, 256 - dh) < 12) & (hsv[..., 1] > 80) & (hsv[..., 2] > 50)
        mask &= np.roll(mask, 1, 0) & np.roll(mask, 1, 1)   # drops lone pixels
        ys, xs = np.nonzero(mask)
        if len(xs) < 6:
            return None
        h, w = mask.shape
        x0, x1 = np.percentile(xs, [2, 98]) / w
        y0, y1 = np.percentile(ys, [2, 98]) / h
        return x0, y0, x1 + 1 / w, y1 + 1 / h

    def crop(self, stream: MJPEGStream, color: Optional[str], aspect: float):
        # aspect: of the slide, in pixels. The camera is 16:9.
        now = time.monotonic()
        if stream.jpeg and now - self.at > self.every:
            self.at = now
            target = self.find(stream.jpeg, color)
            target = fit_box(target, aspect) if target else fit_box((0, 0, 1, 1), aspect)
            self.box = target if not self.box else tuple(a + (b - a) * 0.4 for a, b in zip(self.box, target))
        return tuple(round(v, 3) for v in self.box) if self.box else None

def fit_box(box, aspect: float, margin: float = 0.06, min_w: float = 0.3, src: float = 16 / 9):
    # Grows the box to the slide aspect with some margin, keeps it within the frame.
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w = max(x1 - x0 + 2 * margin, min_w)
    h = max(y1 - y0 + 2 * margin * src, w * src / aspect)
    w = h * aspect / src
    if w > 1:
        w, h = 1, src / aspect
    if h > 1:
        h, w = 1, aspect / src
    cx = min(max(cx, w / 2), 1 - w / 2)
    cy = min(max(cy, h / 2), 1 - h / 2)
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def job_slide(fs: FrameState, state: PrinterState, h: int) -> Frame:
    # What is printing: the parts, the plate render in the corner.
    parts = parts_of(state.filename)
    n = max(state.objects or 0, sum(c for _, c in parts))
    lines = [text(f'{n} objects' if n > 1 else 'Job', muted_small_style)]
    for name, count in parts[:(h - 7) // 7]:
        lines.append(hstack([text(f'{count}x', tiny_dim_style) if count > 1 else None, text(name, tiny_bright_style, overflow='fit')], gap=2))
    return hstack([vstack(lines, gap=2), cover(state, 24)], gap=3, align='top')

def stats_slide(fs: FrameState, state: PrinterState, h: int) -> Frame:
    uname = lambda x: f'{x}_{state.printer_id}'
    stage = stage_text(state)
    layer = f'L{state.current_layer or 0}/{state.total_layers}' if state.total_layers else None
    layer = text(layer, muted_small_style) if layer and layer != stage else None
    stage_style = TextStyle(font=fonts.microfont_35_reg, color=phase_colors.get(state.phase, '#5b5e64'), overflow='fit')
    return vstack([
        hstack([
            temp(fs, toolt_icon, state.extruder_temp, state.extruder_target, uname('toolt')),
            temp(fs, bedt_icon, state.bed_temp, state.bed_target, uname('bedt')),
            hstack([text('ch', tiny_dim_style), text(f'{round(state.chamber_temp)}', muted_small_style)], gap=2) if state.chamber_temp else None,
        ], gap=5),
        hstack([text(stage, stage_style), Spacer(), layer], gap=3),
        hstack([text(state.active_tray, tiny_style, overflow='fit') if state.active_tray else None, Spacer(), text(f'{state.weight:g}g', tiny_style) if state.weight else None], gap=3),
        hstack([
            text(state.started_at, tiny_style) if state.started_at else None,
            Spacer(),
            hstack([tail_arrow_left, text(state.completion_time, muted_small_style)], gap=2) if state.completion_time else None,
        ], gap=3),
    ], gap=3)

def camera_slide(fs: FrameState, state: PrinterState, view: Frame) -> Frame:
    # The stage sits on a scrim over the bottom of the camera.
    color = phase_colors.get(state.phase, '#5b5e64')
    eta = text(state.completion_time, muted_small_style) if state.completion_time else None
    info = hstack([text(stage_text(state), TextStyle(font=fonts.microfont_35_reg, color=color, overflow='fit')), Spacer(), eta], gap=3)
    scrim = div(info, padding=(1, 2, 1, 2), background='#000000a0')
    return div(scrim, width=view.width, height=view.height, anchor='bl', background_frame=view)


def limn_body(fs: FrameState, state: PrinterState, h: int) -> Frame:
    # A plotter: no layers or heaters. Small square camera, what it's doing next to it.
    view = MJPEGStream(state.stream_url).read(h, h) if state.stream_url else None
    # (item, lines it can take), kept while they fit in h.
    wrapped = lambda value, style, n: (text(value, style, overflow='wrap', max_lines=n, spacing=2), n)
    if state.is_printing:
        lines = [
            wrapped(title_of(state), tiny_bright_style, 2),
            (text(state.message, tiny_style, overflow='fit'), 1) if state.message else None,
            (hstack([tail_arrow_left, text(state.completion_time, muted_small_style)], gap=2), 1) if state.completion_time else None,
        ]
    else:
        lines = [wrapped(state.message, tiny_bright_style, 3) if state.message else None]
    if state.position:
        x, y, z = state.position
        lines += [(text(f'X{x:.0f} Y{y:.0f}', tiny_style), 1), (text(f'Z{z:.1f}', tiny_style), 1)]
    kept, budget = [], (h + 2) // 7
    for item, n in filter(None, lines):
        if n > budget:
            break
        kept.append(item)
        budget -= n
    return hstack([vstack(kept, gap=2), div(view, radius=2) if view else None], gap=3, align='top')

def composer(fs: FrameState, state: PrinterState):
    # show_printers expands every online printer, otherwise only the ones printing.
    expanded = state.is_printing or state.phase in live_phases or (state.is_on and RuntimeStateManager().get_state(fs).show_printers)
    if not (state.is_visible or expanded):
        return
    uname = lambda x: f'{x}_{state.printer_id}'
    color = phase_colors.get(state.phase, '#5b5e64')
    name = text((state.printer_name or state.printer_id).split('-')[0].removeprefix('pi_')[:10], tiny_dim_style)

    if state.is_printing:
        headline = hstack([
            text_slide_in(fs, f'{int(state.progress)}', TextStyle(font=fonts.cozette, color='#a6a6a6'), name=uname('progress')),
            text_percent_sign,
        ], gap=1, align='top')
        right = vstack([name, time_remaining(fs, state)], gap=2, align='right')
    else:
        headline = div(text(phase_names.get(state.phase, ''), pill_style), padding=(1, 2, 1, 2), radius=2, background=color)
        # Done or failed for how long, in other phases since when.
        since = ago(fs, state.phase_at)
        right = hstack([
            name,
            text(since, muted_small_style) if since else None,
            text('ago', tiny_dim_style) if since and state.phase in ('done', 'failed') else None,
        ], gap=2, align='bottom')

    head = hstack([hstack([threed_icon.draw(fs.tick) if state.is_printing else done_icon, headline], gap=3), Spacer(), right], gap=2)
    bar = progress_bar(1 if state.is_done else (state.progress or 0) / 100, ProgressStyle(width=card_width, color=color)) if state.is_printing or state.phase in ('done', 'failed') else None

    # The card's width, its rows lay out in it. The tag changes when the card expands, so the widget animates the resize.
    card = lambda *rows: div(vstack([head, bar, *rows], gap=3), width=card_width).tag(('printer_card', state.printer_id, expanded))
    if not expanded:
        return card(text(title_of(state), tiny_style, overflow='fit'))

    h = 40 if fs.config.height < 160 else 48
    if state.model == 'klipper':
        return card(limn_body(fs, state, h - 4))

    # Slides below the progress: camera, the job, details.
    # Live stream when configured (nothing while it connects), cropped to the prints. The camera snapshot otherwise.
    # The snapshot fetch blocks, so it's never used as a stream fallback.
    if state.stream_url:
        stream = MJPEGStream(state.stream_url)
        # Zoomed on the prints while printing, the whole bed otherwise.
        box = ObjectFinder(state.printer_id).crop(stream, state.tray_color, card_width / h) if state.is_printing else fit_box((0, 0, 1, 1), card_width / h)
        view = stream.read(card_width, h, box)
    else:
        view = image_from_url(state.thumbnail, resize=(card_width, card_width * 9 // 16), ratio_fn=min)
        view = view.crop_even(vertical=max(view.height - h, 0) // 2) if view else None
    body = Slides(uname('klipper.slides'), SlidesStyle(width=card_width, height=h, radius=2)).mut([
        (lambda: camera_slide(fs, state, view), slide_times['camera']) if view else None,
        (lambda: job_slide(fs, state, h), slide_times['job']),
        (lambda: stats_slide(fs, state, h), slide_times['stats']),
    ]).draw(fs)
    return card(body)


@cache
def get_draw_loops(n: int):
    loops = []
    for i in range(n):
        loop = draw_loop(composer, sleepms=100, use_threads=True)
        loops.append(loop)
    return loops

def wants_focus(fs: FrameState, state: PrinterState) -> bool:
    # The stack jumps to the card when the print starts, pauses, finishes or fails, and for its last minutes.
    changed = state.phase_at and (fs.now - state.phase_at).total_seconds() < focus_seconds
    ending = state.is_printing and 0 < state.seconds_left(fs.now) < focus_seconds * 4
    return bool(state.is_visible and (changed or ending))

def widget(fs: FrameState):
    printers = get_state(fs)
    loops = get_draw_loops(len(printers))
    widgets = []
    for i, state in enumerate(printers):
        if not state.is_on:
            continue
        w = Widget(
            f'printer_{state.printer_id}',
            frame=loops[i](fs, state),
            style=widget_style,
            priority=2 if state.is_printing else 1,
            focus=wants_focus(fs, state),
            wait_time=sum(slide_times.values()) if state.is_printing else 5)
        widgets.append(w)
    return widgets
