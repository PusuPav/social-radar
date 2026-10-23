"""Mastodon. Full-text search needs an access token on most instances; hashtag
timelines work without one. Set `hashtags:` on a watch for token-free coverage."""
from __future__ import annotations

from datetime import datetime

import httpx

from ..config import Watch
from ..models import Mention
from .base import Collector, log
from .util import parse_time, strip_html


class MastodonCollector(Collector):
    name = "mastodon"

    @property
    def instance(self) -> str:
        return self.settings.get("instance", "https://mastodon.social").rstrip("/")

    def _headers(self) -> dict:
        tok = self.settings.get("access_token")
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def _to_mention(self, s: dict) -> Mention:
        return Mention(
            source=self.name, native_id=s["uri"], url=s.get("url") or s["uri"],
            text=strip_html(s.get("content")), author=s["account"]["acct"],
            published=parse_time(s.get("created_at")),
        )

    def search(self, query: str, watch: Watch, since: datetime) -> list[Mention]:
        if not self.settings.get("access_token"):
            return []  # text search needs auth; hashtags handled in collect()
        r = self.client.get(f"{self.instance}/api/v2/search", headers=self._headers(),
                            params={"q": query, "type": "statuses", "limit": 40})
        r.raise_for_status()
        return [self._to_mention(s) for s in r.json().get("statuses", [])]

    def collect(self, watch: Watch, since: datetime) -> list[Mention]:
        found = {m.native_id: m for m in super().collect(watch, since)}
        for tag in watch.hashtags:
            try:
                r = self.client.get(f"{self.instance}/api/v1/timelines/tag/{tag.lstrip('#')}",
                                    headers=self._headers(), params={"limit": 40})
            except httpx.HTTPError as e:
                log.warning("mastodon: #%s failed: %s", tag, e)
                continue
            if r.is_success:
                for s in r.json():
                    m = self._to_mention(s)
                    if not m.published or m.published >= since:
                        found.setdefault(m.native_id, m)
        return list(found.values())
