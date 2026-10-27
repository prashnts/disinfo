'''Paris metro from IDFM's PRIM: the next trains at the stops of screen_data's metro, and the lines' messages
summed up by the local llm. One job in the data service, it fetches only while the card is wanted.
'''
import re
import html
import json
import time
import threading
import unicodedata
import requests

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, ModelRetry

from disinfo.config import app_config
from disinfo.data_structures import AppBaseModel
from disinfo.redis import db, publish
from disinfo.utils.llm import model
from . import shown

PRIM = 'https://prim.iledefrance-mobilites.fr/marketplace'
KEY = 'di.metro.state'
NOTES_KEY = 'di.metro.notes'
trains_every = 60       # s between two looks at the stops (1M requests a day)
reports_every = 600     # the lines' messages: all the metro in one request (30k a day)
regular_gap = 8         # min: trains further apart and the line is slow, whatever its messages say
horizon = 30            # min of departures looked at for that
ahead_days = 7          # messages for later than this are left out

tz = ZoneInfo(app_config.timezone)
conf = lambda: app_config.screen_data.metro
norm = lambda s: re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower())


def get(path: str, **params) -> dict:
    r = requests.get(f'{PRIM}/{path}', params=params, timeout=15,
                     headers={'apiKey': app_config.idfm_api_key, 'Accept': 'application/json'})
    r.raise_for_status()
    return r.json()

def parse_trains(doc: dict, line_id: str, direction: str) -> list[float]:
    '''Departures (epoch s) of the line going to direction, the cancelled left out.'''
    out = []
    for v in doc['Siri']['ServiceDelivery']['StopMonitoringDelivery'][0].get('MonitoredStopVisit', []):
        j = v['MonitoredVehicleJourney']
        call = j['MonitoredCall']
        names = [n['value'] for n in j.get('DirectionName', []) + j.get('DestinationName', [])]
        at = call.get('ExpectedDepartureTime') or call.get('ExpectedArrivalTime') or call.get('AimedDepartureTime')
        if (not at or call.get('DepartureStatus') == 'cancelled' or f':{line_id}:' not in j['LineRef']['value']
                or not any(norm(direction) in norm(n) for n in names)):
            continue
        out.append(datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp())
    return sorted(out)

def parse_reports(doc: dict, lines: set[str], now: float) -> list[dict]:
    '''The watched lines' messages up to ahead_days, one each with the lines it's on, lifts left out.
    Ended ones stay a day when their period was cut to a second or so: their text may say longer.'''
    by_id = {d['id']: d for d in doc.get('disruptions', [])}
    def links(o):
        if isinstance(o, dict):
            if o.get('type') == 'disruption':
                yield o['id']
            for v in o.values():
                yield from links(v)
        elif isinstance(o, list):
            for v in o:
                yield from links(v)
    stamp = lambda s: datetime.strptime(s, '%Y%m%dT%H%M%S').replace(tzinfo=tz).timestamp()
    out = {}
    for lr in doc.get('line_reports', []):
        line = lr['line']['code']
        if line not in lines:
            continue
        for i in dict.fromkeys(links(lr)):
            d = by_id.get(i)
            if i in out:
                out[i]['lines'].append(line)
            if i in out or not d or 'Ascenseur' in (d.get('tags') or []):
                continue
            periods = [[stamp(p['begin']), stamp(p['end'])] for p in d['application_periods']]
            if not any((e > now or (e - b < 120 and e > now - 86400)) and b < now + ahead_days * 86400 for b, e in periods):
                continue
            msgs = {m['channel']['name']: m['text'] for m in d.get('messages', [])}
            body = msgs.get('moteur') or msgs.get('notification') or msgs.get('email') or ''
            out[i] = {
                'id': i, 'lines': [line], 'updated': d.get('updated_at'), 'periods': periods,
                'status': d['status'], 'effect': d['severity']['effect'], 'title': msgs.get('titre', ''),
                'text': ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', body)).split()),
            }
    return list(out.values())


