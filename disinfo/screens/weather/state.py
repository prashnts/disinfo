import pendulum

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from disinfo.data_structures import FrameState
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage


class WeatherData(BaseModel):
    temperature: float = 25.0
    condition: str = 'Sunny'
    icon_name: str = 'clear-day'
    t_high: float = 30.0
    t_low: float = 20.0
    sunset_time: Optional[datetime]
    updated_at: Optional[datetime]

class WeatherState(BaseModel):
    data: WeatherData = WeatherData()
    valid: bool = False
    should_show_sunset: bool = False
    is_outdated: bool = True

class WeatherStateManager(PubSubStateManager[WeatherState]):
    model = WeatherState
    channels = ('di.pubsub.weather',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            forecast = data.payload
            _today = forecast['daily']['data'][0]
            self.state.data = WeatherData(
                temperature=forecast['currently']['apparentTemperature'],
                condition=forecast['currently']['summary'],
                icon_name=forecast['currently']['icon'],
                t_high=_today['temperatureHigh'],
                t_low=_today['temperatureLow'],
                sunset_time=pendulum.from_timestamp(_today['sunsetTime'], tz='local'),
                updated_at=pendulum.from_timestamp(forecast['currently']['time'], tz='local'),
            )
            self.state.valid = True

    def get_state(self, fs: FrameState) -> WeatherState:
        if not self.state.valid:
            return self.state
        s = self.state.data
        self.state.should_show_sunset = s.sunset_time > fs.now and (s.sunset_time - fs.now).total_seconds() < 2 * 60 * 60
        self.state.is_outdated = (fs.now - s.updated_at).total_seconds() > 30 * 60  # 30 mins.
        return self.state
