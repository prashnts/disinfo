import io
import time
import requests

from functools import lru_cache
from PIL import Image

from discore.elements import Frame


@lru_cache(maxsize=256)
def _fetch_image(url: str) -> bytes:
    r = requests.get(url, timeout=4)
    r.raise_for_status()
    return r.content

@lru_cache(maxsize=256)
def _image_from_url(url: str, resize: tuple[int, int], ratio_fn):
    with io.BytesIO(_fetch_image(url)) as fp:
        img = Image.open(fp)
        return Frame(img, ('img_from_url', url, resize)).resize(resize, ratio_fn=ratio_fn)

_failed_at = {}

def image_from_url(url: str, resize: tuple[int, int] = (42, 42), ratio_fn=max):
    # Failures are not cached, but retried at most every 30s so a dead host doesn't stall drawing.
    fallback = Frame(Image.new('RGBA', resize, (0, 0, 0, 0)), ('img_from_url', url, resize))
    if not url or time.monotonic() - _failed_at.get(url, -30) < 30:
        return fallback
    try:
        return _image_from_url(url, resize, ratio_fn)
    except (requests.RequestException, OSError):
        _failed_at[url] = time.monotonic()
        return fallback
