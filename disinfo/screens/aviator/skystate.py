'''The sky, the weather and the time over home in one doc for the visualisations (di.sky), made once a minute in the data
service from every source there is.

Each source says only what it sees, as observations [value, sigma]: the model (AROME through Open-Meteo) for the sky,
the models blended (weather/forecast.py) for the air, the stations around (weather/stations.py) for what they measure,
the light by the window (daylight.py) for the cloud and the sun by day, the satellite for cold cloud tops, Home
Assistant's weather state, the radar for the rain at home, the planes for the air aloft (aloft.py), and anything else
that writes di.sky.obs.<source> (the half-sky camera, later): {at, q: {name: [value, sigma]}}, with an expiry. The model
is the start, each observation pulls by 1/sigma², an old one less, and sources that disagree make it less sure rather
than meeting halfway. Each quantity is {v, conf (0..1), by {source: value}}.

di.sky: {at, time {sun {alt, az, phase, rise, set}, moon {alt, az, phase}}, sky {cover, deck (low and mid: what hides
the sky), high (cirrus), sun (the direct sun out), dark, brightness, broken, warmth, haze, shutter}, precip {rate mm/h,
snow (its share), near mm/h (8-18 km), next {begin, end, mm, p}}, air {temp, dew, rh, feels, pressure, wind, gust, dir,
tendency (hPa in 3 h), vis, ceiling, wx, freezing_m, profile, lapse, inversion, jet, wind_low, wind_high, contrails
{form_m, persist}, model_bias}, alerts [{phenomenon, color, begin, end}], trend {hours [[t, cover, mm, temp, sun]], seen
[[t, cover, deck, sun, dark, mm]]}, forecast {at, hours [[t, temp, dew, wind, gust, pressure, mm, rain_p, cloud,
spread]], today {high, low}}, sources {name: age s or None}}.
Read it with doc() and v().
'''
import json
import math
import time
import datetime as dt
import numpy as np

from suncalc import get_times

from disinfo.config import app_config
from . import aloft, astro, daylight, weather
from .utils import home

KEY = 'di.sky'
LOG_KEY = 'di.sky.log'      # a row a minute, newest first: [t, cover, deck, high, sun, dark, mm, conf of the cover]
OBS_PREFIX = 'di.sky.obs.'
log_days = 14
home_ground = 47            # m above the sea
rain_home_mm = 6            # mm/h that is a downpour (the HA state's rain, as a rate)
snow_c = (0, 2)             # °C at home: snow under the first, rain over the second
snow_m = (250, 900)         # the freezing level over the ground: snow under the first, rain over the second
rain_p = 0.4                # the models' share that wets an hour for it to be a wet one

# HA weather state -> (cloud 0..1, haze 0..1, darker, rain or snow 0..1, the snow's share 0..1)
conditions = {
    'sunny': (0, 0.1, 0, 0, 0), 'clear-night': (0, 0.1, 0, 0, 0), 'partlycloudy': (0.35, 0.2, 0, 0, 0), 'cloudy': (0.8, 0.35, 0.1, 0, 0),
    'fog': (1, 0.9, 0.1, 0, 0), 'rainy': (0.9, 0.5, 0.25, 0.4, 0), 'pouring': (1, 0.55, 0.35, 0.85, 0), 'snowy': (0.9, 0.6, 0.15, 0.4, 1),
    'snowy-rainy': (0.9, 0.55, 0.2, 0.3, 0.5), 'hail': (1, 0.5, 0.35, 0.5, 0), 'lightning': (0.9, 0.4, 0.35, 0, 0),
    'lightning-rainy': (1, 0.5, 0.4, 0.6, 0), 'windy': (0.3, 0.15, 0, 0, 0), 'windy-variant': (0.5, 0.2, 0.05, 0, 0), 'exceptional': (0.5, 0.3, 0.1, 0, 0),
}
# name -> (kind, the spread that halves the confidence): 'unit' 0..1, 'mm' fused as log(1 + mm/h), 'lin' as is.
quantities = {
    'cover': ('unit', 0.2), 'deck': ('unit', 0.2), 'high': ('unit', 0.2), 'sun': ('unit', 0.2), 'dark': ('unit', 0.2),
    'brightness': ('unit', 0.2), 'broken': ('unit', 0.2), 'warmth': ('lin', 0.2), 'haze': ('unit', 0.2),
    'rate': ('mm', 0.3), 'snow': ('unit', 0.2), 'temp': ('lin', 1.5), 'freezing_m': ('lin', 250),
    'dew': ('lin', 1.5), 'pressure': ('lin', 1.5), 'wind': ('lin', 1.5), 'gust': ('lin', 3),
}
# source -> s after which its sigma has doubled; past 3x it's dropped.
stale = {'model': 3 * 3600, 'light': 600, 'sat': 1800, 'ha': 1800, 'radar': 900, 'planes': 1800, 'stations': 1200,
         'blend': 3 * 3600, 'prior': 1e9}
