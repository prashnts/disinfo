'''dientry: the entrance's screen (the Guition, 800x480 at 2x).

The time, the radar or the solar clock, the salon's cards; scenes and the mirror's light to touch.
'''
import math
from dataclasses import replace as dc_replace
from functools import lru_cache

import numpy as np
from PIL import Image

from discore.button import button, ButtonStyle
from discore.data_structures import FrameState
from discore.elements import Frame, UNBOUNDED, measure, render, scaled
from discore.layers import DivStyle
from discore.layouts import composite_at, grid, hstack, vstack
from discore.screen import Screen, Spot, Option
from discore.stack import Stack, StackStyle
from discore.text import text, TextStyle

from disinfo import fonts
from disinfo.drat import idfm
from disinfo.drat.app_states import TouchStateManager
from disinfo.utils.hass import get_entity
from disinfo.utils.mdi import icon
from . import aviator
from .paris_metro import MetroStateManager
from .common import background, side_cards, bottom_cards, motion, focus, heat_store, across
from .date_time import flip_digital_clock
from .solar.app import AnalogClockStyle, sky_color
from .twenty_two import draw as twenty_two

# The label, the entity, its icon (a Material Design Icons name, or None) and the button: 'big' or 'pill'.
# The entity's domain is the action: a scene turns on, a button presses, the rest toggle.
BUTTONS = [
    ('lumos', 'scene.lumos', 'white-balance-sunny', 'big'),
    ('soir', 'scene.soir', 'weather-sunset', 'big'),
    ('nuit', 'scene.nuit', 'weather-night', 'big'),
    ('dodo', 'scene.dodo', 'bed', 'big'),
    ('mirror', 'light.ikea_driver_study_kallax', 'lightbulb', 'pill'),
    ('entree', 'light.ikea_e27_entree', 'lightbulb', 'pill'),
    ('vacuum', 'button.roborock_qrevo_master_full_clean', 'robot-vacuum', 'pill'),
    ('study', 'button.roborock_qrevo_master_clean_study', 'robot-vacuum', 'pill'),
]
HOLD = 5            # s on a button entity to press it, a bar filling it meanwhile
GAP = 6
SIDE = 88           # the side stack's cards

# The side stack top left, or top right for a while (the time and the solar clock go across); the cards along the
# bottom; the buttons where hands expect them.
screen = Screen('dientry', [
    [Option({'side': Spot('tl', dx=GAP, dy=GAP, jitter=(2, 2))}), Option({'side': Spot('tr', dx=-GAP, dy=GAP, jitter=(2, 2))}, penalty=0.5)],
    [Option({'time': Spot('tr', dx=-GAP, dy=GAP, jitter=(2, 3))}), Option({'time': Spot('tl', dx=GAP, dy=GAP, jitter=(2, 3))}, penalty=0.3)],
    [Option({'bottom': Spot('bl'), 'buttons': Spot('br')})],
], load_heat=(store := heat_store('dientry'))[0], save_heat=store[1], covering={'side', 'bottom', 'buttons'},
                stacked={'side', 'bottom', 'buttons'})

label_style = TextStyle(font=fonts.galmuri7, color='#e0e0e0', overflow='fit')


def big(f: Frame | None, k: int = 2) -> Frame | None:
    # The 128 px panels' cards, k times: whole pixels, sharp. Their targets too.
    if not f:
        return f
    img = f.image.resize((f.width * k, f.height * k), Image.NEAREST)
    return Frame(img, hash=('big', k, f.hash), targets=scaled(f.targets, k, k))


def compact(fs: FrameState) -> bool:
    # Shown at 3x (266x160 on the 800x480 panel): smaller buttons, the time at 1x.
    return fs.config.width < 300

def pad(fs: FrameState) -> int:
    return 4 if compact(fs) else 3

def styles(kind: str, fs: FrameState) -> tuple[ButtonStyle, ButtonStyle]:
    # Normal, and on (the scene last turned on, the toggle on). Big: a tile, the icon over the label;
    # pill: one line. The same radius.
    p = pad(fs)
    cell = dict(padding=p, min_width=36 if compact(fs) else 48)
    cell |= dict(radius=3, border=1, anchor='mm')
    return (ButtonStyle(normal=DivStyle(background='#00000080', border_color='#ffffff30', **cell),
                        pressed=DivStyle(background='#ffffff60', border_color='#ffffffb0', **cell), fill='#e0a04090'),
            ButtonStyle(normal=DivStyle(background='#40300c90', border_color='#e0a040b0', **cell),
                        pressed=DivStyle(background='#e0a04080', border_color='#ffd080', **cell), fill='#e0a04090'))

def control(fs: FrameState, label: str | None, payload: dict, on: bool, mdi: str | None, kind: str,
            outline: bool = False, hold: float = 0, act: str = 'ha.call') -> Frame:
    # outline: the icon's outline, if mdi has one. hold: the seconds to hold it, filling. No label: the icon alone.
    normal, active = styles(kind, fs)
    size = (13 if compact(fs) else 16) if kind == 'big' else (8 if compact(fs) else 10)
    ic = mdi and ((outline and icon(f'{mdi}-outline', size)) or icon(mdi, size))
    label = label and text(label, label_style)
    if kind == 'big':
        content = vstack([ic, label], gap=2, align='center')
    else:
        content = hstack([ic, label], gap=2)
    # A Frame: a div puts a Box's content at the top left, not by its anchor.
    touch = TouchStateManager()
    return button(render(content, *measure(content, UNBOUNDED, UNBOUNDED)), act, payload,
                  pressed=touch.is_pressed(fs, act, payload), style=active if on else normal,
                  hold=hold, progress=hold and touch.held_for(fs, act, payload) / hold)

