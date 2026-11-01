'''xbus: how the processes talk, over Redis.

- Bus: this process's subscriptions, one connection and one thread. Exact channels: a process gets only what it
  listens to.
- Shared / View: one process owns keyed data (HA's states), the others read the keys they use. A View asks for a key
  (or a prefix) the first time, reads it from the hash, then follows its changes. Only wanted keys are mirrored.
- Calls: fire and forget, from a View to the owner's handler.

Redis, for a Shared named n: the hash `x.n` (key -> value), the set `x.n.wanted` (keys, prefixes end in '*'), the
channels `x.n.changed` ('key\\n' + value; nothing after the newline: it's gone), `x.n.want`, `x.n.call` (JSON).
'''
import os
import json
import time
import threading

from typing import Any, Callable

from discore.data_structures import UniqInstance
from disinfo.redis import db

Handler = Callable[[str, bytes], None]      # (channel, data)


class Bus(metaclass=UniqInstance):
    '''Handlers run in the bus's thread: keep them short.'''

    def __init__(self):
        self._pid = os.getpid()
        self._ps = db.pubsub(ignore_subscribe_messages=True)
        self._lock = threading.Lock()
        self._channels: dict[str, list[Handler]] = {}
        threading.Thread(target=self._run, name='xbus', daemon=True).start()

    def on(self, channel: str, fn: Handler):
        if self._pid != os.getpid():
            # Forked: the parent's thread isn't here, nor are its subscriptions.
            self.__init__()
        with self._lock:
            if channel not in self._channels:
                self._channels[channel] = []
                self._ps.subscribe(channel)
            self._channels[channel].append(fn)

    def send(self, channel: str, data: bytes | str) -> int:
        '''How many processes got it.'''
        return db.publish(channel, data)

    def _run(self):
        while True:
            if not self._channels:
                time.sleep(0.05)
                continue
            try:
                # Locked: a subscription from another thread waits for this read, 50 ms at most.
                with self._lock:
                    m = self._ps.get_message(timeout=0.05)
            except Exception as e:
                # Redis gone: it reconnects and subscribes again on the next read.
                print(f'[xbus] {e!r}')
                time.sleep(1)
                continue
            if not m:
                continue
            channel = m['channel'].decode()
            for fn in self._channels.get(channel, ()):
                try:
                    fn(channel, m['data'])
                except Exception as e:
                    print(f'[xbus] {channel}: {e!r}')


class Shared:
    '''Keyed data this process owns. read(key): its value now (None: gone); keys(): all there are.
    on_call(payload): what the Views ask for.'''

    def __init__(self, name: str, read: Callable[[str], str | None], keys: Callable[[], list[str]],
                 on_call: Callable[[dict], Any] | None = None):
        self.name, self.read, self.keys = name, read, keys
        self.ids, self.prefixes = set(), ()
        for w in db.smembers(f'x.{name}.wanted'):
            self._want(w.decode())
        # Filled again as the owner learns its data: nothing stale left in it.
        db.delete(f'x.{name}')
        bus = Bus()
        bus.on(f'x.{name}.want', self._on_want)
        if on_call:
            bus.on(f'x.{name}.call', lambda channel, data: on_call(json.loads(data)))

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

    def wanted(self, key: str) -> bool:
        return key in self.ids or key.startswith(self.prefixes)

    def changed(self, keys: list[str]):
        p = db.pipeline(transaction=False)
        for key in keys:
            if not self.wanted(key):
                continue
            if (value := self.read(key)) is None:
                p.hdel(f'x.{self.name}', key)
            else:
                p.hset(f'x.{self.name}', key, value)
            p.publish(f'x.{self.name}.changed', f'{key}\n{value or ""}')
        if len(p):
            p.execute()

    def _on_want(self, channel: str, data: bytes):
        w = data.decode()
        self._want(w)
        self.changed([k for k in self.keys() if k.startswith(w[:-1])] if w.endswith('*') else [w])


class View:
    '''The keys of a Shared this process reads, parsed once per change. parse(str) -> the value.'''

    def __init__(self, name: str, parse: Callable[[str], Any]):
        self.name, self.parse = name, parse
        self.values: dict[str, Any] = {}
        self.ids, self.prefixes = set(), ()
        Bus().on(f'x.{name}.changed', self._on_changed)

    def _on_changed(self, channel: str, data: bytes):
        key, _, value = data.decode().partition('\n')
        if key not in self.ids and not key.startswith(self.prefixes):
            return
        if value:
            self.values[key] = self.parse(value)
        else:
            self.values.pop(key, None)

    def _want(self, w: str):
        # In the set too: an owner that starts later reads it.
        db.sadd(f'x.{self.name}.wanted', w)
        db.publish(f'x.{self.name}.want', w)

    def get(self, key: str) -> Any:
        if key not in self.ids:
            self.ids.add(key)
            if value := db.hget(f'x.{self.name}', key):
                self.values[key] = self.parse(value.decode())
            self._want(key)
        return self.values.get(key)

    def prefix(self, prefix: str) -> dict[str, Any]:
        if prefix not in self.prefixes:
            self.prefixes = (*self.prefixes, prefix)
            for k, value in db.hscan_iter(f'x.{self.name}', match=prefix + '*'):
                self.values[k.decode()] = self.parse(value.decode())
            self._want(prefix + '*')
        return {k: v for k, v in list(self.values.items()) if k.startswith(prefix)}

    def call(self, **payload) -> bool:
        '''False: no owner listening.'''
        return bool(db.publish(f'x.{self.name}.call', json.dumps(payload)))
