'''Frames from the renderer to the server, and to /ws2 clients.

Renderer -> server: Redis RAW_CHANNEL, outside di.pubsub.* (its subscribers read JSON).
    w, h, name length | name | zlib(RGB)
Server -> client, /ws2 binary message:
    magic, seq, base_seq, x, y, w, h, encoding | payload
base_seq 0: a whole frame. Otherwise the regions that changed since frame base_seq,
the box around them in the header, and in the payload:
    count | (x, y, w, h, length | encoded region) * count
'''
import io
import struct
import zlib

import numpy as np
from PIL import Image

RAW_CHANNEL = 'di.frames.raw'
RAW_HEADER = struct.Struct('<HHH')

WS2_MAGIC = b'DIF2'
WS2_HEADER = struct.Struct('<4sIIHHHHB')
REGION = struct.Struct('<HHHHI')
TILE = 16
RGBZ, PNG, RGB565Z, JPEG = 1, 2, 3, 4
ENCODINGS = {'rgbz': RGBZ, 'png': PNG, 'rgb565z': RGB565Z, 'jpeg': JPEG}
JPEG_QUALITY = 95       # no chroma subsampling: the pixel fonts stay sharp; 95: the dials (USB, small frames)


def pack_raw(name: str, size: tuple[int, int], rgb: bytes) -> bytes:
    n = name.encode()
    return RAW_HEADER.pack(*size, len(n)) + n + zlib.compress(rgb, 1)

def unpack_raw(data: bytes) -> tuple[str, int, int, bytes]:
    w, h, n = RAW_HEADER.unpack_from(data)
    start = RAW_HEADER.size
    return data[start:start + n].decode(), w, h, data[start + n:]

def pack_ws2(seq: int, base_seq: int, box: tuple[int, int, int, int], encoding: int, payload: bytes) -> bytes:
    return WS2_HEADER.pack(WS2_MAGIC, seq, base_seq, *box, encoding) + payload

def changed_boxes(a: bytes, b: bytes, size: tuple[int, int], tile: int = TILE) -> list[tuple[int, int, int, int]]:
    '''Boxes (x, y, w, h) around the tiles that differ, runs of tiles merged down while they line up.'''
    w, h = size
    th, tw = -(-h // tile), -(-w // tile)
    d = np.zeros((th * tile, tw * tile * 3), bool)
    d[:h, :w * 3] = (np.frombuffer(a, np.uint8) != np.frombuffer(b, np.uint8)).reshape(h, w * 3)
    tiles = d.reshape(th, tile, tw, tile * 3).any((1, 3))
    boxes, open_ = [], {}   # (x0, x1) in tiles -> first row
    for y in range(th + 1):
        runs = {}
        if y < th:
            row = np.concatenate(([False], tiles[y], [False]))
            edges = np.flatnonzero(row[1:] != row[:-1])
            runs = {(x0, x1): open_.get((x0, x1), y) for x0, x1 in zip(edges[::2], edges[1::2])}
        for (x0, x1), y0 in open_.items():
            if (x0, x1) not in runs:
                boxes.append((x0 * tile, y0 * tile, min(x1 * tile, w) - x0 * tile, min(y * tile, h) - y0 * tile))
        open_ = runs
    return [tuple(int(v) for v in b) for b in boxes]

def pack_regions(rgb: bytes, size: tuple[int, int], boxes: list, encoding: int) -> bytes:
    a = np.frombuffer(rgb, np.uint8).reshape(size[1], size[0], 3)
    out = [struct.pack('<H', len(boxes))]
    for x, y, w, h in boxes:
        data = encode(a[y:y + h, x:x + w].tobytes(), (w, h), encoding)
        out += [REGION.pack(x, y, w, h, len(data)), data]
    return b''.join(out)

def bounds(boxes: list) -> tuple[int, int, int, int]:
    if not boxes:
        return (0, 0, 0, 0)
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return (x0, y0, max(b[0] + b[2] for b in boxes) - x0, max(b[1] + b[3] for b in boxes) - y0)

def encode(rgb: bytes, size: tuple[int, int], encoding: int) -> bytes:
    if encoding == RGBZ:
        return zlib.compress(rgb, 1)
    if encoding == PNG:
        with io.BytesIO() as b:
            Image.frombytes('RGB', size, rgb).save(b, format='png', compress_level=1)
            return b.getvalue()
    if encoding == JPEG:
        with io.BytesIO() as b:
            Image.frombytes('RGB', size, rgb).save(b, format='jpeg', quality=JPEG_QUALITY, subsampling=0)
            return b.getvalue()
    if encoding == RGB565Z:
        a = np.frombuffer(rgb, np.uint8).reshape(-1, 3).astype(np.uint16)
        return zlib.compress((((a[:, 0] >> 3) << 11) | ((a[:, 1] >> 2) << 5) | (a[:, 2] >> 3)).astype('<u2').tobytes(), 1)
    raise ValueError(f'encoding {encoding}')
