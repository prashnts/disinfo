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
from pydantic import computed_field
from typing import Optional, Generic, TypeVar, Callable, Union
from scipy.interpolate import interp1d

from . import idfm
from ..config import app_config
from ..redis import get_dict, rkeys, db, publish
from ..data_structures import FrameState, AppBaseModel
from ..utils.time import is_expired

StateModel = TypeVar('StateModel')
class PubSubMessage(AppBaseModel):
    action: str
    payload: Optional[dict]


class StateManagerSingleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        key = (cls, args, tuple(kwargs.items()))
        if key not in cls._instances:
            cls._instances[key] = super().__call__(*args, **kwargs)
        return cls._instances[key]


class PubSubManager(metaclass=StateManagerSingleton):
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

class PubSubStateManager(Generic[StateModel], metaclass=StateManagerSingleton):
    model: StateModel
    channels: tuple[str]

    def __init__(self):
        PubSubManager().attach(self.__class__.__name__, self.channels, self.process_message)
        self.state = self.initial_state()

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
        self.state.x %= app_config.matrix_w
        self.state.y %= app_config.matrix_h


class RemoteState(AppBaseModel):
    action: str = 'unknown'
    pressed_at: Optional[datetime] = None

class RemoteStateManager(PubSubStateManager[RemoteState]):
    model = RemoteState
    channels = ('di.pubsub.remote',)

    def process_message(self, channel: str, data: PubSubMessage):
        self.state.action = data.action
        self.state.pressed_at = pendulum.now()

    def get_state(self, fs: FrameState) -> RemoteState:
        s = self.state
        if is_expired(s.pressed_at, seconds=1, now=fs.now):
            return RemoteState(action='unknown')
        return s

class PresenceSensorState(AppBaseModel):
    detected: bool = True
    detected_at: Optional[datetime] = None

    def present_at(self, now: datetime) -> bool:
        delay = 2 if 8 <= now.hour < 23 else 2
        expired = is_expired(self.detected_at, minutes=delay, now=now)
        print(f"expired {expired} at {self.detected_at} now {now}")
        return self.detected and not expired

class PresenceSensorStateManager(PubSubStateManager[PresenceSensorState]):
    model = PresenceSensorState
    channels = ('di.pubsub.presence',)

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        super().__init__()

    def initial_state(self) -> PresenceSensorState:
        return PresenceSensorState(detected=True, detected_at=pendulum.now())

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update' and data.payload['entity_id'] == self.entity_id:
            self.state = PresenceSensorState(
                detected=data.payload['new_state']['state'] == 'on',
                detected_at=pendulum.now(),
            )

            print(self.state, data.payload['new_state']['state'])

            # if s.present:
            #     # when motion is detected, it's on.
            #     s.detected = True
            # else:
            #     # When motion is NOT detected, we want to keep the display on
            #     # for 30 minutes during day (8h -> 23h), otherwise 5 minutes.
            #     # this time is in local timezone.
            #     last_change = pendulum.parse(data.payload['_timestamp'])
            #     now = pendulum.now()
            #     delay = 30 if 8 <= now.hour < 23 else 5
            #     delta = (now - last_change).total_seconds()
            #     s.detected = delta <= 60 * delay
            # s.detected_at = pendulum.now()
            # self.state = s


brightness_min: float = 10
brightness_max: float = 100
brightness_curve = [
    # LUX   BRIGHTNESS %
    [0.2,   10],
    [2,     20],
    [5,     40],
    [20,    60],
    [50,    70],
    [200,   95],
    [400,  100],
]
brightness_interpolator = interp1d(
    *zip(*brightness_curve),
    bounds_error=False,
    fill_value=(brightness_min, brightness_max),
)

class LightSensorState(AppBaseModel):
    lux: float = 50.0

    @computed_field
    @property
    def brightness(self) -> int:
        return int(brightness_interpolator(self.lux))

class LightSensorStateManager(PubSubStateManager[LightSensorState]):
    model = LightSensorState
    channels = ('di.pubsub.lux',)

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        super().__init__()

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update' and data.payload['entity_id'] == self.entity_id:
            self.state.lux = float(data.payload['new_state']['state'])
