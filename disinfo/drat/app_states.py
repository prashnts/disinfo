'''
State managers

Data Source: A place where we fetch or receive certain data.
Sources: Periodic / On demand HTTP Requests, MQTT
State Store: Redis is used to cache the states. Also used to connect multiple processes together.
Application State

Need: PubSub

A subscriber thread is created. The thread hold a slot for state variable and updates it in background.



'''

import pendulum
import json
import time

from datetime import datetime
from typing import Optional, Generic, TypeVar, Callable, Union
from scipy.interpolate import interp1d

from . import idfm
from ..config import app_config
from ..redis import get_dict, rkeys, db, publish
from ..data_structures import FrameState, AppBaseModel, UniqInstance
from ..utils.time import is_expired

StateModel = TypeVar('StateModel')
class PubSubMessage(AppBaseModel):
    action: str
    payload: Optional[dict]


class PubSubManager(metaclass=UniqInstance):
    def __init__(self):
        self.pubsub = db.pubsub()
        self.pubsub.psubscribe(**{'di.pubsub.*': self.handle_message})
        self.pubsub.run_in_thread(sleep_time=0.001, daemon=True)
        self.subscribers = {}

    def handle_message(self, message):
        if not message or message['type'] != 'pmessage':
            return

        channel_name = message['channel'].decode()
        try:
            data = json.loads(message['data'].decode())
            action = data['_action']
            del data['_action']
            payload = data
            msg = PubSubMessage(action=action, payload=payload)
        except KeyError:
            return

        for channels, callback in self.subscribers.values():
            if channel_name in channels:
                try:
                    callback(channel_name, msg)
                except Exception as e:
                    print(f'[PubSub] Error in callback: {e}')

    def attach(self, uid: str, channels: tuple[str], callback: Callable):
        if uid not in self.subscribers:
            self.subscribers[uid] = (channels, callback)
        return self

class PubSubStateManager(Generic[StateModel], metaclass=UniqInstance):
    model: StateModel
    channels: tuple[str]

    def __init__(self):
        self.manager = PubSubManager().attach(self._uid(), self.channels, self.process_message)
        self.state = self.initial_state()

    def _uid(self) -> str:
        return self.__class__.__name__

    def initial_state(self) -> StateModel:
        return self.model()

    def process_message(self, channel: str, data: PubSubMessage):
        raise NotImplemented

    def get_state(self, fs: Optional[FrameState] = None) -> StateModel:
        return self.state



class CursorState(AppBaseModel):
    x: int = 120
    y: int = 42

class CursorStateManager(PubSubStateManager[CursorState]):
    model = CursorState
    channels = ('di.pubsub.remote',)

    # TODO: acceleration

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'up':
            self.state.y -= 1
        if data.action == 'down':
            self.state.y += 1
        if data.action == 'left':
            self.state.x -= 1
        if data.action == 'right':
            self.state.x += 1
        self.state.x %= app_config.width
        self.state.y %= app_config.height


class RemoteState(AppBaseModel):
    action: str = 'unknown'
    pressed_at: Optional[datetime] = None
    is_visible: bool = False
    show_debug: bool = False

class RemoteStateManager(PubSubStateManager[RemoteState]):
    model = RemoteState
    channels = ('di.pubsub.remote',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action != self.state.action and data.action != 'unknown':
            self.state.show_debug = data.action == 'btn_debug'
        self.state.action = data.action
        self.state.pressed_at = pendulum.now()
        self.state.is_visible = not self.state.is_visible

    def get_state(self, fs: FrameState) -> RemoteState:
        s = self.state
        if is_expired(s.pressed_at, seconds=1, now=fs.now):
            self.state.action = 'unknown'
        return s

class PresenceSensorState(AppBaseModel):
    detected: bool = True
    detected_at: Optional[datetime] = None

    def present_at(self, now: datetime) -> bool:
        expired = is_expired(self.detected_at, minutes=app_config.presence_lag_minutes, now=now)
        return not expired

class PresenceSensorStateManager(PubSubStateManager[PresenceSensorState]):
    model = PresenceSensorState
    channels = ('di.pubsub.presence',)

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        super().__init__()

    def _uid(self) -> str:
        return f'{self.__class__.__name__}.{self.entity_id}'

    def initial_state(self) -> PresenceSensorState:
        return PresenceSensorState(detected=True, detected_at=pendulum.now())

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update' and data.payload['entity_id'] == self.entity_id:
            self.state.detected = data.payload['new_state']['state'] == 'on'
            if self.state.detected:
                self.state.detected_at = pendulum.now()


brightness_min: float = 10
brightness_max: float = 90
brightness_curve = [
    # LUX   BRIGHTNESS %
    [0,   10],
    [50,  10],
    [82,  40],
    [90,  50],
    [120, 75],
    [150, 80],
    [200, 90],
]
brightness_interpolator = interp1d(
    *zip(*brightness_curve),
    bounds_error=False,
    fill_value=(brightness_min, brightness_max),
)

class LightSensorState(AppBaseModel):
    lux: float = 100

    @property
    def brightness(self) -> int:
        return int(brightness_interpolator(self.lux))

class LightSensorStateManager(PubSubStateManager[LightSensorState]):
    model = LightSensorState
    channels = ('di.pubsub.lux',)

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        super().__init__()

    def _uid(self) -> str:
        return f'{self.__class__.__name__}.{self.entity_id}'

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update' and data.payload['entity_id'] == self.entity_id:
            self.state.lux = float(data.payload['new_state']['state'])
