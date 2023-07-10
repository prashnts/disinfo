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

from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Generic, TypeVar, Callable, Union
from disinfo.data_structures import FrameState


from . import idfm
from .. import config
from ..redis import get_dict, rkeys, db, publish
from ..data_structures import FrameState
from ..utils.time import is_expired

StateModel = TypeVar('StateModel')
class PubSubMessage(BaseModel):
    action: str
    payload: Optional[dict]


class StateManagerSingleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class PubSubManager(metaclass=StateManagerSingleton):
    def __init__(self):
        self.pubsub = db.pubsub()
        self.pubsub.psubscribe(**{'di.pubsub.*': self.handle_message})
        self.pubsub.run_in_thread(sleep_time=0.0001, daemon=True)
        self.subscribers = {}

    def handle_message(self, message):
        if not message or message['type'] != 'pmessage':
            return

        channel_name = message['channel'].decode()
        try:
            msg = PubSubMessage(**json.loads(message['data'].decode()))
        except KeyError:
            return

        for channels, callback in self.subscribers.values():
            if channel_name in channels:
                callback(channel_name, msg)

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

    def unpack_message(self, message):
        if not message or message['type'] != 'message':
            return
        try:
            data = json.loads(message['data'].decode())
            self.process_message(message['channel'].decode(), PubSubMessage(**data))
        except KeyError:
            pass

    def process_message(self, channel: str, data: PubSubMessage):
        raise NotImplemented

    def get_state(self, fs: Optional[FrameState] = None) -> StateModel:
        return self.state

class MetroAppState(BaseModel):
    show: bool = False
    visible: bool = False
    valid: bool = False
    toggled_at: Optional[datetime] = None
    data: Optional[idfm.MetroData] = None

class MetroAppStateManager(PubSubStateManager[MetroAppState]):
    model = MetroAppState
    channels = ('di.pubsub.metro', 'di.pubsub.remote')

    # TODO support intializing the inner states.

    def process_message(self, channel: str, data: PubSubMessage):
        if channel.endswith('.metro'):
            if data.action == 'update':
                self.update_data()
            if data.action == 'toggle':
                self.toggle()
        if channel.endswith('.remote'):
            if data.action == 'btn_metro':
                self.toggle()

    def initial_state(self) -> MetroAppState:
        return MetroAppState(data=self.load_timing())

    def toggle(self):
        s = self.state
        show = s.show
        if is_expired(s.toggled_at, seconds=25):
            show = True
        else:
            show = not show
        if show:
            publish('di.pubsub.dataservice', action='fetch_metro')
        self.state.show = show
        self.state.toggled_at = pendulum.now()

    def load_timing(self):
        return idfm.MetroData(**get_dict(rkeys['metro_timing']))

    def update_data(self):
        self.state.data = self.load_timing()

    def get_state(self, fs: FrameState):
        s = self.state
        if not s.data:
            s.visible = False
            s.valid = False
        else:
            shown = s.show and not is_expired(s.toggled_at, seconds=25, now=fs.now)
            s.visible = idfm.is_active() or shown
            s.valid = not is_expired(s.data.timestamp, minutes=1, seconds=20, now=fs.now)

        return s


class CursorState(BaseModel):
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
        self.state.x %= config.matrix_w
        self.state.y %= config.matrix_h


class RemoteState(BaseModel):
    action: str = 'unknown'
    pressed_at: Optional[datetime]

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
