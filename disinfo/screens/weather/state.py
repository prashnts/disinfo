import pendulum

from typing import Optional
from datetime import datetime

from disinfo.data_structures import FrameState, AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage


class WeatherData(AppBaseModel):
    temperature: float = 25.0
    condition: str = 'Sunny'
    icon_name: str = 'clear-day'
    t_high: float = 30.0
    t_low: float = 20.0
    sunset_time: Optional[datetime]
    sunrise_time: Optional[datetime]
    updated_at: Optional[datetime]
    moon_phase: int = 50

class WeatherState(AppBaseModel):
    data: WeatherData = WeatherData()
    valid: bool = False
    show_sunrise: bool = False
    show_sunset: bool = False
    show_moon_phase: bool = False
    is_outdated: bool = True

class WeatherStateManager(PubSubStateManager[WeatherState]):
    model = WeatherState
    channels = ('di.pubsub.weather',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            forecast = data.payload
            _today = forecast['daily']['data'][0]
            _tomorrow = forecast['daily']['data'][1]
            self.state.data = WeatherData(
                temperature=forecast['currently']['apparentTemperature'],
                condition=forecast['currently']['summary'],
                icon_name=forecast['currently']['icon'],
                t_high=_today['temperatureHigh'],
                t_low=_today['temperatureLow'],
                sunset_time=pendulum.from_timestamp(_today['sunsetTime'], tz='local'),
                sunrise_time=pendulum.from_timestamp(_tomorrow['sunriseTime'], tz='local'),
                updated_at=pendulum.from_timestamp(forecast['currently']['time'], tz='local'),
                moon_phase=(_today['moonPhase'] * 100) % 100,
            )
            self.state.valid = True

    def get_state(self, fs: FrameState) -> WeatherState:
        if not self.state.valid:
            return self.state
        s = self.state.data
        # Sunset time is shown 2 hours before sunset.
        self.state.show_sunset = s.sunset_time > fs.now and (s.sunset_time - fs.now).total_seconds() < 2 * 60 * 60

        # Sunrise time is shown after sunset.
        self.state.show_sunrise = s.sunrise_time > fs.now and s.sunrise_time > s.sunset_time

        # Moon Phase is when sunset is shown and until 3 hours after sunset.
        self.state.show_moon_phase = self.state.show_sunset or (fs.now - s.sunset_time).total_seconds() < 3 * 60 * 60
        # If the state is not updated for 30 minutes, it's outdated.
        self.state.is_outdated = (fs.now - s.updated_at).total_seconds() > 30 * 60  # 30 mins.
        return self.state
