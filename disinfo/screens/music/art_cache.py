'''Recent cover arts per speaker, kept in redis (spares the sd card).

List `di.music.arts.<entity>` holds digests, newest first.
Blobs live in `di.music.art.<digest>` as png and expire on their own once trimmed out.
'''
import io
import time
import hashlib

from functools import lru_cache
from PIL import Image
from redis import RedisError

from discore.elements import Frame
from disinfo.redis import db

KEEP = 8
TTL = 14 * 24 * 3600
REFRESH = 10

_seen: dict[str, str] = {}      # entity -> last remembered url
_recent: dict[str, tuple[float, list[str]]] = {}


def _list_key(entity_id: str) -> str:
    return f'di.music.arts.{entity_id}'

def _art_key(digest: str) -> str:
    return f'di.music.art.{digest}'


def remember(entity_id: str, url: str, frame: Frame):
    '''Stores `frame` as the latest art of `entity_id`. Cheap to call every frame.'''
    if not url or _seen.get(entity_id) == url:
        return
    if not frame.image.getbbox():
        # Fallback (fetch failed), try again next time.
        return
    buf = io.BytesIO()
    frame.image.save(buf, 'PNG')
    data = buf.getvalue()
    digest = hashlib.sha1(data).hexdigest()[:16]
    key = _list_key(entity_id)
    try:
        with db.pipeline() as p:
            p.set(_art_key(digest), data, ex=TTL)
            p.lrem(key, 0, digest)
            p.lpush(key, digest)
            p.ltrim(key, 0, KEEP - 1)
            p.expire(key, TTL)
            p.execute()
    except RedisError as e:
        print('[music] art cache write failed', e)
        return
    _seen[entity_id] = url
    _recent.pop(entity_id, None)


@lru_cache(maxsize=KEEP * 2)
def _load(digest: str) -> Frame | None:
    data = db.get(_art_key(digest))
    if not data:
        return None
    with io.BytesIO(data) as fp:
        return Frame(Image.open(fp).convert('RGBA'), ('music.art', digest))


def recent(entity_id: str) -> list[Frame]:
    '''Newest first. Redis is polled at most every REFRESH seconds.'''
    at, digests = _recent.get(entity_id, (0, []))
    if time.monotonic() - at > REFRESH:
        try:
            digests = [d.decode() for d in db.lrange(_list_key(entity_id), 0, KEEP - 1)]
        except RedisError:
            pass
        _recent[entity_id] = (time.monotonic(), digests)
    try:
        return [f for f in map(_load, digests) if f]
    except RedisError:
        return []
