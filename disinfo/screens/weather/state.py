import pendulum

from typing import Optional
from datetime import datetime, timedelta

from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage, StateManager
from disinfo.utils.hass import get_entity, Entity, HaWS


ICON_MAP = {
    'clear-night': 'clear-night',
    'cloudy': 'cloudy',
    'fog': 'fog',
    'hail': 'sleet',
    'lightning': 'thunderstorm',
    'rainy': 'rain',
    'lightning-rainy': 'thunderstorm',
    'partlycloudy': 'partly-cloudy',
    'snowy': 'snow',
    'snowy-rainy': 'sleet',
    'pouring': 'rain',
    'sunny': 'clear-day',
    'windy': 'wind',
    'windy-variant': 'wind',
    'exceptional': 'none',
    'unavailable': 'none',
}
MOON_PHASE_MAP = {
    'new_moon': 00,
    'waxing_crescent': 12,
    'first_quarter': 25,
    'waxing_gibbous': 38,
    'full_moon': 50,
    'waning_gibbous': 62,
    'last_quarter': 75,
    'waning_crescent': 88,
}


class WeatherData(AppBaseModel):
    temperature: float = 1.0
    condition: str = 'Snow'
    icon_name: str = 'sleet'
    t_high: float = 5.0
    t_low: float = 0
    sunset_time: Optional[datetime] = pendulum.now().set(hour=19, minute=0, second=0)
    sunrise_time: Optional[datetime] = pendulum.now().set(hour=7, minute=0, second=0)
    updated_at: Optional[datetime] = pendulum.now()
    moon_phase: int = 10

class WeatherState(AppBaseModel):
    data: WeatherData = WeatherData()
    weather_entity: Entity | None = None

    refreshed_at: int = 0

    valid: bool = False
    show_sunrise: bool = True
    show_sunset: bool = True
    show_moon_phase: bool = True
    is_outdated: bool = True

class WeatherStateManager(StateManager[WeatherState]):
    model = WeatherState


sure_decimal = 0.7         # the sky state's temperature this sure: shown to a tenth

def icon_of(d: dict) -> str:
    '''The sky state -> an icon: storm, what falls, fog, wind, then the cloud.'''
    from disinfo.screens.aviator.skystate import v
    night = v(d, 'time.sun.alt', 10) < -0.833
    if any('TS' in w for w in v(d, 'air.wx') or []):
        return 'thunderstorm'
    if v(d, 'precip.rate', 0, conf=0.3) >= 0.1:
        snow = v(d, 'precip.snow', 0)
        return 'snow' if snow > 0.7 else 'sleet' if snow > 0.3 else 'rain'
    if (v(d, 'air.vis') or 1e5) < 1000:
        return 'fog'
    if v(d, 'air.gust', 0, conf=0.3) > 15:
        return 'wind'
    cover = v(d, 'sky.cover', 0.5)
    if cover < 0.25:
        return 'clear-night' if night else 'clear-day'
    return 'cloudy' if cover > 0.75 else 'partly-cloudy-night' if night else 'partly-cloudy-day'

def from_sky(d: dict | None) -> dict | None:
    # The card's values from the sky state (the stations, the models blended), None without its temperature.
    t = (d or {}).get('air', {}).get('temp')
    if not t:
        return None
    today = (d.get('forecast') or {}).get('today') or {}
    return {'temperature': round(t['v'], 1) if t['conf'] >= sure_decimal else round(t['v']), 'icon_name': icon_of(d),
            't_high': today.get('high'), 't_low': today.get('low'), 'outdated': d['sources'].get('stations') is None}

def get_weather_data(fs: FrameState) -> WeatherState | None:
    weather_state = WeatherStateManager().get_state(fs)
    data = get_entity(fs.config.weather_entity)
    
    sunset = get_entity('sensor.sun_next_dusk')
    sunrise = get_entity('sensor.sun_next_dawn')
    moon = get_entity('sensor.moon_phase')

    if not data:
        return None

    if fs.tick > (weather_state.refreshed_at + 15 * 60) or not data.service_response:
        ok = HaWS().call_service(
            'weather.get_forecasts',
            service_data={'type': 'daily'},
            target={'entity_id': data.entity_id},
            return_response=True)
        if ok:
            weather_state.refreshed_at = fs.tick
    forecast = data.service_response.forecast[0] if data.service_response else None 
    from disinfo.screens.aviator import skystate
    sky = from_sky(skystate.doc())

    weather = WeatherData(
        temperature=sky['temperature'] if sky else data.attributes.get('temperature', -42),
        condition=data.state,
        icon_name=sky['icon_name'] if sky else ICON_MAP[data.state],
        t_high=sky['t_high'] if sky and sky['t_high'] is not None else forecast.temperature if forecast else -42,
        t_low=sky['t_low'] if sky and sky['t_low'] is not None else forecast.templow if forecast else -42,
        sunset_time=sunset.state if sunset else None,
        sunrise_time=sunrise.state if sunrise else None,
        moon_phase=MOON_PHASE_MAP[moon.state] if moon else None,
        updated_at=data.last_updated,
    )
    weather_state.data = weather
    weather_state.show_sunrise = fs.now < weather.sunset_time
    weather_state.show_sunset = weather.sunset_time < fs.now
    weather_state.show_moon_phase = True
    weather_state.is_outdated = sky['outdated'] if sky else not data.service_response
    return weather_state
