'''The palette a screen draws with: its scheme, the device's profile, the screen's own changes, then a section's.

Tokens ('@fg', '@card', '@ok/a3') in styles resolve to it when drawn. Overrides are plain dicts (scheme name and
token values) so the web page can set them at runtime.
'''
import time
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

from discore.color import Palette, palette, using
from discore.data_structures import FrameState

schemes: dict[str, Palette] = {
    'dark': Palette(),
    # Lighter cards: the backdrop shows, the guard and the frost dim keep the text readable.
    'vibrant': Palette().of(card='#00000040', scrim='#00000070', dim=(0.0, 0.55)),
}
# Device: the same tokens, what reads on it. AMOLED and LCD don't bloom: no glare cap. LCD lifts the bottom.
profiles: dict[str, dict[str, Any]] = {
    'led': {},
    'amoled': dict(glare=0),
    'lcd': dict(glare=0, ink2='#3b3e46', fg3='#6a6d74', fg2='#93969c', fg='#c3c5cb', ok='#3fb35f',
                accent='#eaa53c'),
}
# Room light: each band lifts the inks (v6). Over the profile: a band wins on the inks; 'frost' adds to the dim's cap.
bands: dict[str, dict[str, Any]] = {
    'night': dict(hero='#c2c4ca', hero2='#9a9da3', fg='#b0b2b8', fg2='#8a8d93', fg3='#5f6268'),
    'room': dict(hero='#dcdee2', hero2='#b8bac0', fg='#c8cad0', fg2='#a6a8ae', fg3='#7c7f85', glare=0.8, hero_glare=0.8),
    'bright': dict(hero='#ffffff', hero2='#e2e3e6', fg='#ecedf0', fg2='#cbcdd2', fg3='#cbcdd2', accent='#ffb54d',
                   ok='#5ed27a', warn='#e6b872', bad='#ff5c3a', glare=0, hero_glare=0, floor=(55, 45), frost=0.15),
}
band_lux = (10, 275)    # lx: night under, bright over; 30% past it to come back
apds_lux = 0.014        # the desk's clear counts to Sensei's lux (median, daylight log 2026-10-31)
by_screen = {'di_pcstate': 'amoled', 'dientry': 'lcd', 'didial': 'lcd', 'disalon_dial': 'lcd'}
# A section's tokens over the screen's: with section('aviator').
sections: dict[str, dict[str, Any]] = {}
# Runtime: screen name (or '*') -> {'scheme': name, token: value}.
overrides: dict[str, dict[str, Any]] = {}


def palette_for(fs: FrameState) -> Palette:
    # The same object while nothing changes: styles resolved once per palette.
    name = fs.config.name
    own = {**overrides.get('*', {}), **overrides.get(name, {})}
    return _palette(own.pop('scheme', None) or fs.config.scheme, fs.config.profile or by_screen.get(name, 'led'),
                    own.pop('band', None) or band(), tuple(sorted(own.items())))

@lru_cache(maxsize=32)
def _palette(scheme: str, profile: str, band: str, own: tuple) -> Palette:
    p = schemes.get(scheme, schemes['dark']).of(**profiles[profile])
    b = dict(bands[band])
    lo, hi = p.dim
    b['dim'] = (lo, min(hi + b.pop('frost', 0), 0.95))
    if not p.glare:     # the profile's: no cap on it
        b.update(glare=0, hero_glare=0)
    return p.of(**b, **dict(own))

_band = ['room', -99.0]     # the band, when the light was last read

def band() -> str:
    '''The room's light band, read every 30 s.'''
    if (now := time.monotonic()) - _band[1] > 30:
        _band[1] = now
        if (lux := room_lux()) is not None:
            _band[0] = next_band(_band[0], lux)
    return _band[0]

def next_band(cur: str, lux: float) -> str:
    lo, hi = band_lux
    if lux < (lo * 1.3 if cur == 'night' else lo):
        return 'night'
    if lux > (hi / 1.3 if cur == 'bright' else hi):
        return 'bright'
    return 'room'

def room_lux() -> float | None:
    '''Sensei's lux, by the window: the flat's light. Without it, the desk's colour sensor (same room).'''
    from disinfo.config import app_config
    from disinfo.utils.hass import get_entity
    from disinfo.web.telemetry import TelemetryStateManager
    try:
        return float(get_entity(app_config.daylight_lux).state)
    except (AttributeError, TypeError, ValueError):
        pass
    ls = TelemetryStateManager(app_config.daylight_node).get_state().light_sensor
    return ls.rgbc[3] * apds_lux if ls.rgbc and time.time() - ls.received_at < 60 else None

@contextmanager
def section(name: str, **tokens) -> Iterator[Palette]:
    with using(palette().of(**sections.get(name, {}), **tokens)) as p:
        yield p
