import websocket
import time
import threading
import json
import rich
from datetime import datetime, timedelta, timezone

from ..redis import publish


def pluck(key, data, default=None):
    ks = key.split('.')
    store = data
    for k in ks:
        store = store.get(k)
        if not store:
            return default
        if type(store) == dict:
            continue
        return store

def calculate_pct_job(data) -> float:
    """Get a pct estimate of the job based on a mix of progress value and fillament used.

    This strategy is inline with Mainsail estimate.

    Source: https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/main/custom_components/moonraker/sensor.py
    """
    print_expected_duration = pluck('file_metadata.estimated_time', data, 0)
    filament_used = pluck('filament_used', data, 0)
    expected_filament = pluck('filament_total', data, 0)
    divider = 0
    time_pct = 0
    filament_pct = 0

    if print_expected_duration != 0:
        time_pct = pluck('progress', data, 0) / 100
        divider += 1

    if expected_filament != 0:
        filament_pct = 1.0 * filament_used / expected_filament
        divider += 1

    if divider == 0:
        return 0

    return (time_pct + filament_pct) / divider

def calculate_eta(data):
    """Calculate ETA of current print.
    
    Source: https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/main/custom_components/moonraker/sensor.py
    """
    percent_job = calculate_pct_job(data)
    if (
        pluck('print_duration', data, 0) <= 0
        or percent_job <= 0
        or percent_job >= 1
    ):
        return None

    time_left = round(
        (pluck('print_duration', data, 0) / percent_job) - pluck('print_duration', data, 0),
        2,
    )

    return (datetime.now(timezone.utc) + timedelta(0, time_left)).isoformat()


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
        # rich.print(f'Received message from {self.host}:', msg)
        s = self.klipper_state
        prev_state = s.copy()
        msg = json.loads(msg)
        if msg.get('id') == 10042:
            status = msg['result']['status']
            s['bed_temp'] = pluck('heater_bed.temperature', status)
            s['extruder_temp'] = pluck('extruder.temperature', status)
            s['filename'] = pluck('print_stats.filename', status)
            s['state'] = pluck('print_stats.state', status)
            s['progress'] = pluck('display_status.progress', status, -1) * 100
        if msg.get('id') == 10043:
            s['file_metadata'] = msg['result']
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
            if pluck('print_stats.print_duration', params):
                s['print_duration'] = pluck('print_stats.print_duration', params)
            if pluck('display_status.progress', params):
                s['progress'] = pluck('display_status.progress', params) * 100
            if pluck('print_stats.filament_used', params):
                s['filament_used'] = pluck('print_stats.filament_used', params)

        if prev_state.get('filename') != s.get('filename') and s.get('filename'):
            self.send("server.files.metadata", 10043, filename=s['filename'])


        s['eta'] = calculate_eta(s)
        s['pct_job'] = calculate_pct_job(s)

        rich.print(f'Klipper state:', s)

        publish('di.pubsub.klipper', action='update', payload=s)

    def on_open(self, ws):
        self.connected = True
        self.retry_count = 0
        print(f'Connected to {self.host}')

        self.send("printer.objects.subscribe", 10042, objects={
            "gcode_move": None,
            "toolhead": ["position", "status"],
            "display_status": None,
            "heater_bed": ["temperature", "state"],
            "extruder": ["temperature", "state"],
            "print_stats": None,
            "print_duration": None,
            "virtual_sdcard": None,
        })
    
    def on_close(self, *args):
        self.connected = False
        print(f'Disconnected to {self.host}, will retry.')
        threading.Thread(target=self.retry_connect).start()
    
    def on_error(self, ws, error):
        print(f'Error in connection to {self.host}: {error}')
        self.connected = False

    def send(self, method: str, id: int, **kwargs):
        if not self.connected:
            return
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": kwargs,
            "id": id,
        }
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