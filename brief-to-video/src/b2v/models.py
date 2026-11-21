from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


def seconds_for(text: str) -> float:
    """Reading-pace duration for one scene (about 2.5 words/second, min 2s)."""
    return max(2.0, round(len(text.split()) / 2.5, 1))


@dataclass
class Brief:
    brief_id: str
    brand: str
    product: str
    audience: str
    tone: str
    facts: List[str]
    cta: str

    @classmethod
    def from_dict(cls, d: dict) -> "Brief":
        return cls(**d)


@dataclass
class Script:
    hook: str
    body: List[str]
    cta: str
    caption: str
    hashtags: List[str] = field(default_factory=list)

    def scene_texts(self) -> List[str]:
        return [self.hook, *self.body, self.cta]

    def durations(self) -> List[float]:
        return [seconds_for(t) for t in self.scene_texts()]

    def total_seconds(self) -> float:
        return round(sum(self.durations()), 1)


@dataclass
class PostResult:
    brief_id: str
    approved: bool
    attempts: int
    cost_usd: float
    issues: List[str]
    video_path: Optional[str] = None
    scheduled_for: Optional[str] = None
