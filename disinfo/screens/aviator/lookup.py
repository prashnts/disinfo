'''Route and photo of the planes with an open card, cached in redis.

The data service fetches them (serve()): a renderer asks over xbus and draws without them meanwhile.
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
WANT = 'x.lookup.want'      # JSON: the key to fill, its ttl, what to fetch
thumb_ttl = 3600            # s: the photos themselves, only while their planes are around
_read = {}          # key -> (when, value): redis once in a while, not each frame; a miss again in 2 s
_asked = {}         # key -> when it was asked for: again in 30 s at most


def ask(key: str, ttl: int, **what):
    now = time.monotonic()
    if now - _asked.get(key, -99) > 30:
        if len(_asked) > 512:
            _asked.clear()
        _asked[key] = now
        Bus().send(WANT, json.dumps({'key': key, 'ttl': ttl, **what}))

def cached(key: str, ttl: int, **what) -> dict | None:
    now = time.monotonic()
    if (r := _read.get(key)) and now - r[0] < (60 if r[1] is not None else 2):
        return r[1]
    if len(_read) > 256:
        _read.clear()
    v = db.get(key)
    _read[key] = now, None if v is None else json.loads(v)
    if v is None:
        ask(key, ttl, **what)
    return _read[key][1]

def fetch_route(callsign: str) -> dict:
    r = requests.get(f'https://api.adsbdb.com/v0/callsign/{callsign}', headers=headers, timeout=5)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    route = r.json()['response']
    if not isinstance(route, dict):
        return {}
    route = route['flightroute']
    place = lambda a: {'iata': a.get('iata_code'), 'city': a.get('municipality')}
    # The flight number when the callsign is one (AFR1234 -> AF1234), most are ATC's own (AFR54ZQ).
    iata = route.get('callsign_iata') or ''
    number = iata if iata[2:].isdigit() else None
    return {'airline': (route.get('airline') or {}).get('name'), 'number': number, 'from': place(route['origin']), 'to': place(route['destination'])}

def fetch_photo(hex: str, reg: str | None, icao_type: str | None) -> dict:
    params = {k: v for k, v in (('reg', reg), ('icaoType', icao_type)) if v}
    r = requests.get(f'https://api.planespotters.net/pub/photos/hex/{hex}', params=params, headers=headers, timeout=5)
    r.raise_for_status()
    photos = r.json().get('photos') or []
    if not photos:
        return {}
    return {'src': photos[0]['thumbnail']['src'], 'by': photos[0].get('photographer')}

def route(p: dict) -> dict | None:
    if not p.get('flight'):
        return {}
    return cached(f'di.aviator.route.{p["flight"]}', 24 * 3600, kind='route', flight=p['flight'])

def photo(p: dict) -> dict | None:
    return cached(f'di.aviator.photo.{p["hex"]}', 7 * 24 * 3600, kind='photo', hex=p['hex'], reg=p.get('r'), type=p.get('t'))

def thumb_key(src: str) -> str:
    return f'di.aviator.thumb.{hashlib.sha1(src.encode()).hexdigest()[:16]}'

_warm = {}      # (src, size) -> the frame once it's loaded

def photo_frame(src: str, size: tuple[int, int]) -> Frame | None:
    key = (src, size)
    if (f := _warm.get(key)) is not None:
        return f
    if not (raw := db.get(thumb_key(src))):
        ask(thumb_key(src), thumb_ttl, kind='thumb', src=src)
        return None
    if len(_warm) > 32:
        _warm.clear()
    try:
        img = Image.open(io.BytesIO(raw))
        f = _warm[key] = Frame(img, ('img_from_url', src, size)).resize(size, ratio_fn=max)
    except OSError:
        return None
    return f


def fetch(what: dict) -> bytes | str:
    match what['kind']:
        case 'route':
            return json.dumps(fetch_route(what['flight']))
        case 'photo':
            return json.dumps(fetch_photo(what['hex'], what.get('reg'), what.get('type')))
        case 'thumb':
            r = requests.get(what['src'], headers=headers, timeout=5)
            r.raise_for_status()
            return r.content

def serve():
    '''In the data service: one at a time, each key once while it's being fetched.'''
    todo, pending = queue.Queue(), set()

    def on_want(_, data: bytes):
        what = json.loads(data)
        if what['key'] not in pending and not db.exists(what['key']):
            pending.add(what['key'])
            todo.put(what)

    def work():
        while True:
            what = todo.get()
            try:
                db.set(what['key'], fetch(what), ex=what['ttl'])
            except Exception as e:
                print(f'[aviator] {what["key"]}: {e}')
                if what['kind'] != 'thumb':
                    db.set(what['key'], 'null', ex=300)    # retried in a while
            finally:
                pending.discard(what['key'])

    threading.Thread(target=work, name='lookup', daemon=True).start()
    Bus().on(WANT, on_want)
