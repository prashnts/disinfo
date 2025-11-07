import pendulum
import json
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
from disinfo.components.transitions import Resize, FadeIn, SlideIn
from disinfo.components.scroller import VScroller
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
    raw: str

    def emoji_im(self, size=60) -> Frame:
        return div(render_emoji(self.emoji, size=size), background="#B9A8A8D6", padding=2, radius=2)
    
    def cover_im(self, resize=(80, 80)) -> Frame:
        return image_from_url(self.primary_image_url, resize=resize)

    @property
    def category_emoji(self) -> Frame:
        map = {
            'france': '🥖',
            'tech': '👾',
            'india': '🛺',
            'world': '🌍',
            'science': '🧬',
            'economy': '💶',
        }
        cat = hstack([
            render_emoji(map[self.category], size=10), 
            text(self.category.upper(), color="#e5e5e5b0")
        ], gap=1)
        stuff = div(cat,
                    padding=(1, 2, 1, 2),
                    radius=2,
                    background="#232A54A3",
                    border=1,
                    border_color="#120f2cff",).tag(self.category)
        return stuff

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
    'india',
    'world',
    'science',
    'economy',
]
STALE_IN = 20 * 60

def kagi_get_category_ids(categories: list[str]) -> dict[str, str]:
    cats = requests.get(f'{KAGI_ENDPOINT}/categories', timeout=10).json()['categories']
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
        stories = requests.get(f'{KAGI_ENDPOINT}/categories/{cid}/stories', timeout=10).json()['stories']
        
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
                raw=json.dumps(story),
            ).save().expire(STALE_IN)
    act('buzzer', 'ok', 'news')


@dataclass
class AppState:
    story: NewsStory = None
    prev_frame: Frame = None
    changed_at: float = 0
    change_in: float = 15
    last_stories: set = field(default_factory=set)

state = AppState()

summary_vscroll = VScroller(35, speed=0.1, pause_at_loop=True, scrollbar=True)


def _news_deck(fs: FrameState):
    kagi_load_stories(fs)

    if (state.changed_at + state.change_in) < fs.tick:
        story = NewsStory.random()
        if len(state.last_stories) > 20:
            state.last_stories = set()
        if story and story.pk not in state.last_stories:
            if random.random() > -1:
                state.story = story
                state.last_stories.add(story.pk)
                state.change_in = min(len(story.title) // 10, 15) + 10
            else:
                state.story = None
                state.change_in = 30
                state.changed_at = fs.tick
                return
            
            state.changed_at = fs.tick
            summary_vscroll.reset_position()

    st = state.story
    if not st:
        return

    title_style = TextStyle(font=fonts.serifpx7, width=112, color="#A3A7A8", outline=1, outline_color="#00000091")
    sumry_style = TextStyle(font=fonts.tamzen__rs, width=112, color="#8B8B8B")

    summary = summary_vscroll.set_frame(text(st.short_summary, sumry_style, multiline=True)).draw(fs.tick)

    slide = vstack([
        (FadeIn('news.story.title', .2, delay=.3)
            .mut(text(st.title, title_style, multiline=True))
            .draw(fs)),
        # (FadeIn('news.story.sumr', .2, delay=.3)
        #     .mut(
        #         div(summary,
        #             background="#0a0e188b",
        #             padding=2,
        #             radius=3))
        #     .draw(fs)),
    ], gap=2)

    s = div(
        vstack([slide], gap=1),
        margin=0,
        padding=(24, 4, 4, 4),
        background="#50453D00",
        radius=3)

    f_emoji = (FadeIn('news.emoji.main', .5, delay=1)
        .mut(render_emoji(st.emoji, size=22))
        .draw(fs))
    f_img = (FadeIn('news.img.main', 1, delay=.5)
        .mut(st.cover_im(s.size).opacity(0.7))
        .draw(fs))
    s = composite_at(f_img, s, 'mm', behind=True, vibrant=0.7, dx=0, dy=0, frost=2.5)
    f_category = Resize('news.story.category', .5, delay=1).mut(st.category_emoji).draw(fs)
    s = composite_at(f_category, s, 'tr', dx=-3, dy=3)
    s = div(
        s,
        background="#5A4F3C82",
        radius=(4, 0, 0, 4),
        margin=(8, 5, 0, 5),
        border=1,
        border_color="#7F848F9B")
    s = composite_at(f_emoji, s, 'tl', dx=10)

    return s.tag(('news', st.uid))


news_deck = draw_loop(_news_deck, use_threads=True)

def news_app(fs: FrameState):
    deck = news_deck(fs)
    w = Widget(
        'di.news',
        deck,
        ease_in=ease.cubic.cubic_in_out,
        style=DivStyle(),
        transition_duration=.5,
        transition_enter=partial(Resize),
    )
    return w
