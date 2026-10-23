"""Hacker News via the free Algolia search API (no key needed)."""
from __future__ import annotations

from datetime import datetime, timezone

from ..config import Watch
from ..models import Mention
from .base import Collector


class HackerNewsCollector(Collector):
    name = "hackernews"
    API = "https://hn.algolia.com/api/v1/search_by_date"

    def search(self, query: str, watch: Watch, since: datetime) -> list[Mention]:
        params = {
            "query": f'"{query}"',
            "tags": "(story,comment)",
            "numericFilters": f"created_at_i>{int(since.timestamp())}",
            "hitsPerPage": self.settings.get("limit", 50),
        }
        r = self.client.get(self.API, params=params)
        r.raise_for_status()
        out = []
        for h in r.json().get("hits", []):
            oid = h["objectID"]
            out.append(Mention(
                source=self.name,
                native_id=oid,
                url=f"https://news.ycombinator.com/item?id={oid}",
                title=h.get("title") or h.get("story_title") or "",
                text=h.get("comment_text") or h.get("story_text") or h.get("url") or "",
                author=h.get("author", ""),
                published=datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc),
            ))
        return out
