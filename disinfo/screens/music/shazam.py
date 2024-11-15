from disinfo.data_structures import FrameState, AppBaseModel
from disinfo.drat.app_states import PubSubMessage, PubSubStateManager
from disinfo import config
from disinfo.components.widget import Widget
from disinfo.components.text import Text, TextStyle, text
from disinfo.components.elements import StillImage, Frame
from disinfo.components.layouts import vstack, hstack
from disinfo.components.layers import div, DivStyle
from disinfo.components.scroller import HScroller
from disinfo.components.spriteim import SpriteIcon
from disinfo.components.widget import Widget
from disinfo.components.transitions import text_slide_in
from disinfo.components import fonts

from .utils import get_album_art

class RecognizedMusic(AppBaseModel):
    title: str = ''
    subtitle: str = ''
    coverart: str = ''


class ShazamStateManager(PubSubStateManager[RecognizedMusic]):
    model = RecognizedMusic
    channels = ('di.pubsub.shazam',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action != 'update':
            return
        print(self.state, "bb")

        if not data.payload:
            self.state = RecognizedMusic()
        
        self.state = RecognizedMusic(**data.payload)
        print(self.state)


hscroller_name = HScroller(size=33, pause_at_loop=True)
hscroller_subtitle = HScroller(size=33, pause_at_loop=True)


def content(fs: FrameState):
    state = ShazamStateManager().get_state(fs)
    if not state or not state.title:
        return None

    info = vstack([
        hscroller_name.set_frame(text(state.title)).draw(fs.tick),
        hscroller_subtitle.set_frame(text(state.subtitle)).draw(fs.tick),
    ])
    return hstack([
        get_album_art(state.coverart),
        info,
    ], gap=2).tag('shazam')

def widget(fs: FrameState) -> Widget:
    return Widget(
        name='shazam.recognized_music',
        frame=content(fs),
        priority=1,
   )
