import pendulum
import math
import requests
import random

from datetime import datetime
from functools import partial
from dataclasses import dataclass, field
from redis_om import HashModel, NotFoundError

from disinfo.data_structures import AppBaseModel, FrameState
from disinfo.components.widget import Widget
from disinfo.components.text import text, TextStyle
from disinfo.components.layouts import vstack, hstack, place_at, composite_at
from disinfo.components.layers import div, DivStyle, styled_div
from disinfo.components.stack import Stack, StackStyle
from disinfo.components.transitions import Resize
from disinfo.components import fonts
from disinfo.components.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act
from disinfo.screens.drawer import draw_loop
from disinfo.utils import ease
from disinfo.utils.imops import image_from_url
from disinfo.utils.cairo import load_svg_string, render_emoji


class NewsStory(HashModel):
    title: str
    short_summary: str
    uid: str
    emoji: str
    category: str
    created_at: datetime
    primary_image_url: str
    primary_image_caption: str

    @property
    def emoji_im(self) -> Frame:
        return render_emoji(self.emoji, size=20)

    @property
    def category_emoji(self) -> Frame:
        map = {
            'france': '🇫🇷',
            'tech': '👾',
            'india': '🇮🇳',
            'world': '🌍',
            'science': '🧬',
            'economy': '💶',
        }
        cat = hstack([render_emoji(map[self.category], size=10), text(self.category)], gap=1)
        return div(cat, padding=(1, 2, 1, 2), radius=3, background="#232A5464", border=1, border_color="#120f2cff")

    @classmethod
    def iter_items(cls, limit: int = 0):
        for i, pk in enumerate(cls.all_pks()):
            if limit and limit <= i:
                break
            try:
                yield cls.get(pk)
            except NotFoundError:
                continue
    
    @classmethod
    def random(cls):
        items = list(cls.iter_items())
        if items:
            return random.choice(items)


KAGI_ENDPOINT = 'https://news.kagi.com/api/batches/latest'
CATEGORIES = [
    'france',
    'tech',
    # 'india',
    'world',
    'science',
    'economy',
]
STALE_IN = 20 * 60

def kagi_get_category_ids(categories: list[str]) -> dict[str, str]:
    cats = requests.get(f'{KAGI_ENDPOINT}/categories').json()['categories']
    mapping = {}
    for cat in cats:
        if cat['categoryId'] in categories:
            mapping[cat['categoryId']] = cat['id']
    return mapping


def kagi_load_stories(fs: FrameState):
    existing_pk = [pk for pk in NewsStory.all_pks()]
    if existing_pk:
        return


    for cat, cid in kagi_get_category_ids(CATEGORIES).items():
        stories = requests.get(f'{KAGI_ENDPOINT}/categories/{cid}/stories').json()['stories']
        
        for story in stories:
            NewsStory(
                title=story['title'],
                short_summary=story['short_summary'],
                uid=story['id'],
                emoji=story['emoji'],
                category=cat,
                created_at=datetime.now(),
                primary_image_url=story.get('primary_image', {}).get('url', ''),
                primary_image_caption=story.get('primary_image', {}).get('caption', ''),
            ).save().expire(STALE_IN)
    act('buzzer', 'ok', 'news')


def draw_news_story(fs: FrameState, st: NewsStory):
    title_style = TextStyle(font=fonts.cozette, width=106, color='#1a1817')
    sumry_style = TextStyle(font=fonts.tamzen__rs, width=110, color="#979796")

    slide = vstack([
        text(st.title, title_style, multiline=True),
        text(st.short_summary[:60] + '...', sumry_style, multiline=True),
    ], gap=2)
    
    return slide

@dataclass
class AppState:
    story: NewsStory = None
    prev_frame: Frame = None
    changed_at: float = 0
    change_in: float = 8
    last_stories: set = field(default_factory=set)

state = AppState()

def _news_deck(fs: FrameState):
    kagi_load_stories(fs)
    div_style = DivStyle(padding=4, radius=4, )

    if not state.story or (state.changed_at + state.change_in) < fs.tick:
        story = NewsStory.random()
        if len(state.last_stories) > 10:
            state.last_stories = set()
        if story and story.pk not in state.last_stories:
            state.story = story
            state.changed_at = fs.tick
            state.last_stories.add(story.pk)

    st = state.story

    if not st:
        return

    s = div(vstack([draw_news_story(fs, st)], gap=1), margin=2, padding=4, background="#C7A99377", radius=3)
    s = composite_at(st.emoji_im, s, 'tr', frost=.8)
    s = composite_at(st.category_emoji, s, 'br', frost=1)
    return s.tag(('news', st.uid))
    return div(s, div_style).tag(('news', st.uid))


news_deck = draw_loop(_news_deck, use_threads=True)

def news_app(fs: FrameState):
    deck = news_deck(fs)
    w = Widget(
        'di.news',
        deck,
        ease_in=ease.cubic.cubic_in_out,
        style=DivStyle(),
        transition_duration=.8,
        transition_enter=Resize,
    )
    return w
