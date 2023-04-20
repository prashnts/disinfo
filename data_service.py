import os
import requests
import redis
import time
import json
import logging
import datetime

from traceback import format_exc
from schedule import Scheduler


logger = logging.getLogger('schedule')

latitude = 48.842
longitude = 2.391

pw_api_key = os.environ.get('PIRATE_WEATHER_TOKEN')
pw_unit = 'ca'  # SI units with kmph for wind.


if not pw_api_key:
    print('WARNING: No API Key for Pirate Weather')

forecast_url = f'https://api.pirateweather.net/forecast/{pw_api_key}/{latitude},{longitude}?units={pw_unit}'


db = redis.Redis(host='localhost', port=6379, db=0)

keys = {
    'weather_data': 'weather.forecast_data',
    'random_msg': 'misc.random_msg',
}


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
            logger.error(format_exc())
            job.last_run = datetime.datetime.now()
            job._schedule_next_run()

def get_weather():
    '''Fetch Weather from PirateWeather API.'''
    try:
        print('[fetch] weather')
        r = requests.get(forecast_url)
        data = r.json()
        # write out the forecast.
        db.set(keys['weather_data'], json.dumps(data))
    except requests.exceptions.RequestException as e:
        print('error', e)

def get_random_text():
    '''Fetch trivia from Numbers API.'''
    try:
        print('[fetch] random text')
        r = requests.get('http://numbersapi.com/random/trivia?json')
        data = r.json()
        db.set(keys['random_msg'], json.dumps(data))
    except requests.exceptions.RequestException as e:
        print('error', e)


scheduler = SafeScheduler()

scheduler.every(15).minutes.do(get_weather)
scheduler.every(2).to(3).minutes.do(get_random_text)

if __name__ == '__main__':
    print('[Data Service] Scheduler Started')
    while True:
        scheduler.run_pending()
        time.sleep(1)
