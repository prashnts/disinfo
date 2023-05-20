import arrow
import requests
import time
import logging
import datetime
import sys

from traceback import format_exc
from schedule import Scheduler

from . import config
from .redis import rkeys, set_dict
from .drat import metro_paris

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger('data_service')
logger.setLevel(logging.DEBUG)


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
    forecast_url = f'https://api.pirateweather.net/forecast/{config.pw_api_key}/{config.pw_latitude},{config.pw_longitude}?units={config.pw_unit}'
    try:
        logger.info('[fetch] weather')
        r = requests.get(forecast_url)
        r.raise_for_status()
        data = r.json()
        # write out the forecast.
        set_dict(rkeys['weather_data'], data)
    except requests.exceptions.RequestException as e:
        logger.error('error', e)

def get_random_text():
    '''Fetch trivia from Numbers API.'''
    try:
        logger.info('[fetch] random text')
        r = requests.get('http://numbersapi.com/random/trivia?json')
        r.raise_for_status()
        data = r.json()
        set_dict(rkeys['random_msg'], data)
    except requests.exceptions.RequestException as e:
        logger.error('error', e)

def get_metro_info():
    '''Fetch metro info in morning.'''
    now = arrow.now()
    do_fetch = any([
        7 <= now.hour <= 9,
        16 <= now.hour <= 18,
    ])
    if not do_fetch:
        logger.info('[fetch] not fetching metro timing')
        return
    try:
        logger.info('[fetch] metro timing')
        data = metro_paris.fetch_state()
        set_dict(rkeys['metro_timing'], data)
    except Exception as e:
        logger.error('error', e)


scheduler = SafeScheduler()

scheduler.every(15).minutes.do(get_weather)
scheduler.every(2).to(3).minutes.do(get_random_text)
scheduler.every(1).minutes.do(get_metro_info)

if __name__ == '__main__':
    logger.info('[Data Service] Scheduler Started')
    while True:
        scheduler.run_pending()
        time.sleep(1)
