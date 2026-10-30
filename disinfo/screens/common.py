'''What the screens share: the background, the cards in the side and bottom stacks.'''
import io
import time

import numpy as np

from discore.data_structures import FrameState
from discore.elements import Frame
from discore.screen import Focus
from discore.transitions import FadeIn

from . import aviator, debug_info, dishwasher, klipper, now_playing, paris_metro, smokes, solar, trash_pickup, washing_machine, weather
from .music.shazam import widgets as shazam_widgets
from .solar import AnalogClockStyle
from disinfo.drat import shown
from disinfo.redis import db
from disinfo.utils.hass import get_entity


motion_every = 10       # s at least between two: a sensor flickering doesn't spin the cards
_motion = {}            # screen -> (the sensors on, when it last moved the stacks on)

def motion(fs: FrameState) -> bool:
    '''A presence sensor of the screen just turned on: someone came, or moved into its range.'''
    on = {e for e in fs.config.presence_sensors if (s := get_entity(e)) and s.state == 'on'}
    before, at = _motion.get(fs.config.name, (on, 0))
    moved = bool(on - before) and time.monotonic() - at > motion_every
    _motion[fs.config.name] = (on, time.monotonic() if moved else at)
    return moved


def radar_wanted(fs: FrameState, on_top: list) -> bool:
    # The sky view always, the map for a plane's card on top; the solar view never. A hand near: the sky, any time.
    if aviator.hand.update(fs) and 'sky' in fs.config.aviator_views:
        return True
    if aviator.app.quiet(fs) or (view := aviator.app.view_mode(fs)) == 'solar':
        return False
    return view == 'sky' or (view == 'map' and aviator.link.on(fs)) or any(w and w.background == 'aviator' for w in on_top)

def background(fs: FrameState, style: AnalogClockStyle, clear: tuple, on_top: list) -> Frame:
    '''The background the widgets on top of the stacks bring (a plane's card: the radar), the solar clock otherwise.
    The sky view has the sun in it: it's the solar clock too, always there. Never the radar in the quiet hours.

    clear: the box the cards leave free, the radar keeps the plane of the card on top in it.
    '''
    if radar_wanted(fs, on_top):
        draw = aviator.sky.sky if aviator.app.view_mode(fs) == 'sky' else aviator.app.radar
        frame = aviator.app.throttled(fs, lambda: draw(fs, clear))
    else:
        frame = solar.draw(fs, style)
    # One fade for whichever is up: switching, the new one fades over the last.
    return FadeIn('background', duration=0.8).mut(frame).draw(fs)

def heat_store(name: str):
    # A screen's burn-in, kept over restarts.
    key = f'di.screen.heat.{name}'
    def load():
        raw = db.get(key)
        return np.load(io.BytesIO(raw)) if raw else None
    def save(heat):
        buf = io.BytesIO()
        np.save(buf, heat)
        db.set(key, buf.getvalue())
    return load, save

def across(screen, spots: dict, x: float, width: int) -> float:
    # x where it's designed, mirrored while the side stack is on its other side.
    designated = screen.choices[0][0].spots['side'].anchor[1]
    return x if spots['side'].anchor[1] == designated else width - x

def focus(fs: FrameState, on_top: list, solar_style):
    '''What the cards shouldn't cover: the planes when the radar's up, the solar clock otherwise.
    solar_style: the clock's style for an arrangement's spots (it goes across from the side stack).'''
    size = (fs.config.width, fs.config.height)
    if radar_wanted(fs, on_top):
        f = Focus(size, follows=True)
        for x, y, weight in aviator.app.plane_marks(fs):
            f.disk(x, y, 5, weight)
        return f
    def clock(spots) -> Focus:
        s = solar_style(spots)
        cx, cy = s.cx or size[0] / 2, s.cy or size[1] / 2
        return Focus(size).disk(cx, cy, min(cx, cy) * max(s.dial_radius_multiplier, s.needle_radius_multiplier))
    return clock

def side_cards(fs: FrameState) -> list:
    return shown.kept(fs, [
        weather.widgets.weather(fs),
        *shazam_widgets(fs),
        now_playing.slideshow_widget(fs),
        weather.widgets.moon_phase(fs),
        dishwasher.widget(fs),
        washing_machine.widget(fs),
        trash_pickup.widget(fs),
        smokes.widget(fs),
    ])

def bottom_cards(fs: FrameState) -> list:
    return shown.kept(fs, [
        *aviator.widgets.planes(fs),
        *paris_metro.widgets(fs),
        weather.widgets.graphs(fs),
        now_playing.widget(fs),
        *klipper.widget(fs),
        *debug_info.widgets(fs),
    ], 'bottom')
