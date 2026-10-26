'''What the weather stations around home measure: Météo-France's observations (API DPObs, every 6 min, Licence Ouverte,
credit Météo-France) and the airports' METAR (aviationweather.gov, no key) for the cloud base, the gusts and what falls.
The air at home comes out of them, the city's stations first. The barometers indoors read the same pressure as outside:
they're calibrated on the stations and stand in when those are missing.

di.weather.obs: {at, stations {id: {name, at, t, td, rh, dir, ms, rr (mm/h), vis (m), p, pmer (hPa)}}, metar {icao: {at,
clouds [[cover 0..1, base m]], gust, wx, vis}}, indoor {entity: pmer}, home {t, td, pmer, ms, dir, gust, rr, vis, deck,
ceiling, wx, tendency (hPa in 3 h), eiffel (°C over the ground's)}}
'''
import json
import math
import time
import requests

from calendar import timegm
from disinfo.config import app_config

URL = 'https://public-api.meteofrance.fr/public/DPObs/v1/station/infrahoraire-6m'
METAR_URL = 'https://aviationweather.gov/api/data/metar'
KEY = 'di.weather.obs'
LOG_KEY = 'di.weather.obs.log'      # a row per fetch, newest first: [t, temp, dew, pmer, ms, rr, indoor {entity: state}, HA's temp]
BARO_KEY = 'di.weather.baro'        # entity -> [offset to the sea-level pressure, n]
log_days = 30
# id -> (name, sigma of its temperature as home's, °C): the city's first, the airports further and cooler at night.
stations = {
    '75114001': ('Montsouris', 0.6), '75110001': ('Lariboisière', 0.6), '94068001': ('St-Maur', 0.9),
    '91027002': ('Orly', 1.4), '95088001': ('Le Bourget', 1.2),
}
eiffel = '75107005'                 # 330 m over the ground: the air above the city's
metars = ('LFPB', 'LFPO', 'LFPG')
cover_of = {'FEW': 0.2, 'SCT': 0.45, 'BKN': 0.75, 'OVC': 1.0, 'OVX': 1.0, 'VV': 1.0}
ft = 0.3048


def fetch_station(key: str, sid: str) -> dict | None:
    r = requests.get(URL, params={'id_station': sid, 'format': 'json'}, headers={'apikey': key}, timeout=30)
    r.raise_for_status()
    return (r.json() or [None])[0]

def parse_station(d: dict) -> dict:
    k = lambda x: None if d.get(x) is None else round(d[x] - 273.15, 2)
    h = lambda x: None if d.get(x) is None else d[x] / 100
    return {'at': timegm(time.strptime(d['validity_time'], '%Y-%m-%dT%H:%M:%SZ')),
            't': k('t'), 'td': k('td'), 'rh': d.get('u'), 'dir': d.get('dd'), 'ms': d.get('ff'),
            'rr': None if d.get('rr_per') is None else d['rr_per'] * 10, 'vis': d.get('vv'), 'p': h('pres'), 'pmer': h('pmer')}

def fetch_metar() -> list:
    r = requests.get(METAR_URL, params={'ids': ','.join(metars), 'format': 'json'}, timeout=30)
    r.raise_for_status()
    return r.json()

def parse_metar(m: dict) -> dict:
    clouds = [[cover_of[c['cover']], round(c['base'] * ft)] for c in m.get('clouds') or [] if c['cover'] in cover_of and c.get('base') is not None]
    vis = m.get('visib')
    vis = 10000 if vis in ('6+', '10+') else (round(float(vis) * 1609) if vis is not None else None)
    kt = lambda x: None if m.get(x) is None else round(m[x] * 0.5144, 1)
    return {'at': m['obsTime'], 'clouds': clouds, 'gust': kt('wgst'), 'ms': kt('wspd'), 'wx': m.get('wxString') or '', 'vis': vis}


def mean(pts: list[tuple[float, float]]) -> tuple[float, float] | None:
    '''(value, sigma) -> the weighted mean and its sigma, wider when they disagree.'''
    pts = [(v, s) for v, s in pts if v is not None]
    if not pts:
        return None
    w = [s ** -2 for _, s in pts]
    m = sum(wi * v for wi, (v, _) in zip(w, pts)) / sum(w)
    spread2 = sum(wi * (v - m) ** 2 for wi, (v, _) in zip(w, pts)) / sum(w)
    return m, math.sqrt(1 / sum(w) + spread2)

