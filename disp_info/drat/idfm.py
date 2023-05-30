import asyncio
import aiohttp
import random
import pendulum

from idfm_api import IDFMApi
from idfm_api.models import TransportType, LineData, StopData, TrafficData, InfoData
from functools import cache
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
line_infos = [
    { 'line': '13', 'line_id': 'C01383' },
    { 'line': '4',  'line_id': 'C01374' },
    { 'line': '3',  'line_id': 'C01373' },
    { 'line': '14', 'line_id': 'C01384' },
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


async def fetch_stop_traffic(stop_id: str) -> list[TrafficData]:
    session = aiohttp.ClientSession()
    idfm = IDFMApi(session, idfm_api_key)
    traffic = await idfm.get_traffic(stop_id)
    await session.close()
    return traffic


async def fetch_line_infos(line_id: str) -> list[InfoData]:
    session = aiohttp.ClientSession()
    idfm = IDFMApi(session, idfm_api_key)
    infos = await idfm.get_infos(line_id)
    await session.close()
    return infos


def is_active():
    now = pendulum.now()
    return any([
        7 <= now.hour <= 9,
        16 <= now.hour < 17,
    ])


def collate_train_time(traffic: list[TrafficData], direction: str):
    now = pendulum.now()
    for t in traffic:
        if t.direction == direction and t.schedule >= now:
            mins = now.diff(t.schedule).total_seconds() / 60
            yield {
                'next_in': mins,
                'retarded': t.retarted
            }

def collate_info(infos: list[InfoData]):
    now = pendulum.now()
    messages = []
    for i in infos:
        if now.diff(i.start_time).total_hours() > 12:
            continue
        messages.append(i.name)

    has_pertubation = any([i.type == 'Perturbation' for i in infos])

    return {
        'messages': messages,
        'issues': has_pertubation,
    }


def fetch_state():
    trains = []
    infos = []

    for s in traffic_stops:
        traffic = asyncio.run(fetch_stop_traffic(s['stop_id']))
        info = asyncio.run(fetch_line_infos(s['line_id']))
        timings = sorted(collate_train_time(traffic, s['direction']), key=lambda x: x['next_in'])
        information = collate_info(info)
        trains.append({**s, 'timings': timings, 'information': information})
        infos.append({**s, **information})

    for s in line_infos:
        info = asyncio.run(fetch_line_infos(s['line_id']))
        information = collate_info(info)
        infos.append({**s, **information})


    return {
        'trains': trains,
        'information': infos,
        'timestamp': pendulum.now().isoformat(),
    }
