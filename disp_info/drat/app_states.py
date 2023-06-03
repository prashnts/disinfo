from ..redis import set_dict, get_dict
from .data_service import get_metro_info
from . import idfm


class MetroInfoState:
    name = 'di.state.metroinfo'
    default_state = {'show': False}
    value: dict

    def refresh(self):
        self.value = get_dict(self.name, self.default_state)

    def process_mqtt_message(self, topic: str, msg: dict):
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['scene_2', 'toggle']:
                visible = self.value['show']
                self.set_state(show=not visible)
                if not visible:
                    # it was previously not visible, so we refresh.
                    get_metro_info(force=True)

    def set_state(self, **kwargs):
        self.value = {**self.value, **kwargs}
        set_dict(self.name, self.value)

    def get_state(self, refresh: bool = True):
        if refresh:
            self.refresh()
        state = self.value
        state['visible'] = idfm.is_active() or state['show']

        return state


state_vars = [MetroInfoState()]
