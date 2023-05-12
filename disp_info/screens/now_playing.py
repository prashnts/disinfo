import requests
import io
import arrow

from PIL import Image
from functools import cache
from datetime import timedelta

from disp_info import config
from disp_info.components import fonts
from disp_info.components.elements import Frame
from disp_info.components.text import Text
from disp_info.components.layouts import stack_horizontal, stack_vertical, composite_at
from disp_info.sprite_icons import SpriteImage
from disp_info.redis import rkeys, get_dict
from disp_info.components.scroller import HScroller
from disp_info.utils import throttle

hscroller = HScroller(size=20, delta=1, speed=0.01, pause_at_loop=True, pause_duration=1)

play_icon = SpriteImage('assets/raster/play-5x5.png')[0]
pause_icon = SpriteImage('assets/raster/pause-5x5.png')[0]
spotify_icon = SpriteImage('assets/raster/spotify-5x5.png')[0]

text_music_info = Text(font=fonts.bitocra, fill='#a1a9b0')


@throttle(1033)
def get_state():
    state = dict(is_visible=False)

    s = get_dict(rkeys['ha_sonos_beam']).get('new_state')

    if not s:
        return state

    state['playing'] = s['state'] == 'playing'
    state['paused'] = s['state'] == 'paused'

    last_updated = arrow.get(s['last_updated']).to('local')
    now = arrow.now()

    state['media_title'] = s['attributes'].get('media_title')
    state['media_album'] = s['attributes'].get('media_album_name')
    state['media_artist'] = s['attributes'].get('media_artist')
    state['is_spotify'] = 'Spotify' in s['attributes'].get('source', '')
    state['album_art'] = get_album_art(
        s['attributes'].get('entity_picture'),
        media_album=state['media_album'],
        is_spotify=state['is_spotify'])

    timeout_delay = 40 if state['playing'] else 2

    state['is_visible'] = all([
        state['playing'] or state['paused'],
        state['media_title'] != 'TV',
        (last_updated + timedelta(minutes=timeout_delay)) > now,
    ])

    return state

@cache
def get_album_art(fragment: str, media_album: str, is_spotify: bool=False):
    if not fragment:
        return None
    if media_album and 'franceinfo' in media_album:
        # Hard code some album arts.
        return SpriteImage('assets/raster/france-info.png')[0]
    try:
        r = requests.get(f'http://{config.ha_base_url}{fragment}')
        r.raise_for_status()
        fp = io.BytesIO(r.content)
        img = Image.open(fp)
        # Dithering helps
        img = img.resize((80, 80)).quantize().resize((25, 25)).convert('RGBA')
        if is_spotify:
            img = composite_at(spotify_icon, img, 'bl')
        return Frame(img)
    except requests.RequestException:
        return None

def draw():
    s = get_state()

    if not s['is_visible']:
        return

    elements = [s['media_title'], s['media_album'], s['media_artist']]
    media_info = ' >> '.join([e for e in elements if e])


    art = s['album_art']

    act_icon = play_icon if s['playing'] else pause_icon

    changed = text_music_info.update(value=media_info)
    # "Refresh" the scroller with the change status of the frame.
    hscroller.set_frame(text_music_info, changed)

    music_elements = [
        stack_horizontal([
            act_icon,
            hscroller.draw(),
        ], gap=0)
    ]

    if art:
        music_elements.append(art)

    return stack_vertical(music_elements, gap=1, align='right')
