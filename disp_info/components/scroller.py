from PIL import Image, ImageDraw, ImageFont

from . import fonts

class ScrollableText:
    def __init__(self,
        message: str,
        width: int=128,
        anchor: tuple=(10, 10),
        speed: int=1,
        delta: int=1,
        font: ImageFont=fonts.tamzen__rs,
        fill: str='#e68b1b',
        gap: int=5,
    ):
        self.width = width
        self.anchor = anchor
        self.font = font
        self.fill = fill
        self.gap = gap
        self.delta = delta

        # the cursor position
        self.ypos = 0
        self.last_step = 0 # a step is a "second"
        self.speed = speed  # px/s

        self.message = ''
        self.set_message(message)

    def set_message(self, msg: str):
        # make a "base image" which will be scrolled later.
        if msg == self.message:
            return
        self.message = msg
        self.ypos = 0
        _, _, w, h = self.font.getbbox(self.message, anchor='lt')
        self.msg_width = w + (self.width * 1)
        self.msg_height = h

        self.im_base = Image.new('RGBA', (self.msg_width, h))
        base_draw = ImageDraw.Draw(self.im_base)
        base_draw.text((self.width, 0), self.message, font=self.font, fill=self.fill, anchor='lt')

    def draw(self, step: int, im: Image) -> Image:
        if (step - self.last_step) >= self.speed:
            self.ypos += self.delta
            self.ypos %= self.msg_width
            self.last_step = step
        # we need to crop the base image by cursor offset.
        yspan = self.ypos + self.width

        crop_rect = (
            self.ypos,
            0,
            min(yspan, self.msg_width),
            self.msg_height
        )
        patch = self.im_base.crop(crop_rect)

        im.alpha_composite(patch, self.anchor)
        return im
