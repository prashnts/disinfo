import websocket
import json
import time
import threading
import re

from datetime import datetime
from pydantic.dataclasses import dataclass

from disinfo.config import app_config
from disinfo.redis import db as redis_db
from discore.data_structures import UniqInstance
from disinfo.data_structures import AppBaseModel



class HaWeatherDatapoint(AppBaseModel):
    datetime: datetime
    condition: str
    temperature: float
    templow: float
    precipitation: float
    wind_speed: float
    wind_bearing: float
    humidity: float
    uv_index: float | None = None

class HaWeatherForecast(AppBaseModel):
    forecast: list[HaWeatherDatapoint]

ForecastServiceResponse = dict[str, HaWeatherForecast]

@dataclass(config=dict(extra="allow"))
class EntityAttributes:
    device_class: str | None = None
    state_class: str | None = None
    unit_of_measurement: str | None = None
    icon: str | None = None

class Entity(AppBaseModel):
    entity_id: str
    state: str
    attributes: dict | None
    last_changed: datetime
    last_updated: datetime
    last_reported: datetime | None
    service_response: HaWeatherForecast | None = None

class StateChangedEventData(AppBaseModel):
    entity_id: str
    old_state: Entity | None
    new_state: Entity | None

class EventData(AppBaseModel):
    event_type: str = "state_changed"
    time_fired: datetime
    data: StateChangedEventData

class ResponseResult(AppBaseModel):
    context: dict
    response: ForecastServiceResponse | None

class Msg(AppBaseModel):
    type: str
    id: int | None = None
    success: bool | None = None
    result: ResponseResult | list[Entity] | None = None
    event: EventData | None = None


class HaWSClient(metaclass=UniqInstance):
    def __init__(self):
        self.connected = False
        self.connecting = False
        self._retries = 0
        self.retry_delay_before_max_retries = 5 # seconds
        self.retry_delay_after_max_retries = 25 # seconds
        self.max_retries = 5
        self._mid = 42
        self.host = app_config.ha_websocket_url
        self.db: dict[str, Entity] = {}
        self.listeners = []     # called with each state_changed event (HA's thread)
        self.changed = []       # called with the entity ids whose state changed (the bridge)
    
    def _counter(self) -> int:
        x = self._mid
        self._mid += 1
        return x
    
    def on_message(self, ws, msg):
        msg = Msg.model_validate_json(msg)

        match msg:
            case Msg(type="auth_required"):
                self.send("auth", access_token=app_config.ha_token.get_secret_value())
            case Msg(type="auth_ok"):
                self.send("subscribe_events", id=self._counter(), event_type="state_changed")
                self.send("get_states", id=self._counter())
            case Msg(result=[*entities]):
                for entity in entities:
                    self.db[entity.entity_id] = entity
                self._changed([e.entity_id for e in entities])
            case Msg(event=event) if event and event.event_type == "state_changed":
                if new_state := event.data.new_state:
                    # A forecast asked for stays until the next one.
                    if new_state.service_response is None and (old := self.db.get(event.data.entity_id)):
                        new_state.service_response = old.service_response
                    self.db[event.data.entity_id] = new_state
                else:
                    self.db.pop(event.data.entity_id, None)
                for f in self.listeners:
                    try:
                        f(event)
                    except Exception as e:
                        print(f'HA listener failed: {e}')
                self._changed([event.data.entity_id])
            case Msg(result=ResponseResult(response=response)) if isinstance(response, dict):
                for uid, data in response.items():
                    if uid in self.db:
                        self.db[uid].service_response = data
                self._changed(list(response))
            case _:
                print(f'Unhandled message from HA: {msg}')

    def _changed(self, ids: list[str]):
        for f in self.changed:
            try:
                f(ids)
            except Exception as e:
                print(f'HA changed hook failed: {e}')

    def on_open(self, ws):
        self.connected = True
        self.connecting = False
        self._retries = 0
        print(f'Connected to {self.host}')
    
    def on_close(self, *args):
        self.connected = False
        self.connecting = False
        print(f'Disconnected to {self.host}, will retry.')
        self.retry_connect()
    
    def on_error(self, ws, *args, **kwargs):
        print(f'Error in connection to {self.host}: {args} {kwargs}')
        # self.connected = False

    def send(self, method: str, **kwargs) -> bool:
        print(method, {k: v for k, v in kwargs.items() if k != 'access_token'}, self.connected)
        if not self.connected:
            return False
        msg = {"type": method, **kwargs}
        self.ws.send(json.dumps(msg))
        return True

    def connect(self):
        if self.connected:
            return
        self.ws = websocket.WebSocketApp(
            self.host,
            on_message=self.on_message,
            on_open=self.on_open,
            on_close=self.on_close,
            on_error=self.on_error)
        
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()
        self.connecting = True
    
    def retry_connect(self):
        if self.connected or self.connecting:
            return
        if self._retries > self.max_retries:
            time.sleep(self.retry_delay_after_max_retries)
        else:
            time.sleep(self.retry_delay_before_max_retries)
        print(f'Retrying connection to {self.host}... (attempt {self._retries})')
        self._retries += 1
        self.connect()


# One websocket to Home Assistant, in the data service (serve()). Every other process gets only the entities it reads,
# over Redis: it asks for one (or a prefix) the first time, reads its state from the hash, then follows its changes.
# Service calls go to the data service the same way.
STATES_KEY = 'di.ha.states'     # entity id -> its state (JSON), the wanted ones
WANTED_KEY = 'di.ha.wanted'     # entity ids, and prefixes ending in '*'
STATE_CHANNEL = 'di.ha.state'   # 'entity_id\n' + its state; nothing after the newline: it's gone
WANT_CHANNEL = 'di.ha.want'
CALL_CHANNEL = 'di.ha.call'