stale_other = 900


def fuse(obs: list[tuple[str, float, float, float]], kind: str, half: float) -> dict | None:
    '''obs: (source, value, sigma, age s) -> {v, conf, by}. Weighted by 1/sigma² (sigma growing with the age); the
    confidence falls with the fused sigma and with the sources' spread around the result.'''
    to = (lambda x: math.log1p(max(x, 0))) if kind == 'mm' else (lambda x: x)
    back = (lambda x: math.expm1(x)) if kind == 'mm' else (lambda x: x)
    pts = []
    for src, val, sigma, age in obs:
        tau = stale.get(src, stale_other)
        if val is None or age > 3 * tau:
            continue
        pts.append((src, to(val), (sigma * (1 + age / tau)) ** -2))
    if not pts:
        return None
    w = np.array([p[2] for p in pts])
    x = np.array([p[1] for p in pts])
    m = float(w @ x / w.sum())
    spread2 = float(w @ (x - m) ** 2 / w.sum())
    conf = 1 / (1 + (1 / w.sum() + spread2) / half ** 2)
    v = back(m)
    if kind == 'unit':
        v = min(max(v, 0), 1)
    r = 1 if kind == 'lin' and half > 10 else 3
    return {'v': round(v, r), 'conf': round(conf, 2), 'by': {s: round(back(val), r) for s, val, _ in pts}}

def v(d: dict | None, path: str, default=None, conf: float = 0):
    '''The value at 'sky.cover' (a quantity's v, or a plain field), default if missing or less sure than conf.'''
    for k in path.split('.'):
        if not isinstance(d, dict) or d.get(k) is None:
            return default
        d = d[k]
    if isinstance(d, dict) and 'v' in d:
        return d['v'] if d['conf'] >= conf else default
    return d


# The sources: each (at, {name: (value, sigma)}) or None, with what else it knows in the last place.

def hour_of(hours: dict, now: float) -> int | None:
    ts = hours.get('time') or []
    if not ts:
        return None
    i = int(np.argmin([abs(t + 1800 - now) for t in ts]))        # an hour's value is for the hour it starts
    return i if abs(ts[i] + 1800 - now) < 2 * 3600 else None

def ice_rh(rh: float, t: float) -> float:
    # % over ice from % over water (Magnus).
    return rh * math.exp(17.62 * t / (243.12 + t)) / math.exp(22.46 * t / (272.62 + t))

levels = (850, 700, 500, 300, 250)