def scheduled(at: datetime) -> bool:
    at = at.astimezone(tz)
    hm = at.strftime('%H:%M')
    return any(at.isoweekday() in w.days and w.month_days[0] <= at.day <= w.month_days[1] and w.start <= hm < w.end
               for w in conf().schedule)

def health(times: list[float], now: float) -> str:
    '''ok: trains within regular_gap of each other, slow: not, none: no trains coming.'''
    soon = [t for t in times if now <= t <= now + horizon * 60]
    if not soon:
        return 'none'
    gaps = [b - a for a, b in zip([now] + soon, soon)]
    return 'ok' if len(soon) > 1 and max(gaps) <= regular_gap * 60 else 'slow'

def catchable(stop, times: list[float], now: float) -> list[int]:
    '''Minutes to the trains one can still walk to.'''
    walk = conf().walk_min if stop.walk_min is None else stop.walk_min
    return [round((t - now) / 60) for t in times if t - now >= walk * 60]


def load(key: str) -> dict | None:
    try:
        return json.loads(db.get(key) or 'null')
    except ValueError:
        return None

_lock = threading.Lock()

def job(pressed: bool = False) -> bool:
    '''Fetches what's due, while the card is wanted. Pressed: a fresher look, but no more than 4 a minute.'''
    now = time.time()
    if not (pressed or shown.wanted(shown.load(), 'metro', scheduled(datetime.now(tz)), now)):
        return False
    doc = load(KEY) or {}
    due = lambda key, every: now - doc.get(key, 0) >= (every / 4 if pressed else every)
    if not due('at', trains_every):
        return False
    c = conf()
    if due('reports_at', reports_every):
        lines = {s.line for s in c.stops} | set(c.lines)
        doc['reports'] = parse_reports(get('v2/navitia/physical_modes/physical_mode%3AMetro/line_reports', count=100, disable_geojson='true'), lines, now)
        doc['reports_at'] = now
    doc['stops'] = [{
        'line': s.line, 'stop': s.stop,
        'times': parse_trains(get('stop-monitoring', MonitoringRef=f'STIF:StopPoint:Q:{s.stop_id}:'), s.line_id, s.direction),
    } for s in c.stops]
    doc['at'] = now
    db.set(KEY, json.dumps(doc), ex=6 * 3600)
    publish('di.pubsub.metro', 'update')
    summarize(doc)
    return True

def task(pressed: bool = False) -> bool:
    if not _lock.acquire(blocking=False):
        return False
    try:
        return job(pressed)
    except Exception as e:
        print(f'metro: {e!r}')
        return False
    finally:
        _lock.release()

def press():
    '''The button: shows the card for a while, or hides it when it's up (drat.shown).'''
    if shown.press('metro'):
        threading.Thread(target=task, kwargs={'pressed': True}, daemon=True).start()


class Span(AppBaseModel):
    start: datetime
    end: datetime

class Note(AppBaseModel):
    id: str
    text: str
    when: str = ''
    spans: list[Span] = []
    level: Literal['stop', 'slow', 'info'] = 'info'
    doubt: str = ''

class Notes(AppBaseModel):
    notes: list[Note]

brief = '''
You sum up Paris metro messages for a small LED display at home. Return one note for every message below, with its id:

- text: what happens, like a telegram, at most 6 words, in French like the message. Leave out the line number, the
  display shows it. Examples: "Travaux, trafic interrompu", "Châtelet fermé", "Arrêt Saint-Michel non desservi".
- spans: only when the text says other times than the periods, else []. The periods are often wrong: cut to a second,
  one for "du 9 au 13 novembre", one for "les mardi et mercredi dès 22:00". Then give the text's times, one span per day
  when it's some days or hours only. Paris time as 2026-11-09T22:00, no timezone.
- when: when it applies, at most 3 words, with absolute days, never "today" or "tonight". Examples: "jusqu'au 22/04",
  "8/11", "27-28/10 22h". Empty when it's now with no known end.
- level: "stop" when the whole line has no trains, or one of our stops is closed; "slow" for delays, a section or
  another station closed; "info" for the rest.
- doubt: at most 5 words when the data disagrees: the periods and the text, the status and the periods, a line said
  to be stopped while its trains run regularly at our stop, or the reverse. Empty when it all agrees.

Use only what's given, don't invent.
'''

