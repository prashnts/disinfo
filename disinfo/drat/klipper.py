import websocket
import time
import threading
import json

from ..redis import publish


def pluck(key, data):
    ks = key.split('.')
    store = data
    for k in ks:
        store = store.get(k)
        if not store:
            return None
        if type(store) == dict:
            continue
        return store

class KlipperClient:
    def __init__(self, host: str):
        self.host = host
        self.connected = False
        self.retry_count = 0
        self.retry_delay_before_max_retries = 5 # seconds
        self.retry_delay_after_max_retries = 25 # seconds
        self.max_retries = 5

        self.klipper_state = {}

        self.ws = websocket.WebSocketApp(f'ws://{host}/websocket',
                                         on_message=self.on_message,
                                         on_open=self.on_open,
                                         on_close=self.on_close,
                                         on_error=self.on_error)
    
    def on_message(self, ws, msg):
        print(f'Received message from {self.host}: {msg}')
        s = self.klipper_state
        msg = json.loads(msg)
        if msg.get('id') == 5434:
            status = msg['result']['status']
            s['bed_temp'] = pluck('heater_bed.temperature', status)
            s['extruder_temp'] = pluck('extruder.temperature', status)
            s['filename'] = pluck('print_stats.filename', status)
            s['state'] = pluck('print_stats.state', status)
            s['progress'] = pluck('display_status.progress', status) * 100
        if msg.get('method') == 'notify_status_update':
            params = msg['params'][0]
            if pluck('heater_bed.temperature', params):
                s['bed_temp'] = pluck('heater_bed.temperature', params)
            if pluck('extruder.temperature', params):
                s['extruder_temp'] = pluck('extruder.temperature', params)
            if pluck('print_stats.filename', params):
                s['filename'] = pluck('print_stats.filename', params)
            if pluck('print_stats.state', params):
                s['state'] = pluck('print_stats.state', params)
            if pluck('display_status.progress', params):
                s['progress'] = pluck('display_status.progress', params) * 100

        publish('di.pubsub.klipper', action='update', payload=s)

    def on_open(self, ws):
        self.connected = True
        self.retry_count = 0
        print(f'Connected to {self.host}')

        sub_status =  {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": {
                    "gcode_move": None,
                    "toolhead": ["position", "status"],
                    "display_status": None,
                    "heater_bed": ["temperature", "state"],
                    "extruder": ["temperature", "state"],
                    "print_stats": None,
                    "virtual_sdcard": None,
                }
            },
            "id": 5434
        }
        self.send(sub_status)
    
    def on_close(self, ws):
        self.connected = False
        print(f'Disconnected to {self.host}, will retry.')
        threading.Thread(target=self.retry_connect).start()
    
    def on_error(self, ws, error):
        print(f'Error in connection to {self.host}: {error}')
        self.connected = False

    def send(self, msg: dict):
        if not self.connected:
            return
        self.ws.send(json.dumps(msg))

    def connect(self):
        if self.connected:
            return
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()
    
    def retry_connect(self):
        if self.connected:
            return
        if self.retry_count > self.max_retries:
            time.sleep(self.retry_delay_after_max_retries)
        else:
            time.sleep(self.retry_delay_before_max_retries)
        print(f'Retrying connection to {self.host}... (attempt {self.retry_count})')
        self.retry_count += 1
        self.connect()