'''Trips: the sky view goes to have a look at a landmark from its vantage (skyline.py), then comes back.

From home it turns and zooms in on the landmark, crosses over to the vantage's view where the landmark is as big and
where it was (the zoom going on through it), settles there a while, then the same way back. The views themselves
are the sky view's; here only when, and how far along.
'''
from typing import NamedTuple


go_s, cross_s, settle_s = 12, 2.5, 6       # s: zooming in from home, crossing over, settling at the vantage
squeeze = 0.8           # the zoom going on through the crossing: the landmark that much bigger after it


class Trip(NamedTuple):
    mark: str           # the landmark (sky.py's name)
    start: float
    dwell: float        # s settled at the vantage
    why: str = ''       # 'show', 'tour', 'visit'


class Leg(NamedTuple):
    there: bool         # at the vantage, else at home
    weight: float       # in the frame (crossing over: both)
    k: float            # home: from its own view (0) to on the landmark (1); there: from as big as from home (0) to settled (1)
    z: float            # the crossing's zoom: 1, down to squeeze
    u: float            # s since it got there


def smooth(k: float) -> float:
    k = min(max(k, 0), 1)
    return k * k * (3 - 2 * k)

def length(t: Trip) -> float:
    return 2 * (go_s + cross_s + settle_s) + t.dwell

def until_back(t: Trip, now: float) -> Trip:
    # Back from now on (or right after settling): the dwell cut short.
    return t._replace(dwell=min(t.dwell, max(now - t.start - go_s - cross_s - settle_s, 0)))

def legs(t: Trip, now: float) -> list[Leg]:
    '''What's in the frame now: one view, or two while crossing over. None after the trip.'''
    u = now - t.start
    there = go_s + cross_s
    back = there + 2 * settle_s + t.dwell
    if u < 0 or u >= length(t):
        return []
    if u < go_s:
        return [Leg(False, 1, smooth(u / go_s), 1, 0)]
    if u < there:
        x = smooth((u - go_s) / cross_s)
        z = 1 - (1 - squeeze) * x
        return [Leg(False, 1 - x, 1, z, 0), Leg(True, x, 0, z, 0)]
    if u < back:
        k = min(smooth((u - there) / settle_s), smooth((back - u) / settle_s))
        return [Leg(True, 1, k, squeeze, u - there)]
    if u < back + cross_s:
        x = smooth((u - back) / cross_s)
        z = squeeze + (1 - squeeze) * x
        return [Leg(False, x, 1, z, 0), Leg(True, 1 - x, 0, z, u - there)]
    return [Leg(False, 1, smooth((length(t) - u) / go_s), 1, 0)]
