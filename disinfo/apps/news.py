import pendulum
import math
import requests

from datetime import datetime
from dataclasses import dataclass
from redis_om import HashModel

from disinfo.data_structures import AppBaseModel, FrameState
from disinfo.components.widget import Widget
from disinfo.components.text import text, TextStyle
from disinfo.components.layouts import vstack, hstack
from disinfo.components.layers import div, DivStyle
from disinfo.components.stack import Stack
from disinfo.components import fonts
from disinfo.components.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act
from disinfo.screens.drawer import draw_loop


class NewsStory(HashModel):
    title: str
    short_summary: str
    uid: str
    emoji: str
    category: str
    created_at: datetime

KAGI_ENDPOINT = 'https://news.kagi.com/api/batches/latest'
CATEGORIES = ['france', 'tech']
STALE_IN = 10 * 60

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
            ).save().expire(STALE_IN)
    act('buzzer', 'ok')

@dataclass
class State:
    mode: str = 'create'
    duration: int = 0
    last_encoder: int = 0
    active_pk: str = ''

state = State()

def draw_news_story(fs: FrameState, st: NewsStory):
    title_style = TextStyle(font=fonts.px_op__l, width=90)
    sumry_style = TextStyle(font=fonts.px_op__r, width=90)
    div_style = DivStyle(padding=2, radius=2, background="#ccaa60af")

    slide = vstack([
        text(st.title, title_style, multiline=True),
        text(st.short_summary, sumry_style, multiline=True),
    ], gap=2)
    return Widget(f'news.story.{st.uid}', div(slide, div_style), wait_time=10, active=True)


def _news_deck(fs: FrameState):
    kagi_load_stories(fs)

    stories = [NewsStory.get(pk) for pk in NewsStory.all_pks()][:2]

    if not stories:
        return None

    view = Stack('news.deck', size=80).mut([draw_news_story(fs, story) for story in stories])
    return div(view.draw(fs).tag(('news', 'deck')))

news_deck = draw_loop(_news_deck, use_threads=False)

def news_app(fs: FrameState):
    return Widget('di.news', news_deck(fs))
