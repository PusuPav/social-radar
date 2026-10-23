"""Core data types shared by collectors, the classifier and notifiers."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Mention:
    """A single post, comment or article that may mention a watched entity."""

    source: str  # e.g. "reddit", "bluesky"
    url: str
    text: str
    author: str = ""
    title: str = ""
    published: datetime | None = None
    native_id: str = ""  # id from the source platform, if any
    watch: str = ""  # name of the watch that matched
    matched_terms: list[str] = field(default_factory=list)

    # Filled in by the classifier
    relevance: float | None = None
    sentiment: str | None = None
    summary: str | None = None

    @property
    def uid(self) -> str:
        """Stable id used for de-duplication across runs."""
        key = f"{self.source}|{self.native_id or self.url}|{self.watch}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    def snippet(self, length: int = 280) -> str:
        body = " ".join((self.title + " " + self.text).split())
        return body if len(body) <= length else body[: length - 1] + "…"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
