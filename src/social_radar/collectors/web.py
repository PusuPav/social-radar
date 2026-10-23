"""Web search collector (Brave Search API) — the compliant way to catch public
LinkedIn posts and articles, or anything else search engines index.

LinkedIn has no public API for keyword monitoring and its terms forbid scraping,
so social-radar never logs in to or scrapes LinkedIn. It asks a search engine for
recently indexed public pages under the sites you list instead. Coverage is
therefore partial and delayed by indexing, but it's safe for your account.
"""
from __future__ import annotations

from datetime import datetime

from ..config import Watch
from ..models import Mention
from .base import Collector
from .util import strip_html

DEFAULT_SITES = ["linkedin.com/posts", "linkedin.com/pulse"]


class WebSearchCollector(Collector):
    name = "web"
    API = "https://api.search.brave.com/res/v1/web/search"

    def enabled(self) -> bool:
        return super().enabled() and bool(self.settings.get("brave_api_key"))

    def search(self, query: str, watch: Watch, since: datetime) -> list[Mention]:
        sites = self.settings.get("sites", DEFAULT_SITES)
        site_q = " OR ".join(f"site:{s}" for s in sites)
        r = self.client.get(
            self.API,
            headers={"X-Subscription-Token": self.settings["brave_api_key"], "Accept": "application/json"},
            params={"q": f'"{query}" ({site_q})' if sites else f'"{query}"',
                    "freshness": self.settings.get("freshness", "pd"),  # pd=day, pw=week
                    "count": 20},
        )
        r.raise_for_status()
        out = []
        for res in r.json().get("web", {}).get("results", []):
            url = res["url"]
            out.append(Mention(
                source="linkedin" if "linkedin.com" in url else self.name,
                native_id=url, url=url,
                title=strip_html(res.get("title")),
                text=strip_html(" ".join([res.get("description", "")] + res.get("extra_snippets", []))),
                author=(res.get("profile") or {}).get("name", ""),
            ))
        return out
