'''When something was active (music playing, a machine running...), kept in redis.

A session starts when activity resumes after `gap` seconds of inactivity, so e.g. automatic
song changes don't count. `di.sessions.<name>.starts` holds session start timestamps, newest first.
`di.sessions.<name>.last` holds the last time activity was seen.

    music = sessions(f'music.{entity_id}')
    if playing:
        music.active()
    if music.is_relevant():
        ...
'''
import time
import pendulum

from dataclasses import dataclass, field
from functools import cache
from redis import RedisError

from disinfo.redis import db

REFRESH = 60


@dataclass
class Sessions:
    name: str
    gap: float = 20 * 60
    recent: float = 2 * 3600     # still relevant this long after the last activity
    habit_days: int = 21
    habit_window: int = 40       # minutes around a past start's time of day
    habit_hits: int = 2          # distinct days needed to call it a habit
    keep: int = 60

    _last: float | None = field(default=None, repr=False)
    _saved: float = field(default=0, repr=False)
    _starts: tuple[float, list[float]] = field(default=(0, []), repr=False)

    @property
    def _starts_key(self) -> str:
        return f'di.sessions.{self.name}.starts'

    @property
    def _last_key(self) -> str:
        return f'di.sessions.{self.name}.last'

    def last(self) -> float:
        if self._last is None:
            try:
                self._last = float(db.get(self._last_key) or 0)
            except RedisError:
                self._last = 0
            self._saved = self._last
        return self._last

    def active(self, now: float | None = None):
        '''Call while the thing is active. Cheap to call every frame.'''
        now = now or time.time()
        try:
            if now - self.last() > self.gap:
                with db.pipeline() as p:
                    p.lpush(self._starts_key, now)
                    p.ltrim(self._starts_key, 0, self.keep - 1)
                    p.execute()
                self._starts = (0, [])
            self._last = now
            if now - self._saved > REFRESH:
                db.set(self._last_key, now)
                self._saved = now
        except RedisError as e:
            print(f'[sessions] {self.name} write failed', e)

    def starts(self) -> list[float]:
        at, ts = self._starts
        if time.monotonic() - at > REFRESH:
            try:
                ts = [float(t) for t in db.lrange(self._starts_key, 0, self.keep - 1)]
            except RedisError:
                pass
            self._starts = (time.monotonic(), ts)
        return ts

    def is_recent(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.last() < self.recent

    def is_habit_time(self, now: pendulum.DateTime | None = None) -> bool:
        '''True if a session started around this time of day on a few recent days.'''
        now = now or pendulum.now()
        minute = now.hour * 60 + now.minute
        days = set()
        for t in self.starts():
            dt = pendulum.from_timestamp(t, tz=now.timezone)
            if (now - dt).in_days() >= self.habit_days:
                continue
            delta = abs(dt.hour * 60 + dt.minute - minute)
            if min(delta, 1440 - delta) <= self.habit_window:
                days.add(dt.date())
        return len(days) >= self.habit_hits

    def is_relevant(self) -> bool:
        return self.is_recent() or self.is_habit_time()


@cache
def sessions(name: str, **kwargs) -> Sessions:
    '''One tracker per name (and settings), shared by all screens.'''
    return Sessions(name, **kwargs)
