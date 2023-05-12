import requests
import io

from PIL import Image
from functools import cache

from disp_info import config
from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.sprite_icons import SpriteImage
from disp_info.redis import rkeys, get_dict
from disp_info.components.scroller import HScroller
from disp_info.utils import throttle

hscroller = HScroller(size=30, delta=1, speed=0.01)
play_icon = SpriteImage('assets/raster/play.9x9.png')[0]

text_music_info = Text(font=fonts.bitocra, fill='#a1a9b0')


@throttle(1033)
def get_state():
    return get_dict(rkeys['ha_sonos_beam'])

@cache
def get_album_art(fragment: str, media_title: str):
    if 'franceinfo' in media_title:
        # Hard code some album arts.
        return SpriteImage('assets/raster/france-info.png')[0]
    try:
        r = requests.get(f'http://{config.ha_base_url}{fragment}')
        r.raise_for_status()
        fp = io.BytesIO(r.content)
        img = Image.open(fp)
        # Dithering helps
        img = img.resize((80, 80)).quantize()
        return Frame(img.resize((25, 25)).convert('RGBA'))
    except requests.RequestException:
        return None

def draw():
    state = get_state()

    if not state.get('new_state'):
        return

    state = state['new_state']
    media_info = ''

    if state['state'] == 'playing':
        media_title = state['attributes'].get('media_title')
        media_album = state['attributes'].get('media_album_name')
        media_artist = state['attributes'].get('media_artist')

        elements = [media_title, media_album, media_artist]
        media_info = ' >> '.join([e for e in elements if e])
    else:
        return

    if not media_info or media_title == 'TV':
        return


    art = get_album_art(state['attributes'].get('entity_picture'), media_title)

    changed = text_music_info.update(value=media_info)
    # "Refresh" the scroller with the change status of the frame.
    hscroller.set_frame(text_music_info, changed)

    music_elements = [
        stack_horizontal([
            play_icon,
            hscroller.draw(),
        ], gap=0)
    ]

    if art:
        music_elements.append(art)

    return stack_vertical(music_elements, gap=1, align='right')
