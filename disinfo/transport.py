'''Frames from the renderer to the server, and to /ws2 clients.

Renderer -> server: Redis RAW_CHANNEL, outside di.pubsub.* (its subscribers read JSON).
    w, h, name length | name | zlib(RGB)
Server -> client, /ws2 binary message:
    magic, seq, base_seq, x, y, w, h, encoding | payload
base_seq 0 is a whole frame. Otherwise a region of frame base_seq.
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
RGBZ, PNG, RGB565Z = 1, 2, 3
ENCODINGS = {'rgbz': RGBZ, 'png': PNG, 'rgb565z': RGB565Z}


def pack_raw(name: str, size: tuple[int, int], rgb: bytes) -> bytes:
    n = name.encode()
    return RAW_HEADER.pack(*size, len(n)) + n + zlib.compress(rgb, 1)

def unpack_raw(data: bytes) -> tuple[str, int, int, bytes]:
    w, h, n = RAW_HEADER.unpack_from(data)
    start = RAW_HEADER.size
    return data[start:start + n].decode(), w, h, data[start + n:]

def pack_ws2(seq: int, base_seq: int, box: tuple[int, int, int, int], encoding: int, payload: bytes) -> bytes:
    return WS2_HEADER.pack(WS2_MAGIC, seq, base_seq, *box, encoding) + payload

def encode(rgb: bytes, size: tuple[int, int], encoding: int) -> bytes:
    if encoding == RGBZ:
        return zlib.compress(rgb, 1)
    if encoding == PNG:
        with io.BytesIO() as b:
            Image.frombytes('RGB', size, rgb).save(b, format='png', compress_level=1)
            return b.getvalue()
    if encoding == RGB565Z:
        a = np.frombuffer(rgb, np.uint8).reshape(-1, 3).astype(np.uint16)
        return zlib.compress((((a[:, 0] >> 3) << 11) | ((a[:, 1] >> 2) << 5) | (a[:, 2] >> 3)).astype('<u2').tobytes(), 1)
    raise ValueError(f'encoding {encoding}')
