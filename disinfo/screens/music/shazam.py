from disinfo.data_structures import FrameState, AppBaseModel
from disinfo.drat.app_states import PubSubMessage, PubSubStateManager
from disinfo.config import app_config
from disinfo.components.widget import Widget
from disinfo.components.text import TextStyle, text
from disinfo.components.layouts import vstack, hstack
from disinfo.components.layers import div, DivStyle
from disinfo.components.scroller import HScroller
from disinfo.components.widget import Widget
from disinfo.components import fonts
from disinfo.utils.cairo import load_svg

from .utils import get_album_art

shazam_icon = load_svg('assets/shazam-icon.svg', scale=0.15)

class RecognizedMusic(AppBaseModel):
    title: str = ''
    subtitle: str = ''
    coverart: str = ''

    is_recording: bool = False

class ShazamStateManager(PubSubStateManager[RecognizedMusic]):
    model = RecognizedMusic
    channels = ('di.pubsub.shazam',)

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'begin-recording':
            self.state.is_recording = True
            return
        elif data.action == 'end-recording':
            self.state.is_recording = False
            return

        if data.action != 'update':
            return

        if not data.payload:
            self.state = RecognizedMusic()
        
        self.state = RecognizedMusic(**data.payload)


hscroller_name = HScroller(size=33, pause_at_loop=True)
hscroller_subtitle = HScroller(size=33, pause_at_loop=True)

s_title = TextStyle(font=fonts.bitocra7, color='#2C552A')
s_subtitle = TextStyle(font=fonts.bitocra7, color='#474C52')


def content(fs: FrameState):
    state = ShazamStateManager().get_state(fs)
    if not state.title:
        return None

    info = vstack([
        hscroller_name.set_frame(text(state.title, s_title)).draw(fs.tick),
        hscroller_subtitle.set_frame(text(state.subtitle, s_subtitle)).draw(fs.tick),
    ], gap=1)
    return hstack([
        get_album_art(state.coverart),
        info,
    ], gap=2).tag('shazam' + state.title)

def indicator(fs: FrameState):
    state = ShazamStateManager().get_state(fs)
    if not state.is_recording:
        return None
    return div(
        shazam_icon,
        DivStyle(padding=1)
    )

def widgets(fs: FrameState) -> Widget:
    return [
        Widget(
            name='shazam.recording',
            frame=indicator(fs),
            priority=1,
            wait_time=app_config.shazam.record_duration,
        ),
        Widget(
            name='shazam.recognized_music',
            frame=content(fs),
            priority=1,
            wait_time=5,
        ),
    ]
