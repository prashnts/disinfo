from idfm_api import IDFMApi
from idfm_api.models import TransportType, LineData, StopData, TrafficData, InfoData
from functools import cache

import asyncio
import aiohttp
import random

import arrow

from dataclasses import dataclass

from ..config import idfm_api_key


traffic_stops = [
    {
        'line': '1',
        'line_id': 'C01371',
        'stop': 'Reuilly - Diderot',
        'stop_id': '44637',
        'direction': 'LA DEFENSE',
    },
    {
        'line': '8',
        'line_id': 'C01378',
        'stop': 'Montgallet',
        'stop_id': '44160',
        'direction': 'BALARD',
    },
    {
        'line': '6',
        'line_id': 'C01376',
        'stop': 'Daumesnil',
        'stop_id': '45229',
        'direction': 'CHARLES DE GAULLE-ETOILE',
    },
]

@dataclass
class MetroTrafficData:
    traffic: TrafficData
    info: InfoData


async def get_stop(line_name: str, stop_name: str = None) -> tuple[LineData, StopData]:
    # we don't need this session, but it's required.
    session = aiohttp.ClientSession()
    idfm = IDFMApi(session, idfm_api_key)

    _lines = await idfm.get_lines(TransportType.METRO)
    line = [l for l in _lines if l.name == line_name][0]

    _stops = await idfm.get_stops(line.id)

    if stop_name:
        stop = [s for s in _stops if s.name == stop_name][0]
    else:
        stop = random.choice(_stops)

    await session.close()

    return line, stop


async def fetch_traffic_info_at_stop(line_id: str, stop_id: str) -> MetroTrafficData:
    session = aiohttp.ClientSession()
    idfm = IDFMApi(session, idfm_api_key)

    traffic = await idfm.get_traffic(stop_id)
    infos = await idfm.get_infos(line_id)

    await session.close()

    return MetroTrafficData(traffic=traffic, info=infos)


def is_active():
    now = arrow.now()
    return any([
        7 <= now.hour <= 9,
        16 <= now.hour < 17,
    ])


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
    for s in traffic_stops:
        info = get_metro_traffic_info(s['line_id'], s['stop_id'])
        timings = list(collate_train_time(info.traffic, s['direction']))
        trains.append({**s, 'timings': timings})

    return {
        'trains': trains,
        'timestamp': arrow.now().isoformat(),
    }
