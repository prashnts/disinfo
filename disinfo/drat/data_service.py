import requests
import time
import datetime

from traceback import format_exc
from schedule import Scheduler

from ..config import app_config
from ..redis import rkeys, set_dict, set_json, db, publish
from .app_states import PubSubManager, PubSubMessage
from . import idfm, washing_machine
from .klipper import KlipperClient
from ..screens.aviator.tasks import adsbx_task


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


scheduler = SafeScheduler(reschedule_on_failure=True)

scheduler.every(15).minutes.do(get_weather)
scheduler.every(2).to(3).minutes.do(get_random_text)
scheduler.every(1).minutes.do(get_metro_info)
# scheduler.every(1).minutes.do(get_washing_machine_info)

def main():
    print('[Data Service] Scheduler Started')

    pubsub = PubSubManager()
    pubsub.attach('data_service', ('di.pubsub.dataservice',), on_pubsub)

    KlipperClient(app_config.klipper_host).connect()

    # Run all the jobs to begin, and then continue with schedule.
    scheduler.run_all(1)
    while True:
        scheduler.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()