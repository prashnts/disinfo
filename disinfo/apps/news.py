import pendulum
import json
import requests
import random

from datetime import datetime
from functools import partial
from dataclasses import dataclass, field
from redis_om import HashModel, NotFoundError
from pydantic import ValidationError

from disinfo.data_structures import AppBaseModel, FrameState
from disinfo.components.widget import Widget
from disinfo.components.text import text, TextStyle
from disinfo.components.layouts import vstack, hstack, place_at, composite_at
from disinfo.components.layers import div, DivStyle, styled_div
from disinfo.components.stack import Stack, StackStyle
from disinfo.components.transitions import Resize, FadeIn, SlideIn, ScaleIn, ScaleOut
from disinfo.components.scroller import VScroller
from disinfo.components import fonts
from disinfo.components.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act
from disinfo.screens.drawer import draw_loop
from disinfo.utils import ease
from disinfo.utils.imops import image_from_url
from disinfo.utils.cairo import load_svg_string, render_emoji, load_svg


class NewsStory(HashModel):
    title: str
    short_summary: str
    uid: str
    index: int
    emoji: str
    category: str
    created_at: datetime
    primary_image_url: str
    primary_image_caption: str
    raw: str
    seen_at: float = 0

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
                    margin=2,
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
            except ValidationError:
                continue
    
    @classmethod
    def random(cls):
        items = list(cls.iter_items())
        if items:
            return random.choice(items)

    @classmethod
    def count(cls) -> int:
        return len(list(cls.all_pks()))


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
    if any(x for x in NewsStory.iter_items()):
        return

    ix = 0
    for cat, cid in kagi_get_category_ids(CATEGORIES).items():
        data = requests.get(f'{KAGI_ENDPOINT}/categories/{cid}/stories', timeout=10).json()
        stories = data['stories']
        
        for story in stories:
            NewsStory(
                title=story['title'],
                short_summary=story['short_summary'],
                uid=story['id'],
                index=ix,
                emoji=story['emoji'],
                category=cat,
                created_at=datetime.now(),
                primary_image_url=story.get('primary_image', {}).get('url', ''),
                primary_image_caption=story.get('primary_image', {}).get('caption', ''),
                raw=json.dumps(story),
            ).save().expire(STALE_IN)
            ix += 1
    act('buzzer', 'ok', 'news')


@dataclass
class AppState:
    story: NewsStory = None
    prev_frame: Frame = None
    changed_at: float = 0
    change_in: float = 25
    min_change_in: float = 15
    details: bool = False
    detail_in: float = 10
    last_stories: set = field(default_factory=set)
    story_timeout: int = 6000
    count: int = 0

state = AppState()

summary_vscroll = VScroller(35, speed=0.1, pause_at_loop=True, scrollbar=True)
kagi_news_icon = load_svg('assets/kagi_news_full.svg', 0.2).trim(upper=2, lower=2)


def _news_deck(fs: FrameState):
    kagi_load_stories(fs)

    if (state.changed_at + state.change_in) < fs.tick:
        story = NewsStory.random()
        if len(state.last_stories) > 20:
            state.last_stories = set()
        if story and (story.seen_at > fs.tick + state.story_timeout or not story.seen_at):
            if random.random() > -1:
                state.story = story
                story.seen_at = fs.tick
                story.save().expire(STALE_IN)
                state.count = NewsStory.count()
                state.last_stories.add(story.pk)
                state.change_in = min(len(story.title) // 10, 15) + state.min_change_in
            else:
                state.story = None
                state.change_in = state.min_change_in
                state.changed_at = fs.tick
                return
            
            state.changed_at = fs.tick
            summary_vscroll.reset_position()

    st: NewsStory = state.story
    if not st:
        return

    state.details = (state.changed_at + state.detail_in) < fs.tick


    title_style = TextStyle(
        font=fonts.mixserif if not state.details else fonts.scientifica__r,
        width=112,
        color="#A3A7A8",
        outline=1,
        spacing=2,
        outline_color="#000000AF")
    sumry_style = TextStyle(font=fonts.tamzen__rs, width=112, color="#8B8B8B", spacing=2)

    divblock = styled_div(
        background='#ffffff55',
        padding=(0, 2, 0, 2),
        radius=2,
        margin=2)

    sum_scroll = summary_vscroll.set_frame(text(st.short_summary, sumry_style, multiline=True)).draw(fs.tick)
    summary = div(sum_scroll,
        background="#0a0e188b",
        padding=2,
        radius=3)
    
    if not state.details:
        summary = summary.resize((1, 1))
        summary_vscroll.reset_position()


    slides = [
        (Resize('news.story.title', .3)
            .mut(text(st.title, title_style, multiline=True))
            .draw(fs)),
        (Resize('news.story.sumr', .4)
            .mut(summary)
            .draw(fs))
    ]

    s = div(
        vstack(slides, gap=2),
        margin=0,
        padding=(16, 4, 10, 4),
        background="#50453D00",
        radius=3)

    f_img = (Resize('news.img.main', .5)
        .mut(st.cover_im(s.size).brightness(0.3 if state.details else 0.8).opacity(0.7).color_(0.2 if state.details else 0.6).tag(('storycover', st.pk)))
        .draw(fs))
    f_category = Resize('news.story.category', .5, delay=1).mut(st.category_emoji).draw(fs)
    s = composite_at(f_img, s, 'mm', behind=True, vibrant=0.7, dx=0, dy=0, frost=.5)
    s = composite_at(f_category, s, 'tl')
    f_emoji = (Resize('news.emoji.main', .2, delay=1)
        .mut(render_emoji(st.emoji, size=26) if state.details else None)
        .draw(fs))
    s = composite_at(f_emoji, s, 'tr', dx=-5, dy=10, behind=True)
    s = div(
        s,
        background="#5A4F3C82",
        radius=(4, 0, 0, 4),
        margin=(8, 0, 0, 0),
        border=1,
        border_color="#7F848F9B")
    s = composite_at(
        hstack([
            divblock(text(f'{st.index}/{state.count}', color="#0C0C0CC5"), padding=1),
            divblock(kagi_news_icon),
        ]).opacity(0.7), s, 'br', frost=2)

    return s.tag(('news', st.pk))


news_deck = draw_loop(_news_deck, use_threads=True)

def news_app(fs: FrameState):
    deck = news_deck(fs)
    w = Widget(
        'di.news',
        deck,
        ease_in=ease.cubic.cubic_in_out,
        style=DivStyle(),
        transition_duration=.5,
    )
    return w
