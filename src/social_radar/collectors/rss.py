"""Any RSS/Atom feed: Google Alerts, Talkwalker Alerts, news sites, blogs, podcasts.

Tip for LinkedIn: create a Google Alert for  site:linkedin.com "Your Company"
and choose "Deliver to: RSS feed". Paste the feed URL here.
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, urlparse

import feedparser
import httpx

from ..config import Watch
from ..models import Mention
from .base import Collector, log
from .util import parse_time, strip_html


class RSSCollector(Collector):
    name = "rss"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._cache: list[tuple[dict, Mention]] | None = None

    def _feeds(self) -> list[dict]:
        feeds = [{"url": f} if isinstance(f, str) else f for f in self.settings.get("feeds") or []]
        return [f for f in feeds if f.get("url")]  # skip feeds whose ${VAR} is unset

    def enabled(self) -> bool:
        return super().enabled() and bool(self._feeds())

    def search(self, query, watch, since):  # pragma: no cover - feeds aren't queried per term
        return []

    def _entries(self) -> list[tuple[dict, Mention]]:
        if self._cache is not None:
            return self._cache
        self._cache = []
        for feed in self._feeds():
            try:
                r = self.client.get(feed["url"])
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("rss: %s failed: %s", feed["url"], e)
                continue
            for e in feedparser.parse(r.content).entries:
                link = _unwrap_google(e.get("link", ""))
                self._cache.append((feed, Mention(
                    source=feed.get("label", self.name), native_id=e.get("id", link), url=link,
                    title=strip_html(e.get("title")), text=strip_html(e.get("summary")),
                    author=e.get("author", ""),
                    published=parse_time(e.get("published") or e.get("updated")),
                )))
        return self._cache

    def collect(self, watch: Watch, since: datetime) -> list[Mention]:
        out = []
        for feed, m in self._entries():
            # A feed can be pinned to one watch with `watch: <name>`; otherwise it's shared.
            if feed.get("watch") not in (None, watch.name):
                continue
            if m.published and m.published < since:
                continue
            # Feeds pinned to a watch are already query-specific (e.g. a Google Alert),
            # so they skip the keyword check in the pipeline.
            pinned = ["feed:" + feed.get("label", "rss")] if feed.get("watch") == watch.name else []
            out.append(Mention(**{**m.__dict__, "matched_terms": pinned}))
        return out


def _unwrap_google(link: str) -> str:
    """Google Alerts wraps links in a redirect; return the real URL."""
    if "google.com/url" in link:
        target = parse_qs(urlparse(link).query).get("url")
        if target:
            return target[0]
    return link