_serving = False

def _keep_listening(e, pubsub, worker):
    print(f'[ha] {e!r}')

def prefix_of(pattern: str) -> str:
    # get_entities' patterns are prefixes: r'media_player\.'.
    prefix = re.sub(r'\\(.)', r'\1', pattern)
    if re.escape(prefix) != pattern.replace('\\_', '_'):
        raise ValueError(f'Not a prefix: {pattern!r}')
    return prefix


class HaLocal(metaclass=UniqInstance):
    '''The websocket and all of HA's states: the data service. It mirrors the wanted ones to Redis.'''

    def __init__(self):
        self.client = HaWSClient()
        self.ids, self.prefixes = set(), ()
        for w in redis_db.smembers(WANTED_KEY):
            self._want(w.decode())
        # Filled again once HA sends its states: nothing stale left in it.
        redis_db.delete(STATES_KEY)
        self.client.changed.append(self.mirror)
        ps = redis_db.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(**{WANT_CHANNEL: self.on_want, CALL_CHANNEL: self.on_call})
        ps.run_in_thread(sleep_time=0.05, daemon=True, exception_handler=_keep_listening)
        self.client.connect()

    def _want(self, w: str) -> bool:
        if w.endswith('*'):
            if w[:-1] in self.prefixes:
                return False
            self.prefixes = (*self.prefixes, w[:-1])
        elif w in self.ids:
            return False
        else:
            self.ids.add(w)
        return True

    def wanted(self, entity_id: str) -> bool:
        return entity_id in self.ids or entity_id.startswith(self.prefixes)

    def mirror(self, ids: list[str]):
        p = redis_db.pipeline(transaction=False)
        for entity_id in ids:
            if not self.wanted(entity_id):
                continue
            if e := self.client.db.get(entity_id):
                raw = e.model_dump_json()
                p.hset(STATES_KEY, entity_id, raw)
            else:
                raw = ''
                p.hdel(STATES_KEY, entity_id)
            p.publish(STATE_CHANNEL, f'{entity_id}\n{raw}')
        if len(p):
            p.execute()

    def on_want(self, message):
        w = message['data'].decode()
        if self._want(w):
            redis_db.sadd(WANTED_KEY, w)
        match = (lambda k: k.startswith(w[:-1])) if w.endswith('*') else (lambda k: k == w)
        self.mirror([k for k in list(self.client.db) if match(k)])

    def on_call(self, message):
        call = json.loads(message['data'])
        self.client.send('call_service', id=self.client._counter(), **call)

    def get_entity(self, entity_id: str) -> Entity | None:
        return self.client.db.get(entity_id)

    def grep_entities(self, pattern: str) -> list[Entity]:
        expr = re.compile(pattern)
        keys = [k for k in list(self.client.db) if expr.match(k)]
        return [e for k in keys if (e := self.client.db.get(k))]

    def call_service(self, name: str, **kwargs) -> bool:
        domain, service = name.split('.')
        return self.client.send("call_service", domain=domain, service=service, id=self.client._counter(), **kwargs)


class HaMirror(metaclass=UniqInstance):
    '''The entities this process reads, from the data service's websocket.'''

    def __init__(self):
        self.db: dict[str, Entity] = {}
        self.ids, self.prefixes = set(), ()
        self.client = self      # HA's events (client.listeners) are the data service's
        self.listeners = []
        ps = redis_db.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(**{STATE_CHANNEL: self.on_state})
        ps.run_in_thread(sleep_time=0.05, daemon=True, exception_handler=_keep_listening)

    def on_state(self, message):
        entity_id, _, raw = message['data'].decode().partition('\n')
        if entity_id not in self.ids and not entity_id.startswith(self.prefixes):
            return
        if raw:
            self.db[entity_id] = Entity.model_validate_json(raw)
        else:
            self.db.pop(entity_id, None)

    def get_entity(self, entity_id: str) -> Entity | None:
        if entity_id not in self.ids:
            self.ids.add(entity_id)
            if raw := redis_db.hget(STATES_KEY, entity_id):
                self.db[entity_id] = Entity.model_validate_json(raw)
            self._want(entity_id)
        return self.db.get(entity_id)

    def grep_entities(self, pattern: str) -> list[Entity]:
        prefix = prefix_of(pattern)
        if prefix not in self.prefixes:
            self.prefixes = (*self.prefixes, prefix)
            for k, raw in redis_db.hscan_iter(STATES_KEY, match=prefix + '*'):
                self.db[k.decode()] = Entity.model_validate_json(raw)
            self._want(prefix + '*')
        expr = re.compile(pattern)
        return [e for k, e in list(self.db.items()) if expr.match(k)]

    def _want(self, w: str):
        # Kept in the set too: the data service reads it when it starts.
        redis_db.sadd(WANTED_KEY, w)
        redis_db.publish(WANT_CHANNEL, w)

    def call_service(self, name: str, **kwargs) -> bool:
        domain, service = name.split('.')
        return bool(redis_db.publish(CALL_CHANNEL, json.dumps({'domain': domain, 'service': service, **kwargs})))


def serve():
    '''This process (the data service) holds the websocket, for all.'''
    global _serving
    _serving = True
    HaLocal()

def HaWS() -> HaLocal | HaMirror:
    return HaLocal() if _serving else HaMirror()

def get_entity(entity_id: str) -> Entity | None:
    return HaWS().get_entity(entity_id)

def get_entities(pattern: str) -> list[Entity]:
    return HaWS().grep_entities(pattern)
