import redis
import json

rkeys = {
    'weather_data': 'weather.forecast_data',
    'random_msg': 'misc.random_msg',
    'octoprint_printing': 'hass.octoprint.printing',
    'ha_pir_salon': 'hass.pir.salon',
    'ha_enki_rmt': 'hass.enki.rmt',
}

db = redis.Redis(host='localhost', port=6379, db=0)

def get_dict(key: str) -> dict:
    value = db.get(key)
    return json.loads(value)

def set_dict(key: str, payload: dict):
    data = json.dumps(payload)
    db.set(key, data)
