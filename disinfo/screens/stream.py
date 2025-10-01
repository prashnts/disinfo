import io
from PIL import Image
from mjpeg.client import MJPEGClient

from .drawer import draw_loop
from ..components.layers import div, DivStyle
from ..components.elements import Frame, StillImage
from ..data_structures import FrameState, AppBaseModel
from ..components.widget import Widget

url = "https://kvm.as.noop.pw/streamer/stream"

_image = None

def setup_stream():
    global _image
    client = MJPEGClient(url)

    # Allocate memory buffers for frames
    bufs = client.request_buffers(565536, 50)
    for b in bufs:
        client.enqueue_buffer(b)
        
    # Start the client in a background thread
    client.start()

    while True:
        buf = client.dequeue_buffer()
        with io.BytesIO(buf.data) as buffer:
            img = Image.open(buffer)
            ratio = min(120/img.width, 120/img.height)
            _image = img.resize((int(img.width*ratio), int(img.height*ratio))).convert('RGBA')
        client.enqueue_buffer(buf)

_stream = setup_stream()

def stream_frame(fs):
    global _stream
    return Frame(_image, hash=('mjpeg', url)).tag('stream')

draw = draw_loop(stream_frame, use_threads=True, sleepms=10)

def widget(fs: FrameState):
    return Widget('stream', draw(fs), priority=0.5, wait_time=8)
