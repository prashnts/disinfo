import requests
import io
import pendulum

from PIL import Image
from functools import cache
from datetime import timedelta

from ..utils.drawer import draw_loop
from ..config import app_config
from ..components import fonts
from ..components.elements import Frame, StillImage
from ..components.text import Text, TextStyle, text
from ..components.layouts import hstack, vstack, composite_at
from ..components.layers import div, DivStyle
from ..components.transitions import SlideIn, Resize
from ..components.widget import Widget
from ..components.scroller import HScroller
from ..utils.func import throttle
from ..utils import ease
from ..data_structures import FrameState

from disinfo.utils.hass import get_entity
from disinfo.utils.imops import image_from_url

play_icon = StillImage('assets/raster/play-5x5.png')
pause_icon = StillImage('assets/raster/pause-5x5.png')
spotify_icon = StillImage('assets/raster/spotify-5x5.png')


@throttle(1033)
def get_state():
    state = {}
    state['is_visible'] = False

    s = get_entity(app_config.speaker_entity)

    if not s:
        return state
    
    s = s.model_dump()

    state['entity_id'] = s['entity_id']
    state['playing'] = s['state'] == 'playing'
    state['paused'] = s['state'] == 'paused'

    last_updated = s['last_updated']
    now = pendulum.now('utc')

    state['media_title'] = s['attributes'].get('media_title', '')
    state['media_album'] = s['attributes'].get('media_album_name', '')
    state['media_artist'] = s['attributes'].get('media_artist', '')
    state['is_spotify'] = 'Spotify' in s['attributes'].get('source', '')
    state['album_art'] = s['attributes'].get('entity_picture')

    timeout_delay = 40 if state['playing'] else 2

    state['is_visible'] = all([
        state['playing'] or state['paused'],
        state['media_title'] != 'TV',
        (last_updated + timedelta(minutes=timeout_delay)) > now,
    ])

    return state


def composer(fs: FrameState):
    s = get_state()

    if not s['is_visible']:
        return

    uname = lambda x: f'{x}_{s["entity_id"]}'

    act_icon = play_icon if s['playing'] else pause_icon
    spot_icon = spotify_icon if s['is_spotify'] else None

    details = div(
        vstack([
            hstack([act_icon, spot_icon]),
            (HScroller(size=40, pause_at_loop=True, name=uname('media_title'))
                .set_frame(text(s['media_title'], font=fonts.greybeard))
                .draw(fs.tick)),
            (HScroller(size=33, pause_at_loop=True, name=uname('media_artist'))
                .set_frame(hstack([text(s['media_album']), text(s['media_artist'])]))
                .draw(fs.tick)),
        ], gap=2),
        style=DivStyle(
            padding=2,
            radius=3,
            background="#2c2c2c76",
        )
    )

    art = s['album_art']
    if art:
        background = (Resize(uname('np.albumart'), 2.3)
            .mut(image_from_url(f'{app_config.ha_base_url}{art}', resize=(64, 64)))
            .draw(fs)
        )
    else:
        background = None

    return div(
        details,
        style=DivStyle(
            padding=0,
            radius=2,
            background_frame=background,
            background_blur=1,
            width=48,
            height=40,
            anchor='bl'
        ),
    ).tag('music')

def widget(fs: FrameState):
    return Widget('music', composer(fs))

draw = draw_loop(composer)
