"""Base class every collector implements. Add a network by subclassing Collector."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from ..config import Watch
from ..models import Mention

log = logging.getLogger(__name__)
USER_AGENT = "social-radar/0.1 (+https://github.com/PusuPav/social-radar)"


class Collector(ABC):
    #: name used in the watchlist `sources:` list
    name: str = ""

    def __init__(self, settings: dict | None = None, client: httpx.Client | None = None):
        self.settings = settings or {}
        self.client = client or httpx.Client(
            timeout=20, headers={"User-Agent": self.settings.get("user_agent", USER_AGENT)},
            follow_redirects=True,
        )

    def enabled(self) -> bool:
        """Return False when required credentials are missing, so the run skips it."""
        return self.settings.get("enabled", True)

    @abstractmethod
    def search(self, query: str, watch: Watch, since: datetime) -> list[Mention]:
        """Return raw candidate mentions for one search term."""

    def collect(self, watch: Watch, since: datetime) -> list[Mention]:
        found: dict[str, Mention] = {}
        for term in watch.terms:
            try:
                for m in self.search(term, watch, since):
                    if m.published and m.published < since:
                        continue
                    found.setdefault(m.native_id or m.url, m)
            except httpx.HTTPError as e:
                log.warning("%s: search for %r failed: %s", self.name, term, e)
        return list(found.values())
