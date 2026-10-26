import time
import datetime

from traceback import format_exc
from schedule import Scheduler

from ..redis import db
from .app_states import PubSubManager, PubSubMessage
from . import idfm
from ..screens.aviator.tasks import adsbx_task
from ..screens.weather import vigilance, stations, forecast
from ..screens.aviator.weather import radar_task, wind_task, sat_task
from ..screens.aviator import daylight, skystate


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


def on_pubsub(channel_name: str, message: PubSubMessage):
    # The metro button, here only: one press, one toggle, whatever the screens.
    if message.action in ('show_metro', 'btn_metro'):
        idfm.press()


starting = True        # until the first run of all the jobs is done

def cached(name: str, every: float, fn):
    '''A fetch that records when it last succeeded (fn returns True), in redis: at a restart it is not asked again
    until its interval has passed since then (the data it wrote is still there, with its own expiry).'''
    key = f'di.dataservice.ran.{name}'
    def run():
        if starting:
            try:
                if time.time() - float(db.get(key) or 0) < every:
                    print(f'[Data Service] {name}: fetched {round(time.time() - float(db.get(key)))} s ago, not again yet')
                    return
            except (TypeError, ValueError):
                pass
        if fn():
            db.set(key, time.time())
    return run

scheduler = SafeScheduler(reschedule_on_failure=True)

scheduler.every(15).seconds.do(idfm.task)     # fetches only what's due, while the card is wanted
scheduler.every(1).seconds.do(adsbx_task)
scheduler.every(5).minutes.do(cached('radar', 300, radar_task))
scheduler.every(30).minutes.do(cached('wind', 1800, wind_task))
scheduler.every(10).minutes.do(cached('sat', 600, sat_task))
scheduler.every(15).minutes.do(cached('vigil', 900, vigilance.task))
scheduler.every(30).minutes.do(cached('forecast', 1800, vigilance.forecast_task))
scheduler.every(15).minutes.do(cached('sky', 900, daylight.sky_task))
scheduler.every(6).minutes.do(cached('obs', 360, stations.task))
scheduler.every(30).minutes.do(cached('blend', 1800, forecast.task))     # after the stations: it checks the runs on them
scheduler.every(1).minutes.do(daylight.task)
scheduler.every(1).minutes.do(skystate.task)        # after the others: they're its sources


def main():
    print('[Data Service] Scheduler Started')

    pubsub = PubSubManager()
    pubsub.attach('data_service', ('di.pubsub.dataservice', 'di.pubsub.remote'), on_pubsub)
    pubsub.attach('daylight', ('di.pubsub.telemetry',), daylight.on_telemetry)

    # Run all the jobs to begin, and then continue with schedule.
    scheduler.run_all(1)
    global starting
    starting = False
    while True:
        scheduler.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()