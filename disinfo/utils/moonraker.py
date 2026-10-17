import json
import threading
import pendulum
import websocket

from discore.data_structures import UniqInstance


# Klipper objects the printer card reads. None subscribes to all of an object's fields.
objects = {
    'print_stats': None,
    'idle_timeout': ['state'],
    'webhooks': None,
    'display_status': None,
    'virtual_sdcard': ['progress', 'is_active'],
    'toolhead': ['position', 'homed_axes'],
}
# Fields whose last change is remembered, for 'Ready 3m'.
watched = [('print_stats', 'state'), ('idle_timeout', 'state'), ('webhooks', 'state')]


class MoonrakerWS(metaclass=UniqInstance):
    '''Live Klipper status from Moonraker's websocket.

    Moonraker pushes what changed (Klipper batches them every ~250ms), merged here
    into `status`. Reconnects by itself; `live` is False until it has a status.
    '''

    def __init__(self, url: str, api_key: str | None = None):
        self.url = url
        self.status: dict[str, dict] = {}
        self.changed_at: dict[tuple[str, str], pendulum.DateTime] = {}
        self.live = False
        self.klippy = True
        self.ws = websocket.WebSocketApp(
            url,
            header={'X-Api-Key': api_key} if api_key else None,
            on_open=self.on_open,
            on_message=self.on_message,
            on_close=self.on_close)
        threading.Thread(target=self.ws.run_forever, kwargs=dict(reconnect=5, ping_interval=20), daemon=True).start()

    def subscribe(self):
        self.ws.send(json.dumps({'jsonrpc': '2.0', 'method': 'printer.objects.subscribe', 'params': {'objects': objects}, 'id': 1}))

    def on_open(self, ws):
        print(f'Connected to {self.url}')
        self.subscribe()

    def on_close(self, *args):
        self.live = False

    def merge(self, status: dict, initial: bool = False):
        before = {k: self.status.get(k[0], {}).get(k[1]) for k in watched}
        for name, fields in status.items():
            self.status.setdefault(name, {}).update(fields)
        now = pendulum.now('local')
        for k in watched:
            # The first status says nothing about when: left to the caller's fallback.
            if not initial and self.status.get(k[0], {}).get(k[1]) != before[k]:
                self.changed_at[k] = now

    def on_message(self, ws, msg):
        msg = json.loads(msg)
        match msg:
            case {'id': 1, 'result': {'status': status}}:
                self.merge(status, initial=not self.status)
                self.live = self.klippy = True
            case {'id': 1, 'error': error}:
                # Klippy isn't ready yet, notify_klippy_ready subscribes again.
                print(f'[moonraker] {self.url}: {error}')
            case {'method': 'notify_status_update', 'params': [status, *_]}:
                self.merge(status)
            case {'method': 'notify_klippy_ready'}:
                self.subscribe()
            case {'method': 'notify_klippy_disconnected'}:
                # Klipper's host process is gone, the status is stale until it's ready again.
                self.klippy = False
                self.changed_at[('webhooks', 'state')] = pendulum.now('local')

    def get(self, name: str, field: str, default=None):
        return self.status.get(name, {}).get(field, default)
