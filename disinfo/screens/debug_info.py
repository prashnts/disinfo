import time
from PIL import Image
from typing import Callable
import numpy as np

from functools import cache
from ..utils.drawer import draw_loop
from discore.text import text, TextStyle
from discore.layouts import vstack, composite_at, hstack
from discore.fonts import register as font_register
from disinfo.fonts import small_bars
from discore.scroller import VScroller
from discore.layers import div, DivStyle
from ..utils.func import throttle
from discore.data_structures import FrameState
from ..drat import shown
from discore.widget import Widget
from disinfo import fonts
from disinfo.web.telemetry import TelemetryStateManager, act
from discore.elements import Frame


sample_vscroll = lambda: VScroller(size=98, name='debug.samples', pause_at_loop=True, pause_duration=2.5, pause_offset=18, speed=0.001, delta=1, scrollbar=True)

@cache
def font_demo(debug=False):
    sample = """\
10/20/2023 à 12:34
Le ˝café˝. L′hopital
ACCENTS: à â ä é è ê ë ï î ô ö ù û ç
CHARS: £ € « ″ -> [ ] { } < > # $ % œ æ
1234567890ABCDEF

EN: A quick brown fox jumps over the lazy dog.
FR: Voix ambiguë d’un cœur qui au zéphyr préfère les jattes de kiwis.
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


    if debug:
        demoslide = vstack([hstack(row, gap=5, align='top') for row in np.resize(np.array(samples), (len(samples) // 4 + 1, 4))])
        demoslide.image.save('./.debugdemo.png')
    demoslide = vstack(samples, gap=spacing, align='left')

    return demoslide, False, pauses

# font_demo(debug=True)  # uncomment to autogenerate the font cards, saved to .debugdemo.png

def get_palette(name):
    from matplotlib import cm
    cmap = cm.get_cmap(name, 256)

    try:
        colors = cmap.colors
    except AttributeError:
        colors = np.array([cmap(i) for i in range(256)], dtype=float)

    arr = np.array(colors * 255).astype('uint8')
    arr = arr.reshape((16, 16, 4))
    arr = arr[:, :, 0:3]
    return arr.tobytes()

_tof_asked = [0.0]
s_tof = TextStyle(font=fonts.tamzen__rs, color='#DFD9C9')

def tof_info(fs: FrameState):
    telem = TelemetryStateManager(fs.config.name).get_state(fs)
    tof = telem.tof
    # The grid comes only while asked: again before the client's 30 s are up.
    if time.time() - _tof_asked[0] > 10:
        _tof_asked[0] = time.time()
        act(fs, 'tof', 'debug', str(int(_tof_asked[0])))

    # In the sensor's view (as a camera): near bright, far dark, no reading black; the foreground's zones dotted.
    dmm = np.array(tof.debug.grid if tof.debug and len(tof.debug.grid) == 64 else [0] * 64).reshape((8, 8)).astype('float64')
    fg = np.array(tof.debug.fg if tof.debug and len(tof.debug.fg) == 64 else [0] * 64).reshape((8, 8))
    valid = dmm > 0
    level = np.clip((3000 - dmm) * (254.0 / 2700), 0, 254) + 1
    dmm = np.where(valid, level, 0).astype(np.uint8)

    def _make_img(pallette, size, resample):
        img = Image.frombytes("P", (8, 8), dmm.tobytes())
        img.putpalette(pallette)
        img = img.convert('RGBA')
        img = img.resize((size, size), resample)
        c = size // 8
        for y, x in zip(*np.nonzero(fg)):
            img.putpixel((int(x) * c + c // 2, int(y) * c + c // 2), (255, 255, 255, 255))
        frame = Frame(img, hash=('tof_info', dmm.tobytes(), fg.tobytes()))
        return div(frame, style=DivStyle(border=1, border_color='#111111', radius=2))

    img2 = _make_img([0, 0, 0] + list(get_palette('viridis'))[3:], 32, Image.Resampling.NEAREST)

    t = tof.target
    info = vstack([
        text(f'P {"on" if tof.present.on else "--"} {tof.hz:.0f}Hz', s_tof),
        text(f'T {t.mm if t else "--"} {f"{t.x:.0f},{t.y:.0f}" if t else ""}', s_tof),
        text(f'N {tof.near.mm if tof.near.pressed else "--"}', s_tof),
    ], gap=1)

    imgs = vstack([
        text('ToF'),
        hstack([img2, info], gap=2),
    ], gap=2)
    return div(imgs, style=DivStyle(border=1, border_color="#252525", background="#0443048F", radius=2, padding=2))


def ir_cam_info(fs: FrameState):
    telem = TelemetryStateManager(fs.config.name).get_state(fs)

    # if not telem.ircam.enabled:
    act(fs, 'ircam', 'start', str(fs.tick))

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
    telem = TelemetryStateManager(fs.config.name).get_state(fs)


    items = hstack([text(f'{telem.light_sensor.proximity}')])

    return div(items)


def info_sensors(fs: FrameState):
    telem = TelemetryStateManager(fs.config.name).get_state(fs)
    if not shown.up(fs, 'sensors'):
        if telem.ircam.enabled:
            act(fs, 'ircam', 'stop', str(fs.tick))
        return

    try:
        tof = tof_info(fs)
        # irc = ir_cam_info(fs)
        info = vstack([tof])
    except Exception as e:
        print(e)
        info = text('Error reading sensors')
        pass

    info = composite_at(di_rmt(fs), info, 'mm', frost=3)
        
    return info.tag(('debug_info', 1))

def info_fonts(fs: FrameState):
    if not shown.up(fs, 'fonts_credit'):
        sample_vscroll().reset_position()
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
    sample_vscroll().set_frame(*font_demo(), pause_offset=header.height + 4)
    info = composite_at(header, div(sample_vscroll().draw(fs.tick), style=DivStyle(background="#ffffff21", radius=3, padding=2)), 'tr', frost=2.4)
    return info.tag(('info_fonts', 1))


def fonts_demo(fs: FrameState):
    return Widget('fonts_demo', info_fonts(fs), style=DivStyle(
        background="#100F1D88",
        padding=3,
        margin=0,
        radius=(3, 0, 0, 3),
        border=1,
        border_color='#b196ce'
    ))

def widgets(fs: FrameState):
    return [
        Widget('info_sensors', info_sensors(fs), priority=20, wait_time=25, style=DivStyle(
            background="#100F1D88",
            padding=3,
            margin=0,
            radius=(3, 0, 0, 3),
            border=1,
            border_color='#b196ce'
        )),
    ]