'''dientry: the entrance's screen (the Guition, 800x480 at 2x).

The time, the radar or the solar clock, the salon's cards; scenes and the mirror's light to touch. The timers too:
the pill opens a sheet, a time made of chips or a known timer started with a tap; a touch anywhere mutes one ringing.
'''
import math
import time
from collections import defaultdict
from dataclasses import replace as dc_replace
from functools import lru_cache

import numpy as np
from PIL import Image

from discore.button import button, ButtonStyle
from discore.data_structures import FrameState
from discore.elements import Frame, Target, UNBOUNDED, measure, render, scaled
from discore.layers import DivStyle, div, shapes
from discore.layouts import composite_at, grid, hstack, vstack
from discore.screen import Screen, Spot, Option
from discore.stack import Stack, StackStyle
from discore.text import text, TextStyle

from disinfo import fonts
from disinfo.apps import timer as T
from disinfo.drat import shown
from disinfo.drat.app_states import TouchStateManager
from disinfo.utils.hass import get_entity
from disinfo.utils.mdi import icon
from . import aviator
from . import paris_metro
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
SHEET = 30          # s the timer sheet stays, untouched
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
    return (ButtonStyle(normal=DivStyle(background='@card', border_color='@line', **cell),
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
    # The timers: the soonest one's time left (or since it was done), a tap for the sheet.
    live = [t for t in T.timers(fs.tick) if t.left() > -t.tail]
    soonest = min(live, key=lambda t: t.left()) if live else None
    buttons.append(control(fs, soonest and T.over(soonest), {'screen': fs.config.name, 'open': 1},
                           bool(soonest) or sheets[fs.config.name][0] > 0, 'timer-outline', 'pill', act='timer'))
    # The metro card: shown or hidden for a while (drat.shown), on while it's up.
    buttons.append(control(fs, None, None, paris_metro.up(fs), 'subway-variant', 'pill', act='show_metro'))
    # The bottom stacks hidden on every screen, zen on this one: on while they are.
    buttons.append(control(fs, None, None, not shown.bottom(fs), 'dock-bottom', 'pill', act='bottom'))
    buttons.append(control(fs, None, {'screen': fs.config.name}, shown.zen(fs), 'meditation', 'pill', act='zen'))
    # Fewer columns till it fits: cut to width, the buttons lose their right edges. One column is cut anyway.
    for n in range(ncols, 0, -1):
        g = grid(buttons, ncols=n, gap=GAP//2, anchor='tm', masonry=True)
        if g.width <= width:
            return g
    return grid(buttons, ncols=1, gap=GAP, anchor='tm', width=width)

sheets = defaultdict(lambda: [0.0, 0])     # screen -> [opened at (0: closed), the time being set]

def timer_sheet(fs: FrameState) -> Frame | None:
    # Its taps first (the pill's too), then the sheet if open: the time and its chips, the known timers, the running
    # ones (held: cancelled). Anything ringing: open, and a touch anywhere mutes it.
    sh, now = sheets[fs.config.name], time.monotonic()
    shown = T.timers(fs.tick)
    for p in T.taps(fs):
        sh[0] = now
        if T.mute(shown) or p.get('mute'):
            continue
        if p.get('close'):
            sh[:] = 0, 0
        elif 'add' in p:
            sh[1] = max(0, sh[1] + p['add'])
        elif p.get('start') and sh[1]:
            T.start(sh[1], origin=fs.config.name)
            sh[:] = 0, 0
        elif 'known' in p and p['known'] < len(ks := T.known()):
            k = ks[p['known']]
            T.start(k['duration'], k['label'], k['icon'], fs.config.name)
            sh[:] = 0, 0
        elif 'cancel' in p:
            T.cancel(p['cancel'])
    ringing = any(t.ringing() for t in shown)
    if ringing:
        sh[0] = now
    if sh[0] and now - sh[0] > SHEET:
        sh[:] = 0, 0
    if not sh[0]:
        return None
    me = {'screen': fs.config.name}
    tap = lambda label, payload, on=False, mdi=None, kind='pill', hold=0: control(fs, label, {**me, **payload}, on, mdi, kind, hold=hold, act='timer')
    rows = [hstack([text(T.mmss(sh[1]), TextStyle(font=fonts.px_op__l, color='#f0f0f0' if sh[1] else '#808080')),
                    tap('start', {'start': 1}, bool(sh[1]), 'play'), tap(None, {'close': 1}, False, 'close')], gap=4),
            hstack([tap(s, {'add': a}) for s, a in (('-1m', -60), ('+30s', 30), ('+1m', 60), ('+5m', 300), ('+10m', 600))], gap=3)]
    if (ks := T.known()):
        n = max(1, (fs.config.width - 24) // (48 if compact(fs) else 56))
        rows.append(grid([tap(T.mmss(k['duration']), {'known': i}, False, k['icon'], 'big') for i, k in enumerate(ks[:2 * n])],
                         ncols=n, gap=3, anchor='tm'))
    if (live := [t for t in shown if t.left() > -t.tail][:4]):
        rows.append(hstack([tap(T.over(t), {'cancel': t.pk}, t.ringing(), t.icon, hold=1.5)
                            for t in live[:3 if compact(fs) else 4]], gap=3))
        rows.append(text('hold one to stop it' if not ringing else 'touch to mute', TextStyle(font=fonts.galmuri7, color='#a0a0a0')))
    f = div(vstack(rows, gap=4, align='center'), dc_replace(shapes.card, background='@scrim', padding=6, border_color='@accent/a4'))
    return f

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
    if (sheet := timer_sheet(fs)):
        canvas = composite_at(sheet, canvas, 'mm')
    if any(t.ringing() for t in T.timers(fs.tick)):
        canvas = Frame(canvas.image, hash=canvas.hash, targets=(*canvas.targets, Target(0, 0, w, h, 'timer', {'screen': fs.config.name, 'mute': 1})))
    if holding(fs):
        # Its thickness pulses, k to 2k, once a second.
        k = 2 if compact(fs) else 3
        canvas = composite_at(checkered(w, h, k, round(k * (1.5 - 0.5 * math.cos(2 * math.pi * fs.tick)))), canvas, 'mm')
    return canvas.tag('entry')
