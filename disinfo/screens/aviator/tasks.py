import time
import geopy.distance
import requests

from collections import defaultdict

from disinfo.config import app_config
from disinfo.redis import publish


def distance_to_home(lat: float, lon: float) -> float:
    return geopy.distance.distance((lat, lon), (app_config.latitude, app_config.longitude)).km


def fetch_planes():
    url = f'http://{app_config.adsbx_host}/data/aircraft.json'

    r = requests.get(url)
    r.raise_for_status()
    data = r.json()

    return data['aircraft']

positions = defaultdict(list)


def fetch_closest_planes():
    planes = fetch_planes()
    planes_with_pos = []
    now = time.time()

    for plane in planes:
        if 'lat' not in plane or 'lon' not in plane or 'alt_baro' not in plane or not plane.get('flight'):
            continue
        plane['distance'] = distance_to_home(plane['lat'], plane['lon'])

        # TODO: the positions array grows indefinitely.
        positions[plane['hex']].append((plane['lat'], plane['lon'], plane['alt_baro'], plane.get('track'), now))
        plane['positions'] = positions[plane['hex']]

        if len(plane['positions']) > 400:
            del plane['positions'][:-400]

        planes_with_pos.append(plane)
    
    for hex, pos in positions.items():
        if now - pos[-1][-1] > 60 * 60:
            del positions[hex]

    return {
        'planes': sorted(planes_with_pos, key=lambda x: x['distance'])[:50],
    }


def adsbx_task():
    planes = fetch_closest_planes()
    publish('di.pubsub.aviator', action='update', payload=planes)
    print('Published planes')
