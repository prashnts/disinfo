'''Route and photo of the planes with an open card, cached in redis.

Fetched in a thread: the card draws without them and fills in.
'''
import json
import threading
import requests

from disinfo.redis import db


# planespotters asks for a contact in the user agent.
headers = {'User-Agent': 'disinfo (+https://github.com/prashnts/disinfo)'}
_pending = set()


def cached(key: str, fetch, ttl: int) -> dict | None:
    if (v := db.get(key)) is not None:
        return json.loads(v)
    if key in _pending:
        return None
    _pending.add(key)

    def run():
        try:
            db.set(key, json.dumps(fetch()), ex=ttl)
        except Exception as e:
            print(f'[aviator] {key}: {e}')
            db.set(key, 'null', ex=300)    # retried in a while
        finally:
            _pending.discard(key)
    threading.Thread(target=run, daemon=True).start()
    return None

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
    return cached(f'di.aviator.route.{p["flight"]}', lambda: fetch_route(p['flight']), 24 * 3600)

def photo(p: dict) -> dict | None:
    return cached(f'di.aviator.photo.{p["hex"]}', lambda: fetch_photo(p['hex'], p.get('r'), p.get('t')), 7 * 24 * 3600)

_warm = {}      # (src, size) -> the frame once it's loaded

def photo_frame(src: str, size: tuple[int, int]):
    # image_from_url blocks on the first fetch: warmed in a thread, None until then.
    from disinfo.utils.imops import image_from_url
    key = (src, size)
    if key not in _warm:
        if len(_warm) > 32:
            _warm.clear()
        _warm[key] = None
        threading.Thread(target=lambda: _warm.__setitem__(key, image_from_url(src, resize=size, ratio_fn=max)), daemon=True).start()
    return _warm[key]
