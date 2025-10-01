import time
import threading
import json
import io
import base64
import websocket

from typing import Callable

from pydantic import BaseModel
from PIL import Image, ImageFile

from sensors.gesture import gesture_detector

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

    def matrix_options(self) -> RGBMatrixOptions:
        options = RGBMatrixOptions()
        for key, value in self.dict().items():
            print(key, value)
            setattr(options, key, value)
        return options


class Config(BaseModel):
    websocket_url: str = 'wss://disinfo.amd.noop.pw/ws-salon'
    fps: int = 30
    matrix_conf: RGBMatrixConf

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
        self.retry_delay_before_max_retries = 5 # seconds
        self.retry_delay_after_max_retries = 25 # seconds
        self.max_retries = 5
        self.callback = callback
    
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
            self.url,
            on_message=self.on_message,
            on_open=self.on_open,
            on_close=self.on_close,
            on_error=self.on_error)
        
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
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
    prev_frame = None
    telemetry = {}

    _tf = 1 / conf.fps

    # This is apparently needed to avoid PIL not loading its extensions.
    # Without this, we get UnidentifiedImageError later.
    Image.open('test.jpg')

    matrix = RGBMatrix(options=conf.matrix_conf.matrix_options())
    double_buffer = matrix.CreateFrameCanvas()

    def _set_telemetry(values: dict):
        nonlocal telemetry
        telemetry = values

    def _set_frame(ws: WebsocketClient, msg: str):
        nonlocal frame
        try:
            bytes_ = base64.b64decode(msg)
            with io.BytesIO(bytes_) as img_io:
                frame = Image.open(img_io).convert('RGB')
        except Exception as e:
            print('[Error loading frame]', e)

    ws = WebsocketClient(conf.websocket_url, _set_frame)
    ws.connect()
    gesture_detector(_set_telemetry)

    print('[Matrix Renderer started]')

    while True:
        t_start = time.monotonic()
        if frame:
            double_buffer.SetImage(frame)
            double_buffer = matrix.SwapOnVSync(double_buffer)
        ws.send(telemetry=json.dumps(telemetry))
        t_draw = time.monotonic() - t_start
        delay = max(_tf - t_draw, 0)
        time.sleep(delay)
