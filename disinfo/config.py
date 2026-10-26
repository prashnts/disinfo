import os
import json

from pathlib import Path
from typing import Optional
from pydantic import SecretStr, field_validator

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
        'binary_sensor.radar_kitchen_radar_kitchen_presence',
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

screen_data_path = Path(os.environ.get('DI_SCREEN_DATA_PATH', Path(__file__).parent.parent / 'config' / 'screen_data.json'))

class AviatorData(AppBaseModel):
    # (lat, lon) of what's visible from the window.
    landmarks: list[tuple[float, float]] = []

class MetroStop(AppBaseModel):
    line: str               # as on the sign: '1', '3B'
    line_id: str            # IDFM's: 'C01371'
    stop_id: str            # the stop's zone: STIF:StopPoint:Q:<stop_id>:
    stop: str
    direction: str          # the trains going there, in their direction or destination
    walk_min: float | None = None       # over MetroData.walk_min

class MetroWindow(AppBaseModel):
    days: list[int] = [1, 2, 3, 4, 5]   # isoweekday: monday 1
    start: str = '07:00'
    end: str = '09:00'
    month_days: tuple[int, int] = (1, 31)

class MetroData(AppBaseModel):
    walk_min: float = 5     # trains sooner than this are left out
    stops: list[MetroStop] = []
    lines: list[str] = []   # their messages only
    schedule: list[MetroWindow] = []    # the card's in the bottom stack then, the button shows it any time

class ScreenData(AppBaseModel):
    # Shared by all the screens, from config/screen_data.json.
    aviator: AviatorData = AviatorData()
    metro: MetroData = MetroData()

def load_screen_data() -> ScreenData:
    if not screen_data_path.exists():
        return ScreenData()
    with open(screen_data_path) as f:
        return ScreenData(**json.load(f))

class Config(AppBaseModel):
    devmode: bool = False

    redis_host: str = 'localhost'

    # Homeassistant Websocket
    ha_websocket_url: str = 'wss://hass.amd.noop.pw/api/websocket'
    ha_base_url: str = 'https://hass.amd.noop.pw'
    ha_token: SecretStr | None = None

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

    oai_api_key: SecretStr = SecretStr('')
    oai_base_url: str = 'https://owui.amd.noop.pw/api/v1'

    # Panel
    width: int
    height: int
    name: str
    panel_host: Optional[str] = None
    brightness_divider: float = 400
    panel_gamma: float = 1.2

    udp_panel: list[UDPPanel] = []

    # Klipper
    klipper_host: str = 'limn.go.malow.im'


    # Bambu
    printer_ids: list[str] = []
    # printer id -> mjpeg url, shown in the card. Merged over the defaults.
    printer_streams: dict[str, str] = {'pi_limn2': 'https://endo.nb.malow.im/stream.mjpg'}
    # printer id -> Moonraker websocket, for live Klipper state. Merged over the defaults, HA otherwise.
    moonraker_urls: dict[str, str] = {'pi_limn2': 'wss://limn.nb.malow.im/websocket'}
    moonraker_api_key: SecretStr | None = None

    # Aviator
    overpass_url: str = 'https://overpass-api.de/api/interpreter'
    adsbx_url: str = 'https://adsb.nb.malow.im'
    meteo_france_api_key__radar: SecretStr | None = None
    meteo_france_api_key__vigil: SecretStr | None = None
    meteo_france_api_key__observations: SecretStr | None = None
    vigilance_domain: str = '75'      # the département on the weather card
    # Bearings seen from the window, clockwise from north. The planes in there get the cards.
    aviator_window: tuple[float, float] = (0, 180)
    # Solar only, local time.
    aviator_quiet: list[tuple[str, str]] = [('06:00', '07:30')]
    # The bearing up on this screen's map: where one faces looking at it (270: facing west).
    aviator_map_up: float = 0
    # The map's zoom on its view (the window's slice): under 1 it pulls out, centered on home at the end.
    aviator_zoom: float = 1
    # 'map': the radar from above, when there's something to see. 'sky': out of the window, the sun and the planes, always.
    # 'solar': the solar clock, no planes in the background.
    aviator_view: str = 'map'
    # The window's height over the street, m: the roofs around sit under the horizon or over it (11th floor).
    aviator_eye_m: float = 35
    # The light by the window (aviator/daylight.py): Sensei's lux and UV, the desk's colour sensor (its telemetry
    # node) and the lamps around it, taken off its counts.
    daylight_lux: str = 'sensor.sensei_lux'
    daylight_uv: str = 'sensor.sensei_uv'
    daylight_node: str = 'distudy'
    daylight_lamps: list[str] = ['light.ikea_driver_study_desk_left', 'light.ikea_driver_study_desk_right', 'light.ikea_e27_study_desklamp']

    shazam: ShazamConfig = ShazamConfig()

    screen_data: ScreenData = load_screen_data()

    # Music Widget
    speaker_entity: str = 'media_player.sonos_beam'
    weather_entity: str = 'weather.reuilly'
    # Indoors read the outside's pressure (weather/stations.py); the others are logged, to learn the window's later.
    weather_barometers: list[str] = ['sensor.sensei_pressure', 'sensor.nusr_pressure']
    weather_indoor_log: list[str] = ['sensor.sensei_temperature', 'sensor.sensei_humidity', 'sensor.sensei_bme680_temperature',
                                     'sensor.temp_average', 'sensor.alpstuga_air_quality_monitor_carbon_dioxide']


    @field_validator('printer_streams', 'moonraker_urls')
    @classmethod
    def _merge_defaults(cls, v, info):
        return {**cls.model_fields[info.field_name].default, **v}

    def replace(self, **kwargs):
        """
        Replace the config with new values.
        """
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
            else:
                raise ValueError(f'Config has no attribute {k}')


def load_config(path: str) -> Config:
    with open(path) as f:
        return Config(**json.load(f))

# Process wide config: services (HA, idfm, openai...) and the default screen.
# Drawing code must use fs.config, which is the config of the screen being drawn.
app_config = load_config(os.environ.get('DI_CONFIG_PATH', '.config.json'))
