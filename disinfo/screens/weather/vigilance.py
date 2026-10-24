'''Météo-France's Vigilance (API Bulletin Vigilance, Licence Ouverte, credit Météo-France) for one département: what is
yellow or worse today and tomorrow, as short lines for the weather card. The user cares about rain and cold first.
'''
import json
import time
import pendulum
import requests

from disinfo.config import app_config
from disinfo.redis import db, publish

URL = 'https://public-api.meteofrance.fr/public/DPVigilance/v1/cartevigilance/encours'
KEY = 'di.weather.vigil'
read_every = 60

PHENOMENA = {
    '1': 'Vent', '2': 'Pluie', '3': 'Orages', '4': 'Crues', '5': 'Neige/verglas',
    '6': 'Canicule', '7': 'Grand froid', '8': 'Avalanches', '9': 'Vagues',
}
# Shown from yellow (1 is green, 2 yellow, 3 orange, 4 red in the colour ids: green is 1).
CARED = {'2', '5', '7'}         # rain, snow/ice, cold: from yellow; the others from orange


def fetch(key: str) -> dict:
    r = requests.get(URL, headers={'apikey': key}, timeout=30)
    r.raise_for_status()
    return r.json()

def parse(doc: dict, domain: str) -> dict:
    '''The département's phenomena: [{id, windows: [[begin, end, color] as epoch s]}], only those past green.'''
    out = {}
    for period in doc['product']['periods']:
        for d in period['timelaps']['domain_ids']:
            if d['domain_id'] != domain:
                continue
            for ph in d['phenomenon_items']:
                for t in ph['timelaps_items']:
                    if t['color_id'] > 1:
                        out.setdefault(ph['phenomenon_id'], []).append(
                            [pendulum.parse(t['begin_time']).int_timestamp, pendulum.parse(t['end_time']).int_timestamp, t['color_id']])
    return {'at': time.time(), 'update': doc['product']['update_time'], 'domain': domain, 'phenomena': out}

def job():
    key = app_config.meteo_france_api_key__vigil
    if not key:
        return
    doc = parse(fetch(key.get_secret_value()), app_config.vigilance_domain)
    db.set(KEY, json.dumps(doc), ex=3 * 3600)
    publish('weather', 'vigil')

def task():
    try:
        job()
        return True
    except Exception as e:
        print(f'weather vigilance: {e!r}')
    return False


_cache = {'read': 0.0, 'doc': None}

def doc() -> dict | None:
    now = time.monotonic()
    if now - _cache['read'] > read_every:
        _cache['read'] = now
        try:
            _cache['doc'] = json.loads(db.get(KEY) or 'null')
        except ValueError:
            _cache['doc'] = None
    return _cache['doc']

def lines(now: float, d: dict | None = None) -> list[tuple[int, str]]:
    '''[(color, text)], the worst first (the colour is the level, the card draws it): the worst colour still to come (or now) for each phenomenon and when.'''
    d = d or doc()
    if not d:
        return []
    out = []
    for ph, windows in d['phenomena'].items():
        live = [w for w in windows if w[1] > now and w[2] >= (2 if ph in CARED else 3)]
        if not live:
            continue
        begin, end, color = max(live, key=lambda w: (w[2], -w[0]))
        t = lambda s: pendulum.from_timestamp(s, 'Europe/Paris')
        span = f'jusqu\'à {t(end).format("H")}h' if begin <= now else f'{t(begin).format("H")}h-{t(end).format("H")}h'
        out.append((color, f'{PHENOMENA.get(ph, ph)} {span}'))
    return sorted(out, key=lambda l: -l[0])


# The next hours at home (AROME through Open-Meteo, CC-BY 4.0, no key): when it rains, how cold it gets.
FORECAST_URL = 'https://api.open-meteo.com/v1/meteofrance'
FORECAST_KEY = 'di.weather.forecast'
rain_mm = 0.2           # an hour with at least this much rain is a wet hour
cold_c = 5              # the lowest temperature is worth a line when it is this or lower
horizon_h = 12

def fetch_forecast() -> list:
    r = requests.get(FORECAST_URL, timeout=30, params={
        'latitude': app_config.latitude, 'longitude': app_config.longitude, 'hourly': 'precipitation,temperature_2m',
        'forecast_hours': horizon_h + 1, 'timeformat': 'unixtime', 'timezone': 'UTC'})
    r.raise_for_status()
    h = r.json()['hourly']
    return [[t, p, c] for t, p, c in zip(h['time'], h['precipitation'], h['temperature_2m']) if p is not None and c is not None]

def forecast_job():
    db.set(FORECAST_KEY, json.dumps({'at': time.time(), 'hours': fetch_forecast()}), ex=3 * 3600)

def forecast_task():
    try:
        forecast_job()
        return True
    except Exception as e:
        print(f'weather forecast: {e!r}')
    return False


_fcache = {'read': 0.0, 'doc': None}

def forecast_doc() -> dict | None:
    now = time.monotonic()
    if now - _fcache['read'] > read_every:
        _fcache['read'] = now
        try:
            _fcache['doc'] = json.loads(db.get(FORECAST_KEY) or 'null')
        except ValueError:
            _fcache['doc'] = None
    return _fcache['doc']

def forecast_lines(now: float, d: dict | None = None) -> list[str]:
    '''The first rain still to come (from when to when, the most in an hour) and the lowest temperature, if cold.'''
    d = d or forecast_doc()
    if not d:
        return []
    hours = [h for h in d['hours'] if h[0] + 3600 > now]       # an hour's value is the hour that ends at its time
    t = lambda s: pendulum.from_timestamp(s, 'Europe/Paris').format('H')
    out = []
    wet = [i for i, h in enumerate(hours) if h[1] >= rain_mm]
    if wet:
        first = wet[0]
        last = first
        while last + 1 < len(hours) and hours[last + 1][1] >= rain_mm:
            last += 1
        most = max(h[1] for h in hours[first:last + 1])
        span = f'jusqu\'à {t(hours[last][0] + 3600)}h' if hours[first][0] <= now else f'{t(hours[first][0])}h-{t(hours[last][0] + 3600)}h'
        out.append(f'Pluie {span} {most:.0f}mm/h' if most >= 1 else f'Pluie {span}')
    if hours:
        low = min(hours, key=lambda h: h[2])
        if low[2] <= cold_c:
            out.append(f'Min {low[2]:.0f}C à {t(low[0])}h')
    return out
