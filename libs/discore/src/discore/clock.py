'''Aware datetimes from the stdlib: the bits of pendulum disinfo used. Plain datetime objects in and out.'''
import os

from datetime import datetime, timezone, tzinfo
from functools import cache
from zoneinfo import ZoneInfo

UTC = timezone.utc


@cache
def local() -> tzinfo:
    # $TZ, else the system's zone with its DST rules (datetime.astimezone() would give a fixed offset).
    if key := os.environ.get('TZ', '').lstrip(':'):
        return ZoneInfo(key)
    try:
        with open('/etc/localtime', 'rb') as f:
            return ZoneInfo.from_file(f, key='localtime')
    except OSError:
        return UTC


def zone(tz: str | tzinfo | None = None) -> tzinfo:
    '''None or 'local' -> the local zone, 'UTC' or an IANA name -> its zone.'''
    if tz is None or tz == 'local':
        return local()
    if isinstance(tz, tzinfo):
        return tz
    return UTC if tz.upper() == 'UTC' else ZoneInfo(tz)


def now(tz: str | tzinfo | None = None) -> datetime:
    return datetime.now(zone(tz))


def aware(dt: datetime, tz: str | tzinfo | None = UTC) -> datetime:
    '''dt as is when it has a zone, else read in tz (UTC, like pendulum).'''
    return dt if dt.tzinfo else dt.replace(tzinfo=zone(tz))


def parse(s: str, tz: str | tzinfo | None = UTC) -> datetime:
    '''An ISO 8601 string ('Z' too); a naive one is read in tz.'''
    return aware(datetime.fromisoformat(s), tz)


def from_ts(ts: float, tz: str | tzinfo | None = None) -> datetime:
    return datetime.fromtimestamp(ts, zone(tz))


def local_hm(s: str | None) -> str | None:
    '''An ISO string as the local 'HH:MM', None stays None.'''
    return parse(s).astimezone(local()).strftime('%H:%M') if s else None
