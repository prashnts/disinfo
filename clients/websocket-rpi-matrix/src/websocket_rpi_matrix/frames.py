'''Frames from /ws2, see disinfo/transport.py.'''
import io
import struct
import zlib

from PIL import Image

WS2_MAGIC = b'DIF2'
WS2_HEADER = struct.Struct('<4sIIHHHHB')
REGION = struct.Struct('<HHHHI')
RGBZ, PNG = 1, 2


class FrameAssembler:
    '''The current frame, from whole frames and the regions that changed.'''

    def __init__(self):
        self.frame: Image.Image | None = None
        self.seq = 0
        self.boxes: list[tuple[int, int, int, int]] | None = None     # what the last apply changed, None: all of it

    def apply(self, msg: bytes) -> bool:
        '''False when regions don't apply to the current frame: ask for a whole one.'''
        magic, seq, base_seq, x, y, w, h, enc = WS2_HEADER.unpack_from(msg)
        if magic != WS2_MAGIC:
            raise ValueError(f'not a /ws2 frame: {magic!r}')
        at = WS2_HEADER.size
        if not base_seq:
            self.frame, self.seq, self.boxes = decode(msg[at:], (w, h), enc), seq, None
            return True
        if self.frame is None or base_seq != self.seq:
            return False
        # All of them on a copy: the frame shown is never half done.
        frame = self.frame.copy()
        (count,) = struct.unpack_from('<H', msg, at)
        at += 2
        boxes = []
        for _ in range(count):
            x, y, w, h, n = REGION.unpack_from(msg, at)
            at += REGION.size
            frame.paste(decode(msg[at:at + n], (w, h), enc), (x, y))
            boxes.append((x, y, x + w, y + h))
            at += n
        self.frame, self.seq, self.boxes = frame, seq, boxes
        return True


def decode(payload: bytes, size: tuple[int, int], enc: int) -> Image.Image:
    if enc == RGBZ:
        return Image.frombytes('RGB', size, zlib.decompress(payload))
    if enc == PNG:
        return Image.open(io.BytesIO(payload)).convert('RGB')
    raise ValueError(f'encoding {enc}')
