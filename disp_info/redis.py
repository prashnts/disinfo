import redis
import json

rkeys = {
    'remote': 'input.remote',
    'weather_data': 'weather.forecast_data',
    'metro_timing': 'metro.timing',
    'random_msg': 'misc.random_msg',
    'octoprint_printing': 'hass.octoprint.printing',
    'octoprint_bedt': 'hass.octoprint.bedt',
    'octoprint_toolt': 'hass.octoprint.toolt',
    'ha_pir_salon': 'hass.pir.salon',
    'ha_pir_kitchen': 'hass.pir.kitchen',
    'ha_enki_rmt': 'hass.enki.rmt',
    'ha_ikea_rmt_0x01': 'hass.ikea.rmt.0x01',
    'ha_sonos_beam': 'hass.sonos.beam',
    'ha_enviomental_lux': 'hass.enviomental.lux',
    'ha_driplant_volts': 'hass.driplant.volts',
}

db = redis.Redis(host='localhost', port=6379, db=0)

def get_dict(key: str, default: dict = {}) -> dict:
    value = db.get(key)
    try:
        return json.loads(value)
    except TypeError:
        return default

def set_dict(key: str, payload: dict):
    data = json.dumps(payload)
    db.set(key, data)