def model_obs(sky: dict | None, now: float, alt: float):
    if not sky:
        return None
    q = {'cover': (sky['cloud_cover'] / 100, 0.3), 'high': (sky['cloud_cover_high'] / 100, 0.3),
         'deck': (1 - (1 - sky['cloud_cover_low'] / 100) * (1 - sky['cloud_cover_mid'] / 100), 0.3)}
    if alt > daylight.min_alt:
        kt = sky['shortwave_radiation'] / daylight.clear_ghi(alt)
        q['sun'] = float(np.clip((kt - 0.45) / 0.3, 0, 1)), 0.3
        q['dark'] = float(np.clip((0.3 - kt) / 0.25, 0, 1)), 0.35
    hours = sky.get('hours') or {}
    i = hour_of(hours, now)
    lv = {}
    if i is not None:
        h = lambda k: hours.get(k, [None] * (i + 1))[i]
        if h('precipitation') is not None:
            q['rate'] = h('precipitation'), 0.5
        lv = {p: {k: h(f'{k}_{p}hPa') for k in ('temperature', 'relative_humidity', 'wind_speed', 'wind_direction')} for p in levels}
        # The freezing level between the ground and the levels (their pressure altitudes: close enough).
        pts = [(home_ground, h('temperature_2m'))] + [(aloft.pressure_m(p), lv[p]['temperature']) for p in levels]
        pts = [(a, t) for a, t in pts if t is not None]
        for (a0, t0), (a1, t1) in zip(pts, pts[1:]):
            if t0 >= 0 > t1:
                q['freezing_m'] = a0 + (a1 - a0) * t0 / (t0 - t1), 300
                break
    return sky['at'], q, lv

def light_obs(d: dict | None):
    # The window's light: the cloud and the sun when the sun's in its view; behind it, only how dark it is.
    if not d or d['source'] not in ('light', 'shutter'):
        return None
    if d['source'] == 'shutter':
        return d['at'], {}, {'shutter': True}
    lb = math.log10(max(d['b'], 1e-3))
    q = {'brightness': (min(d['b'], 1), 0.1), 'dark': (d['dark'], 0.15 if d.get('window', True) else 0.25)}
    if d['broken'] is not None:
        q['broken'] = d['broken'], 0.2
    if d['warmth'] is not None:
        q['warmth'] = d['warmth'], 0.2
    if d.get('window', True):
        q.update(deck=(d['cloud'], 0.15), cover=(d['cloud'], 0.25), sun=(d['sun'], 0.15))
    elif lb < -0.8:
        q['deck'] = float(np.clip((-lb - 0.15) / 0.75, 0, 1)), 0.25
    return d['at'], q, {'shutter': False}

def sat_obs():
    # The infrared over home (the nearest bins, every bearing): cold tops, so high and mid cloud. Blind to the low, and
    # thin cirrus looks warm through it: seeing nothing says little.
    doc = weather.sat_doc()
    if not doc or not (prof := weather.sky_profile('clouds')):
        return None
    c = float(np.clip(prof[0][:, :2].mean() * 2.5, 0, 1))
    return doc['at'], {'cover': (c, 0.35), 'high': (c, 0.35)} if c > 0.3 else {'cover': (c, 0.7)}, {}

def ha_obs(now: float):
    from disinfo.utils.hass import get_entity
    e = get_entity(app_config.weather_entity)
    if e is None:
        return None
    c = conditions.get(e.state, (0.3, 0.2, 0, 0, 0))
    q = {'cover': (c[0], 0.35), 'haze': (c[1], 0.3), 'dark': (c[2], 0.35), 'rate': (c[3] * rain_home_mm, 0.6)}
    if c[3] > 0:
        q['snow'] = c[4], 0.2
    try:
        q['temp'] = float((e.attributes or {})['temperature']), 1.5      # met.no's model, not a measure
    except (KeyError, TypeError, ValueError):
        pass
    return now, q, {'state': e.state}

def radar_obs():
    doc = weather.rain_doc()
    if not doc or not (prof := weather.sky_profile('rain')):
        return None
    near = float(prof[0][:, :2].max()) * weather.rain_full
    return doc['at'], {'rate': (prof[1], 0.25)}, {'near': round(near, 2)}

