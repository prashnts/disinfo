import requests
import io

from PIL import Image
from functools import cache

from disinfo import config
from disinfo.components.elements import Frame, StillImage



@cache
def get_album_art(fragment: str, media_album: str, is_spotify: bool=False):
    if not fragment:
        return None
    if media_album and 'franceinfo' in media_album:
        # Hard code some album arts.
        return StillImage('assets/raster/france-info.png')
    try:
        r = requests.get(f'http://{config.ha_base_url}{fragment}')
        r.raise_for_status()
        fp = io.BytesIO(r.content)
        img = Image.open(fp)
        # Dithering helps
        img = img.resize((80, 80)).quantize().resize((25, 25)).convert('RGBA')
        if is_spotify:
            return composite_at(spotify_icon, img, 'bl')
        return Frame(img)
    except requests.RequestException:
        return None