def action(entity, last_scene) -> tuple[str, bool]:
    # The service and whether it's on, by the domain. A scene's (a button's) state is when it was last used.
    domain = entity.entity_id.split('.')[0]
    if domain == 'scene':
        return 'scene.turn_on', entity.state == last_scene
    if domain in ('button', 'input_button'):
        return f'{domain}.press', False
    if domain == 'script':
        return 'script.turn_on', entity.state == 'on'
    return 'homeassistant.toggle', entity.state == 'on'

def controls(fs: FrameState, width: int, ncols: int = 3) -> Frame:
    # Masonry of up to ncols, in BUTTONS' order, each as wide as it needs.
    entities = [(name, get_entity(eid), mdi, kind) for name, eid, mdi, kind in BUTTONS]
    entities = [(name, e, mdi, kind) for name, e, mdi, kind in entities if e]
    last = max((e.state for _, e, _, _ in entities if e.entity_id.startswith('scene.')), default=None)
    buttons = []
    for name, e, mdi, kind in entities:
        service, on = action(e, last)
        buttons.append(control(fs, name, {'service': service, 'target': {'entity_id': e.entity_id}}, on, mdi, kind,
                               outline=service == 'homeassistant.toggle' and not on, hold=HOLD if service.endswith('.press') else 0))
    # The metro card: shown or hidden for a while (drat.idfm.press), on while it's up.
    buttons.append(control(fs, None, None, idfm.visible(fs.now, MetroStateManager().get_state(fs).press), 'subway-variant', 'pill',
                           act='show_metro'))
    # Fewer columns till it fits: cut to width, the buttons lose their right edges. One column is cut anyway.
    for n in range(ncols, 0, -1):
        g = grid(buttons, ncols=n, gap=GAP//2, anchor='tm', masonry=True)
        if g.width <= width:
            return g
    return grid(buttons, ncols=1, gap=GAP, anchor='tm', width=width)

def holding(fs: FrameState) -> bool:
    # A button entity held down: its HOLD running.
    p = TouchStateManager().state.pressed.get(fs.config.name)
    return bool(p) and p[0] == 'ha.call' and p[1].get('service', '').endswith('.press')

@lru_cache(maxsize=16)
def checkered(w: int, h: int, k: int, t: int) -> Frame:
    # The screen's edge, t px: yellow ticks of 2k, black ones of 4k.
    ys, xs = np.mgrid[:h, :w]
    ring = (xs < t) | (xs >= w - t) | (ys < t) | (ys >= h - t)
    yellow = (xs + ys) % (6 * k) < 2 * k
    arr = np.zeros((h, w, 4), np.uint8)
    arr[ring] = (0, 0, 0, 255)
    arr[ring & yellow] = (240, 190, 20, 255)
    return Frame(Image.fromarray(arr), hash=('checkered', w, h, k, t))

def compose(fs: FrameState) -> Frame:
    # Like the salon: the radar or the solar clock, the side and bottom stacks, the scenes to touch. The time at 2x.
    w, h = fs.config.width, fs.config.height
    canvas = Frame(Image.new('RGBA', (w, h), (0, 0, 0, 255)))
    buttons = controls(fs, int(w // 1.5))
    above = h - buttons.height - 2 * GAP        # what the buttons leave
    side_conf = StackStyle(size=above, align='left', horizontal=False)
    side = Stack('main_cards', side_conf).mut(side_cards(fs))
    side.style = dc_replace(side_conf, align='right' if screen.spot('side').anchor[1] == 'r' else 'left')
    bottom = Stack('bottom_cards', StackStyle(align='bottom', horizontal=True, offset_top=0, size=w)).mut(bottom_cards(fs))
    if moved := motion(fs):
        side.next_widget()
        bottom.next_widget()
    aviator.app.follow(fs, bottom.current)
    on_top = [side.current, bottom.current]
    align = 'right' if screen.spot('time').anchor[1] == 'r' else 'left'
    items = {
        'side': side.draw(fs),
        'bottom': bottom.draw(fs),
        'time': big(flip_digital_clock(fs, align=align), 1 if compact(fs) else 2),
        'buttons': buttons,
    }

    # The solar clock across from the side stack.
    clock = lambda spots: AnalogClockStyle(cx=across(screen, spots, w // 2 + 60, w), cy=h // 2 - 20, tick_radius_multiplier=0.36,
                                           dial_radius_multiplier=0.36, needle_radius_multiplier=0.42, background=sky_color(fs))
    calm = any(c and c.background == 'aviator' for c in on_top)
    layout = screen.arrange(fs, items, focus(fs, on_top, clock), when={'calm'} if calm else (), relayout=moved)
    canvas = composite_at(background(fs, clock(screen.spots()), layout.clear, on_top), canvas, 'mm')
    canvas = layout.place('side', items['side'], canvas, frost=1.8)
    canvas = layout.place('bottom', items['bottom'], canvas, frost=1.8)
    canvas = layout.place('time', items['time'], canvas, frost=1.8)
    canvas = layout.place('buttons', buttons, canvas, frost=1.8)
    canvas = composite_at(twenty_two(fs), canvas, 'mm')
    if holding(fs):
        # Its thickness pulses, k to 2k, once a second.
        k = 2 if compact(fs) else 3
        canvas = composite_at(checkered(w, h, k, round(k * (1.5 - 0.5 * math.cos(2 * math.pi * fs.tick)))), canvas, 'mm')
    return canvas.tag('entry')