def planes_obs(now: float):
    if not (prof := aloft.profile(now)):
        return None
    der = aloft.derived(prof)
    q = {'freezing_m': (der['freezing_m'], 150)} if der['freezing_m'] is not None else {}
    if der['inversion']:
        q['haze'] = min(0.3 + der['inversion']['dt'] / 6, 0.9), 0.4
    return now, q, {'profile': prof, **der}

def stations_obs(d: dict | None, now: float):
    # What the stations measure (weather/stations.py): the air, the airports' cloud deck, fog, what falls.
    if not d or now - d['at'] > 3600:
        return None
    h = d['home']
    q = {name: tuple(h[k]) for name, k in (('temp', 't'), ('dew', 'td'), ('pressure', 'pmer'), ('wind', 'ms'),
                                            ('gust', 'gust'), ('rate', 'rr'), ('deck', 'deck')) if h.get(k)}
    wx = ' '.join(h.get('wx') or [])
    if 'SN' in wx or 'SG' in wx:
        q['snow'] = 1.0, 0.2
    elif any(k in wx for k in ('RA', 'DZ')):
        q['snow'] = 0.0, 0.3
    vis = h['vis'][0] if h.get('vis') else None
    if vis is not None and vis < 5000:
        q['haze'] = float(np.clip(1.2 - vis / 5000, 0.3, 1)), 0.2
    elif h.get('eiffel') is not None and h['eiffel'] > 0:       # warmer up the tower than down: an inversion
        q['haze'] = min(0.3 + h['eiffel'] / 6, 0.9), 0.4
    return d['at'], q, {k: h.get(k) for k in ('dir', 'tendency', 'ceiling', 'wx', 'eiffel')} | {'vis': vis}

def blend_obs(d: dict | None, now: float):
    # The models blended (weather/forecast.py) at now, as the prior for the air; sure as they've been here.
    from disinfo.screens.weather import forecast
    if not d:
        return None
    skill = forecast.skill()
    q = {}
    for name in ('temp', 'dew', 'pressure', 'wind', 'gust'):
        if (x := forecast.at(d, name, now)) is not None:
            q[name] = x, forecast.error(skill, 'blend', name if name in forecast.checked else 'temp', (now - d['at']) / 3600)[1]
    return d['at'], q, {}

def external_obs(db, now: float) -> dict:
    # Whatever else writes di.sky.obs.<source> (the camera): {at, q: {name: [value, sigma]}}.
    out = {}
    for key in db.scan_iter(f'{OBS_PREFIX}*'):
        key = key.decode() if isinstance(key, bytes) else key
        try:
            d = json.loads(db.get(key) or 'null')
            out[key[len(OBS_PREFIX):]] = d['at'], {k: tuple(x) for k, x in d['q'].items() if k in quantities}, d.get('notes') or {}
        except (TypeError, ValueError, KeyError):
            continue
    return out


def sun_phase(alt: float) -> str:
    for edge, name in ((-18, 'night'), (-12, 'astronomical'), (-6, 'nautical'), (-0.833, 'civil'), (6, 'golden')):
        if alt < edge:
            return name
    return 'day'

def sun_times(now: float) -> dict:
    # The next sunrise and sunset (s), today's or tomorrow's.
    out = {}
    for k, name in (('sunrise', 'rise'), ('sunset', 'set')):
        for day in (0, 1):
            t = get_times(dt.datetime.fromtimestamp(now + day * 86400, dt.timezone.utc), home[1], home[0])[k]
            t = t.replace(tzinfo=dt.timezone.utc).timestamp() if t.tzinfo is None else t.timestamp()
            if t > now:
                out[name] = round(t)
                break
    return out

def snow_obs(temp: dict | None, freezing: dict | None) -> list:
    # The snow's share from the temperature at home and the freezing level over the ground.
    out = []
    if temp:
        out.append(('temp', float(np.clip((snow_c[1] - temp['v']) / (snow_c[1] - snow_c[0]), 0, 1)), 0.3, 0))
    if freezing:
        agl = freezing['v'] - home_ground
        out.append(('freezing', float(np.clip((snow_m[1] - agl) / (snow_m[1] - snow_m[0]), 0, 1)), 0.2, 0))
    return out

