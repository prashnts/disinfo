'''The palette a screen draws with: its scheme, the device's profile, the screen's own changes, then a section's.

Tokens ('@fg', '@card', '@ok/a3') in styles resolve to it when drawn. Overrides are plain dicts (scheme name and
token values) so the web page can set them at runtime.
'''
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
    'amoled': dict(glare=False),
    'lcd': dict(glare=False, ink2='#3b3e46', fg3='#6a6d74', fg2='#93969c', fg='#c3c5cb', ok='#3fb35f',
                accent='#eaa53c'),
}
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
                    tuple(sorted(own.items())))

@lru_cache(maxsize=32)
def _palette(scheme: str, profile: str, own: tuple) -> Palette:
    return schemes.get(scheme, schemes['dark']).of(**profiles[profile], **dict(own))

@contextmanager
def section(name: str, **tokens) -> Iterator[Palette]:
    with using(palette().of(**sections.get(name, {}), **tokens)) as p:
        yield p
