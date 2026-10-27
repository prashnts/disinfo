from functools import cache
from PIL import Image, ImageDraw

from disinfo import fonts
from discore.elements import Frame, StillImage
from discore.text import TextStyle, text
from discore.layouts import hstack, vstack, grid, mosaic
from discore.layers import div, DivStyle, rounded_rectangle
from discore.frame_cycler import FrameCycler
from discore.scroller import VScroller, HScroller
from discore.data_structures import FrameState
from discore.widget import Widget
from ..utils.palettes import metro_colors
from ..data_structures import AppBaseModel
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..drat import idfm, shown

warning_tile = StillImage('assets/raster/warning-tile-3x3.png')
metro_issue_icon = StillImage('assets/raster/metro-issues.png')
metro_paris_banner = StillImage('assets/raster/metro-paris-old-52x16.png')
msg_vscroll = VScroller(size=40, name='metro.notes', pause_at_loop=True, pause_duration=1.5, speed=0.02)
status_hscroll = HScroller(size=30, name='metro.issues', pause_at_loop=True, pause_duration=1, pause_offset=0, speed=0.02)

time_style = TextStyle(font=fonts.bitocra7, color='#a57a05')
note_style = TextStyle(font=fonts.microfont_35_reg, color='#b9b9b9', outline=1, outline_color='#181818', overflow='wrap')
later_style = TextStyle(font=fonts.microfont_35_reg, color='#7a7a7a', overflow='wrap')
doubt_style = TextStyle(font=fonts.microfont_35_reg, color='#b7925e', overflow='wrap')
health_colors = {'ok': '#2f9e44', 'slow': '#b7925e', 'none': '#c93f20'}
card_style = DivStyle(background='#05153486', padding=3, radius=3, border=1, border_color='#333435C9')
max_width = 160         # the card's content on the wide screens
fresh_s = 600           # older data is not shown, the banner is


class MetroState(AppBaseModel):
    doc: dict | None = None
    notes: dict = {}

class MetroStateManager(PubSubStateManager[MetroState]):
    '''What the data service fetched (drat.idfm), read again when it says so.'''
    model = MetroState
    channels = ('di.pubsub.metro',)

    def initial_state(self) -> MetroState:
        return MetroState(
            doc=idfm.load(idfm.KEY),
            notes=(idfm.load(idfm.NOTES_KEY) or {}).get('notes', {}))

    def process_message(self, channel: str, data: PubSubMessage):
        self.state = self.initial_state()


@cache
def metro_icon(line_name: str, has_problems: bool = False) -> Frame:
    size = 9
    start_x = 0 if len(line_name) > 1 else 1
    background, text_color = metro_colors.get(line_name, ['#C6C6C6', '#000'])

    img = rounded_rectangle(
        width=size + 1,
        height=size,
        radius=(4,) * 4,
        fill=background,
        border=1 if has_problems else 0,
        border_color='#ba1c11')

    draw = ImageDraw.Draw(img)
    draw.text(
        ((size / 2) + start_x, size / 2),
        line_name,
        fill=text_color,
        font=fonts.tamzen__rs.font,
        anchor='mm')

    return Frame(img, hash=('metro_icon', line_name, has_problems))

@cache
def line_icon(line: str, issues: bool = False) -> FrameCycler:
    # A red outline blinks while the line has trouble now.
    return FrameCycler([metro_icon(line), metro_icon(line, has_problems=issues)])

@cache
def health_bar(state: str) -> Frame:
    # Trains coming regularly or not, whatever the messages say.
    return Frame(Image.new('RGBA', (2, 7), health_colors[state]), hash=('metro.health', state))

@cache
def warning_line(h: int) -> Frame:
    return mosaic(warning_tile, nx=1, ny=max(h // warning_tile.height, 1), seamless=False)


def note_row(fs: FrameState, n: dict) -> Frame:
    style = note_style if n['now'] else later_style
    # The lines and when on top, what happens under.
    head = hstack([*[line_icon(l).draw(fs.tick) for l in n['lines']], text(n['when'], later_style, overflow='fit') if n['when'] else None], gap=2)
    return vstack([head, text(n['text'], style), text(f"? {n['doubt']}", doubt_style) if n['doubt'] else None], gap=1, align='hstretch')

def card(fs: FrameState, s: MetroState) -> Frame:
    now = fs.now.timestamp()
    doc = s.doc
    notes = [n for r in doc.get('reports', []) if (n := idfm.note(r, s.notes, now))]
    notes.sort(key=lambda n: (not n['now'], ['stop', 'slow', 'info'].index(n['level'])))
    troubled = list(dict.fromkeys(l for n in notes if n['now'] and n['level'] != 'info' for l in n['lines']))
    n_times = 3 if notes else 4

    stopped = {(st['line'], st['stop']): st['times'] for st in doc['stops']}
    cells = []
    for stop in idfm.conf().stops:
        times = stopped.get((stop.line, stop.stop), [])
        mins = idfm.catchable(stop, times, now)[:n_times]
        cells += [line_icon(stop.line, stop.line in troubled).draw(fs.tick), health_bar(idfm.health(times, now))]
        cells += [text(f'{m}'.rjust(2), time_style) for m in mins] + [text('--', time_style)] * (n_times - len(mins))
    left = [grid(cells, ncols=2 + n_times, gap=2, anchor='ml')]
    others = [line_icon(l, True).draw(fs.tick) for l in troubled if l not in {st.line for st in idfm.conf().stops}]
    if others:
        ticker = status_hscroll.set_frame(hstack(others, gap=2)).set_size(n_times * 10)
        left.append(hstack([metro_issue_icon, ticker.draw(fs.tick)], gap=1))
    left = vstack(left, gap=2)
    if not notes:
        return left

    width = min(fs.config.width - 8, max_width) - left.width - 2
    rows = [div(note_row(fs, n), width=width - warning_tile.width - 3) for n in notes]
    h = max(left.height, 24)
    # A stop at each note.
    msg_vscroll.set_size(h).set_frame(vstack(rows, gap=4), pauses=[sum(r.height + 4 for r in rows[:i]) for i in range(len(rows))], pause_offset=0)
    box = div(hstack([warning_line(h), msg_vscroll.draw(fs.tick)], gap=1, align='top'),
              style=DivStyle(background='#24242485', padding=1, radius=(2, 2, 0, 0)))
    return hstack([left, box], gap=2, align='top')


def up(fs: FrameState) -> bool:
    return shown.up(fs, 'metro', idfm.scheduled(fs.now))

def widgets(fs: FrameState) -> list[Widget]:
    '''In the bottom stack on schedule, on top for a minute when the button's pressed.'''
    s = MetroStateManager().get_state(fs)
    if not up(fs):
        # Kept, empty: it shrinks away (Resize), and grows back from nothing.
        return [Widget('di.metro.info', None, style=card_style)]
    fresh = s.doc and fs.now.timestamp() - s.doc['at'] < fresh_s
    frame = card(fs, s) if fresh else div(metro_paris_banner, padding=10)
    pressed = shown.is_pressed(fs, 'metro')
    return [Widget('di.metro.info', frame.tag(('metro', fresh and s.doc['at'], len(s.notes))), focus=pressed, priority=2 if pressed else 1,
                   wait_time=14, style=card_style)]
