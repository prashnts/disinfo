from PIL import Image, ImageColor


from ..components import fonts
from ..components.elements import StillImage
from ..components.layers import div, DivStyle
from ..components.layouts import hstack, composite_at
from ..components.widget import Widget
from ..components.text import TextStyle, text
from ..drat.app_states import PubSubStateManager, PubSubMessage
from ..data_structures import FrameState, AppBaseModel
from ..utils.cairo import load_svg, load_svg_string

WIDTH = 960
HEIGHT = 540

FG = '#000000'
BG = '#FFFFFF'


dishwasher_icon = load_svg('assets/dishwasher.svg', scale=8)

px_op__xxl = fonts.TTFFont('assets/fonts/PixelOperator.ttf', 48)
shinfo = fonts.TTFFont('assets/fonts/ShadowsIntoLight-Regular.ttf', 48)
bangers = fonts.TTFFont('assets/fonts/Bangers-Regular.ttf', 88)
label_style = TextStyle(font=bangers, color=FG)



def clock(fs: FrameState):
    t = fs.now
    return hstack([
        text(t.strftime('%H:%M'), label_style),
    ])


def draw(fs: FrameState):
    img = Image.new('RGBA', (WIDTH, HEIGHT), ImageColor.getrgb(BG))

    rabits = StillImage('/Users/prashant/Desktop/Screenshot 2024-03-24 at 22.47.16.png', resize=(WIDTH, HEIGHT))

    composite_at(rabits, img, 'mm')
    composite_at(clock(fs), img, 'tr', dx=-20, dy=20)
    composite_at(dishwasher_icon, img, 'mm')

    return img
