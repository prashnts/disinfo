import math

from typing import NamedTuple

from disinfo.config import app_config


# Local flat projection around home: km east, km north. Good to well under 1% within 100 km.
home = app_config.latitude, app_config.longitude
km_lat = 110.574
km_lon = 111.320 * math.cos(math.radians(home[0]))

def local_xy(lat: float, lon: float) -> tuple[float, float]:
    return (lon - home[1]) * km_lon, (lat - home[0]) * km_lat


class Airport(NamedTuple):
    code: str
    lat: float
    lon: float

    @property
    def x(self) -> float:
        return local_xy(self.lat, self.lon)[0]

    @property
    def y(self) -> float:
        return local_xy(self.lat, self.lon)[1]

# In the order they get the focus.
airports = [
    Airport('CDG', 49.0097, 2.5479),
    Airport('ORY', 48.7262, 2.3652),
    Airport('LBG', 48.9694, 2.4414),
]


def bearing(x: float, y: float) -> float:
    # Clockwise from north, as seen from home.
    return math.degrees(math.atan2(x, y)) % 360

def in_window(b: float) -> bool:
    start, end = app_config.aviator_window
    return (b - start) % 360 <= (end - start) % 360

def elevation(alt_m: float, dist_km: float) -> float:
    # Degrees above the horizon, seen from home.
    return math.degrees(math.atan2(alt_m / 1000, dist_km))

def closest_approach(p: dict, lookahead: float) -> dict:
    # Straight line at the current track and speed: when (s) and how close (km) to home within lookahead.
    v = p['gs'] / 3600
    vx, vy = v * math.sin(math.radians(p['track'])), v * math.cos(math.radians(p['track']))
    t = 0 if v == 0 else -(p['x'] * vx + p['y'] * vy) / (v * v)
    t = min(max(t, 0), lookahead)
    d = math.hypot(p['x'] + vx * t, p['y'] + vy * t)
    alt = max(p['alt'] + p['vr'] * t / 60, 0)
    return {'t': round(t), 'd': round(d, 3), 'elev': round(elevation(alt, d), 1)}
