import pendulum

from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Generic, TypeVar

from . import idfm
from .data_service import get_metro_info
from .. import config
from ..redis import set_dict, get_dict, set_json, rkeys, db
from ..data_structures import FrameState
from ..utils.time import is_expired

StateModel = TypeVar('StateModel')

class MetroAppState(BaseModel):
    show: bool = False
    visible: bool = False
    valid: bool = False
    toggled_at: Optional[datetime] = None
    data: Optional[idfm.MetroData] = None


class CursorState(BaseModel):
    x: int = 120
    y: int = 42


class BaseStateManager(Generic[StateModel]):
    name: str
    model: BaseModel

    @property
    def value(self) -> StateModel:
        return self.model(**get_dict(self.name))

    def get_state(self, fs: FrameState) -> StateModel:
        return self.value

    def set_state(self, **kwargs):
        value = self.model(**{**self.value.dict(), **kwargs})
        set_json(self.name, value.json())

class MetroInfoStateManager(BaseStateManager[MetroAppState]):
    name = 'di.state.metroinfo'
    model = MetroAppState

    def process_mqtt_message(self, topic: str, msg: dict):
        # Executed in ha process!
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['scene_2', 'toggle']:
                self.manual_trigger()

    def manual_trigger(self):
        s = self.value
        show = s.show
        if is_expired(s.toggled_at, seconds=25):
            show = True
        else:
            show = not show

        self.set_state(show=show, toggled_at=pendulum.now())
        if show:
            # it was previously not visible, so we refresh.
            get_metro_info(force=True)

    def get_state(self, fs: FrameState):
        s = self.value
        s.data = idfm.MetroData(**get_dict(rkeys['metro_timing']))

        shown = s.show and not is_expired(s.toggled_at, seconds=25, now=fs.now)
        s.visible = idfm.is_active() or shown
        s.valid = not is_expired(s.data.timestamp, minutes=1, seconds=20, now=fs.now)

        return s


class RemoteState(BaseModel):
    action: str = ''

class RemoteStateManager(BaseStateManager[RemoteState]):
    model = RemoteState

    def __init__(self, name: str, topic: str):
        self.name = name
        self.topic = topic

    def process_mqtt_message(self, topic: str, msg: dict):
        # if topic == self.topic:
            # self.set_state()
        ...
class CursorStateManager(BaseStateManager[CursorState]):
    name = 'di.state.cursor'
    model = CursorState

    def process_mqtt_message(self, topic: str, msg: dict):
        v = self.value
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['color_saturation_step_up', 'brightness_up_click']:
                v.y -= 2
            if msg['action'] in ['color_saturation_step_down', 'brightness_down_click']:
                v.y += 2
            if msg['action'] in ['color_hue_step_up', 'arrow_right_click']:
                v.x += 2
            if msg['action'] in ['color_hue_step_down', 'arrow_left_click']:
                v.x -= 2
            v.x %= config.matrix_w
            v.y %= config.matrix_h
            set_json(self.name, v.json())


state_vars = [MetroInfoStateManager(), CursorStateManager()]
