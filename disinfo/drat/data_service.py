import requests
import time
import datetime

from traceback import format_exc
from schedule import Scheduler

from .. import config
from ..redis import rkeys, set_dict, set_json, db
from . import idfm


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
    forecast_url = f'https://api.pirateweather.net/forecast/{config.pw_api_key}/{config.pw_latitude},{config.pw_longitude}?units={config.pw_unit}'
    try:
        print('[i] [fetch] weather')
        r = requests.get(forecast_url)
        r.raise_for_status()
        data = r.json()
        # write out the forecast.
        set_dict(rkeys['weather_data'], data)
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
        set_json(rkeys['metro_timing'], data.json())
        db.publish('di.pubsub.metro', 'update')
    except Exception as e:
        print('[e] metro_info', e)


scheduler = SafeScheduler()

scheduler.every(15).minutes.do(get_weather)
scheduler.every(2).to(3).minutes.do(get_random_text)
scheduler.every(1).minutes.do(get_metro_info)

if __name__ == '__main__':
    print('[Data Service] Scheduler Started')

    # Run all the jobs to begin, and then continue with schedule.
    scheduler.run_all(1)
    while True:
        scheduler.run_pending()
        time.sleep(1)
