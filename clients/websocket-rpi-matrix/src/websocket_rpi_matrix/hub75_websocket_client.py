import time
import threading
import json
import io
import base64
import websocket

from collections import deque
from typing import Callable

from pydantic import BaseModel
from PIL import Image, ImageFile, ImageDraw, ImageFont

from websocket_rpi_matrix.di_remote import sensor_thread, Config as SensorConfig
from websocket_rpi_matrix.frames import FrameAssembler, WS2_MAGIC

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions   # type: ignore
except ImportError:
    from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions

ImageFile.LOAD_TRUNCATED_IMAGES = True

class RGBMatrixConf(BaseModel):
    rows: int = 64
    cols: int = 64
    chain_length: int = 3
    parallel: int = 2
    brightness: int = 80
    pwm_bits: int = 11
    pwm_dither_bits: int = 0
    scan_mode: int = 0
    pixel_mapper_config: str = ''
    gpio_slowdown: int = 3
    drop_privileges: bool = True
    hardware_mapping: str = 'regular'
    show_refresh_rate: bool = True
    disable_hardware_pulsing: bool = False
    # Pads each frame to a fixed time: uneven frames show as flicker. 0 is unlimited.
    limit_refresh_rate_hz: int = 0

    def matrix_options(self) -> RGBMatrixOptions:
        options = RGBMatrixOptions()
        for key, value in self.model_dump().items():
            setattr(options, key, value)
        return options


class Config(BaseModel):
    websocket_url: str = 'wss://disinfo.amd.noop.pw/ws-salon'
    # v1: /ws/<screen>, a frame for each telemetry sent. v2: /ws2/<screen>, frames pushed as they change.
    protocol: str = 'v1'
    telemetry_hz: float = 30
    fps: int = 30
    matrix_conf: RGBMatrixConf = RGBMatrixConf()
    sensor_conf: SensorConfig = SensorConfig()

    @property
    def width(self) -> int:
        return self.matrix_conf.cols * self.matrix_conf.chain_length

    @property
    def height(self) -> int:
        return self.matrix_conf.rows * self.matrix_conf.parallel


class WebsocketClient:
    def __init__(self, url: str, callback: Callable[[dict], None]):
        self.url = url
        self.connected = False
        self.retry_count = 0
        self.retry_delay_before_max_retries = 1 # seconds
        self.retry_delay_after_max_retries = 5 # seconds
        self.max_retries = 5
        self.callback = callback
        self.acts_id = None     # the last acts the server sent: a reconnect asks for what came after
    
    def on_message(self, ws, msg):
        self.callback(self, msg)

    def on_open(self, ws):
        self.connected = True
        self.retry_count = 0
        print(f'Connected to {self.url}')
    
    def on_close(self, *args):
        self.connected = False
        print(f'Disconnected to {self.url}, will retry.')
        self.retry_connect()
    
    def on_error(self, ws, *args, **kwargs):
        print(f'Error in connection to {self.url}: {args} {kwargs}')
        self.connected = False

    def send(self, **kwargs):
        if not self.connected:
            return
        self.ws.send(json.dumps(kwargs))

    def connect(self):
        if self.connected:
            return
        self.ws = websocket.WebSocketApp(
            self.url + (f"{'&' if '?' in self.url else '?'}since={self.acts_id}" if self.acts_id else ''),
            on_message=self.on_message,
            on_open=self.on_open,
            on_close=self.on_close,
            on_error=self.on_error)
        
        # The text frames (v1) are big: websocket-client's utf-8 check, in Python, was most of the desk's CPU.
        self.ws_thread = threading.Thread(target=self.ws.run_forever, kwargs={'skip_utf8_validation': True}, daemon=True)
        self.ws_thread.start()
    
    def retry_connect(self):
        if self.connected:
            return
        if self.retry_count > self.max_retries:
            time.sleep(self.retry_delay_after_max_retries)
        else:
            time.sleep(self.retry_delay_before_max_retries)
        print(f'Retrying connection to {self.url}... (attempt {self.retry_count})')
        self.retry_count += 1
        self.connect()

