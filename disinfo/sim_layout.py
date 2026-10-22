'''A screen's layout over simulated days: where its items spent their time, how often they moved.

    DI_CONFIG_PATH=.config.json python -m disinfo.sim_layout 72 8 2>&1 >/dev/null

Composes the screen a few times (forced awake) for its real items and focus, then runs its Screen on a fake
clock in 10 s steps: awake, then `night` hours a day asleep (only the time and date; calm). Heat isn't loaded
or saved. The report is on stderr.
'''
import sys
import time
import collections

from discore import screen as layout
from discore.data_structures import FrameState
from disinfo import compositor
from disinfo.config import app_config
from disinfo.drat.app_states import RuntimeStateManager


def report(line: str):
    print(line, file=sys.stderr, flush=True)

def main(hours: float = 72, night: float = 8):
    RuntimeStateManager().get_state().motion_override = True
    s = compositor.screen_for(app_config.name)
    for _ in range(10):
        compositor.compose(FrameState.create(config=app_config))
        time.sleep(0.05)
    seen, arrange = {}, s.arrange
    s.arrange = lambda fs, items, focus=None, *a, **k: seen.update(fs=fs, items=items, focus=focus) or arrange(fs, items, focus, *a, **k)
    compositor.compose(FrameState.create(config=app_config))
    s.arrange = arrange

    s.load_heat = s.save_heat = None
    s.heat, s.current, s.moves = None, tuple(0 for _ in s.choices), {}
    clock = [time.monotonic() + 1]
    layout.time.monotonic = lambda: clock[0]
    # The entry's dark while nobody's there: only its awake hours count.
    sleeps = app_config.name != 'dientry'
    spent, moves, before = collections.Counter(), 0, None
    for step in range(int(hours * 360)):
        clock[0] += 10
        asleep = step / 360 % 24 < night
        if asleep and not sleeps:
            continue
        items = {k: v for k, v in seen['items'].items() if not asleep or k in ('time', 'date')}
        s.arrange(seen['fs'], items, None if asleep else seen['focus'], when={'calm'} if asleep else ())
        now = (s.spot('side').anchor, s.spot('time').anchor)
        spent[('asleep' if asleep else 'awake', *now)] += 10
        moves += before is not None and now != before
        before = now
    report(f'{app_config.name}: {hours:.0f} h, {night:.0f} h asleep a day, {moves} moves')
    for (state, side, at), seconds in sorted(spent.items()):
        report(f'  {state:6}  side {side}  time {at}  {seconds / 3600:5.1f} h')


if __name__ == '__main__':
    main(*map(float, sys.argv[1:3]))
