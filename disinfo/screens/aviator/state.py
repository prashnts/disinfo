import pendulum

from typing import Optional
from datetime import datetime

from disinfo.data_structures import FrameState, AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage

class ADSBxStateManager(PubSubStateManager[list]):
    model = list
    channels = ('di.pubsub.aviator',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            self.state = data.payload['planes']