def main(conf: Config):
    frame = None
    acts = deque()      # from the websocket's thread to the sensors'
    prev_frame = None
    last_ping = 0
    telemetry = {}
    node_id = conf.websocket_url.split('/')[-1]

    _tf = 1 / conf.fps

    # Loaded now: the matrix drops privileges, PIL's lazy imports from /home/pi fail after that.
    status_font = ImageFont.load_default(size=10)
    clock_font = ImageFont.load_default(size=24)

    def status_frame(text: str, size: tuple[int, int]) -> Image.Image:
        # Dim: it can stay up for long while the server is down.
        im = Image.new('RGB', size)
        draw = ImageDraw.Draw(im)
        draw.fontmode = '1'   # crisp pixels, no antialiasing
        w, h = size
        draw.text((w // 2, h // 2), time.strftime('%H:%M'), fill=(40, 40, 40), font=clock_font, anchor='mm')
        draw.text((w // 2, h // 2 + 18), text, fill=(22, 22, 22), font=status_font, anchor='mm')
        return im

    # This is apparently needed to avoid PIL not loading its extensions.
    # Without this, we get UnidentifiedImageError later.
    Image.open('test.jpg')

    def _set_telemetry(values: dict):
        nonlocal telemetry
        telemetry = values
        return [acts.popleft() for _ in range(len(acts))]

    changes = deque(maxlen=8)       # (version, boxes) of the last frames, boxes None: all of it
    latest = (0, None)              # (version, frame), set together: the loop reads them in one go

    def _new_frame(im: Image.Image, boxes: list | None):
        nonlocal frame, latest
        v = latest[0] + 1
        changes.append((v, boxes))
        frame, latest = im, (v, im)

    def _got_acts(ws: WebsocketClient, msg: dict):
        acts.extend(msg.get('acts') or [])
        ws.acts_id = msg.get('acts_id', ws.acts_id)

    def _set_frame(ws: WebsocketClient, msg: str):
        nonlocal last_ping
        try:
            msg = json.loads(msg)
            _got_acts(ws, msg)

            bytes_ = base64.b64decode(msg['img'])
            with io.BytesIO(bytes_) as img_io:
                _new_frame(Image.open(img_io).convert('RGB'), None)
        except Exception as e:
            print('[Error loading frame]', e)
        last_ping = time.monotonic()
        ws.send(telemetry=json.dumps(telemetry), _node=node_id)

    assembler = FrameAssembler()

    def _set_frame_v2(ws: WebsocketClient, msg):
        nonlocal last_ping
        last_ping = time.monotonic()
        try:
            # Without utf-8 validation, text frames come as bytes too: the frames start with the magic.
            if isinstance(msg, str) or not msg.startswith(WS2_MAGIC):
                _got_acts(ws, json.loads(msg))
            elif assembler.apply(msg):
                _new_frame(assembler.frame, assembler.boxes)
            else:
                ws.send(resync=1)
        except Exception as e:
            print('[Error loading frame]', e)

    v2 = conf.protocol == 'v2'
    ws = WebsocketClient(conf.websocket_url, _set_frame_v2 if v2 else _set_frame)
    ws.connect()
    sensor_thread(_set_telemetry, conf.sensor_conf)
    time.sleep(1)
    print('[Inial setup done]')

    matrix = RGBMatrix(options=conf.matrix_conf.matrix_options())
    double_buffer = matrix.CreateFrameCanvas()

    print('[Matrix Renderer started]')
    last_telemetry = 0
    # SetImage is slow (each pixel through the mapper into every PWM bit plane): only what changed, into each of the
    # two canvases (they take turns at each swap). Nothing changed, no swap.
    drawn = [0, 0]      # the version each canvas holds, the back one first
    def since(v: int) -> list | None:
        hist = list(changes)
        if not v or not hist or hist[0][0] > v + 1:
            return None
        boxes = []
        for n, b in hist:
            if n > v:
                if b is None:
                    return None
                boxes += b
        return boxes


    while True:
        t_start = time.monotonic()
        v, im = latest
        if im and drawn[0] != v:
            boxes = since(drawn[0])
            if boxes is None:
                double_buffer.SetImage(im)
            for b in boxes or []:
                double_buffer.SetImage(im.crop(b), b[0], b[1])
            drawn[0] = v
            double_buffer = matrix.SwapOnVSync(double_buffer)
            drawn.reverse()
        elif not im:
            dots = '.' * (int(t_start) % 4)
            double_buffer.SetImage(status_frame(('waiting' if ws.connected else 'connecting') + dots, (double_buffer.width, double_buffer.height)))
            double_buffer = matrix.SwapOnVSync(double_buffer)

        if v2 and time.monotonic() - last_telemetry > 1 / conf.telemetry_hz:
            ws.send(telemetry=json.dumps(telemetry), _node=node_id)
            last_telemetry = time.monotonic()

        if time.monotonic() - last_ping > (5 if frame else 0.5):
            # Initial ping and then every 5 seconds, or 0.5s until the first frame arrives.
            ws.send(telemetry=json.dumps(telemetry), _node=node_id)
            if frame:
                # let supervisor restart
                raise RuntimeError()

        t_draw = time.monotonic() - t_start
        delay = max(_tf - t_draw, 0)
        time.sleep(delay)
