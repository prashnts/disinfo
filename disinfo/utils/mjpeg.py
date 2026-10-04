import io
import time
import threading
import urllib.request

from PIL import Image

from discore.elements import Frame
from discore.data_structures import UniqInstance


class MJPEGStream(metaclass=UniqInstance):
    '''Latest frame of an MJPEG stream, shared by everything drawing the same url.

    The reader runs in the background only while frames are read, and stops
    after `idle_timeout` seconds without reads. It keeps the newest jpeg only,
    so what's drawn is live. Decoding happens on read, once per new frame and
    at a reduced scale.
    '''
    idle_timeout = 10
    stale_after = 2

    def __init__(self, url: str):
        self.url = url
        self.jpeg: bytes | None = None
        self.jpeg_at = 0
        self.read_at = 0
        self._thread = None
        self._lock = threading.Lock()
        self._fitted = {}   # width -> (jpeg, frame)

    def _wanted(self):
        return time.monotonic() - self.read_at < self.idle_timeout

    def _run(self):
        while self._wanted():
            try:
                with urllib.request.urlopen(self.url, timeout=5) as r:
                    buf = b''
                    while self._wanted():
                        # Large reads: few GIL round trips, the draw threads keep it busy.
                        chunk = r.read1(1 << 18)
                        if not chunk:
                            break
                        buf += chunk
                        # Keep the last complete jpeg (SOI..EOI), drop the older ones.
                        end = buf.rfind(b'\xff\xd9')
                        if end == -1:
                            continue
                        start = buf.rfind(b'\xff\xd8', 0, end)
                        if start != -1:
                            self.jpeg, self.jpeg_at = buf[start:end + 2], time.monotonic()
                        buf = buf[end + 2:]
            except OSError as e:
                print(f'[mjpeg] {self.url}: {e}')
                time.sleep(1)
        self.jpeg = None

    def read(self, width: int) -> Frame | None:
        '''Latest frame fitted to `width`, or None while connecting or stalled.'''
        self.read_at = time.monotonic()
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

        jpeg = self.jpeg
        if not jpeg or time.monotonic() - self.jpeg_at > self.stale_after:
            return
        if (cached := self._fitted.get(width)) and cached[0] is jpeg:
            return cached[1]

        try:
            img = Image.open(io.BytesIO(jpeg))
            ratio = min(width / img.width, width / img.height)
            size = (int(img.width * ratio), int(img.height * ratio))
            img.draft('RGB', size)   # jpeg decodes at 1/2, 1/4 or 1/8 scale, much cheaper
            img = img.convert('RGB')
        except OSError:
            return
        size_mid = (2 * size[0], 2 * size[1])
        fitted = img.resize(size_mid).quantize()
        fitted = fitted.resize(size, resample=Image.Resampling.LANCZOS).convert('RGBA')
        # One hash for the whole stream: it's a live value, transitions shouldn't restart on each frame.
        frame = Frame(fitted, hash=('mjpeg', self.url, width))
        self._fitted[width] = (jpeg, frame)
        return frame