def air(lv: dict, planes: dict | None) -> dict:
    '''The profile, the winds low and high, the trails (where they form: the planes, else the model; if they last: the
    model's humidity over ice), and how far the model is off the planes at its levels.'''
    out = {'profile': None, 'lapse': None, 'inversion': None, 'jet': None, 'wind_low': None, 'wind_high': None,
           'contrails': None, 'model_bias': None}
    bins = planes['profile']['bins'] if planes else []
    if planes:
        out.update({k: planes[k] for k in ('lapse', 'inversion', 'jet')}, profile=bins)
    for name, p in (('wind_low', 850), ('wind_high', 300)):
        if bins and (w := aloft.wind_at(bins, aloft.pressure_m(p))):
            out[name] = {'dir': w[0], 'ms': w[1], 'by': 'planes'}
        elif lv.get(p, {}).get('wind_speed') is not None:
            out[name] = {'dir': lv[p]['wind_direction'], 'ms': lv[p]['wind_speed'], 'by': 'model'}
    form = planes and planes['contrail_m']
    if not form:
        for p in (300, 250):
            if (t := lv.get(p, {}).get('temperature')) is not None and t < aloft.contrail_c(p):
                form = round(aloft.pressure_m(p))
                break
    persist = [ice_rh(lv[p]['relative_humidity'], lv[p]['temperature']) for p in (300, 250)
               if lv.get(p, {}).get('relative_humidity') is not None and lv[p]['temperature'] is not None]
    if form or persist:
        out['contrails'] = {'form_m': form or None, 'persist': round(float(np.clip((max(persist) - 95) / 15, 0, 1)), 2) if persist else None}
    diffs = [lv[p]['temperature'] - t for p in levels if lv.get(p, {}).get('temperature') is not None
             and (t := aloft.temp_at(bins, aloft.pressure_m(p))) is not None]
    if diffs:
        out['model_bias'] = round(float(np.mean(diffs)), 1)
    return out

def alerts(now: float) -> list:
    from disinfo.screens.weather import vigilance
    d = vigilance.doc()
    out = []
    for ph, windows in (d or {}).get('phenomena', {}).items():
        for begin, end, color in windows:
            if end > now and color >= 2:
                out.append({'phenomenon': vigilance.PHENOMENA.get(ph, ph), 'color': color, 'begin': begin, 'end': end})
    return sorted(out, key=lambda a: (-a['color'], a['begin']))

def next_rain(now: float, fc: dict | None = None) -> dict | None:
    # The first wet hours ahead: the blend's when there is one (with how many models agree), else AROME's.
    from disinfo.screens.weather import vigilance
    if fc:
        hours = [[t, mm, p] for t, mm, p in zip(fc['time'], fc['rain'], fc['rain_p']) if mm is not None and t + 3600 > now]
    else:
        hours = [[h[0], h[1], None] for h in (vigilance.forecast_doc() or {}).get('hours', []) if h[0] + 3600 > now]
    wet = [i for i, h in enumerate(hours) if h[1] >= vigilance.rain_mm and (h[2] is None or h[2] >= rain_p)]
    if not wet:
        return None
    a = b = wet[0]
    while b + 1 < len(hours) and hours[b + 1][1] >= vigilance.rain_mm and (hours[b + 1][2] is None or hours[b + 1][2] >= rain_p):
        b += 1
    p = [h[2] for h in hours[a:b + 1] if h[2] is not None]
    return {'begin': hours[a][0] - 3600, 'end': hours[b][0], 'mm': max(h[1] for h in hours[a:b + 1]), 'p': max(p) if p else None}

def magnus(t: float) -> float:
    return 6.112 * math.exp(17.62 * t / (243.12 + t))

