import requests
import time
import datetime
import json
import websocket
import threading

from traceback import format_exc
from schedule import Scheduler

from ..config import app_config
from ..redis import rkeys, set_dict, set_json, db, publish
from .app_states import PubSubManager, PubSubMessage
from ..data_structures import AppBaseModel
from . import idfm, washing_machine


class SafeScheduler(Scheduler):
    '''
    An implementation of Scheduler that catches jobs that fail, logs their
    exception tracebacks as errors, optionally reschedules the jobs for their
    next run time, and keeps going.
    Use this to run jobs that may or may not crash without worrying about
    whether other jobs will run or if they'll crash the entire script.

    Copied from https://gist.github.com/mplewis/8483f1c24f2d6259aef6
    '''

    def __init__(self, reschedule_on_failure=True):
        '''
        If reschedule_on_failure is True, jobs will be rescheduled for their
        next run as if they had completed successfully. If False, they'll run
        on the next run_pending() tick.
        '''
        self.reschedule_on_failure = reschedule_on_failure
        super().__init__()

    def _run_job(self, job):
        try:
            super()._run_job(job)
        except Exception:
            print(format_exc())
            job.last_run = datetime.datetime.now()
            job._schedule_next_run()

def get_weather():
    '''Fetch Weather from PirateWeather API.'''
    forecast_url = f'https://api.pirateweather.net/forecast/{app_config.pw_api_key}/{app_config.latitude},{app_config.longitude}?units={app_config.pw_unit}'
    try:
        print('[i] [fetch] weather')
        r = requests.get(forecast_url)
        r.raise_for_status()
        data = r.json()
        # write out the forecast.
        publish('di.pubsub.weather', action='update', payload=data)
    except requests.exceptions.RequestException as e:
        print('[e] weather', e)

def get_random_text():
    '''Fetch trivia from Numbers API.'''
    try:
        print('[i[ [fetch] random text')
        r = requests.get('http://numbersapi.com/random/trivia?json')
        r.raise_for_status()
        data = r.json()
        set_dict(rkeys['random_msg'], data)
        publish('di.pubsub.numbers', action='update', payload=data)
    except requests.exceptions.RequestException as e:
        print('[e] numbers', e)

def get_metro_info(force: bool = False):
    '''Fetch metro info in morning.'''
    if not force and not idfm.is_active():
        print('[i] [fetch] not fetching metro timing')
        return
    try:
        print('[i] [fetch] metro timing')
        data = idfm.fetch_state()
        set_json(rkeys['metro_timing'], data.model_dump_json())
        publish('di.pubsub.metro', action='update')
    except Exception as e:
        print('[e] metro_info', e)

def get_washing_machine_info():
    '''Fetch washing machine info.'''
    try:
        print('[i] [fetch] washing machine')
        data = washing_machine.read_display()
        publish('di.pubsub.washing_machine', action='update', payload=data)
    except Exception as e:
        print('[e] washing_machine', e)


def on_pubsub(channel_name: str, message: PubSubMessage):
    if message.action == 'fetch_metro':
        get_metro_info(force=True)
    if message.action == 'fetch_weather':
        get_weather()
    if message.action == 'fetch_numbers':
        get_random_text()


scheduler = SafeScheduler()

scheduler.every(15).minutes.do(get_weather)
scheduler.every(2).to(3).minutes.do(get_random_text)
scheduler.every(1).minutes.do(get_metro_info)
# scheduler.every(1).minutes.do(get_washing_machine_info)


klipper_state = {}

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

def on_klipper_msg(ws, msg):
    s = klipper_state
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
    print(msg)

    publish('di.pubsub.klipper', action='update', payload=s)

def on_klipper_connect(ws):
    print('Connected to klipper')
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
    ws.send(json.dumps(sub_status))

if __name__ == '__main__':
    print('[Data Service] Scheduler Started')

    pubsub = PubSubManager()
    pubsub.attach('data_service', ('di.pubsub.dataservice',), on_pubsub)

    ws = websocket.WebSocketApp(f'ws://{app_config.klipper_host}/websocket',
                                on_message=on_klipper_msg,
                                on_open=on_klipper_connect)
    ws_thread = threading.Thread(target=ws.run_forever)
    ws_thread.start()

    # Run all the jobs to begin, and then continue with schedule.
    scheduler.run_all(1)
    while True:
        scheduler.run_pending()
        time.sleep(1)
    ws_thread.join()