agent = Agent(model, output_type=Notes, deps_type=set, retries=2)

@agent.output_validator
def every_one(ctx, out: Notes) -> Notes:
    if missing := ctx.deps - {n.id for n in out.notes}:
        raise ModelRetry(f'Give a note for every message, missing: {", ".join(missing)}')
    return out

def prompt(doc: dict, now: float) -> str:
    when = lambda t: datetime.fromtimestamp(t, tz).strftime('%a %Y-%m-%dT%H:%M')
    trains = {s['line']: f"{health(s['times'], now)} at {s['stop']}, next in {[round((t - now) / 60) for t in s['times'] if t >= now]} min" for s in doc['stops']}
    out = [brief, f'Now: {when(now)}, Paris.', f'Our stops: {", ".join(f"{s.stop} (line {s.line}, to {s.direction})" for s in conf().stops)}.']
    for r in doc['reports']:
        out += ['', f"[{r['id']}] lines {', '.join(r['lines'])}, status {r['status']}, effect {r['effect']}",
                f"periods: {'; '.join(f'{when(b)} to {when(e)}' for b, e in r['periods'])}",
                *[f'trains on {l} now: {trains[l]}' for l in r['lines'] if l in trains],
                r['title'], r['text']]
    return '\n'.join(out)

def checked(spans: list[Span], periods: list) -> list:
    '''The llm's times when they make sense: in order, from about when the message begins (that one's right).'''
    out = [[s.start.replace(tzinfo=tz).timestamp(), s.end.replace(tzinfo=tz).timestamp()] for s in spans]
    if out and all(b < e for b, e in out) and abs(min(b for b, _ in out) - min(b for b, _ in periods)) < 86400:
        return out
    return []

_summary = {'thread': None}

def summarize(doc: dict):
    '''In the background, once per set of messages and lines without trains (they may contradict them).'''
    now = time.time()
    sig = json.dumps([[r['id'], r['updated']] for r in doc['reports']] + sorted(s['line'] for s in doc['stops'] if health(s['times'], now) == 'none'))
    if (load(NOTES_KEY) or {}).get('sig') == sig or (_summary['thread'] and _summary['thread'].is_alive()):
        return
    def run():
        periods = {r['id']: r['periods'] for r in doc['reports']}
        notes = {}
        try:
            out = agent.run_sync(prompt(doc, now), deps=set(periods)).output.notes if periods else []
            notes = {n.id: {**n.model_dump(exclude={'spans'}), 'spans': checked(n.spans, periods[n.id])} for n in out if n.id in periods}
        except Exception as e:
            print(f'metro summary: {e!r}')
        # Failed too: not again until the messages change, they're shown as they come.
        db.set(NOTES_KEY, json.dumps({'sig': sig, 'notes': notes}), ex=86400)
        publish('di.pubsub.metro', 'update')
    _summary['thread'] = threading.Thread(target=run, daemon=True)
    _summary['thread'].start()

def note(r: dict, notes: dict, now: float) -> dict | None:
    '''The llm's note on a message, or one from the message itself until it's there. None once it's over.'''
    n = notes.get(r['id']) or {
        'text': re.sub(r'^Métro [^:]+ : ', '', r['title']), 'when': '', 'doubt': '', 'spans': [],
        'level': 'stop' if 'Trafic interrompu' in r['title'] else 'slow' if r['effect'] in ('NO_SERVICE', 'SIGNIFICANT_DELAYS') else 'info'}
    spans = n['spans'] or r['periods']
    if all(e < now for _, e in spans):
        return None
    now_ = any(b <= now < e for b, e in spans)
    when = n['when'] or ('' if now_ else datetime.fromtimestamp(min(b for b, _ in spans), tz).strftime('%d/%m'))
    return {**n, 'lines': r['lines'], 'now': now_, 'when': when}
