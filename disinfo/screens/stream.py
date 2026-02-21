import io
import time
import queue
from PIL import Image
from mjpeg.client import MJPEGClient

from .drawer import draw_loop
from ..components.elements import Frame
from ..data_structures import FrameState
from ..components.widget import Widget

url = "https://kvm.amd.noop.pw/streamer/stream"
url = "http://pi-webcam.local/html/cam_pic_new.php?time=1764173339202&pDelay=40000"
url = None

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
        buf = client.dequeue_buffer(timeout=5)
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
            # client.print_stats()
            client.enqueue_buffer(buf)
            yield img

_stream = None
_client = None
_last_update = None
_prev_url = None

def stream_frame(fs):
    global _last_update, _stream, _prev_url
    if not _stream:
        return
    try:
        img = next(_stream)
    except queue.Empty:
        _stream = None
        return
    _last_update = fs.tick
    return Frame(img, hash=('mjpeg', url)).tag('stream')

def draw_stream(fs: FrameState):
    global _stream, _client, _last_update, _prev_url
    if (_last_update and _last_update < (fs.tick - 20)) or not _stream or _prev_url != url:
        print("* no updates")
        # reset stream
        if _client:
            print("* stopping client")
            _client.stop()
        try:
            time.sleep(5)
            print(url)
            _stream = setup_stream()
        except Exception as e:
            return None
        _client = next(_stream)
        _last_update = fs.tick
        _prev_url = url
        print("* client started")
    return stream_frame(fs)

draw = draw_loop(draw_stream, use_threads=True)

def widget(fs: FrameState):
    return Widget('stream', draw(fs), priority=0.5, wait_time=8)
