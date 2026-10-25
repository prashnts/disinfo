'''What the light coming in says about the sky over home: worked out once a minute in the data service, for all screens.

Sensei by the window (Home Assistant's lux and UV) and the desk's colour sensor (telemetry, its counts per channel),
each against the brightest it has seen with the sun where it is now: a window faces one way, the light it lets in
follows the sun's bearing more than the hour. That ratio says how much the cloud takes: about 1 clear (or the sun out),
a tenth a dark overcast, nothing with the shutter down. The desk's lamps are taken off its counts (learnt at night).
Open-Meteo's model (cover by height, radiation) is there for what a window can't tell, and stands in when it's blind.

di.daylight: {at, source ('light', 'shutter', 'night', 'none'), b (0..1+), cloud, dark, sun, broken (0..1 or None),
warmth (None until a day of log), model {cloud, low, mid, high, kt}}.
'''
import json
import math
import time
import datetime as dt
import threading
import requests
import numpy as np

from suncalc import get_position

from disinfo.config import app_config
from .utils import home

KEY = 'di.daylight'
LOG_KEY = 'di.daylight.log'         # a JSON row a minute, newest first: [t, lux, uv, r, g, b, c, lamps...]
ENV_KEY = 'di.daylight.env'
SKY_KEY = 'di.weather.sky'
SKY_URL = 'https://api.open-meteo.com/v1/meteofrance'
log_days = 14
az_step = 5             # degrees: the envelope's bins
min_alt = 3             # the sun under this: no daylight reading
night_alt = -8          # the lamps alone
shutter_b = 0.04        # under this with a bright model sky: the shutter's down

_desk = {'at': 0.0, 'rgbc': None}


def sun_at(t: float) -> tuple[float, float]:
    p = get_position(dt.datetime.fromtimestamp(t, dt.timezone.utc), home[1], home[0])
    return math.degrees(p['altitude']), (math.degrees(p['azimuth']) + 180) % 360

def clear_ghi(alt: float) -> float:
    # W/m² on a clear day (Haurwitz).
    s = math.sin(math.radians(alt))
    return 1098 * s * math.exp(-0.057 / s) if s > 0 else 0.0

def fetch_sky() -> dict:
    r = requests.get(SKY_URL, timeout=30, params={'latitude': home[0], 'longitude': home[1],
        'current': 'cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,shortwave_radiation,direct_radiation'})
    r.raise_for_status()
    c = r.json()['current']
    return {'at': time.time(), **{k: c[k] for k in ('cloud_cover', 'cloud_cover_low', 'cloud_cover_mid', 'cloud_cover_high',
                                                     'shortwave_radiation', 'direct_radiation')}}

def sky_task():
    from disinfo.redis import db
    try:
        db.set(SKY_KEY, json.dumps(fetch_sky()), ex=3 * 3600)
        return True
    except Exception as e:
        print(f'daylight sky: {e!r}')
    return False

def on_telemetry(channel: str, msg):
    # The desk's light sensor, the latest only (the telemetry comes many times a second).
    p = msg.payload or {}
    if p.get('_node') != app_config.daylight_node:
        return
    ls = json.loads(p['data']).get('light_sensor') or {}
    if ls.get('rgbc'):
        _desk.update(at=time.time(), rgbc=ls['rgbc'])

def ha_history(entity: str, days: int) -> list[tuple[float, float]]:
    headers = {'Authorization': f'Bearer {app_config.ha_token.get_secret_value()}'}
    now, out = dt.datetime.now(dt.timezone.utc), []
    for k in range(days, 0, -1):
        a = now - dt.timedelta(days=k)
        r = requests.get(f'{app_config.ha_base_url}/api/history/period/{a.isoformat()}', headers=headers, timeout=60, params={
            'end_time': (a + dt.timedelta(days=1)).isoformat(), 'filter_entity_id': entity, 'minimal_response': '1', 'no_attributes': '1'})
        for s in r.json():
            for x in s:
                try:
                    out.append((dt.datetime.fromisoformat(x['last_changed']).timestamp(), float(x['state'])))
                except ValueError:
                    pass
    return out

