import requests
import io
import arrow

from PIL import Image
from functools import cache
from datetime import timedelta

from .drawer import draw_loop
from ..config import app_config
from ..components import fonts
from ..components.elements import Frame, StillImage
from ..components.text import Text, TextStyle
from ..components.layouts import hstack, vstack, composite_at
from ..components.layers import div, DivStyle
from ..components.transitions import SlideIn
from ..redis import rkeys, get_dict
from ..components.scroller import HScroller
from ..utils.func import throttle
from ..utils import ease
from ..data_structures import FrameState

scroll_media_title = HScroller(size=20, delta=1, speed=0.03, pause_at_loop=True, pause_duration=1)
scroll_artist_name = HScroller(size=20, delta=1, speed=0.05, pause_at_loop=True, pause_duration=1)
scroll_album_title = HScroller(size=20, delta=1, speed=0.05, pause_at_loop=True, pause_duration=1)

play_icon = StillImage('assets/raster/play-5x5.png')
pause_icon = StillImage('assets/raster/pause-5x5.png')
spotify_icon = StillImage('assets/raster/spotify-5x5.png')

text_media_title = Text(style=TextStyle(font=fonts.bitocra7, color='#a1a9b0'))
text_artist_name = Text(style=TextStyle(font=fonts.bitocra7, color='#a1a9b0'))
text_album_title = Text(style=TextStyle(font=fonts.bitocra7, color='#a1a9b0'))


@throttle(1033)
def get_state():
    state = {}
    state['is_visible'] = False

    s = get_dict(rkeys['ha_sonos_beam']).get('new_state')

    if not s:
        return state

    state['playing'] = s['state'] == 'playing'
    state['paused'] = s['state'] == 'paused'

    last_updated = arrow.get(s['last_updated']).to('local')
    now = arrow.now()

    state['media_title'] = s['attributes'].get('media_title', '')
    state['media_album'] = s['attributes'].get('media_album_name', '')
    state['media_artist'] = s['attributes'].get('media_artist', '')
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
        return StillImage('assets/raster/france-info.png')
    try:
        r = requests.get(f'http://{app_config.ha_base_url}{fragment}')
        r.raise_for_status()
        fp = io.BytesIO(r.content)
        img = Image.open(fp)
        # Dithering helps
        img = img.resize((80, 80)).quantize().resize((20, 20)).convert('RGBA')
        if is_spotify:
            return composite_at(spotify_icon, img, 'bl')
        return Frame(img)
    except requests.RequestException:
        return None

def composer(fs: FrameState):
    s = get_state()

    if not s['is_visible']:
        return

    elements = [s['media_title'], s['media_album'], s['media_artist']]
    media_info = ' >> '.join([e if e else '--' for e in elements])

    c = text_media_title.update(value=s['media_title'])
    scroll_media_title.set_frame(text_media_title, c)
    c = text_album_title.update(value=s['media_album'][:5])
    scroll_album_title.set_frame(text_album_title, c)
    c = text_artist_name.update(value=s['media_artist'])
    scroll_artist_name.set_frame(text_artist_name, c)

    art = s['album_art']

    act_icon = play_icon if s['playing'] else pause_icon

    media_info = vstack([
        scroll_media_title.draw(fs.tick),
        text_album_title,
    ])

    music_elements = [
        hstack([
            act_icon,
            media_info,
        ], align='center'),
    ]

    if art:
        music_elements.insert(0, SlideIn('np.albumart', 1, edge='right', easing=ease.ease_bounce_out).mut(art).draw(fs))

    return div(
        hstack(music_elements, gap=1, align='top'),
        style=DivStyle(
            background='#0000008f',
            padding=2,
            radius=2,
        ),
    )

draw = draw_loop(composer, sleepms=10)
