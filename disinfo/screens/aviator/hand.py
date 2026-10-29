'''A hand near the screen (its ToF's `near`, telemetry): the sky view comes, the screen in zen, and it turns with the
hand (across: turns, nearer: zooms in); held where it was left a few seconds after the hand's gone, then back to its own, zen off (if it was ours).
Per screen, in the renderer: nothing kept.
'''
import time

from discore.data_structures import FrameState
from disinfo.redis import publish
from disinfo.drat import shown
from disinfo.web.telemetry import TelemetryStateManager

linger = 4              # s, after the hand's gone
deg_per_zone = 14       # the hand across one of the ToF's zones turns the view this much
turn_sign = -1          # the sensor's x grows to the user's left: the hand to the right looks right
mm_per_half = 150       # the hand this much nearer halves the view's width (farther: doubles it)
zoom_sign = 1           # -1: nearer zooms out
fov_range = (12, 120)
_pans = {}              # screen -> {'x0', 'x', 'mm0', 'mm', 'yaw0', 'fov0', 'seen', 'zen'}


def update(fs: FrameState) -> dict | None:
    '''Once a frame: the pan going on for this screen, or None.'''
    name, now = fs.config.name, time.monotonic()
    near = TelemetryStateManager(name).get_state(fs).tof.near
    p = _pans.get(name)
    if near.pressed:
        if not p:
            p = _pans[name] = {'x0': near.x, 'mm0': near.mm, 'yaw0': None, 'fov0': None, 'zen': False}
            if not shown.zen(fs):
                publish('di.pubsub.remote', action='zen', payload={'screen': name, 'on': True})
                p['zen'] = True
        p.update(x=near.x, mm=near.mm, seen=now)
    elif p and now - p['seen'] > linger:
        if p['zen']:
            publish('di.pubsub.remote', action='zen', payload={'screen': name, 'on': False})
        del _pans[name]
        p = None
    return p


def active(fs: FrameState) -> bool:
    return fs.config.name in _pans


def yaw(fs: FrameState, current: float) -> float | None:
    '''Where the hand turns the view: from where it was when the hand came. current: the camera's yaw now.'''
    p = _pans.get(fs.config.name)
    if not p:
        return None
    if p['yaw0'] is None:
        p['yaw0'] = current
    return (p['yaw0'] + turn_sign * deg_per_zone * (p['x'] - p['x0'])) % 360


def fov(fs: FrameState, current: float) -> float | None:
    '''How wide the hand makes the view: from how wide it was when the hand came. current: the camera's now.'''
    p = _pans.get(fs.config.name)
    if not p:
        return None
    if p['fov0'] is None:
        p['fov0'] = current
    f = p['fov0'] * 2 ** (zoom_sign * (p['mm'] - p['mm0']) / mm_per_half)
    return min(max(f, fov_range[0]), fov_range[1])
