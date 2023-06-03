import pendulum

from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from . import idfm
from .data_service import get_metro_info
from ..redis import set_dict, get_dict, set_json, rkeys
from ..data_structures import FrameState
from ..utils.time import is_expired


class MetroAppState(BaseModel):
    show: bool = False
    visible: bool = False
    valid: bool = False
    toggled_at: Optional[datetime] = None
    data: Optional[idfm.MetroData] = None


class MetroInfoStateManager:
    name = 'di.state.metroinfo'
    value: MetroAppState

    def refresh(self):
        self.value = MetroAppState(**get_dict(self.name))

    def process_mqtt_message(self, topic: str, msg: dict):
        # Executed in ha process!
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['scene_2', 'toggle']:
                visible = self.value.show
                if is_expired(self.value.toggled_at, seconds=25):
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
        s = self.value
        s.data = idfm.MetroData(**get_dict(rkeys['metro_timing']))

        shown = s.show and not is_expired(s.toggled_at, seconds=25, now=fs.now)
        s.visible = idfm.is_active() or shown
        s.valid = not is_expired(s.data.timestamp, minutes=1, seconds=20, now=fs.now)

        return s


state_vars = [MetroInfoStateManager()]
