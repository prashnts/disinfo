import time
import typer
import base64
import socket
import numpy as np

from io import BytesIO
from pydash import flatten
from itertools import chain
from PIL import Image, ImageDraw, ImageEnhance

from ..compositor import compose_frame
from ..drat.app_states import LightSensorStateManager
from ..data_structures import FrameState
from ..redis import publish
from ..config import app_config
from ..utils.imops import apply_gamma
from ..utils.func import throttle
from ..components.transitions import NumberTransition

target_ip = '10.0.1.214'
target_port = 6002

# 10.0.1.132 => pico-study      28:CD:C1:0C:38:FA 
# 10.0.1.214 => pico-3dpanel    28:CD:C1:0F:3D:F0 
# 10.0.1.170 -> pico-salon-a    28:CD:C1:11:78:5F 
# 10.0.1.140 -> pico-salon-b    28:CD:C1:11:73:09 

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def reencode_frame(img: Image.Image, brightness: float = 1):
    img = apply_gamma(img, 1.4)
    e = ImageEnhance.Brightness(img)
    img = e.enhance(brightness / 400)
    return img

# @throttle()
def publish_frame(img):
    return
    with BytesIO() as buffer:
        img.save(buffer, format='png')
        encoded_img = base64.b64encode(buffer.getvalue()).decode()

    publish('di.pubsub.frames', action='new-frame-3dp' if app_config.name == '3dpanel' else 'new-frame-pico', payload=dict(img=encoded_img))

def emit_frame(img, brightness):
    publish_frame(img)
    img = reencode_frame(img, brightness)

    im = np.array(img)
    im = np.flip(im, 1)

    if app_config.name == '3dpanel':
        im = np.rot90(im, 1)
        im = im.reshape(64 * 32, 4)
        im = np.stack([im[:, 0], im[:, 2], im[:, 1], im[:, 3]], axis=1)
        ims = [im]
    elif app_config.name == 'picowpanel':
        im = im.reshape(64 * 64, 4)
        ims = [im]
    elif app_config.name == 'salon':
        im_1, im_2 = np.hsplit(im, 2)
        im_1 = np.rot90(im_1, 3)
        im_2 = np.rot90(im_2, 3)
        ims = [np.reshape(im_1, (64 * 64, 4)), np.reshape(im_2, (64 * 64, 4))]
    else:
        raise ValueError('Unknown panel type.')

    offsets = list(range(0, 64, 2))
    even_offsets = offsets[::2]
    odd_offsets = offsets[1::2]
    errors = 0

    for i in flatten(zip(even_offsets, odd_offsets)):
        for pix, panel in enumerate(app_config.udp_panel):
            a = i * panel.size
            b = a + panel.size * 2

            payload = bytes([i, 0, 0] + ims[pix][a:b].astype(np.uint8).flatten().tolist())
            try:
                udp_socket.sendto(payload, (panel.ip, target_port))
            except OSError:
                errors += 1

    if errors:
        print(f'encountered {errors} errors.')


def main(fps: int = 60, stats: bool = False):
    _tf = 1 / fps

    while True:
        t_start = time.monotonic()
        fs = FrameState.create()
        frame = compose_frame(FrameState.create())
        als = LightSensorStateManager(app_config.ambient_light_sensor).get_state()
        brightness = NumberTransition('sys.brightness', 2, initial=50).mut(als.brightness).value(fs)
        emit_frame(frame, int(brightness))
        t_draw = time.monotonic() - t_start

        delay = max(_tf - t_draw, 0)
        _fps = (1 / (t_draw + delay))

        if stats:
            print(f't draw: {t_draw:0.4}')
            print(f'fps:    \033[34m{_fps:0.4}\033[0m')
            print('\033[3A')
        time.sleep(delay)



if __name__ == '__main__':
    typer.run(main)