def home_air(st: dict, mt: dict, indoor: dict, now: float, old: float = 1800) -> dict:
    '''The stations (fresh ones) -> home's air: each value [v, sigma] or None, and the clouds and the weather as notes.'''
    fresh = {i: s for i, s in st.items() if now - s['at'] < old and i in stations}
    sig = lambda i, base: stations[i][1] / 0.6 * base
    at = lambda k, base: mean([(s[k], sig(i, base)) for i, s in fresh.items() if s.get(k) is not None])
    out = {'t': at('t', 0.6), 'td': at('td', 0.8), 'ms': at('ms', 1.0), 'rr': at('rr', 0.5)}
    # Fog is local: the nearest that sees (the city's first).
    vis = next((s['vis'] for i, s in sorted(fresh.items(), key=lambda x: stations[x[0]][1]) if s.get('vis') is not None), None)
    out['vis'] = (vis, 500) if vis is not None else None
    pm = [(s['pmer'], 0.3) for s in fresh.values() if s.get('pmer') is not None]
    out['pmer'] = mean(pm or [(v, 0.4) for v in indoor.values()])
    dirs = [(s['dir'], s['ms']) for s in fresh.values() if s.get('dir') is not None and s.get('ms')]
    out['dir'] = round(math.degrees(math.atan2(sum(m * math.sin(math.radians(d)) for d, m in dirs),
                                               sum(m * math.cos(math.radians(d)) for d, m in dirs))) % 360) if dirs else None
    mf = [m for m in mt.values() if now - m['at'] < 5400]
    gusts = [m['gust'] for m in mf if m['gust']]
    out['gust'] = (max(gusts), 2.0) if gusts else None
    if mf:
        # The low and mid cloud the airports' ceilometers see (up to ~4 km: a clear METAR says nothing of the cirrus).
        decks = [1 - math.prod(1 - c for c, b in m['clouds'] if b < 6000) for m in mf]
        out['deck'] = sum(decks) / len(decks), 0.25 if any(decks) else 0.35
        ceil = [b for m in mf for c, b in m['clouds'] if c >= 0.75]
        out['ceiling'] = min(ceil) if ceil else None
        out['wx'] = sorted({m['wx'] for m in mf if m['wx']})
    e = st.get(eiffel)
    if e and e.get('t') is not None and out['t'] and now - e['at'] < old:
        out['eiffel'] = round(e['t'] - out['t'][0], 1)
    return out

def tendency(log: list, pmer: float | None, now: float) -> float | None:
    # hPa in 3 h, from the row nearest 3 h ago.
    rows = [r for r in log if r[3] is not None and abs(now - 3 * 3600 - r[0]) < 1200]
    if pmer is None or not rows:
        return None
    r = min(rows, key=lambda r: abs(now - 3 * 3600 - r[0]))
    return round((pmer - r[3]) * 3 * 3600 / (now - r[0]), 1)

def barometers(db, pmer: float | None, readings: dict) -> dict:
    '''The indoor barometers as the sea-level pressure: an offset learnt on the stations (slowly: they agree to 0.1 hPa).'''
    cal = json.loads(db.get(BARO_KEY) or '{}')
    out = {}
    for e, p in readings.items():
        off, n = cal.get(e, (0.0, 0))
        if pmer is not None:
            a = 1 / min(n + 1, 50)
            off, n = off + a * (pmer - p - off), n + 1
            cal[e] = off, n
        if n >= 5:
            out[e] = round(p + off, 2)
    db.set(BARO_KEY, json.dumps(cal))
    return out


def ha_float(entity: str) -> float | None:
    from disinfo.utils.hass import get_entity
    e = get_entity(entity)
    try:
        return float(e.state)
    except (AttributeError, TypeError, ValueError):
        return None

def ha_temp() -> float | None:
    # What the weather card showed before: Home Assistant's weather (met.no), scored with the models.
    from disinfo.utils.hass import get_entity
    try:
        return float(get_entity(app_config.weather_entity).attributes['temperature'])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None

def job():
    from disinfo.redis import db, publish
    key = app_config.meteo_france_api_key__observations
    now = time.time()
    prev = json.loads(db.get(KEY) or 'null') or {}
    st, mt = dict(prev.get('stations') or {}), dict(prev.get('metar') or {})
    if key:
        for sid in (*stations, eiffel):
            try:
                if d := fetch_station(key.get_secret_value(), sid):
                    st[sid] = {'name': stations.get(sid, ('Tour Eiffel',))[0], **parse_station(d)}
            except Exception as e:
                print(f'weather station {sid}: {e!r}')
    try:
        mt.update({m['icaoId']: parse_metar(m) for m in fetch_metar()})
    except Exception as e:
        print(f'weather metar: {e!r}')
    fresh = [s['pmer'] for s in st.values() if s.get('pmer') is not None and now - s['at'] < 1800]
    indoor = barometers(db, sum(fresh) / len(fresh) if fresh else None,
                        {e: p for e in app_config.weather_barometers if (p := ha_float(e)) is not None})
    home = home_air(st, mt, indoor, now)
    log = [json.loads(r) for r in db.lrange(LOG_KEY, 0, 60)]
    g = lambda k: home[k] and round(home[k][0], 2)
    home['tendency'] = tendency(log, g('pmer'), now)
    db.lpush(LOG_KEY, json.dumps([round(now), g('t'), g('td'), g('pmer'), g('ms'), g('rr'),
                                  {e: ha_float(e) for e in app_config.weather_indoor_log}, ha_temp()]))
    db.ltrim(LOG_KEY, 0, log_days * 240)
    db.set(KEY, json.dumps({'at': now, 'stations': st, 'metar': mt, 'indoor': indoor, 'home': home}), ex=3 * 3600)
    publish('weather', 'obs')
    return any(now - s['at'] < 1800 for s in st.values())

def task():
    try:
        return job()
    except Exception as e:
        print(f'weather obs: {e!r}')
    return False


def doc() -> dict | None:
    from disinfo.screens.aviator import daylight
    return daylight.read(KEY)
