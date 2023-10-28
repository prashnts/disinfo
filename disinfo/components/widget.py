from dataclasses import dataclass
from typing import Optional

from .elements import Frame

@dataclass
class Widget:
    name: str
    frame: Optional[Frame] = None
    priority: int = 0
    active: bool = True
