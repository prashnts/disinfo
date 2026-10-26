'''The next two days at home from every model Open-Meteo has over France (CC-BY 4.0, no key): each one taken off its
bias here and weighed by its error (both by lead time, learnt against the stations), then pulled to what the stations
see now, the gap fading over a few hours. Every run is kept until it can be checked against the stations: the score of
each model, of the blend and of what the card used to show (Home Assistant's met.no).

di.weather.blend: {at, time [s], temp, dew, wind, gust, pressure, rain (mm in the hour before), rain_p (0..1, the models
that wet it), cloud (0..1), spread (°C, the models around the blend)}: the hour's values, not yet pulled to the stations
(anchored() does that). di.weather.skill: {model: {var: {bucket: [bias, mse, n]}}}.
'''
import json
import math
import time
import requests

from disinfo.config import app_config

URL = 'https://api.open-meteo.com/v1/forecast'
KEY = 'di.weather.blend'
RUNS_KEY = 'di.weather.runs'        # the runs still to check, newest first: {at, time, m {model: {var: [...]}}}
SKILL_KEY = 'di.weather.skill'
CHECKED_KEY = 'di.weather.checked'  # the last hour checked (s)
VERIFY_KEY = 'di.weather.verify'    # an hour checked, newest first: [t, obs {var}, {model: {var: [[lead h, error]]}}]
verify_days = 60
hours_ahead = 48
models = {      # name -> the error assumed until it has one here (°C for the temperature; the others scale on it)
    'meteofrance_arome_france_hd': 1.1, 'meteofrance_arome_france': 1.2, 'meteofrance_arpege_europe': 1.5, 'icon_d2': 1.3,
    'ecmwf_ifs025': 1.4, 'ukmo_seamless': 1.5, 'knmi_seamless': 1.6, 'gfs_seamless': 1.9, 'metno_seamless': 1.4,
}
names = {'temperature_2m': 'temp', 'dew_point_2m': 'dew', 'wind_speed_10m': 'wind', 'wind_gusts_10m': 'gust',
         'pressure_msl': 'pressure', 'precipitation': 'rain', 'cloud_cover': 'cloud'}
checked = {'temp': 1.0, 'dew': 1.2, 'wind': 1.0, 'pressure': 0.6}    # against the stations, the prior error's scale
obs_of = {'temp': 1, 'dew': 2, 'pressure': 3, 'wind': 4}            # their place in the stations' log rows
buckets = (3, 6, 12, 24, 48)        # h: the leads are scored in these
memory = 7 * 24                     # hours a score remembers (each hour checked counts once per bucket)
shrink = 12                         # hours checked before the learnt bias and error count as much as the prior
fade = {'temp': 3, 'dew': 4, 'pressure': 8, 'wind': 2}     # h: how fast the stations' gap fades ahead
rain_mm = 0.2


def bucket(lead_h: float) -> int:
    return next((b for b in buckets if lead_h < b), buckets[-1])

def fetch() -> dict:
    r = requests.get(URL, timeout=60, params={'latitude': app_config.latitude, 'longitude': app_config.longitude,
        'hourly': ','.join(names), 'models': ','.join(models), 'forecast_hours': hours_ahead + 1,
        'timeformat': 'unixtime', 'wind_speed_unit': 'ms'})
    r.raise_for_status()
    h = r.json()['hourly']
    m = {name: {v: h.get(f'{k}_{name}') for k, v in names.items()} for name in models}
    for d in m.values():
        if d['cloud']:
            d['cloud'] = [c if c is None else c / 100 for c in d['cloud']]
    return {'at': time.time(), 'time': h['time'], 'm': m}


def error(skill: dict, model: str, var: str, lead_h: float) -> tuple[float, float]:
    '''(bias, rmse) of a model at a lead: what was learnt, shrunk to the prior while there's little of it.'''
    prior = models.get(model, 1.5) * checked.get(var, 1.0) * (1 + lead_h / 36)
    bias, mse, n = (skill.get(model) or {}).get(var, {}).get(str(bucket(lead_h)), (0.0, prior ** 2, 0))
    k = n / (n + shrink)
    return k * bias, math.sqrt(k * mse + (1 - k) * prior ** 2)

def blend(run: dict, skill: dict) -> dict:
    out = {'at': run['at'], 'time': run['time'], **{v: [] for v in names.values()}, 'rain_p': [], 'spread': []}
    for i, t in enumerate(run['time']):
        lead = max(t - run['at'], 0) / 3600
        for var in names.values():
            pts = []
            for name, d in run['m'].items():
                x = (d.get(var) or [None] * (i + 1))[i]
                if x is None:
                    continue
                # The ones not checked here weigh as the temperature does.
                bias, rmse = error(skill, name, var if var in checked else 'temp', lead)
                pts.append((x - bias if var in checked else x, rmse ** -2))
            if not pts:
                out[var].append(None)
                if var == 'rain':
                    out['rain_p'].append(None)
                if var == 'temp':
                    out['spread'].append(None)
                continue
            w = sum(p[1] for p in pts)
            m = sum(x * wi for x, wi in pts) / w
            out[var].append(round(max(m, 0) if var in ('rain', 'wind', 'gust') else m, 2))
            if var == 'rain':
                out['rain_p'].append(round(sum(wi for x, wi in pts if x >= rain_mm) / w, 2))
            if var == 'temp':
                out['spread'].append(round(math.sqrt(sum(wi * (x - m) ** 2 for x, wi in pts) / w), 2))
    return out

