import pendulum
import math
import requests

from datetime import datetime
from dataclasses import dataclass
from redis_om import HashModel, NotFoundError

from disinfo.data_structures import AppBaseModel, FrameState
from disinfo.components.widget import Widget
from disinfo.components.text import text, TextStyle
from disinfo.components.layouts import vstack, hstack, place_at, composite_at
from disinfo.components.layers import div, DivStyle
from disinfo.components.stack import Stack, StackStyle
from disinfo.components import fonts
from disinfo.components.elements import Frame
from disinfo.web.telemetry import TelemetryStateManager, act
from disinfo.screens.drawer import draw_loop
from disinfo.utils.imops import image_from_url
from disinfo.utils.cairo import load_svg_string


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
        template = f'''<?xml version="1.0" encoding="UTF-8"?>
        <svg width="26px" height="20px" viewBox="0 0 20 30" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <title>dishwasher-segment copy</title>
            <g id="Artboard" stroke="none" stroke-width="1" fill="#ccc" font-family="AppleColorEmoji, Apple Color Emoji" font-size="20" font-weight="normal">
                <text id="main">
                    <tspan x="0" y="20">{self.emoji}</tspan>
                </text>
            </g>
        </svg>'''
        return load_svg_string(template)


    @classmethod
    def iter_items(cls, limit: int = 0):
        for i, pk in enumerate(cls.all_pks()):
            if limit and limit <= i:
                break
            try:
                yield cls.get(pk)
            except NotFoundError:
                continue


KAGI_ENDPOINT = 'https://news.kagi.com/api/batches/latest'
CATEGORIES = ['france', 'tech']
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
    title_style = TextStyle(font=fonts.cozette, width=100, color='#1a1817')
    sumry_style = TextStyle(font=fonts.tamzen__rs, width=110, color="#7c7c7b")

    slide = vstack([
        text(st.title, title_style, multiline=True),
        text(st.short_summary[:100] + '...', sumry_style, multiline=True),
    ], gap=2)
    
    # place_at(image_from_url(st.primary_image_url), slide, x=10, y=10, anchor='tl')
    return slide


def _news_deck(fs: FrameState):
    kagi_load_stories(fs)
    stack_style = StackStyle(size=95, speed=0.001, scroll_delta=2, scrollbar=True, offset_top=-5)
    div_style = DivStyle(padding=4, radius=4, background="#C7A99377")

    stories = []

    for st in NewsStory.iter_items():
        s = vstack([draw_news_story(fs, st)], gap=1)
        s = composite_at(st.emoji_im, s, 'tr', dx=2)
        w = Widget(f'news.story.{st.uid}', div(s, div_style), wait_time=7, active=False)
        stories.append(w)

    if not stories:
        return None

    view = Stack('news.deck', stack_style).mut(stories)
    return div(view.draw(fs).tag(('news', 'deck')))

news_deck = draw_loop(_news_deck, use_threads=False)

def news_app(fs: FrameState):
    return Widget('di.news', news_deck(fs))
