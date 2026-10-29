import requests
import os
from PIL import ImageFont, features
from pathlib import Path
from dataclasses import dataclass

register = {}

def _download_font(url: str) -> Path:
    _cache_dir = Path(__file__).parent / '.fonts_cache'
    _cache_dir.mkdir(exist_ok=True)

    filename = url.split('/')[-1]
    file_path = _cache_dir / filename

    if file_path.exists():
        return file_path.absolute()

    try:
        response = requests.get(url)
        response.raise_for_status()

        with open(file_path, 'wb') as f:
            f.write(response.content)
        return file_path.absolute()
    except requests.RequestException as e:
        raise Exception(f"Failed to download font from {url}: {str(e)}")

@dataclass
class TTFFont:
    path: str | Path
    size: int
    license: str = 'unknown'
    credit: str = ''
    spacing: int = 0
    layout_engine: str = 'basic'
    # Stem width in px, the glare cap and the legibility floor follow it. 0: measured (stem).
    stroke: int = 0
    # Fonts for the characters it lacks, in order: runs of them on its baseline.
    fallback: tuple['TTFFont', ...] = ()

    def __post_init__(self):
        if str(self.path).startswith('https://'):
            self.path = _download_font(self.path)
        else:
            self.path = Path(self.path)
        self.filename = self.path.name
        self._font = None

        if not self.filename in register:
            register[self.filename] = self

    @property
    def font(self):
        if self._font is None:
            mapping = {
                'basic': ImageFont.Layout.BASIC,
                'raqm': ImageFont.Layout.RAQM
            }
            self._font = ImageFont.truetype(str(self.path), self.size, layout_engine=mapping[self.layout_engine])
        return self._font

    @property
    def stem(self) -> int:
        '''The stroke, or the widest run of lit px across the middle of its 'l'.'''
        if self.stroke:
            return self.stroke
        if (key := (self.filename, self.size)) not in _stems:
            m = self.font.getmask('l')
            w, h = m.size
            row = [m.getpixel((x, h // 2)) > 127 for x in range(w)] if w and h else []
            runs = ''.join('1' if p else ' ' for p in row).split()
            _stems[key] = max((len(r) for r in runs), default=1)
        return _stems[key]

    def covers(self, ch: str) -> bool:
        '''It has a glyph for ch: one that doesn't draw as its missing glyph.'''
        if ch.isspace():
            return True
        if (key := (self.filename, self.size, ch)) not in _covers:
            _covers[key] = bytes(self.font.getmask(ch)) != bytes(self.font.getmask(_missing))
        return _covers[key]

    def runs(self, value: str) -> list[tuple['TTFFont', str]]:
        '''value cut where the font changes: each run in the first of it and its fallbacks that has the glyph.'''
        out = []
        for ch in value:
            f = next((f for f in (self, *self.fallback) if f.covers(ch)), self)
            if out and out[-1][0] is f:
                out[-1] = (f, out[-1][1] + ch)
            else:
                out.append((f, ch))
        return out

    def __hash__(self):
        return hash((self.path, self.size, self.license, self.credit, self.stroke))

    def __repr__(self) -> str:
        return f'TTFFont(path={self.path}, size={self.size})'

# A private-use code point: no font has it, it draws as the missing glyph.
_missing = '\U0010fffd'
_covers: dict[tuple, bool] = {}
_stems: dict[tuple, int] = {}

# Used when a TextStyle has no font. Set by the app, e.g. `fonts.default = my_font`.
default: TTFFont | None = None
