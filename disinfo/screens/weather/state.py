import pendulum

from typing import Optional
from datetime import datetime, timedelta

from disinfo.config import app_config
from disinfo.data_structures import FrameState, AppBaseModel
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


def get_weather_data(fs: FrameState) -> WeatherState | None:
    weather_state = WeatherStateManager().get_state(fs)
    data = get_entity(app_config.weather_entity)
    
    sunset = get_entity('sensor.sun_next_dusk')
    sunrise = get_entity('sensor.sun_next_dawn')
    moon = get_entity('sensor.moon_phase')

    if not data:
        print('No weather entities found')
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

    weather = WeatherData(
        temperature=data.attributes.get('temperature', -42),
        condition=data.state,
        icon_name=ICON_MAP[data.state],
        t_high=forecast.temperature if forecast else -42,
        t_low=forecast.templow if forecast else -42,
        sunset_time=sunset.state if sunset else None,
        sunrise_time=sunrise.state if sunrise else None,
        moon_phase=MOON_PHASE_MAP[moon.state] if moon else None,
        updated_at=data.last_updated,
    )
    weather_state.data = weather
    weather_state.show_sunrise = fs.now < weather.sunset_time
    weather_state.show_sunset = weather.sunset_time < fs.now
    weather_state.show_moon_phase = True
    weather_state.is_outdated = not data.service_response
    return weather_state


class WeatherStateManager(PubSubStateManager[WeatherState]):
    model = WeatherState
    channels = ('di.pubsub.weather',)

    def get_state(self, fs: FrameState) -> WeatherState:
        if not self.state.valid:
            return self.state
        s = self.state.data
        # Sunset time is shown 5 hours before sunset.
        self.state.show_sunset = s.sunset_time > fs.now > s.sunset_time.subtract(hours=5)

        # Sunrise time is shown after sunset.
        self.state.show_sunrise = fs.now > s.sunset_time

        # Moon Phase is when sunset is shown and until 3 hours after sunset. (Always shown)
        self.state.show_moon_phase = True
        # If the state is not updated for 30 minutes, it's outdated.
        self.state.is_outdated = (fs.now - s.updated_at).total_seconds() > 30 * 60  # 30 mins.
        return self.state
