from urllib.parse import urlparse, parse_qs

from ..utils.drawer import draw_loop
from ..utils.mjpeg import MJPEGStream
from disinfo import fonts
from discore.layouts import composite_at
from discore.elements import Frame
from discore.text import text
from discore.data_structures import FrameState
from discore.widget import Widget
from ..drat.app_states import RuntimeStateManager

def draw_stream(fs: FrameState) -> Frame | None:
    state = RuntimeStateManager().get_state(fs)
    url = state.stream_url
    # The stream client stops by itself once we stop reading it.
    if not url or not state.show_stream:
        return
    if not (frame := MJPEGStream(url).read(width=120)):
        return
    name = parse_qs(urlparse(url).query).get('src', [url])[0]
    return composite_at(text(name, font=fonts.two_slice), frame, 'bl').tag('stream')

draw = draw_loop(draw_stream, use_threads=True)

def widget(fs: FrameState):
    return Widget('stream', draw(fs), priority=0.5, wait_time=8)
