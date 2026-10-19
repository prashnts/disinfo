'''dientry: the entrance's screen (the Guition, 800x480 at 2x).

The time and the solar clock, weather and moon, the music playing; scenes and the mirror's light to touch.
'''
from PIL import Image

from discore.button import button, ButtonStyle
from discore.data_structures import FrameState
from discore.elements import Frame, scaled
from discore.layers import DivStyle
from discore.layouts import composite_at, hstack, vstack
from discore.text import text, TextStyle

from disinfo import fonts
from disinfo.drat.app_states import TouchStateManager
from disinfo.utils.hass import get_entity
from . import now_playing
from .date_time import flip_digital_clock
from .solar import draw as solar
from .solar.app import AnalogClockStyle, sky_color
from .weather import widgets as weather

SCENES = [('lumos', 'scene.lumos'), ('dodo', 'scene.dodo'), ('soir', 'scene.soir'), ('nuit', 'scene.nuit')]
MIRROR = 'light.ikea_driver_study_kallax'
GAP = 6

label_style = TextStyle(font=fonts.cozette, color='#e0e0e0', overflow='fit')


def big(f: Frame | None, k: int = 2) -> Frame | None:
    # The 128 px panels' cards, k times: whole pixels, sharp. Their targets too.
    if not f:
        return f
    img = f.image.resize((f.width * k, f.height * k), Image.NEAREST)
    return Frame(img, hash=('big', k, f.hash), targets=scaled(f.targets, k, k))


def styles(width: int) -> tuple[ButtonStyle, ButtonStyle]:
    # Normal, and on (the scene last turned on, the light on).
    cell = dict(width=width, height=24, padding=5, radius=4, border=1, anchor='mm')
    return (ButtonStyle(normal=DivStyle(background='#00000080', border_color='#ffffff30', **cell),
                        pressed=DivStyle(background='#ffffff60', border_color='#ffffffb0', **cell)),
            ButtonStyle(normal=DivStyle(background='#40300c90', border_color='#e0a040b0', **cell),
                        pressed=DivStyle(background='#e0a04080', border_color='#ffd080', **cell)))

def control(fs: FrameState, label: str, payload: dict, on: bool, width: int) -> Frame:
    normal, active = styles(width)
    return button(text(label, label_style), 'ha.call', payload,
                  pressed=TouchStateManager().is_pressed(fs, 'ha.call', payload), style=active if on else normal)

def controls(fs: FrameState, width: int) -> Frame:
    # One row across: the scenes, then the mirror's light.
    each = (width - GAP * len(SCENES)) // (len(SCENES) + 1) - 2 * 5 - 2
    scenes = [(name, get_entity(eid)) for name, eid in SCENES]
    # A scene's state is when it was last turned on.
    last = max((e.state for _, e in scenes if e), default=None)
    buttons = [control(fs, name, {'service': 'scene.turn_on', 'target': {'entity_id': e.entity_id}}, e.state == last, each)
               for name, e in scenes if e]
    mirror = get_entity(MIRROR)
    buttons.append(control(fs, 'mirror', {'service': 'light.toggle', 'target': {'entity_id': MIRROR}},
                           bool(mirror and mirror.state == 'on'), each))
    return hstack(buttons, gap=GAP)

def compose(fs: FrameState) -> Frame:
    w, h = fs.config.width, fs.config.height
    canvas = Frame(Image.new('RGBA', (w, h), (0, 0, 0, 255)))
    clock = AnalogClockStyle(cx=w // 2 + 60, cy=h // 2 - 20, tick_radius_multiplier=0.36,
                             dial_radius_multiplier=0.36, needle_radius_multiplier=0.42, background=sky_color(fs))
    canvas = composite_at(solar(fs, clock), canvas, 'mm')
    cards = vstack([big(weather.weather(fs).draw(fs)), big(weather.moon_phase(fs).draw(fs)),
                    big(now_playing.widget(fs).draw(fs))], gap=6)
    canvas = composite_at(cards, canvas, 'tl', dx=6, dy=6, frost=1.8)
    canvas = composite_at(big(flip_digital_clock(fs, align='right')), canvas, 'tr', dx=-6, dy=6, frost=1.8)
    canvas = composite_at(controls(fs, w - 2 * GAP), canvas, 'bm', dy=-GAP, frost=1.8)
    return canvas.tag('entry')
