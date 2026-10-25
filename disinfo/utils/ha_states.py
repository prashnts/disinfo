'''A display's sensors as Home Assistant states: sensor.<screen>_<reading>, over its REST API.

States set this way have no unique id: Home Assistant shows them, but they can't be edited there,
and after it restarts they're back with the next reading. A display that had entities before (ESPHome)
keeps their ids: the history and statistics go on.
'''
import requests

from disinfo.config import app_config

# reading -> name, unit, device class
SENSORS = {
    'temperature': ('Temperature', '°C', 'temperature'),
    'humidity': ('Humidity', '%', 'humidity'),
    'pressure': ('Pressure', 'hPa', 'atmospheric_pressure'),
    'gas_resistance': ('Gas Resistance', 'Ω', None),
    'aqi': ('Air Quality Index', None, 'aqi'),
    'tvoc': ('TVOC', 'ppb', 'volatile_organic_compounds_parts'),
    'eco2': ('eCO2', 'ppm', 'carbon_dioxide'),
    'lux': ('Lux', 'lx', 'illuminance'),
    'visible': ('Visible', None, None),
    'infrared': ('IR', None, None),
    'full_spectrum': ('Full Spectrum', None, None),
    'clear': ('Clear', None, None),                 # the desk's colour sensor, its clear channel
    'daylight': ('Daylight', '%', None),            # of the brightest seen with the sun there (aviator/daylight.py)
    'sky_cloud': ('Sky Cloud', '%', None),
}
# The BME680 warms itself: ESPHome took 1 °C off.
OFFSETS = {'temperature': -1}

# node -> reading -> (entity id, name) it had
KNOWN = {
    'dientry': {    # the Guition, ESPHome's "guiton"
        'temperature': ('sensor.guiton_bme680_temperature', 'Guiton BME680 Temperature'),
        'humidity': ('sensor.guiton_bme680_humidity', 'Guiton BME680 Humidity'),
        'pressure': ('sensor.guiton_bme680_pressure', 'Guiton BME680 Pressure'),
        'gas_resistance': ('sensor.guiton_bme680_gas_resistance', 'Guiton BME680 Gas Resistance'),
        'aqi': ('sensor.guiton_ens160_air_quality_index', 'Guiton ENS160 Air Quality Index'),
        'eco2': ('sensor.guiton_ens160_eco2', 'Guiton ENS160 eCO2'),
        'tvoc': ('sensor.guiton_ens160_tvoc', 'Guiton ENS160 TVOC'),
        'lux': ('sensor.guiton_dientry_lux', 'Guiton dientry Lux'),
        'visible': ('sensor.guiton_dientry_visible', 'Guiton dientry Visible'),
        'infrared': ('sensor.guiton_dientry_ir', 'Guiton dientry IR'),
        'full_spectrum': ('sensor.guiton_dientry_full_spectrum', 'Guiton dientry Full Spectrum'),
    },
}


def publish(node: str, data: dict):
    headers = {'Authorization': f'Bearer {app_config.ha_token.get_secret_value()}'}
    for key, value in data.items():
        if key not in SENSORS or not isinstance(value, (int, float)):
            continue
        name, unit, device_class = SENSORS[key]
        entity_id, friendly = KNOWN.get(node, {}).get(key, (f'sensor.{node}_{key}', f'{node} {name}'))
        attributes = {'friendly_name': friendly, 'state_class': 'measurement'}
        if unit:
            attributes['unit_of_measurement'] = unit
        if device_class:
            attributes['device_class'] = device_class
        state = round(value + OFFSETS.get(key, 0), 2)
        requests.post(f'{app_config.ha_base_url}/api/states/{entity_id}', headers=headers,
                      json={'state': state, 'attributes': attributes}, timeout=5)
