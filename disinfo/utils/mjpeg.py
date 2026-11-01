import io
import time
import hashlib
import threading
import urllib.request

from PIL import Image

from discore.elements import Frame
from discore.data_structures import UniqInstance
from disinfo.xbus import Bus

# The data service reads each stream once, while someone draws it, and sends its jpegs over xbus: x.mjpeg.want
# (the url, again every few seconds while it's drawn), x.mjpeg.<id> (the jpegs).
WANT = 'x.mjpeg.want'
idle_timeout = 10       # s without a want: the stream is closed
max_fps = 10            # jpegs sent a second, at most

def channel(url: str) -> str:
    return f'x.mjpeg.{hashlib.sha1(url.encode()).hexdigest()[:12]}'


class Relay(metaclass=UniqInstance):
    '''In the data service: the streams someone wants, read and sent.'''

    def __init__(self):
        self.wanted: dict[str, float] = {}      # url -> when it was last asked for
        self.threads: dict[str, threading.Thread] = {}
        Bus().on(WANT, self.on_want)

    def on_want(self, _, data: bytes):
        url = data.decode()
        self.wanted[url] = time.monotonic()
        if not (t := self.threads.get(url)) or not t.is_alive():
            self.threads[url] = t = threading.Thread(target=self._run, args=(url,), name='mjpeg', daemon=True)
            t.start()

    def _run(self, url: str):
        wanted = lambda: time.monotonic() - self.wanted.get(url, 0) < idle_timeout
        to, sent = channel(url), 0.0
        while wanted():
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    buf = b''
                    while wanted():
                        chunk = r.read1(1 << 18)
                        if not chunk:
                            break
                        buf += chunk
                        # The last complete jpeg (SOI..EOI), the older ones dropped.
                        end = buf.rfind(b'\xff\xd9')
                        if end == -1:
                            continue
                        start = buf.rfind(b'\xff\xd8', 0, end)
                        if start != -1 and (now := time.monotonic()) - sent >= 1 / max_fps:
                            Bus().send(to, buf[start:end + 2])
                            sent = now
                        buf = buf[end + 2:]
            except OSError as e:
                print(f'[mjpeg] {url}: {e}')
                time.sleep(1)


def serve():
    Relay()


class MJPEGStream(metaclass=UniqInstance):
    '''Latest frame of an MJPEG stream, from the data service's relay.

    Asked for while frames are read; it stops after `idle_timeout` s without. Decoding happens on read, once per new
    frame and at a reduced scale.
    '''
    stale_after = 2

    def __init__(self, url: str):
        self.url = url
        self.jpeg: bytes | None = None
        self.jpeg_at = 0
        self.asked_at = -99.0
        self._fitted = {}   # (width, height, box) -> (jpeg, frame)
        Bus().on(channel(url), self._got)

    def _got(self, _, data: bytes):
        self.jpeg, self.jpeg_at = data, time.monotonic()

    def read(self, width: int, height: int | None = None, box: tuple[float, float, float, float] | None = None) -> Frame | None:
        '''Latest frame fitted to `width` x `height`, or None while connecting or stalled.

        `box` crops it first, (x0, y0, x1, y1) as fractions of the frame.
        '''
        if (now := time.monotonic()) - self.asked_at > 2:
            Bus().send(WANT, self.url)
            self.asked_at = now

        jpeg = self.jpeg
        if not jpeg or time.monotonic() - self.jpeg_at > self.stale_after:
            return
        key = (width, height, box)
        if (cached := self._fitted.get(key)) and cached[0] is jpeg:
            return cached[1]

        try:
            img = Image.open(io.BytesIO(jpeg))
            x0, y0, x1, y1 = box or (0, 0, 1, 1)
            ratio = min(width / (img.width * (x1 - x0)), (height or width) / (img.height * (y1 - y0)))
            img.draft('RGB', (int(img.width * ratio), int(img.height * ratio)))   # jpeg decodes at 1/2, 1/4 or 1/8 scale, much cheaper
            img = img.convert('RGB')
            if box:
                img = img.crop((int(x0 * img.width), int(y0 * img.height), int(x1 * img.width), int(y1 * img.height)))
            ratio = min(width / img.width, (height or width) / img.height)
            size = (int(img.width * ratio), int(img.height * ratio))
        except OSError:
            return
        size_mid = (2 * size[0], 2 * size[1])
        fitted = img.resize(size_mid).quantize()
        fitted = fitted.resize(size, resample=Image.Resampling.LANCZOS).convert('RGBA')
        # One hash for the whole stream: it's a live value, transitions shouldn't restart on each frame.
        frame = Frame(fitted, hash=('mjpeg', self.url, width))
        if len(self._fitted) > 8:   # the crop box moves, old ones are dead
            self._fitted.clear()
        self._fitted[key] = (jpeg, frame)
        return frame
