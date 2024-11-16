import requests
import io

from PIL import Image
from functools import cache

from disinfo import config
from disinfo.components.elements import Frame, StillImage



@cache
def get_album_art(url: str, size: int = 16):
    if not url:
        return None
    try:
        r = requests.get(url)
        r.raise_for_status()
        fp = io.BytesIO(r.content)
        img = Image.open(fp)
        # Dithering helps
        img = img.resize((80, 80)).quantize().resize((size, size)).convert('RGBA')
        return Frame(img)
    except requests.RequestException:
        return None