def feels(t: float, rh: float | None, wind: float | None) -> float:
    # Wind chill under 10 °C, the heat index over 27 °C (Steadman's, simple), else the air's.
    kmh = (wind or 0) * 3.6
    if t <= 10 and kmh > 4.8:
        return 13.12 + 0.6215 * t - 11.37 * kmh ** 0.16 + 0.3965 * t * kmh ** 0.16
    if t >= 27 and rh is not None:
        return t + 0.33 * rh / 100 * magnus(t) - 4
    return t

def surface(f: dict, notes: dict) -> dict:
    '''The air at home: the fused values, the humidity and the feel from them, and what only the stations know.'''
    g = lambda k: f[k]['v'] if f.get(k) else None
    t, td = g('temp'), g('dew')
    rh = round(min(100 * magnus(td) / magnus(t), 100)) if t is not None and td is not None else None
    return {'dew': f.get('dew'), 'rh': rh, 'feels': None if t is None else round(feels(t, rh, g('wind')), 1),
            'pressure': f.get('pressure'), 'wind': f.get('wind'), 'gust': f.get('gust'),
            **{k: notes.get(k) for k in ('dir', 'tendency', 'vis', 'ceiling', 'wx')}}

def outlook(fc: dict | None, obs_log: list, now: float, tz: str = 'Europe/Paris') -> dict | None:
    '''The blend pulled to the stations, by the hour ahead, and today's high and low: what the stations saw since
    midnight with what's ahead until the next.'''
    import pendulum
    from disinfo.screens.weather import forecast, stations
    if not fc:
        return None
    a = forecast.anchored(fc, (stations.doc() or {}).get('home'), now)
    rows = [[t, *(a[k][i] for k in ('temp', 'dew', 'wind', 'gust', 'pressure', 'rain', 'rain_p', 'cloud', 'spread'))]
            for i, t in enumerate(a['time']) if t + 3600 > now]
    day = pendulum.from_timestamp(now, tz).start_of('day')
    a0, a1 = day.int_timestamp, day.add(days=1).int_timestamp
    temps = [r[1] for r in obs_log if a0 <= r[0] <= now and r[1] is not None]
    temps += [r[1] for r in rows if now < r[0] <= a1 and r[1] is not None]
    today = {'high': round(max(temps), 1), 'low': round(min(temps), 1)} if temps else None
    return {'at': fc['at'], 'hours': rows, 'today': today}

def trend(sky: dict | None, db, now: float) -> dict:
    hours = (sky or {}).get('hours') or {}
    rows = []
    for i, t in enumerate(hours.get('time') or []):
        g = lambda k: (hours.get(k) or [None] * (i + 1))[i]
        alt = daylight.sun_at(t + 1800)[0]
        sun = round(min(g('direct_radiation') / (0.75 * daylight.clear_ghi(alt)), 1), 2) if alt > daylight.min_alt and g('direct_radiation') is not None else None
        rows.append([t, g('cloud_cover') and g('cloud_cover') / 100, g('precipitation'), g('temperature_2m'), sun])
    seen = [json.loads(r) for r in db.lrange(LOG_KEY, 0, 180)][::10][::-1]
    return {'hours': rows, 'seen': [[r[0], r[1], r[2], r[4], r[5], r[6]] for r in seen]}


