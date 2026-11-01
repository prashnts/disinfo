'''Each panel's colour by hand, and test pictures: a page on its own port (panel_tune.html, the same as the ESP
matrix board's), kept in a JSON file next to the client.

Panels are the canvas's 64x64 tiles as seen (after the pixel mapper), lettered A B / C D / ... Gains (0..1 a channel)
scale light, so they go through the library's CIE 1931 curve: a table per tile and channel, PIL's point() on what
changed. All gains 1: nothing done.
'''
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image

PAGE = Path(__file__).with_name('panel_tune.html')
TESTS = [0, 7, 9, 8, 6, 4]     # regular, sky, swatches, greys, bands, white
TILE = 64
# navy, sky blue, disinfo's orange, skin; red, green, blue, white; teal, magenta, yellow, purple; greys
SWATCH = [(10, 20, 90), (120, 180, 235), (199, 114, 45), (224, 172, 130), (200, 30, 30), (30, 170, 60),
          (30, 60, 200), (240, 240, 240), (0, 128, 128), (190, 40, 160), (230, 210, 40), (90, 40, 150),
          (30, 30, 30), (80, 80, 80), (160, 160, 160), (220, 220, 220)]


def cie(v: np.ndarray) -> np.ndarray:
    l = v * 100
    return np.where(l <= 8, l / 902.3, ((l + 16) / 116) ** 3)


def cie_inv(y: np.ndarray) -> np.ndarray:
    return np.where(y <= 0.008856, y * 902.3, 116 * np.cbrt(y) - 16) / 100


def tile_picture(test: int) -> np.ndarray:
    '''One tile's test picture, the same on every panel.'''
    y, x = np.mgrid[0:TILE, 0:TILE]
    p = np.zeros((TILE, TILE, 3), np.float32)
    if test == 4:
        p[:] = 255
    elif test == 6:     # white, red, green, blue bands; full left, low (64) right
        v = np.where(x < TILE // 2, 255, 64)
        band = y // 16
        for c in range(3):
            p[..., c] = np.where((band == 0) | (band == c + 1), v, 0)
    elif test == 7:     # navy to sky blue to a pale horizon, a cloud, the sun
        stops = np.array([[8, 18, 70], [90, 150, 225], [205, 215, 225]], np.float32)
        t = y / (TILE - 1) * 2
        k = (t >= 1).astype(int)
        p[:] = stops[k] + (stops[k + 1] - stops[k]) * (t - k)[..., None]
        p[(x - 18) ** 2 / 4 + (y - 34) ** 2 * 2 < 60] = 235
        p[(x - 46) ** 2 + (y - 14) ** 2 < 36] = (255, 230, 150)
    elif test == 8:     # 8 grey steps across, the lower half a touch blue
        v = np.array([6, 12, 24, 48, 80, 128, 192, 255])[x // 8]
        p[..., 0] = p[..., 1] = v
        p[..., 2] = np.where(y < TILE // 2, v, v + (255 - v) // 6)
    elif test == 9:     # 4x4 swatches
        p[:] = np.array(SWATCH, np.float32)[(y // 16) * 4 + x // 16]
    return p.astype(np.uint8)


class PanelTune:
    def __init__(self, path: Path, size: tuple[int, int], brightness: int, name: str = 'Salon'):
        self.path, self.size, self.name = path, size, name
        self.cols, self.rows = size[0] // TILE, size[1] // TILE
        self.gain = [[1.0, 1.0, 1.0] for _ in range(self.cols * self.rows)]
        self.brightness, self.test = brightness, 0
        self.version = 0            # moves at each change: the client draws all of it again
        self.status = ''
        self._lock = threading.Lock()
        if path.exists():
            try:
                self._merge(json.loads(path.read_text()))
            except (ValueError, KeyError) as e:
                print('[PanelTune] bad settings, defaults:', e)
        self.test = 0               # never a test picture after a restart
        self._tables()

    # --- settings
    def config(self) -> dict:
        layout = [[i % self.cols, i // self.cols, 0] for i in range(self.cols * self.rows)]
        return {'brightness': self.brightness,
                'board': {'gain': self.gain, 'layout': layout, 'rotate': 0, 'test': self.test, 'tests': TESTS,
                          'name': self.name, 'unit': 'tile'}}

    def _merge(self, d: dict):
        if isinstance(d.get('brightness'), (int, float)):
            self.brightness = max(1, min(100, int(d['brightness'])))
        b = d.get('board') or {}
        g = b.get('gain')
        if isinstance(g, list) and len(g) == len(self.gain):
            self.gain = [[min(1.0, max(0.0, float(v))) for v in rgb[:3]] for rgb in g]
        if b.get('test') in TESTS:
            self.test = b['test']

    def apply(self, d: dict, save: bool):
        with self._lock:
            self._merge(d)
            self._tables()
            self.version += 1
            if save:
                self.path.write_text(json.dumps({'brightness': self.brightness, 'board': {'gain': self.gain}}))

    def _tables(self):
        v = np.arange(256) / 255
        self.identity = all(g == [1.0, 1.0, 1.0] for g in self.gain)
        self.tables = [sum((list(np.clip(np.round(cie_inv(cie(v) * g) * 255), 0, 255).astype(int)) for g in rgb), [])
                       for rgb in self.gain]

    # --- pictures
    def picture(self) -> Image.Image:
        t = tile_picture(self.test)
        return self.correct(Image.fromarray(np.tile(t, (self.rows, self.cols, 1))))

    def correct(self, im: Image.Image, at: tuple[int, int] = (0, 0)) -> Image.Image:
        '''im placed at `at` on the canvas, each tile through its tables.'''
        if self.identity:
            return im
        out = im.copy()
        x0, y0 = at
        w, h = im.size
        for ty in range(y0 // TILE, (y0 + h - 1) // TILE + 1):
            for tx in range(x0 // TILE, (x0 + w - 1) // TILE + 1):
                box = (max(tx * TILE, x0) - x0, max(ty * TILE, y0) - y0,
                       min((tx + 1) * TILE, x0 + w) - x0, min((ty + 1) * TILE, y0 + h) - y0)
                i = ty * self.cols + tx
                if 0 <= i < len(self.tables):
                    out.paste(im.crop(box).point(self.tables[i]), box[:2])
        return out

    # --- the page
    def serve(self, port: int):
        tune = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, body: bytes, kind='application/json'):
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == '/':
                    return self._send(PAGE.read_bytes(), 'text/html')
                if self.path == '/api/config':
                    return self._send(json.dumps(tune.config()).encode())
                if self.path == '/api/status':
                    return self._send(json.dumps({'chips': tune.status}).encode())
                self.send_error(404)

            def do_POST(self):
                if not self.path.startswith('/api/config'):
                    return self.send_error(404)
                try:
                    d = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                except ValueError:
                    return self.send_error(400)
                tune.apply(d, 'save=0' not in self.path)
                self._send(json.dumps(tune.config()).encode())

        server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f'[PanelTune] http://0.0.0.0:{port}')
