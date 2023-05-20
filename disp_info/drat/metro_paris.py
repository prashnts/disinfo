from idfm_api import IDFMApi
from idfm_api.models import TransportType, LineData, StopData, TrafficData, InfoData
import asyncio
import aiohttp
import random

import arrow

from dataclasses import dataclass

from ..config import idfm_api_key


@dataclass
class MetroTrafficData:
    traffic: TrafficData
    info: InfoData
    line: LineData
    stop: StopData


async def fetch_traffic_info_at_stop(line_name: str, stop_name: str = None) -> MetroTrafficData:
    session = aiohttp.ClientSession()

    idfm = IDFMApi(session, idfm_api_key)

    _lines = await idfm.get_lines(TransportType.METRO)
    line = [l for l in _lines if l.name == line_name][0]

    _stops = await idfm.get_stops(line.id)


    if stop_name:
        stop = [s for s in _stops if s.name == stop_name][0]
    else:
        stop = random.choice(_stops)

    directions = await idfm.get_destinations(stop.id)

    traffic = await idfm.get_traffic(stop.id)
    infos = await idfm.get_infos(line.id)

    await session.close()

    return MetroTrafficData(traffic=traffic, info=infos, line=line, stop=stop)


traffic_stops = [
    {
        'line': '1',
        'stop': 'Reuilly - Diderot',
        'direction': 'CHARLES DE GAULLE-ETOILE',
    },
    {
        'line': '8',
        'stop': 'Montgallet',
        'direction': 'BALARD',
    }
]


def collate_train_time(traffic: list[TrafficData], direction: str):
    now = arrow.now()
    for t in traffic:
        if t.direction == direction:
            sched = arrow.get(t.schedule).to('local')
            mins = (sched - now).total_seconds() / 60
            if mins < 0:
                # possible due to api delays
                continue
            yield {
                'next_in': mins,
                'retarded': t.retarted
            }


def get_metro_traffic_info(line_name: str, stop_name: str = None):
    metros = asyncio.run(fetch_traffic_info_at_stop(line_name, stop_name))

    # transform the data to what we're interested in displaying.
    # Information OU Perturbation OU Commercial
    # Use closest time for the pertubations

    return metros

def fetch_state():
    trains = []
    for stop in traffic_stops:
        info = get_metro_traffic_info(stop['line'], stop['stop'])
        timings = list(collate_train_time(info.traffic, stop['direction']))
        trains.append({**stop, 'timings': timings})

    return {
        'trains': trains,
        'timestamp': arrow.now().isoformat(),
    }
