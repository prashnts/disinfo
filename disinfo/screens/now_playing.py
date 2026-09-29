import requests
import io
import pendulum

from PIL import Image
from functools import cache, lru_cache
from datetime import timedelta

from ..utils.drawer import draw_loop
from ..config import app_config
from disinfo import fonts
from discore.elements import Frame, StillImage
from discore.text import Text, TextStyle, text
from discore.layouts import hstack, vstack, composite_at
from discore.layers import div, DivStyle
from discore.transitions import SlideIn, Resize, FadeIn
from discore.widget import Widget
from discore.scroller import HScroller
from ..utils.func import throttle
from discore import ease
from discore.data_structures import FrameState
from discore.cairo import load_svg

from disinfo.utils.hass import get_entity
from disinfo.utils.imops import image_from_url
from disinfo.utils.sessions import sessions
from .music import art_cache

play_icon = StillImage('assets/raster/play-5x5.png')
pause_icon = StillImage('assets/raster/pause-5x5.png')
spotify_icon = load_svg('assets/spotify.svg', scale=0.375)


def _tint(frame: Frame, color: str) -> Frame:
    img = Image.new('RGBA', frame.size, color)
    img.putalpha(frame.image.getchannel('A'))
    return Frame(img, ('tint', color, frame.hash))

def _chip(icon: Frame) -> Frame:
    return div(icon, style=DivStyle(padding=2, radius=2, background="#000000A8"))

play_chip = _chip(_tint(play_icon, '#3DFF8B'))
pause_chip = _chip(_tint(pause_icon, '#FFC23D'))


@throttle(1033)
def get_state(fs: FrameState):
    state = {}
    state['is_visible'] = False

    s = get_entity(fs.config.speaker_entity)

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
    if state['playing'] and state['media_title'] != 'TV':
        sessions(f"music.{state['entity_id']}").active()

    return state


SLIDE_SIZE = (29, 24)  # 60% of the playing card
SLIDE_EVERY = 6


@lru_cache(maxsize=16)
def _slide(art: Frame) -> Frame:
    w, h = SLIDE_SIZE
    img = art.resize(SLIDE_SIZE, ratio_fn=max).image
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return Frame(img.crop((left, top, left + w, top + h)), ('np.recent', art.hash))


@throttle(30_000)
def _slideshow_relevant(entity_id: str) -> bool:
    return sessions(f'music.{entity_id}').is_relevant()


def recent_arts(fs: FrameState) -> Frame | None:
    '''Slideshow of the last few cover arts, while music is recent or habitual.'''
    entity_id = fs.config.speaker_entity
    if not _slideshow_relevant(entity_id):
        return
    arts = art_cache.recent(entity_id)
    if not arts:
        return
    art = arts[int(fs.tick / SLIDE_EVERY) % len(arts)]
    slide = FadeIn(f'np.recent.{entity_id}', 1).mut(_slide(art)).draw(fs)
    return div(slide, style=DivStyle(padding=0, radius=2)).tag(('music.recent', entity_id))


def composer(fs: FrameState):
    s = get_state(fs)

    if not s['is_visible']:
        return

    uname = lambda x: f'{x}_{s["entity_id"]}'

    details = div(
        vstack([
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
            background="#2c2c2c50",
        )
    )

    art = s['album_art']
    if art:
        art_frame = image_from_url(f'{app_config.ha_base_url}{art}', resize=(64, 64))
        art_cache.remember(s['entity_id'], art, art_frame)
        background = (Resize(uname('np.albumart'), 2.3)
            .mut(art_frame)
            .draw(fs)
        )
    else:
        background = None

    card = div(
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
    )
    # Icons sit on the unblurred artwork.
    card = composite_at(play_chip if s['playing'] else pause_chip, card, 'tl', dx=1, dy=1)
    if s['is_spotify']:
        card = composite_at(spotify_icon, card, 'tr', dx=-1, dy=1)
    return card.tag('music')

def widget(fs: FrameState):
    return Widget('music', composer(fs))

def slideshow_widget(fs: FrameState):
    s = get_state(fs)
    return Widget('music.recent', None if s['is_visible'] else recent_arts(fs))

draw = draw_loop(composer)
