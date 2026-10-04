from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubMessage, PubSubStateManager
from discore.widget import Widget
from discore.text import TextStyle, text
from discore.layouts import vstack, hstack
from discore.layers import div, DivStyle
from discore.scroller import HScroller
from discore.widget import Widget
from disinfo import fonts
from discore.cairo import load_svg

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


# Scrollers are looked up per screen, so each screen scrolls on its own.
hscroller_name = lambda: HScroller(size=33, pause_at_loop=True, name='shazam.name')
hscroller_subtitle = lambda: HScroller(size=33, pause_at_loop=True, name='shazam.subtitle')

s_title = TextStyle(font=fonts.bitocra7, color='#2C552A')
s_subtitle = TextStyle(font=fonts.bitocra7, color='#474C52')


def content(fs: FrameState):
    state = ShazamStateManager().get_state(fs)
    if not state.title:
        return None

    info = vstack([
        hscroller_name().set_frame(text(state.title, s_title)).draw(fs.tick),
        hscroller_subtitle().set_frame(text(state.subtitle, s_subtitle)).draw(fs.tick),
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
            name='shazam.recognized_music',
            frame=content(fs),
            priority=1,
            wait_time=5,
        ),
    ]

def indicators(fs: FrameState) -> Widget:
    return Widget(
        name='shazam.recording',
        frame=indicator(fs),
        priority=1,
        wait_time=fs.config.shazam.record_duration,
    )
