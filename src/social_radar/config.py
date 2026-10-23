"""Loads the YAML watchlist and expands ${ENV_VARS} so secrets stay out of git."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ALL_SOURCES = ["hackernews", "reddit", "bluesky", "mastodon", "rss", "web", "x"]
_ENV = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


@dataclass
class Watch:
    name: str
    terms: list[str]
    type: str = "topic"  # topic | person | company
    context: str = ""  # tells the classifier what you actually mean
    exclude: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=lambda: list(ALL_SOURCES))
    min_relevance: float = 0.6
    subreddits: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)

    def matches(self, text: str) -> list[str]:
        """Return the terms found in text, or [] if none / an exclude term hits."""
        low = text.lower()
        if any(x.lower() in low for x in self.exclude):
            return []
        hits = [t for t in self.terms if _contains(low, t.lower())]
        hits += [h for h in self.hashtags if _contains(low, "#" + h.lstrip("#").lower())]
        return hits


def _contains(haystack: str, needle: str) -> bool:
    # Whole-word match so "Meta" doesn't match "metadata".
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack) is not None


@dataclass
class Config:
    watches: list[Watch]
    sources: dict[str, dict]
    notify: dict[str, Any]
    classifier: dict[str, Any]
    lookback_hours: int = 24
    db_path: str = "radar.db"


def load_config(path: str | Path) -> Config:
    raw = _expand(yaml.safe_load(Path(path).read_text()) or {})
    watches = []
    for w in raw.get("watches", []):
        if not w.get("name") or not w.get("terms"):
            raise ValueError(f"Each watch needs a name and terms: {w}")
        unknown = set(w.get("sources", [])) - set(ALL_SOURCES)
        if unknown:
            raise ValueError(f"Watch '{w['name']}' has unknown sources: {sorted(unknown)}")
        watches.append(Watch(**w))
    if not watches:
        raise ValueError("No watches defined in config")
    return Config(
        watches=watches,
        sources=raw.get("sources", {}) or {},
        notify=raw.get("notify", {}) or {},
        classifier=raw.get("classifier", {}) or {},
        lookback_hours=int(raw.get("lookback_hours", 24)),
        db_path=raw.get("db_path", "radar.db"),
    )
