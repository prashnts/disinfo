'''The standalone remotes (~/repo/disinfo-remote): their actions done here, the state they show sent back.

Actions (a remote's widgets; ones not known here are skipped, remotes are shared):
  ha.<domain>.<object>[.brightness]  a scene turns on, a button presses, a script runs, the rest toggle (or
                                     follow the value: on/off, a brightness 0-100)
  timer.start.<s>, timer.add.<s>     a timer; add: to the soonest one, else a new one
  di.<action>                        as a press on the screens (di.pubsub.remote): a dict value is the payload, a
                                     bool its 'on', else 'v'; the remote's scope (local.scope.<screen>) its 'screen'
  di.aviator.<verb>.<arg>            the arg goes in the payload: view.<map|sky|solar>, map_up.<deg>, layer.<name>
                                     (a toggle: on), demo.<scene> ('-' for spaces), visit.<place>;
                                     turn.<sun|moon|landmark>: the sky view turned there; release: back to its own;
                                     fov, zoom: a slider's 0-100 scaled (30-180 deg, 0.25-4x)
Layouts: BUNDLES/<remote id>.svg or default.svg (compiled here, pushed when its hash differs).
State keys: ha.<entity> (its state), ha.<entity>.brightness (0-100), weather.temp, home.temp, timer.next,
  aviator.sky (the compass: remote sky widget), aviator.view.<v>, aviator.layer.<l>, aviator.light (bools),
  aviator.zoom (0-100), for the remote's scope.

    uv run --with-editable ../disinfo-remote python -m disinfo.remotes --dry [--ble] [--no-usb]   # the PC test: HA calls logged only
'''
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

from disinfo.redis import db, publish
from disinfo.utils import hass

log = logging.getLogger('remotes')
DRY = '--dry' in sys.argv


def ha_call(service: str, entity: str, **data):
    if DRY:
        log.info('dry: %s %s %s', service, entity, data or '')
        return
    hass.HaWS().call_service(service, target={'entity_id': entity}, service_data=data)


def act(action: str, value, remote: dict):
    ns, _, rest = action.partition('.')
    log.info('%s: %s %s', remote.get('remote'), action, '' if value is None else value)
    if ns == 'ha':
        parts = rest.split('.')
        entity, attr = '.'.join(parts[:2]), parts[2] if len(parts) > 2 else ''
        domain = parts[0]
        if attr == 'brightness':
            ha_call('light.turn_on', entity, brightness_pct=int(value or 0))
        elif domain == 'scene':
            ha_call('scene.turn_on', entity)
        elif domain == 'button':
            ha_call('button.press', entity)
        elif domain == 'script':
            ha_call('script.turn_on', entity)
        elif isinstance(value, bool):
            ha_call(f'homeassistant.turn_{"on" if value else "off"}', entity)
        else:
            ha_call('homeassistant.toggle', entity)
    elif ns == 'timer':
        from disinfo.apps import timer
        what, _, secs = rest.partition('.')
        secs = int(secs or 60)
        ts = timer.timers(time.time())
        if what == 'add' and ts:
            timer.shift(ts[0], secs)
        elif what in ('add', 'start'):
            timer.start(secs, origin='remote')
    elif ns == 'di':
        di_act(rest, value, remote)
    else:
        log.info('skipped: %s', action)


ARGS = {'aviator.view': 'view', 'aviator.map_up': 'deg', 'aviator.layer': 'layer', 'aviator.demo': 'scene',
        'aviator.visit': 'place'}
SCALED = {'aviator.fov': ('aviator.sky', 'fov', 30, 180), 'aviator.zoom': ('aviator.zoom', 'zoom', 0.25, 4)}


def di_act(rest: str, value, remote: dict):
    payload = {'remote': remote.get('id')} | ({'screen': remote['scope']} if remote.get('scope') else {})
    action = rest
    for a, k in ARGS.items():
        if rest.startswith(a + '.'):
            action, payload[k] = a, rest[len(a) + 1:].replace('-', ' ')
    if rest.startswith('aviator.turn.'):
        yaw = bearing_of(rest[len('aviator.turn.'):])
        action, value = 'aviator.sky', {'yaw': yaw} if yaw is not None else None
    elif rest == 'aviator.release':
        action, value = 'aviator.sky', None
    elif rest in SCALED and isinstance(value, (int, float)):
        action, k, lo, hi = SCALED[rest]
        value = {k: round(lo + (hi - lo) * value / 100, 2)}
    if isinstance(value, dict):
        payload |= value
    elif isinstance(value, bool):
        payload['on'] = value
    elif value is not None:
        payload['v'] = value
    publish('di.pubsub.remote', action=action, payload=payload)


def bearing_of(name: str) -> float | None:
    '''The sun, the moon or a landmark, as seen from home.'''
    from disinfo.config import app_config
    from disinfo.screens.aviator import astro, sky
    from disinfo.screens.aviator.utils import bearing, local_xy
    lat, lon = app_config.latitude, app_config.longitude
    if name == 'sun':
        from datetime import datetime, timezone
        from suncalc import get_position
        return round((math.degrees(get_position(datetime.now(timezone.utc), lon, lat)['azimuth']) + 180) % 360)
    if name == 'moon':
        return round(astro.moon_at(time.time(), lat, lon)[0])
    for n, mlat, mlon, *_ in sky.landmarks:
        if n.lower().replace(' ', '-') == name.lower():
            return round(bearing(*local_xy(mlat, mlon)))
    return None


