import os
import json

from .data_structures import AppBaseModel

class MonitorConfig(AppBaseModel):
    # These are all the ha entities we are interested in.
    presence_sensors: list[str] = [
        'binary_sensor.ikea_pir_salon_occupancy',
        'binary_sensor.ikea_pir_kitchen_occupancy',
        'binary_sensor.ikea_pir_study_occupancy',
    ]
    ambient_light_sensors: list[str] = [
        'sensor.sensei_lux',
        'sensor.enviomental_lux',
    ]

class Config(AppBaseModel):
    pw_api_key: str
    pw_unit: str = 'ca'

    # Homeassistant MQTT
    ha_base_url: str
    ha_mqtt_host: str
    ha_mqtt_port: int
    ha_mqtt_username: str
    ha_mqtt_password: str

    # idf mobilité
    idfm_api_key: str

    latitude: float
    longitude: float
    timezone: str

    # Speaker source
    speaker_source: str = 'media_player.office'
    presence_sensors: list[str] = ['binary_sensor.ikea_pir_study_occupancy']
    ambient_light_sensor: str = 'sensor.sensei_lux'
    presence_lag_minutes: int = 20

    monitors: MonitorConfig = MonitorConfig()

    # Panel
    width: int
    height: int
    name: str

    # Klipper
    klipper_host: str = '10.0.1.91'


with open(os.environ.get('DI_CONFIG_PATH', '.config.json')) as f:
    app_config = Config(**json.load(f))
