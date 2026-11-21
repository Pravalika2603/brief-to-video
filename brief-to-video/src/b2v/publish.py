"""Publishing boundary. Ships with a dry-run publisher; add real platforms behind the same interface."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List


class Publisher(ABC):
    @abstractmethod
    def schedule(self, video: str, caption: str, hashtags: List[str], when: datetime) -> str:
        """Queue a post; return an identifier for the scheduled item."""


class DryRunPublisher(Publisher):
    """Writes the would-be API payload to disk so the whole flow is testable offline."""

    def __init__(self, queue_dir: Path):
        self.queue_dir = Path(queue_dir)

    def schedule(self, video: str, caption: str, hashtags: List[str], when: datetime) -> str:
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        item = self.queue_dir / f"{Path(video).stem}.json"
        item.write_text(json.dumps({
            "video": video, "caption": caption, "hashtags": hashtags,
            "scheduled_for": when.isoformat(), "status": "dry_run",
        }, indent=2))
        return str(item)


class InstagramPublisher(Publisher):
    """Extension point. Implement with the official Graph API and an OAuth 2.0 access token
    (token from env/secret manager, never committed). Left unimplemented on purpose: this
    demo does not post to real accounts."""

    def schedule(self, video, caption, hashtags, when):  # pragma: no cover
        raise NotImplementedError("Implement against the platform's official API.")


def next_slot(now: datetime | None = None, hours_ahead: int = 2) -> datetime:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(hours=hours_ahead)).replace(minute=0, second=0, microsecond=0)