def state(now: float, sources: dict, al: list = (), fc: dict | None = None) -> dict:
    '''sources: name -> (at, {name: (value, sigma)}, notes). The doc (without the trend).'''
    alt, az = daylight.sun_at(now)
    obs = {}
    for src, (at, q, _) in sources.items():
        for name, (val, sigma) in q.items():
            obs.setdefault(name, []).append((src, val, sigma, max(now - at, 0)))
    obs.setdefault('haze', []).append(('prior', 0.2, 0.4, 0))
    f = {name: fuse(o, *quantities[name]) for name, o in obs.items() if name in quantities}
    f['snow'] = fuse(obs.get('snow', []) + snow_obs(f.get('temp'), f.get('freezing_m')), 'unit', 0.2)
    notes = lambda src: sources[src][2] if src in sources else {}
    mb, me, phase = astro.moon_at(now, home[0], home[1])
    out = {
        'at': now,
        'time': {'sun': {'alt': round(alt, 1), 'az': round(az, 1), 'phase': sun_phase(alt), **sun_times(now)},
                 'moon': {'alt': round(me, 1), 'az': round(mb, 1), 'phase': round(phase, 3)}},
        'sky': {k: f.get(k) for k in ('cover', 'deck', 'high', 'sun', 'dark', 'brightness', 'broken', 'warmth', 'haze')},
        'precip': {'rate': f.get('rate'), 'snow': f.get('snow'), 'near': notes('radar').get('near'), 'next': next_rain(now, fc)},
        'air': {'temp': f.get('temp'), **surface(f, notes('stations')), 'freezing_m': f.get('freezing_m'),
                **air(notes('model').get('levels', {}), notes('planes') or None)},
        'alerts': list(al),
        'sources': {name: (round(now - sources[name][0]) if name in sources else None)
                    for name in sorted({*stale, *sources} - {'prior'})},
    }
    out['sky']['shutter'] = bool(notes('light').get('shutter'))
    if alt < daylight.min_alt:
        out['sky']['sun'] = None
    return out

def gather(db, now: float) -> tuple[dict, dict | None]:
    def safe(fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            print(f'sky {fn.__name__}: {e!r}')
            return None
    sky = json.loads(db.get(daylight.SKY_KEY) or 'null')
    alt = daylight.sun_at(now)[0]
    sources = {}
    if m := safe(model_obs, sky, now, alt):
        sources['model'] = m[0], m[1], {'levels': m[2]}
    from disinfo.screens.weather import forecast, stations
    for name, r in (('light', safe(light_obs, json.loads(db.get(daylight.KEY) or 'null'))), ('sat', safe(sat_obs)),
                    ('ha', safe(ha_obs, now)), ('radar', safe(radar_obs)), ('planes', safe(planes_obs, now)),
                    ('stations', safe(stations_obs, json.loads(db.get(stations.KEY) or 'null'), now)),
                    ('blend', safe(blend_obs, json.loads(db.get(forecast.KEY) or 'null'), now))):
        if r:
            sources[name] = r
    sources.update(safe(external_obs, db, now) or {})
    return sources, sky

def task():
    from disinfo.redis import db, publish
    now = time.time()
    sources, sky = gather(db, now)
    try:
        al = alerts(now)
    except Exception:
        al = []
    from disinfo.screens.weather import forecast, stations
    fc = json.loads(db.get(forecast.KEY) or 'null')
    out = state(now, sources, al, fc)
    out['trend'] = trend(sky, db, now)
    try:
        out['forecast'] = outlook(fc, [json.loads(r) for r in db.lrange(stations.LOG_KEY, 0, 300)], now)
    except Exception as e:
        print(f'sky outlook: {e!r}')
        out['forecast'] = None
    g = lambda k: v(out, k)
    db.lpush(LOG_KEY, json.dumps([round(now), g('sky.cover'), g('sky.deck'), g('sky.high'), g('sky.sun'), g('sky.dark'),
                                  g('precip.rate'), (out['sky']['cover'] or {}).get('conf')]))
    db.ltrim(LOG_KEY, 0, log_days * 1440)
    db.set(KEY, json.dumps(out), ex=15 * 60)
    publish('weather', 'sky')
    return True

def observe(source: str, q: dict, ttl: float = 600, **notes):
    '''For another source in this code base: write its observations ({name: (value, sigma)}) for the fusion.'''
    from disinfo.redis import db
    db.set(f'{OBS_PREFIX}{source}', json.dumps({'at': time.time(), 'q': q, 'notes': notes}), ex=round(ttl))


def doc() -> dict | None:
    '''The latest state; None if it's older than 10 minutes (the data service down).'''
    d = daylight.read(KEY)
    return d if d and time.time() - d['at'] < 600 else None
