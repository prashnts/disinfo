import geopy.distance
import requests

from disinfo.config import app_config
from disinfo.redis import publish


def distance_to_home(lat: float, lon: float) -> float:
    return geopy.distance.distance((lat, lon), (app_config.latitude, app_config.longitude)).km


def fetch_planes():
    url = f'http://{app_config.adsbx_host}/tar1090/data/aircraft.json'

    r = requests.get(url)
    r.raise_for_status()
    data = r.json()

    return data['aircraft']

def fetch_closest_planes():
    planes = fetch_planes()
    planes_with_pos = []

    for plane in planes:
        if 'lat' not in plane or 'lon' not in plane or not plane.get('flight'):
            continue
        plane['distance'] = distance_to_home(plane['lat'], plane['lon'])
        planes_with_pos.append(plane)

    return {
        'planes': sorted(planes_with_pos, key=lambda x: x['distance'])[:10],
    }


def adsbx_task():
    planes = fetch_closest_planes()
    publish('di.pubsub.aviator', action='update', payload=planes)