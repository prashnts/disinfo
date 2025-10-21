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
from disinfo.web.telemetry import TelemetryStateManager
from disinfo.components.elements import Frame


sample_vscroll = VScroller(size=98, pause_at_loop=True, pause_duration=2.5, pause_offset=18, speed=0.001, delta=3, scrollbar=True)

@cache
def font_demo():
    sample = """\
10/20/2023 12:34
A quick brown fox jumps over the lazy dog.
-> [ ] { } < > # $ % 
"""

    samples = []
    spacing = 10
    pauses = [2]
    _p = 0
    font_bg = DivStyle(border=1, border_color='#444444', background="#DDD1AE6A", padding=3, radius=2)

    for fname, font in font_register.items():
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


def tof_info(fs: FrameState):
    telem = TelemetryStateManager().get_state(fs)

    distance = 512

    dmm = np.flipud(np.array(telem.tof.distance_mm).reshape((8, 8))).astype('float64')
    dmm *= (255.0 / distance)
    dmm = np.clip(dmm, 0, 255).astype(np.uint8)

    def _make_img(pallette, size, resample):
        img = Image.frombytes("P", (8, 8), dmm.tobytes())
        img.putpalette(pallette)
        img = img.convert('RGBA')
        img = img.resize((size, size), resample)
        frame = Frame(img, hash=('tof_info', f'v1_{size}_{resample}'))
        return div(frame, style=DivStyle(border=1, border_color='#111111', radius=2))

    img1 = _make_img(_plasma, 20, Image.NEAREST)
    img2 = _make_img(_viridis, 50, Image.Resampling.LANCZOS)
    img3 = _make_img(_inferno, 30, Image.Resampling.LANCZOS)
    img4 = _make_img(_twilight, 30, Image.Resampling.LANCZOS)

    imgs = vstack([
        hstack([vstack([img1, img3], gap=2), img2], gap=2),
        hstack([img4], gap=2)
    ], gap=2)
    return div(imgs, style=DivStyle(border=1, border_color="#252525", background="#0443048F", radius=2, padding=2))

def info_content(fs: FrameState):
    if not RemoteStateManager().get_state(fs).show_debug:
        sample_vscroll.reset_position()
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
        return composite_at(tof, info, 'mm', frost=3).tag('debug_info')
    except Exception as e:
        print(f'[DebugInfo] Error drawing ToF info: {e}')
        return info.tag('debug_info')
    # return vstack([header, sample_vscroll.draw(fs.tick)], gap=1)


def widget(fs: FrameState):
    return Widget('debug_info', info_content(fs), style=DivStyle(
        background="#100F1D88",
        padding=3,
        margin=0,
        radius=(3, 0, 0, 3),
        border=1,
        border_color='#b196ce'
    ))
