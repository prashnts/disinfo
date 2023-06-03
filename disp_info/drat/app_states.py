import pendulum

from datetime import datetime
from pydantic import BaseModel
from dataclasses import dataclass
from typing import Optional, Union

from ..redis import set_dict, get_dict, set_json, rkeys
from ..data_structures import FrameState
from .data_service import get_metro_info
from . import idfm


class TrainTiming(BaseModel):
    next_in: float
    retarded: bool

class TrainInformation(BaseModel):
    messages: list[str]
    issues: bool
class MetroTrain(BaseModel):
    line: str
    line_id: str
    stop: str
    stop_id: str
    direction: str
    timings: list[TrainTiming]
    information: TrainInformation

class MetroInformation(BaseModel):
    line: str
    line_id: str
    messages: list[str]
    issues: bool

class MetroData(BaseModel):
    trains: list[MetroTrain]
    information: list[MetroInformation]
    timestamp: datetime

class MetroAppState(BaseModel):
    show: bool = False
    visible: bool = False
    valid: bool = False
    toggled_at: Optional[datetime] = None
    data: Optional[MetroData] = None


def in_future(dt: Union[str, pendulum.DateTime, datetime, None], seconds: int = 0, minutes: int = 0):
    if not dt:
        return False
    if isinstance(dt, str):
        dt = pendulum.parse(dt)
    if isinstance(dt, datetime):
        dt = pendulum.instance(dt)
    return dt.add(seconds=seconds, minutes=minutes) > pendulum.now()

class MetroInfoState:
    name = 'di.state.metroinfo'
    default_state = {'show': False, 'toggle_time': None}
    value: MetroAppState

    def refresh(self):
        self.value = MetroAppState(**get_dict(self.name))

    def process_mqtt_message(self, topic: str, msg: dict):
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['scene_2', 'toggle']:
                visible = self.value.show
                if in_future(self.value.toggled_at, seconds=25):
                    visible = not visible
                else:
                    visible = True

                self.set_state(show=visible, toggled_at=pendulum.now().isoformat())
                if visible:
                    # it was previously not visible, so we refresh.
                    get_metro_info(force=True)

    def set_state(self, **kwargs):
        self.value = MetroAppState(**{**self.value.dict(), **kwargs})
        set_json(self.name, self.value.json())

    def get_state(self, fs: FrameState, refresh: bool = True):
        if refresh:
            self.refresh()
        state = self.value
        state.data = MetroData(**get_dict(rkeys['metro_timing']))

        shown = state.show and in_future(state.toggled_at, seconds=25)
        state.visible = idfm.is_active() or shown
        state.valid = in_future(state.data.timestamp, minutes=1, seconds=20)

        return state


state_vars = [MetroInfoState()]
