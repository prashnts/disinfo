import time
import datetime

from traceback import format_exc
from schedule import Scheduler

from ..redis import publish
from .app_states import PubSubManager, PubSubMessage
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


def get_metro_info(force: bool = False):
    '''Fetch metro info in morning.'''
    if not force and not idfm.is_active():
        print('[i] [fetch] not fetching metro timing')
        return
    try:
        print('[i] [fetch] metro timing')
        data = idfm.fetch_state()
        publish('di.pubsub.metro', action='update')
    except Exception as e:
        print('[e] metro_info', e)


def on_pubsub(channel_name: str, message: PubSubMessage):
    if message.action == 'fetch_metro':
        get_metro_info(force=True)


scheduler = SafeScheduler(reschedule_on_failure=True)

scheduler.every(1).minutes.do(get_metro_info)


def main():
    print('[Data Service] Scheduler Started')

    pubsub = PubSubManager()
    pubsub.attach('data_service', ('di.pubsub.dataservice',), on_pubsub)

    # Run all the jobs to begin, and then continue with schedule.
    scheduler.run_all(1)
    while True:
        scheduler.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()