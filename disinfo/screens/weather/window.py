'''Close the windows: the wind blows in from where they face (top floor, nothing in its way), hard, or with rain.
A small card attached under the weather card, there only while it's advised.
'''
import math
import time

from disinfo import fonts
from disinfo.config import app_config
from disinfo.utils import mdi
from discore.text import TextStyle, text
from discore.layouts import hstack, Spacer
from discore.data_structures import FrameState
from disinfo.screens.colors import light_gray
from disinfo.screens.aviator import skystate
from disinfo.screens.aviator.skystate import v

arc = 70                # degrees either side of where they face: the wind blows in
wind_ms = 6             # its part into the window, sustained: close (~20 km/h)
gust_ms = 10            # or in the gusts (~35 km/h)
rain_ms = 2             # with rain, now or within rain_s, a lighter wind will do
rain_mm = 0.2           # mm/h
rain_s = 1800
hold_s = 600            # kept up this long after the last reason: no blinking on and off with the gusts
amber = '#f7a401'
s_value = TextStyle(font=fonts.bitocra7, color=light_gray.darken(0.1).hex)
s_label = TextStyle(font=fonts.bitocra7, color='@fg3')

_held = {'until': 0, 'why': None}


def into(dir: float, facing: float | None = None) -> float:
    '''How much of a wind from dir blows into the window: 1 straight in, 0 from the side or behind.'''
    off = (dir - (app_config.window_facing if facing is None else facing) + 180) % 360 - 180
    return math.cos(math.radians(off)) if abs(off) < arc else 0.0

def advice(sky: dict | None, now: float) -> dict | None:
    '''Why to close them now ({dir, wind, gust, rain}), None if there's no need.'''
    dir, wind = v(sky, 'air.dir'), v(sky, 'air.wind', conf=0.3)
    if dir is None or wind is None or not (k := into(dir)):
        return None
    gust = v(sky, 'air.gust', conf=0.3) or wind
    nxt = v(sky, 'precip.next') or {}
    rain = (v(sky, 'precip.rate', 0, conf=0.3) >= rain_mm
            or (nxt.get('begin', math.inf) - now < rain_s and nxt.get('end', 0) > now and (nxt.get('p') or 0) >= 0.5))
    if wind * k >= wind_ms or gust * k >= gust_ms or (rain and wind * k >= rain_ms):
        return {'dir': dir, 'wind': wind, 'gust': gust, 'rain': rain}
    return None

def shown(sky: dict | None, now: float) -> dict | None:
    # The last reason, for a while after it's gone.
    if why := advice(sky, now):
        _held.update(until=now + hold_s, why=why)
    return _held['why'] if now < _held['until'] else None

def card(fs: FrameState):
    if not (a := shown(skystate.doc(), time.time())):
        return None
    speed = f"{a['wind'] * 3.6:.0f}" + (f"-{a['gust'] * 3.6:.0f}" if a['gust'] * 3.6 >= a['wind'] * 3.6 + 10 else '')
    # As narrow as the weather card: the window shut, then why (the wind or the rain) and how hard, km/h.
    return hstack([
        mdi.icon('window-closed-variant', 9, amber),
        Spacer(),
        mdi.icon('weather-pouring' if a['rain'] else 'weather-windy', 9, s_label.color),
        text(speed, s_value),
    ], gap=2, align='center')
