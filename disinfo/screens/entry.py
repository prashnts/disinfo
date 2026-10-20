'''dientry: the entrance's screen (the Guition, 800x480 at 2x).

The time, the radar or the solar clock, the salon's cards; scenes and the mirror's light to touch.
'''
from PIL import Image

from discore.button import button, ButtonStyle
from discore.data_structures import FrameState
from discore.elements import Frame, scaled
from discore.layers import DivStyle
from discore.layouts import composite_at, hstack, vstack
from discore.stack import Stack, StackStyle
from discore.text import text, TextStyle

from disinfo import fonts
from disinfo.drat.app_states import TouchStateManager
from disinfo.utils.hass import get_entity
from . import aviator
from .common import background, side_cards, bottom_cards, motion
from .date_time import flip_digital_clock
from .solar.app import AnalogClockStyle, sky_color

SCENES = [
    ('lumos', 'scene.lumos'),
    ('dodo', 'scene.dodo'),
    ('soir', 'scene.soir'),
    ('nuit', 'scene.nuit')]
MIRROR = 'light.ikea_driver_study_kallax'
GAP = 6
SIDE = 88           # the side stack's cards

label_style = TextStyle(font=fonts.cozette, color='#e0e0e0', overflow='fit')


def big(f: Frame | None, k: int = 2) -> Frame | None:
    # The 128 px panels' cards, k times: whole pixels, sharp. Their targets too.
    if not f:
        return f
    img = f.image.resize((f.width * k, f.height * k), Image.NEAREST)
    return Frame(img, hash=('big', k, f.hash), targets=scaled(f.targets, k, k))


def compact(fs: FrameState) -> bool:
    # Shown at 3x (266x160 on the 800x480 panel): smaller buttons, the time at 1x.
    return fs.config.width < 300

def styles(width: int, pad: int = 5) -> tuple[ButtonStyle, ButtonStyle]:
    # Normal, and on (the scene last turned on, the light on).
    cell = dict(width=width, height=24 if pad > 2 else 16, padding=pad, radius=4 if pad > 2 else 2, border=1, anchor='mm')
    return (ButtonStyle(normal=DivStyle(background='#00000080', border_color='#ffffff30', **cell),
                        pressed=DivStyle(background='#ffffff60', border_color='#ffffffb0', **cell)),
            ButtonStyle(normal=DivStyle(background='#40300c90', border_color='#e0a040b0', **cell),
                        pressed=DivStyle(background='#e0a04080', border_color='#ffd080', **cell)))

def control(fs: FrameState, label: str, payload: dict, on: bool, width: int) -> Frame:
    normal, active = styles(width, 2 if compact(fs) else 5)
    return button(text(label, label_style), 'ha.call', payload,
                  pressed=TouchStateManager().is_pressed(fs, 'ha.call', payload), style=active if on else normal)

def controls(fs: FrameState, width: int) -> Frame:
    # One row across: the scenes, then the mirror's light.
    each = (width - GAP * len(SCENES)) // (len(SCENES) + 1) - 2 * (2 if compact(fs) else 5) - 2
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
    # Like the salon: the radar or the solar clock, the side and bottom stacks, the scenes to touch. The time at 2x.
    w, h = fs.config.width, fs.config.height
    canvas = Frame(Image.new('RGBA', (w, h), (0, 0, 0, 255)))
    buttons = controls(fs, w - 2 * GAP)
    above = h - buttons.height - 2 * GAP        # what the buttons leave
    # The bottom stack takes the right of the side stack's cards.
    right = w - SIDE - 2 * GAP
    side = Stack('main_cards', StackStyle(size=above, align='left', horizontal=False)).mut(side_cards(fs))
    bottom = Stack('bottom_cards', StackStyle(align='bottom', horizontal=True, offset_top=0, size=right)).mut(bottom_cards(fs))
    if motion(fs):
        side.next_widget()
        bottom.next_widget()
    aviator.app.follow(fs, bottom.current)
    side_f, bottom_f = side.draw(fs), bottom.draw(fs)

    clock = AnalogClockStyle(cx=w // 2 + 60, cy=h // 2 - 20, tick_radius_multiplier=0.36,
                             dial_radius_multiplier=0.36, needle_radius_multiplier=0.42, background=sky_color(fs))
    # What the cards leave of the radar: between the stacks.
    clear = (GAP + (side_f.width if side_f else 0), GAP, w - GAP - (bottom_f.width if bottom_f else 0), above)
    canvas = composite_at(background(fs, clock, clear, [side.current, bottom.current]), canvas, 'mm')
    canvas = composite_at(side_f, canvas, 'tl', dx=GAP, dy=GAP, frost=1.8)
    canvas = composite_at(bottom_f, canvas, 'br', dx=-GAP, dy=-(h - above), frost=1.8)
    canvas = composite_at(big(flip_digital_clock(fs, align='right'), 1 if compact(fs) else 2), canvas, 'tr', dx=-GAP, dy=GAP, frost=1.8)
    canvas = composite_at(buttons, canvas, 'bm', dy=-GAP, frost=1.8)
    return canvas.tag('entry')
