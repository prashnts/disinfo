'''Images from URLs: fetched once in the data service (serve()) and kept in Redis a while. Renderers ask over xbus and
draw without them meanwhile: no fetch in a renderer, none twice.
'''
import io
import json
import time
import queue
import hashlib
import threading
import requests

from PIL import Image

from discore.elements import Frame
from disinfo.redis import db
from disinfo.xbus import Bus

# planespotters asks for a contact in the user agent.
headers = {'User-Agent': 'disinfo (+https://github.com/prashnts/disinfo)'}
WANT = 'x.images.want'      # JSON: {url, ttl}
ttl_s = 3600                # s in Redis since the fetch
_asked = {}                 # url -> when: again in 30 s at most (a failed fetch is retried then)
_looked = {}                # url -> when Redis had none: not again for 2 s
_warm = {}                  # (url, size, ratio_fn) -> the frame


def key(url: str) -> str:
    return f'di.image.{hashlib.sha1(url.encode()).hexdigest()[:16]}'

def ask(url: str, ttl: int = ttl_s):
    now = time.monotonic()
    if now - _asked.get(url, -99) > 30:
        if len(_asked) > 512:
            _asked.clear()
        _asked[url] = now
        Bus().send(WANT, json.dumps({'url': url, 'ttl': ttl}))

def data(url: str, ttl: int = ttl_s) -> bytes | None:
    '''The image's bytes, None till they're fetched.'''
    if not url:
        return None
    now = time.monotonic()
    if now - _looked.get(url, -99) < 2:
        return None
    if raw := db.get(key(url)):
        _looked.pop(url, None)
        return raw
    if len(_looked) > 512:
        _looked.clear()
    _looked[url] = now
    ask(url, ttl)
    return None

def frame(url: str, size: tuple[int, int], ratio_fn=max, ttl: int = ttl_s) -> Frame | None:
    '''Resized to cover size (ratio_fn=max) or fit in it (min); None till it's fetched.'''
    k = url, size, ratio_fn
    if (f := _warm.get(k)) is not None:
        return f
    if not (raw := data(url, ttl)):
        return None
    try:
        f = Frame(Image.open(io.BytesIO(raw)), ('img_from_url', url, size)).resize(size, ratio_fn=ratio_fn)
    except OSError:
        return None
    if len(_warm) > 64:
        _warm.clear()
    _warm[k] = f
    return f


def serve():
    '''In the data service: one at a time, each url once while it's being fetched.'''
    todo, pending = queue.Queue(), set()

    def on_want(_, raw: bytes):
        what = json.loads(raw)
        if what['url'] not in pending and not db.exists(key(what['url'])):
            pending.add(what['url'])
            todo.put(what)

    def work():
        while True:
            what = todo.get()
            try:
                r = requests.get(what['url'], headers=headers, timeout=5)
                r.raise_for_status()
                db.set(key(what['url']), r.content, ex=what['ttl'])
            except Exception as e:
                print(f'[images] {what["url"][:80]}: {e!r}')
            finally:
                pending.discard(what['url'])

    threading.Thread(target=work, name='images', daemon=True).start()
    Bus().on(WANT, on_want)


def image_from_url(url: str, resize: tuple[int, int] = (42, 42), ratio_fn=max) -> Frame:
    '''Blank till it's there.'''
    if url and (f := frame(url, resize, ratio_fn)) is not None:
        return f
    return Frame(Image.new('RGBA', resize, (0, 0, 0, 0)), ('img_from_url', url, resize))
