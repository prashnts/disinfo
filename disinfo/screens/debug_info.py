from PIL import Image
from matplotlib import cm
import numpy as np

from functools import cache
from .drawer import draw_loop
from ..components.text import text, TextStyle
from ..components.layouts import vstack, composite_at, hstack
from ..components.fonts import register as font_register, small_bars
from ..components.scroller import VScroller
from ..components.layers import div, DivStyle
from ..utils.func import throttle
from ..data_structures import FrameState
from ..drat.app_states import RemoteStateManager
from disinfo.components.widget import Widget
from disinfo.components import fonts
from disinfo.web.telemetry import TelemetryStateManager, act
from disinfo.components.elements import Frame


sample_vscroll = VScroller(size=98, pause_at_loop=True, pause_duration=2.5, pause_offset=18, speed=0.001, delta=3, scrollbar=True)

@cache
def font_demo():
    sample = """\
10/20/2023 à 12:34
Le café.
A quick brown fox jumps over the lazy dog.
-> [ ] { } < > # $ % 
"""

    samples = []
    spacing = 10
    pauses = [2]
    _p = 0
    font_bg = DivStyle(border=1, border_color='#444444', background="#DDD1AE6A", padding=3, radius=2)

    for fname, font in reversed(font_register.items()):
        license =  div(
            text(font.license, style=TextStyle(font=small_bars, color="#021f19cc")),
            style=DivStyle(
                background='#ffffff77',
                padding=2,
                radius=2
            ))
        demo = vstack([
            text(fname, style=TextStyle(width=100, font=fonts.spleen__s, color="#E1781D9B"), multiline=True),
            div(text(sample, style=TextStyle(font=font, width=100, color="#E5E5E5"), multiline=True), style=font_bg),
            license,
        ], gap=2)
        _p += demo.height + spacing
        pauses.append(_p)
        samples.append(demo)

    
    return vstack(samples, gap=spacing, align='left'), False, pauses

def get_palette(name):
    cmap = cm.get_cmap(name, 256)

    try:
        colors = cmap.colors
    except AttributeError:
        colors = np.array([cmap(i) for i in range(256)], dtype=float)

    arr = np.array(colors * 255).astype('uint8')
    arr = arr.reshape((16, 16, 4))
    arr = arr[:, :, 0:3]
    return arr.tobytes()

_plasma = get_palette('plasma')
_viridis = get_palette('viridis')
_inferno = get_palette('inferno')
_twilight = get_palette('twilight')
_brbg = get_palette('BrBG')


def tof_info(fs: FrameState):
    telem = TelemetryStateManager().get_state(fs)

    dmm = np.flipud(np.array(telem.tof.distance_mm).reshape((8, 8))).astype('float64')
    mind = dmm.min()
    maxd = dmm.max()
    dmm -= mind

    dmm *= (255.0 / (maxd - mind))
    dmm = np.clip(dmm, 0, 255).astype(np.uint8)

    def _make_img(pallette, size, resample):
        img = Image.frombytes("P", (8, 8), dmm.tobytes())
        img.putpalette(pallette)
        img = img.convert('RGBA')
        img = img.resize((size, size), resample)
        frame = Frame(img, hash=('tof_info', f'v1_{size}_{resample}')).rotate(180)
        return div(frame, style=DivStyle(border=1, border_color='#111111', radius=2))

    img2 = _make_img(get_palette('viridis'), 32, Image.Resampling.LANCZOS)

    info = vstack([
        text(f'MIN: {mind:.1f}'),
        text(f'MAX: {maxd:.1f}'),
    ])

    imgs = vstack([
        text('ToF'),
        hstack([img2, info], gap=2),
    ], gap=2)
    return div(imgs, style=DivStyle(border=1, border_color="#252525", background="#0443048F", radius=2, padding=2))


def ir_cam_info(fs: FrameState):
    telem = TelemetryStateManager().get_state(fs)

    if not telem.ircam.enabled:
        act('ircam', 'start', str(fs.tick))

    if not telem.ircam.render:
        return

    shape = (24, 32)

    dmm = np.flipud(np.array(telem.ircam.render)).astype('float64')

    maxt = dmm.max()
    mint = dmm.min()

    dmm = maxt - dmm
    dmm *= (255.0 / (maxt - mint))
    dmm = np.clip(dmm, 0, 255).astype(np.uint8)

    def _make_img(pallette, size, resample):
        img = Image.frombytes("P", shape, dmm.tobytes())
        img.putpalette(pallette)
        img = img.convert('RGBA')
        img = img.resize(size, resample)
        frame = Frame(img, hash=('ircam_info', f'v1_{size}_{resample}')).rotate(180)
        return div(frame, style=DivStyle(border=1, border_color='#11111188', radius=2))

    img2 = _make_img(get_palette('twilight'), (48, 64), Image.Resampling.LANCZOS)

    info = vstack([
        text(f'MIN: {mint:.1f}'),
        text(f'MAX: {maxt:.1f}'),
    ])

    imgs = vstack([
        text('IR Cam'),
        hstack([img2, info], gap=2),
    ], gap=2)
    return div(imgs, style=DivStyle(border=1, border_color="#252525", background="#0443048F", radius=2, padding=2))


def di_rmt(fs: FrameState):
    telem = TelemetryStateManager().get_state(fs)


    items = hstack([text(f'{telem.light_sensor.proximity}')])

    return div(items)


def info_content(fs: FrameState):
    telem = TelemetryStateManager().get_state(fs)
    if not RemoteStateManager().get_state(fs).show_debug:
        sample_vscroll.reset_position()
        if telem.ircam.enabled:
            act('ircam', 'stop', str(fs.tick))
        return

    header = div(hstack([
        text('Font Demo', style=TextStyle(font=small_bars, width=45, color="#021f19cc")),
    ], gap=2), style=DivStyle(
        background='#ffffff77',
        padding=2,
        radius=(2, 0, 3, 0),
        border=0,
        border_color='#444444',
    ))
    sample_vscroll.set_frame(*font_demo(), pause_offset=header.height + 4)
    info = composite_at(header, div(sample_vscroll.draw(fs.tick), style=DivStyle(background="#ffffff21", radius=3, padding=2)), 'tr', frost=2.4)
    try:
        tof = tof_info(fs)
        irc = ir_cam_info(fs)
        info = composite_at(vstack([tof, irc]), info, 'mm', frost=3)
    except Exception as e:
        print(e)
        pass

    
    info = composite_at(di_rmt(fs), info, 'mm', frost=3)
        
    return info.tag(('debug_info', 1))


def widget(fs: FrameState):
    return Widget('debug_info', info_content(fs), style=DivStyle(
        background="#100F1D88",
        padding=3,
        margin=0,
        radius=(3, 0, 0, 3),
        border=1,
        border_color='#b196ce'
    ))
