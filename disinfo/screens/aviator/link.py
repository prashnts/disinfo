'''The planes and the sky linked: one plane at a time, a glance at the map to see where it is, then the sky on it.
The default while no view is pressed. The Eiffel tower sparkling wins over all but a tapped plane.'''
import time

from suncalc import get_position

from discore.data_structures import FrameState

from .state import ADSBxStateManager, OpenedStateManager
from . import sky

glance, stay = 8, 45    # s: on the map to see where the plane is, then in the sky on it
near_km = 25            # without watched planes, the nearest in the air within that
_on = {}                # screen -> [the plane, since, the ones shown lately]


def on(fs: FrameState) -> bool:
    return bool(OpenedStateManager().get_state(fs).of('link', fs))

def eiffel(fs: FrameState) -> bool:
    sun = get_position(fs.now.in_tz('UTC'), fs.config.longitude, fs.config.latitude)
    return sky.show(sun['altitude'] * 57.29578, time.time()) is not None

def plane(fs: FrameState, first: str | None) -> str | None:
    '''The plane the show is on: first (a card's, one overhead) at once, else kept glance + stay s, then the next
    of the watched and the nearest, the ones not shown lately first.'''
    st, now = ADSBxStateManager().get_state(fs), time.monotonic()
    c = _on.setdefault(fs.config.name, [None, 0, []])
    if first and first not in OpenedStateManager().get_state(fs).opened and eiffel(fs):
        first = None
    if first is None and eiffel(fs):
        c[0] = None
        return None
    if first and first != c[0]:
        c[:2] = first, now
    elif first is None and (c[0] not in st.planes or now - c[1] > glance + stay):
        near = sorted((h for h, p in st.planes.items() if not p['ground'] and p['dist'] < near_km), key=lambda h: st.planes[h]['dist'])
        pool = [h for h in st.watched if h in st.planes] + near
        fresh = [h for h in pool if h not in c[2]]
        if not fresh:
            c[2], fresh = [], [h for h in pool if h != c[0]] or pool
        c[:2] = fresh[0] if fresh else None, now
    if c[0] and c[0] not in c[2]:
        c[2] = (c[2] + [c[0]])[-8:]
    return c[0]

def phase(fs: FrameState) -> str:
    # The map while glancing at a new plane, the sky otherwise.
    c = _on.get(fs.config.name)
    return 'map' if c and c[0] and time.monotonic() - c[1] < glance else 'sky'
