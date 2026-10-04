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

    def __hash__(self):
        return hash((self.path, self.size, self.license, self.credit))

    def __repr__(self) -> str:
        return f'TTFFont(path={self.path}, size={self.size})'

# Used when a TextStyle has no font. Set by the app, e.g. `fonts.default = my_font`.
default: TTFFont | None = None
