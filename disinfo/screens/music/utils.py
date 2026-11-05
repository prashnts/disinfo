import io

from PIL import Image

from discore.elements import Frame
from disinfo.utils import imops

_art = {}       # (url, size) -> the frame


def get_album_art(url: str, size: int = 16) -> Frame | None:
    '''None till the data service has it (utils/imops).'''
    if (f := _art.get((url, size))) is not None:
        return f
    if not (raw := imops.data(url)):
        return None
    try:
        # Dithering helps
        img = Image.open(io.BytesIO(raw)).resize((80, 80)).quantize().resize((size, size)).convert('RGBA')
    except OSError:
        return None
    if len(_art) > 16:
        _art.clear()
    f = _art[url, size] = Frame(img, hash=('album_art', url, size)).pictured()
    return f
