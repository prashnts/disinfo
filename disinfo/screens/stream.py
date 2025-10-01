import io
from PIL import Image
from mjpeg.client import MJPEGClient

from .drawer import draw_loop
from ..components.layers import div, DivStyle
from ..components.elements import Frame, StillImage
from ..data_structures import FrameState, AppBaseModel
from ..components.widget import Widget

url = "https://kvm.as.noop.pw/streamer/stream"

def setup_stream():
    client = MJPEGClient(url)

    # Allocate memory buffers for frames
    bufs = client.request_buffers(365536, 50)
    for b in bufs:
        client.enqueue_buffer(b)
        
    # Start the client in a background thread
    client.start()

    while True:
        buf = client.dequeue_buffer()
        with io.BytesIO(buf.data) as buffer:
            img = Image.open(buffer).rotate(90)
            ratio = min(190/img.width, 190/img.height)
            img = img.resize((int(img.width*ratio), int(img.height*ratio)))
            yield img
        client.enqueue_buffer(buf)

_stream = setup_stream()

def stream_frame(fs):
    global _stream
    img = next(_stream)
    img = img.convert('RGBA')
    # img = img.resize((64, 64))
    return Frame(img, hash=('mjpeg', url)).tag('stream')

draw = draw_loop(stream_frame, use_threads=True, sleepms=10)

def widget(fs: FrameState):
    return Widget('stream', draw(fs), priority=0.5, wait_time=8)