def at(doc: dict, var: str, t: float) -> float | None:
    # A value between the hours (the rain: the hour's).
    ts, vs = doc['time'], doc[var]
    for (t0, v0), (t1, v1) in zip(zip(ts, vs), zip(ts[1:], vs[1:])):
        if t0 <= t <= t1 and v0 is not None and v1 is not None:
            return v0 if var in ('rain', 'rain_p') else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return None

def anchored(doc: dict, home: dict | None, now: float) -> dict:
    '''The blend pulled to the stations: their gap at now, fading ahead (fade). home: stations.doc()['home'].'''
    out = dict(doc)
    k = {'temp': 't', 'dew': 'td', 'pressure': 'pmer', 'wind': 'ms'}
    for var, h in fade.items():
        obs = (home or {}).get(k[var])
        here = at(doc, var, now)
        if not obs or here is None:
            continue
        gap = obs[0] - here
        out[var] = [None if v is None else round(v + gap * math.exp(-max(t - now, 0) / 3600 / h), 2)
                    for t, v in zip(doc['time'], doc[var])]
    return out


def check(db, now: float, obs_log: list) -> int:
    '''Score the runs on the hours the stations have seen since the last check. The number of hours checked.'''
    last = float(db.get(CHECKED_KEY) or now - 3 * 3600)
    hours = [h for h in range(int(last // 3600 + 1) * 3600, int(now - 600), 3600)]
    if not hours or not obs_log:
        return 0
    runs = [json.loads(r) for r in db.lrange(RUNS_KEY, 0, -1)]
    skill = json.loads(db.get(SKILL_KEY) or '{}')
    for h in hours:
        row = min(obs_log, key=lambda r: abs(r[0] - h))
        if abs(row[0] - h) > 400:
            continue
        obs = {var: row[i] for var, i in obs_of.items() if row[i] is not None}
        errs = {}
        for run in runs:
            if run['at'] >= h or h not in run['time']:
                continue
            i, lead = run['time'].index(h), (h - run['at']) / 3600
            for name, d in run['m'].items():
                for var, o in obs.items():
                    if (x := (d.get(var) or [None] * (i + 1))[i]) is not None:
                        errs.setdefault(name, {}).setdefault(var, []).append([round(lead, 1), round(x - o, 2)])
        if len(row) > 7 and row[7] is not None and 'temp' in obs:
            errs['ha'] = {'temp': [[0, round(row[7] - obs['temp'], 2)]]}
        for name, vs in errs.items():
            for var, es in vs.items():
                for b in buckets:
                    e = [x for lead, x in es if bucket(lead) == b]
                    if not e:
                        continue
                    bias, mse, n = skill.setdefault(name, {}).setdefault(var, {}).get(str(b), (0.0, 0.0, 0))
                    a = 1 / min(n + 1, memory)
                    me, se = sum(e) / len(e), sum(x * x for x in e) / len(e)
                    skill[name][var][str(b)] = [round(bias + a * (me - bias), 3), round(mse + a * (se - mse), 3), n + 1]
        db.lpush(VERIFY_KEY, json.dumps([h, obs, errs]))
    db.ltrim(VERIFY_KEY, 0, verify_days * 24)
    db.set(SKILL_KEY, json.dumps(skill))
    db.set(CHECKED_KEY, hours[-1])
    # A run is done with once its last hour is checked (the oldest are last).
    keep = [i for i, r in enumerate(runs) if r['time'][-1] > hours[-1]]
    db.ltrim(RUNS_KEY, 0, max(keep)) if keep else db.delete(RUNS_KEY)
    return len(hours)

def job():
    from disinfo.redis import db, publish
    from . import stations
    now = time.time()
    obs = stations.doc() or {}
    check(db, now, [json.loads(r) for r in db.lrange(stations.LOG_KEY, 0, 30 * 24 * 10)])
    run = fetch()
    doc = blend(run, json.loads(db.get(SKILL_KEY) or '{}'))
    # Ours is scored with the others: the blend as the card would have used it, pulled to the stations.
    a = anchored(doc, obs.get('home') if obs and now - obs['at'] < 1800 else None, now)
    run['m']['blend'] = {v: a[v] for v in checked}
    db.lpush(RUNS_KEY, json.dumps({'at': run['at'], 'time': run['time'],
                                   'm': {k: {v: d[v] for v in checked if d.get(v)} for k, d in run['m'].items()}}))
    db.set(KEY, json.dumps(doc), ex=6 * 3600)
    publish('weather', 'blend')
    return True

def task():
    try:
        return job()
    except Exception as e:
        print(f'weather blend: {e!r}')
    return False


def doc() -> dict | None:
    from disinfo.screens.aviator import daylight
    return daylight.read(KEY)

def skill() -> dict:
    from disinfo.screens.aviator import daylight
    return daylight.read(SKILL_KEY) or {}

def skill_table(skill: dict, var: str = 'temp') -> list[str]:
    '''Lines: each model's rmse and bias by lead bucket, the best first (for a look in a shell).'''
    rows = []
    for name, vs in skill.items():
        d = vs.get(var) or {}
        cells = [d.get(str(b)) for b in buckets]
        rmse = [math.sqrt(c[1]) if c else None for c in cells]
        rows.append((next((r for r in rmse if r is not None), 99), name, cells, rmse))
    out = [f'{var:<28}' + ''.join(f'{f"<{b}h":>14}' for b in buckets)]
    for _, name, cells, rmse in sorted(rows):
        out.append(f'{name:<28}' + ''.join(f'{r:6.2f} {c[0]:+5.2f}#{c[2]:<3}' if c else f'{"":>14}' for c, r in zip(cells, rmse)))
    return out

if __name__ == '__main__':
    from disinfo.redis import db
    s = json.loads(db.get(SKILL_KEY) or '{}')
    for var in checked:
        print('\n'.join(skill_table(s, var)), end='\n\n')