SHORT = {'disalon': 'salon', 'distudy': 'study', 'dientry': 'entry', 'di_pcstate': 'pc'}


def sky_doc(scope: str | None) -> dict:
    '''The web page's compass data, small: the planes (watched first, then the highest), the sun, the moon, the
    landmarks, the window, what the screens on the sky view show (scope's only, if one).'''
    from datetime import datetime, timezone
    from suncalc import get_position
    from disinfo.config import app_config
    from disinfo.screens.aviator import astro, sky, state as avs
    from disinfo.screens.aviator.utils import bearing, local_xy
    lat, lon, now = app_config.latitude, app_config.longitude, time.time()
    st = avs.read_state()
    sun = get_position(datetime.now(timezone.utc), lon, lat)
    planes = sorted(((h in st.watched, p.get('elev') or 0, h, p) for h, p in st.planes.items() if 'bearing' in p),
                    reverse=True)[:60]
    live = []
    for k, raw in db.hgetall(avs.LIVE_KEY).items():
        screen, l = k.decode(), json.loads(raw)
        if now - l.get('at', 0) < 30 and l.get('yaw') is not None and (l.get('view') or 'sky') == 'sky' \
                and (not scope or scope == screen):
            live.append([SHORT.get(screen, screen), round(l['yaw']), round(l.get('fov') or 90)])
    return {'win': app_config.aviator_window,
            'sun': [round((math.degrees(sun['azimuth']) + 180) % 360), round(math.degrees(sun['altitude']))],
            'moon': [round(x) for x in astro.moon_at(now, lat, lon)[:2]],
            'marks': [[n, round(bearing(*local_xy(mlat, mlon)))] for n, mlat, mlon, *_ in sky.landmarks],
            'planes': [[h, p.get('flight') or h, round(p['bearing']), round(p.get('elev') or 0), w]
                       for w, _, h, p in planes],
            'live': live, 'hold': avs.SKY_HOLD}


def aviator_state(k: str, scope: str | None):
    from disinfo.screens.aviator import state as avs
    pick = lambda key, default: (lambda d: d.get(scope or '*', d.get('*', default)))(avs.read_scoped(key))
    what, _, arg = k.removeprefix('aviator.').partition('.')
    if what == 'sky':
        return sky_doc(scope)
    if what == 'view':
        view, at = pick(avs.VIEW_KEY, [None, 0]) or [None, 0]
        return view == arg and time.time() - at < avs.VIEW_HOLD
    if what == 'layer':
        return arg not in (pick(avs.LAYERS_KEY, []) or [])
    if what == 'light':
        return bool(pick(avs.LIGHT_KEY, False))
    if what == 'zoom':
        z = float(pick(avs.ZOOM_KEY, 1) or 1)
        return round((z - 0.25) / 3.75 * 100)
    return None


def weather_temp() -> str:
    raw = db.lindex('di.weather.obs.log', 0)
    obs = json.loads(raw) if raw else None
    return f'{obs[1]:.0f}°' if obs and obs[1] is not None else ''


def state(keys: list[str], remote: dict | None = None) -> dict:
    out = {}
    for k in keys:
        ns, _, rest = k.partition('.')
        if ns == 'aviator':
            try:
                if (v := aviator_state(k, (remote or {}).get('scope'))) is not None:
                    out[k] = v
            except Exception as e:
                log.warning('%s: %s', k, e)
        elif ns == 'ha':
            parts = rest.split('.')
            e = hass.get_entity('.'.join(parts[:2]))
            if not e:
                continue
            if len(parts) > 2 and parts[2] == 'brightness':
                b = e.attributes.get('brightness')
                out[k] = round(b * 100 / 255) if b is not None and e.state == 'on' else 0
            else:
                out[k] = e.state
        elif k == 'weather.temp':
            out[k] = weather_temp()
        elif k == 'home.temp':
            e = hass.get_entity('sensor.temp_average')
            out[k] = f'{float(e.state):.1f}°' if e and e.state not in ('unknown', 'unavailable') else ''
        elif k == 'timer.next':
            from disinfo.apps import timer
            ts = timer.timers(time.time())
            out[k] = timer.over(ts[0]) if ts else ''
    return out


BUNDLES = Path(os.environ.get('DI_REMOTES', Path.home() / '.local' / 'state' / 'disinfo-remote' / 'remotes'))
_compiled: dict[Path, tuple[float, object]] = {}


def bundle(hello: dict):
    '''The remote's layout: <its id, ':' as '-'>.svg in BUNDLES, else default.svg; compiled when changed.'''
    from disinfo_remote.compiler import compile_svg
    for name in (hello.get('id', '').replace(':', '-'), 'default'):
        p = BUNDLES / f'{name}.svg'
        if p.exists():
            mtime = p.stat().st_mtime
            if _compiled.get(p, (0,))[0] != mtime:
                _compiled[p] = mtime, compile_svg(p.read_bytes(), name=p.stem)
            return _compiled[p][1]
    return None


def main():
    from disinfo_remote.hub import Hub
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    hass.serve()                    # standalone: its own HA websocket (in the server: the data service's)
    Hub(act, state, bundle, usb='--no-usb' not in sys.argv, ble='--ble' in sys.argv).start()
    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()
