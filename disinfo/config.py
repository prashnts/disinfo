import os
import json

from typing import Optional

from .data_structures import AppBaseModel

class MonitorConfig(AppBaseModel):
    # These are all the ha entities we are interested in.
    presence_sensors: list[str] = [
        'binary_sensor.ikea_pir_salon_occupancy',
        'binary_sensor.ikea_pir_kitchen_occupancy',
        'binary_sensor.ikea_pir_study_occupancy',
        'binary_sensor.presence',
        'binary_sensor.radar_salon_presence',
        'binary_sensor.radar_study_presence',
        'binary_sensor.radar_entree_presence',
        'binary_sensor.radar_kitchen_presence',
    ]
    ambient_light_sensors: list[str] = [
        'sensor.sensei_lux',
        'sensor.enviomental_lux',
    ]

class ShazamConfig(AppBaseModel):
    chunk: int = 1024
    channels: int = 1
    sample_rate: int = 48000
    record_duration: int = 6
    device_index: int = 6

class UDPPanel(AppBaseModel):
    ip: str
    size: int

class Config(AppBaseModel):
    devmode: bool = False

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
    ambient_light_sensor: str = 'sensor.radar_salon_light'
    presence_lag_minutes: int = 20

    monitors: MonitorConfig = MonitorConfig()

    # Panel
    width: int
    height: int
    name: str
    panel_host: Optional[str] = None
    brightness_divider: float = 400
    panel_gamma: float = 1.2

    udp_panel: list[UDPPanel] = []

    # Klipper
    klipper_host: str = '10.0.1.91'

    # Bambu
    bambu_printer_id: str = 'ender3'

    # Aviator
    adsbx_host: str = '10.0.1.131:8080'

    shazam: ShazamConfig = ShazamConfig()


    def replace(self, **kwargs):
        """
        Replace the config with new values.
        """
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
            else:
                raise ValueError(f'Config has no attribute {k}')


with open(os.environ.get('DI_CONFIG_PATH', '.config.json')) as f:
    app_config = Config(**json.load(f))
