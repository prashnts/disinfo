import websocket
import json
import time
import threading
import rich
import re

from rich.columns import Columns
from datetime import datetime
from collections import defaultdict
from pydantic.dataclasses import dataclass

from disinfo.config import app_config
from disinfo.data_structures import UniqInstance, AppBaseModel



class HaWeatherDatapoint(AppBaseModel):
    datetime: datetime
    condition: str
    temperature: float
    templow: float
    precipitation: float
    wind_speed: float
    wind_bearing: float
    humidity: float
    uv_index: float | None = None

class HaWeatherForecast(AppBaseModel):
    forecast: list[HaWeatherDatapoint]

ForecastServiceResponse = dict[str, HaWeatherForecast]

@dataclass(config=dict(extra="allow"))
class EntityAttributes:
    device_class: str | None = None
    state_class: str | None = None
    unit_of_measurement: str | None = None
    icon: str | None = None

class Entity(AppBaseModel):
    entity_id: str
    state: str
    attributes: dict | None
    last_changed: datetime
    last_updated: datetime
    last_reported: datetime | None
    service_response: HaWeatherForecast | None = None

class StateChangedEventData(AppBaseModel):
    entity_id: str
    old_state: Entity | None
    new_state: Entity | None

class EventData(AppBaseModel):
    event_type: str = "state_changed"
    time_fired: datetime
    data: StateChangedEventData

class ResponseResult(AppBaseModel):
    context: dict
    response: ForecastServiceResponse | None

class Msg(AppBaseModel):
    type: str
    id: int | None = None
    success: bool | None = None
    result: ResponseResult | list[Entity] | None = None
    event: EventData | None = None


class HaWSClient(metaclass=UniqInstance):
    def __init__(self):
        self.connected = False
        self._retries = 0
        self.retry_delay_before_max_retries = 5 # seconds
        self.retry_delay_after_max_retries = 25 # seconds
        self.max_retries = 5
        self._mid = 42
        self.host = app_config.ha_websocket_url
        self.db: dict[str, Entity] = {}
    
    def _counter(self) -> int:
        x = self._mid
        self._mid += 1
        return x
    
    def on_message(self, ws, msg):
        msg = Msg.model_validate_json(msg)

        match msg:
            case Msg(type="auth_required"):
                self.send("auth", access_token=app_config.ha_token.get_secret_value())
            case Msg(type="auth_ok"):
                self.send("subscribe_events", id=self._counter(), event_type="state_changed")
                self.send("get_states", id=self._counter())
            case Msg(result=[*entities]):
                for entity in entities:
                    self.db[entity.entity_id] = entity
            case Msg(event=event) if event and event.event_type == "state_changed":
                if new_state := event.data.new_state:
                    self.db[event.data.entity_id] = new_state
            case Msg(result=ResponseResult(response=response)) if isinstance(response, dict):
                for uid, data in response.items():
                    if uid in self.db:
                        self.db[uid].service_response = data
            case _:
                print(f'Unhandled message from HA: {msg}')

    def on_open(self, ws):
        self.connected = True
        self._retries = 0
        print(f'Connected to {self.host}')
    
    def on_close(self, *args):
        self.connected = False
        print(f'Disconnected to {self.host}, will retry.')
        self.retry_connect()
    
    def on_error(self, ws, *args, **kwargs):
        print(f'Error in connection to {self.host}: {args} {kwargs}')
        # self.connected = False

    def send(self, method: str, **kwargs) -> bool:
        print(method, kwargs, self.connected)
        if not self.connected:
            return False
        msg = {"type": method, **kwargs}
        self.ws.send(json.dumps(msg))
        return True

    def connect(self):
        if self.connected:
            return
        self.ws = websocket.WebSocketApp(
            self.host,
            on_message=self.on_message,
            on_open=self.on_open,
            on_close=self.on_close,
            on_error=self.on_error)
        
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()
    
    def retry_connect(self):
        if self.connected:
            return
        if self._retries > self.max_retries:
            time.sleep(self.retry_delay_after_max_retries)
        else:
            time.sleep(self.retry_delay_before_max_retries)
        print(f'Retrying connection to {self.host}... (attempt {self._retries})')
        self._retries += 1
        self.connect()


class HaWS(metaclass=UniqInstance):
    def __init__(self):
        self.client = HaWSClient()
        self.client.connect()
    
    def get_entity(self, entity_id: str) -> Entity | None:
        return self.client.db.get(entity_id)
    
    def grep_entities(self, pattern: str) -> list[Entity]:
        expr = re.compile(pattern)
        keys = [k for k in self.client.db.keys() if expr.match(k)]
        return [self.client.db[k] for k in keys]
    
    def call_service(self, name: str, **kwargs) -> bool:
        domain, service = name.split('.')
        return self.client.send("call_service", domain=domain, service=service, id=self.client._counter(), **kwargs)


def get_entity(entity_id: str) -> Entity | None:
    return HaWS().get_entity(entity_id)

def get_entities(pattern: str) -> list[Entity]:
    return HaWS().grep_entities(pattern)
