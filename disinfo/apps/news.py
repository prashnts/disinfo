import json
import time
import requests
import random

from datetime import datetime
from dataclasses import dataclass, field
from redis_om import HashModel, NotFoundError, Field
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
from disinfo.utils.func import throttle, uname
from disinfo.utils.imops import image_from_url
from disinfo.utils.cairo import load_svg_string, render_emoji, load_svg


class NewsStory(HashModel, index=True):
    title: str
    short_summary: str
    uid: str = Field(primary_key=True)
    index: int = Field(index=True, sortable=True)
    emoji: str
    category: str = Field(index=True, sortable=True)
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
    def get_by_index(cls, ix: int):
        return [i for i in cls.iter_items() if i.index == ix][0]

    @staticmethod
    def shuffled_indices():
        sysrandom = random.SystemRandom()
        sysrandom.seed(time.time())
        items = [i.index for i in NewsStory.iter_items()]
        sysrandom.shuffle(items)
        return items

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


@throttle(15000)
def kagi_load_stories(fs: FrameState) -> bool:
    if any(x for x in NewsStory.iter_items()):
        print("[*] Skipping News Update")
        return False

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
            ).save()
            ix += 1
    act('buzzer', 'ok', 'news')
    return True


@dataclass
class AppState:
    story: NewsStory = None
    shuffled: list[int] = None
    story_index: int = 0
    prev_frame: Frame = None
    changed_at: float = 0
    change_in: float = 45
    min_change_in: float = 15
    details: bool = False
    detail_in: float = 6
    count: int = 0

state = AppState()

kagi_news_icon = load_svg('assets/kagi_news_full.svg', 0.2).trim(upper=2, lower=2)


def _news_deck(fs: FrameState):
    try:
        kagi_load_stories(fs)
    except Exception as e:
        print("Can't load news", str(e))
        return
    if not state.shuffled:
        state.shuffled = NewsStory.shuffled_indices()
        state.story_index = 0

    if (state.changed_at + state.change_in) < fs.tick:
        state.count = NewsStory.count()
        state.story_index += 1
        state.changed_at = fs.tick
        if state.story:
            state.story.expire(1)

    try:
        st: NewsStory = NewsStory.get_by_index(state.shuffled[state.story_index])
    except IndexError:
        state.shuffled = None
        return

    state.story = st
    state.details = (state.changed_at + state.detail_in) < fs.tick


    title_style = TextStyle(
        font=fonts.cozette if not state.details else fonts.tamzen__rs,
        width=112,
        color="#A3A7A8",
        spacing=3)
    sumry_style = TextStyle(font=fonts.scientifica__r, width=112, color="#8B8B8B", spacing=2)

    divblock = styled_div(
        background="#ffffff49",
        padding=(0, 2, 0, 2),
        radius=2,
        margin=1)

    summary = div(
        (VScroller(52, speed=0.1, delta=1, pause_at_loop=True, scrollbar=True)
            .set_frame(text(st.short_summary, sumry_style, multiline=True))
            .reset_position(not state.details)
            .draw(fs.tick)),
        background="#BEB9C928",
        padding=0,
        radius=3)

    if not state.details:
        summary = summary.resize((summary.width, 1)).opacity(0)

    story_title = div(Resize(duration=.2)
        .mut(text(st.title, title_style, multiline=True))
        .draw(fs))
    story_summary = div(
        Resize(delay=.3).mut(summary).draw(fs),
        padding=0,
        radius=2,
    )

    s = div(
        vstack([story_title, story_summary], gap=4),
        margin=0,
        padding=(14, 4, 4, 4),
        background="#50453D00",
        radius=3)
    

    f_img = (Resize()
        .mut(st.cover_im(s.size)
             .brightness(0.3 if state.details else 0.8)
             .opacity(0.9)
             .color_(0.5 if state.details else 0.8)
             .tag(('storycover', st.pk)))
        .draw(fs))
    f_category = Resize(delay=1).mut(st.category_emoji).draw(fs)
    f_emoji = (Resize(duration=.2, delay=1)
        .mut(render_emoji(st.emoji, size=26) if state.details else None)
        .draw(fs))
    s = composite_at(f_img, s, 'mm', behind=True, vibrant=0.7, dx=0, dy=0, frost=.5)
    s = composite_at(f_emoji, s, 'mr', dx=-5, dy=10, behind=True, frost=-2)
    s = composite_at(f_emoji, s, 'mr', dx=-5, dy=10, frost=-2)
    s = div(
        s,
        background="#5A4F3C82",
        radius=(4, 0, 0, 4),
        margin=(8, 0, 0, 0),
        border=1,
        border_color="#15501A9B")
    s = composite_at(
        vstack([
            divblock(kagi_news_icon),
            divblock(text(f'{st.index}/{state.count}', color="#0C0C0CC5"), padding=1),
        ], align='right', gap=1).opacity(1), s, 'tr', frost=2, dy=2)
    s = composite_at(f_category, s, 'tl', frost=2)

    return s.tag(('news', st.pk))


news_deck = draw_loop(_news_deck, use_threads=True)

def news_app(fs: FrameState):
    deck = news_deck(fs)
    return Widget(
        'di.news',
        deck,
        ease_in=ease.cubic.cubic_in_out,
        style=DivStyle(),
        transition_duration=.5,
    )
