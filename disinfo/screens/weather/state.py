import pendulum

from typing import Optional
from datetime import datetime

from disinfo.data_structures import FrameState, AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage


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
    valid: bool = False
    show_sunrise: bool = True
    show_sunset: bool = True
    show_moon_phase: bool = True
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
                temperature=forecast['currently']['temperature'],
                condition=forecast['currently']['summary'],
                icon_name=forecast['currently']['icon'],
                t_high=_today['temperatureHigh'],
                t_low=_today['temperatureLow'],
                sunset_time=pendulum.from_timestamp(_today['sunsetTime'], tz='local'),
                sunrise_time=pendulum.from_timestamp(_tomorrow['sunriseTime'], tz='local'),
                updated_at=pendulum.from_timestamp(forecast['currently']['time'], tz='local'),
                moon_phase=int((_today['moonPhase'] * 100) % 100),
            )
            self.state.valid = True

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
