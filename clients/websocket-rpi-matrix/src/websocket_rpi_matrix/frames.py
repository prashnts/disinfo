'''Frames from /ws2, see disinfo/transport.py.'''
import io
import struct
import zlib

from PIL import Image

WS2_MAGIC = b'DIF2'
WS2_HEADER = struct.Struct('<4sIIHHHHB')
RGBZ, PNG = 1, 2


class FrameAssembler:
    '''The current frame, from whole frames and regions of one.'''

    def __init__(self):
        self.frame: Image.Image | None = None
        self.seq = 0

    def apply(self, msg: bytes) -> bool:
        '''False when a region doesn't apply to the current frame: ask for a whole one.'''
        magic, seq, base_seq, x, y, w, h, enc = WS2_HEADER.unpack_from(msg)
        if magic != WS2_MAGIC:
            raise ValueError(f'not a /ws2 frame: {magic!r}')
        if base_seq and (self.frame is None or base_seq != self.seq):
            return False
        part = decode(msg[WS2_HEADER.size:], (w, h), enc)
        if base_seq:
            frame = self.frame.copy()
            frame.paste(part, (x, y))
            part = frame
        self.frame, self.seq = part, seq
        return True


def decode(payload: bytes, size: tuple[int, int], enc: int) -> Image.Image:
    if enc == RGBZ:
        return Image.frombytes('RGB', size, zlib.decompress(payload))
    if enc == PNG:
        return Image.open(io.BytesIO(payload)).convert('RGB')
    raise ValueError(f'encoding {enc}')