def envelope(ts, vs) -> dict | None:
    '''The floor (the sun well down) and the brightest over it by the sun's bearing (p90 of each bin, by day).'''
    ts, vs = np.asarray(ts, float), np.asarray(vs, float)
    order = np.argsort(ts)
    ts, vs = ts[order], vs[order]
    if len(ts) < 100:
        return None
    # A row each 2 minutes at most: Sensei sends every few seconds.
    keep = np.r_[True, np.diff(ts // 120) > 0]
    ts, vs = ts[keep], vs[keep]
    alt, az = np.array([sun_at(t) for t in ts]).T
    night = vs[alt < night_alt]
    floor = float(np.median(night)) if len(night) > 20 else float(np.percentile(vs, 2))
    day = alt > min_alt
    bins = np.arange(0, 360, az_step)
    env = [float(np.percentile(vs[s] - floor, 90)) if (s := day & (abs((az - b + 180) % 360 - 180) < az_step * 1.5)).sum() >= 10 else None
           for b in bins]
    if sum(e is not None for e in env) < 5:
        return None
    return {'at': time.time(), 'floor': floor, 'env': env}

def env_at(e: dict, az: float) -> float | None:
    bins = np.arange(0, 360, az_step)
    ok = [i for i, v in enumerate(e['env']) if v is not None and v > 0]
    near = [i for i in ok if abs((bins[i] - az + 180) % 360 - 180) <= az_step * 2]
    if not near:
        return None
    return float(np.interp(az, bins[ok], [e['env'][i] for i in ok], period=360))

def lamps() -> list[float] | None:
    from disinfo.utils.hass import get_entity
    out = []
    for name in app_config.daylight_lamps:
        e = get_entity(name)
        if e is None or e.state not in ('on', 'off'):
            return None
        out.append(round((e.attributes or {}).get('brightness') or 0) if e.state == 'on' else 0)
    return out

def lamp_model(rows: list) -> np.ndarray | None:
    # The desk's counts (r, g, b, c) from the lamps' brightness, the sun well down: [1 + lamps, 4].
    n = len(app_config.daylight_lamps)
    x, y = [], []
    for row in rows:
        if row[3] is not None and len(row) == 7 + n and None not in row[7:] and sun_at(row[0])[0] < night_alt:
            x.append([1, *(v / 255 for v in row[7:])])
            y.append(row[3:7])
    if len(x) < 60:
        return None
    x, y = np.array(x), np.array(y)
    # Lamps never seen on can't be told apart: they count for nothing.
    seen = np.r_[True, x[:, 1:].max(axis=0) > 0]
    coef = np.zeros((x.shape[1], 4))
    coef[seen] = np.linalg.lstsq(x[:, seen], y, rcond=None)[0]
    return coef

def desk_daylight(row: list, coef) -> np.ndarray | None:
    # The desk's counts (r, g, b, c) with the lamps taken off; None while they're unknown.
    if row[3] is None or coef is None or len(row) != 6 + coef.shape[0] or None in row[7:]:
        return None
    return np.array(row[3:7]) - np.array([1, *(v / 255 for v in row[7:])]) @ coef

def refresh(rows: list) -> dict:
    '''Once a day: Sensei's envelope from Home Assistant's history (more days than the log), the lamps on the desk,
    its envelope and its usual colour (log r/b) from the log.'''
    hist = ha_history(app_config.daylight_lux, log_days)
    envs = {'at': time.time(), 'sensei': envelope([t for t, _ in hist], [v for _, v in hist]), 'coef': None, 'desk': None, 'rb': None}
    if (coef := lamp_model(rows)) is None:
        return envs
    envs['coef'] = coef.tolist()
    day = [(r[0], d) for r in rows if (d := desk_daylight(r, coef)) is not None]
    if len(day) > 2 * 720:
        envs['desk'] = envelope([t for t, _ in day], [d[3] for _, d in day])
    rbs = [math.log(d[0] / d[2]) for t, d in day[::10] if d[0] > 0 and d[2] > 0 and sun_at(t)[0] > 10]
    envs['rb'] = float(np.median(rbs)) if len(rbs) > 100 else None
    return envs

def estimate(rows: list, envs: dict, sky: dict | None, now: float) -> dict:
    alt, az = sun_at(now)
    env_s, env_d, rb = envs.get('sensei'), envs.get('desk'), envs.get('rb')
    coef = np.array(envs['coef']) if envs.get('coef') else None
    model = None
    if sky and now - sky['at'] < 3 * 3600:
        model = {'cloud': sky['cloud_cover'] / 100, 'low': sky['cloud_cover_low'] / 100, 'mid': sky['cloud_cover_mid'] / 100,
                 'high': sky['cloud_cover_high'] / 100, 'kt': sky['shortwave_radiation'] / clear_ghi(alt) if alt > min_alt else None}
    out = {'at': now, 'alt': round(alt, 1), 'source': 'none', 'b': None, 'cloud': None, 'dark': None, 'sun': None,
           'broken': None, 'warmth': None, 'model': model}
    if alt < min_alt:
        out['source'] = 'night'
        return out

    def ratio(row):
        # log10 of the daylight over the brightest seen with the sun there: Sensei's and the desk's, averaged.
        _, a = sun_at(row[0])
        logs = []
        if env_s and row[1] is not None and (e := env_at(env_s, a)):
            logs.append(math.log10(max(row[1] - env_s['floor'], 0.05) / e))
        if env_d and (d := desk_daylight(row, coef)) is not None and (e := env_at(env_d, a)):
            logs.append(math.log10(max(d[3], 1) / e))
        return float(np.mean(logs)) if logs else None

    logs = [v for r in rows if now - r[0] < 20 * 60 and (v := ratio(r)) is not None]
    if not logs:
        return out
    lb = float(np.median(logs[:5]))
    if lb < math.log10(shutter_b) and (model is None or (model['kt'] or 0) > 0.35):
        out['source'] = 'shutter'
        return out
    out.update(source='light', b=round(10 ** lb, 3),
               # Dimmed by the cloud: none at 0.7 of the brightest, all at a seventh.
               cloud=round(float(np.clip((-lb - 0.15) / 0.75, 0, 1)), 3),
               dark=round(float(np.clip((-lb - 0.6) / 0.8, 0, 1)), 3),
               sun=round(float(np.clip((lb + 0.4) / 0.3, 0, 1)), 3),
               broken=round(float(np.clip(np.std(logs) / 0.2, 0, 1)), 3) if len(logs) >= 8 else None)
    # The colour: redder or bluer than the desk's daylight usually is.
    if rb is not None and (d := desk_daylight(rows[0], coef)) is not None and d[0] > 0 and d[2] > 0:
        out['warmth'] = round(math.log(d[0] / d[2]) - rb, 3)
    return out

_refreshing = threading.Event()

def task():
    from disinfo.redis import db, publish
    from disinfo.utils.hass import get_entity
    now = time.time()
    num = lambda name: float(e.state) if (e := get_entity(name)) and e.state not in ('unknown', 'unavailable') else None
    desk = _desk['rgbc'] if now - _desk['at'] < 120 else None
    row = [round(now), num(app_config.daylight_lux), num(app_config.daylight_uv), *(desk or [None] * 4), *(lamps() or [None] * len(app_config.daylight_lamps))]
    db.lpush(LOG_KEY, json.dumps(row))
    db.ltrim(LOG_KEY, 0, log_days * 1440)

    envs = json.loads(db.get(ENV_KEY) or '{}')
    if now - envs.get('at', 0) > 86400 and not _refreshing.is_set():
        # A minute's work (HA's history): not in the scheduler's thread, the planes are polled there.
        def run():
            try:
                db.set(ENV_KEY, json.dumps(refresh([json.loads(r) for r in db.lrange(LOG_KEY, 0, -1)])), ex=3 * 86400)
            except Exception as e:
                print(f'daylight refresh: {e!r}')
            finally:
                _refreshing.clear()
        _refreshing.set()
        threading.Thread(target=run, daemon=True).start()
    out = estimate([json.loads(r) for r in db.lrange(LOG_KEY, 0, 30)], envs, json.loads(db.get(SKY_KEY) or 'null'), now)
    db.set(KEY, json.dumps(out), ex=15 * 60)
    publish('weather', 'daylight')
    if app_config.devmode:
        return True
    try:
        from disinfo.utils import ha_states
        pct = lambda v: None if v is None else v * 100
        ha_states.publish(app_config.daylight_node, {'clear': desk[3] if desk else None, 'daylight': pct(out['b']), 'sky_cloud': pct(out['cloud'])})
    except Exception as e:
        print(f'daylight ha: {e!r}')
    return True


_doc = {'read': 0.0, 'doc': None}

def doc() -> dict | None:
    '''The latest, read from redis every 20 s; None if it's older than 10 minutes.'''
    now = time.monotonic()
    if now - _doc['read'] > 20:
        from disinfo.redis import db
        _doc['read'] = now
        try:
            _doc['doc'] = json.loads(db.get(KEY) or 'null')
        except ValueError:
            _doc['doc'] = None
    d = _doc['doc']
    return d if d and time.time() - d['at'] < 600 else None
