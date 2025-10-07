import io
import time
from PIL import Image
from mjpeg.client import MJPEGClient

from .drawer import draw_loop
from ..components.layers import div, DivStyle
from ..components.elements import Frame, StillImage
from ..data_structures import FrameState, AppBaseModel
from ..components.widget import Widget

url = "https://kvm.amd.noop.pw/streamer/stream"

def setup_stream():
    client = MJPEGClient(url)

    # Allocate memory buffers for frames
    bufs = client.request_buffers(965536, 7)
    for b in bufs:
        client.enqueue_buffer(b)
        
    # Start the client in a background thread
    client.start()

    # emit client
    yield client

    while True:
        buf = client.dequeue_buffer()
        if buf.timestamp < time.time() - 3:
            client.enqueue_buffer(buf)
            print('[skipping old frame]')
            continue
        with io.BytesIO(buf.data) as buffer:
            img = Image.open(buffer)
            ratio = min(120/img.width, 120/img.height)
            size = (int(img.width*ratio), int(img.height*ratio))
            size_mid = (2 * size[0], 2 * size[1])
            img = img.resize(size_mid).quantize()
            img = img.resize(size, resample=Image.Resampling.LANCZOS).convert('RGBA')
            client.print_stats()
            client.enqueue_buffer(buf)
            yield img

_stream = None
_client = None
_last_update = None
_lock = True

def stream_frame(fs):
    global _last_update, _stream
    if _lock or not _stream:
        return
    img = next(_stream)
    _last_update = fs.tick
    return Frame(img, hash=('mjpeg', url)).tag('stream')

draw = draw_loop(stream_frame, use_threads=True)

def widget(fs: FrameState):
    global _stream, _client, _lock
    if not _last_update or _last_update < (fs.tick + 9):
        print("* no updates")
        # reset stream
        _lock = True
        if _client:
            _client.stop()
        _stream = setup_stream()
        _client = next(_stream)
        _lock = False
    return Widget('stream', draw(fs), priority=0.5, wait_time=8)
