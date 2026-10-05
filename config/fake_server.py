"""A tiny fake of the services disinfo talks to, for the demo image.

Home Assistant (websocket: states, forecast) and the ADS-B feed (aircraft.json).
Entity ids come from the config, so it follows whatever the demo is configured with.
Kagi is not faked: the news is real.

    uvicorn config.fake_server:app --port 4201
"""
import json
import math
import time

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from disinfo.config import app_config as cfg

app = FastAPI()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _entity(entity_id: str, state: str, **attributes) -> dict:
    t = _now().isoformat()
    return dict(entity_id=entity_id, state=state, attributes=attributes,
                last_changed=t, last_updated=t, last_reported=t)


def states() -> list[dict]:
    now = _now()
    return [
        *[_entity(e, 'on') for e in cfg.presence_sensors],
        _entity(cfg.ambient_light_sensor, '120', unit_of_measurement='lx', device_class='illuminance'),
        _entity(cfg.weather_entity, 'partlycloudy', temperature=17.5, humidity=60),
        _entity('sensor.sun_next_dusk', (now + timedelta(hours=3)).isoformat()),
        _entity('sensor.sun_next_dawn', (now + timedelta(hours=15)).isoformat()),
        _entity('sensor.moon_phase', 'waxing_gibbous'),
        _entity(cfg.speaker_entity, 'playing', media_title='Space Oddity', media_artist='David Bowie',
                media_album_name='David Bowie', source='Spotify'),
    ]


def forecast() -> dict:
    day = _now().replace(hour=12, minute=0, second=0, microsecond=0)
    return {'forecast': [
        dict(datetime=(day + timedelta(days=i)).isoformat(), condition='partlycloudy',
             temperature=21.0 - i, templow=11.0 - i, precipitation=0.0, wind_speed=12.0,
             wind_bearing=180.0, humidity=55.0)
        for i in range(5)
    ]}


@app.websocket('/api/websocket')
async def homeassistant(ws: WebSocket):
    await ws.accept()
    await ws.send_json({'type': 'auth_required', 'ha_version': 'fake'})
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind, mid = msg.get('type'), msg.get('id')
            if kind == 'auth':
                await ws.send_json({'type': 'auth_ok', 'ha_version': 'fake'})
            elif kind == 'get_states':
                await ws.send_json({'type': 'result', 'id': mid, 'success': True, 'result': states()})
            elif kind == 'call_service' and msg.get('service') == 'get_forecasts':
                response = {msg['target']['entity_id']: forecast()}
                await ws.send_json({'type': 'result', 'id': mid, 'success': True,
                                    'result': {'context': {}, 'response': response}})
            else:
                await ws.send_json({'type': 'result', 'id': mid, 'success': True, 'result': None})
    except WebSocketDisconnect:
        pass


@app.get('/data/aircraft.json')
def aircraft():
    """A few planes circling the configured home position."""
    t = time.time()
    planes = []
    for i, (flight, radius, alt, period) in enumerate([('AFR1234', 0.03, 3500, 300), ('DLH88X', 0.06, 12000, 420),
                                                       ('EZY42', 0.09, 31000, 600)]):
        a = 2 * math.pi * ((t % period) / period + i / 3)
        planes.append(dict(
            hex=f'3c66{i:02x}', flight=flight.ljust(8), category='A3', alt_baro=alt, gs=250 + 40 * i,
            lat=cfg.latitude + radius * math.sin(a), lon=cfg.longitude + radius * math.cos(a) * 1.5,
            track=(math.degrees(a) + 90) % 360))
    return {'now': t, 'aircraft': planes}
