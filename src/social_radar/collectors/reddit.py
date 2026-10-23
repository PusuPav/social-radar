"""Reddit search. Uses app-only OAuth when client id/secret are set (recommended),
otherwise falls back to the public JSON endpoint, which Reddit may rate-limit."""
from __future__ import annotations

from datetime import datetime, timezone

from ..config import Watch
from ..models import Mention
from .base import Collector


class RedditCollector(Collector):
    name = "reddit"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._token: str | None = None

    def _base(self) -> str:
        cid, secret = self.settings.get("client_id"), self.settings.get("client_secret")
        if not (cid and secret):
            return "https://www.reddit.com"
        if not self._token:
            r = self.client.post(
                "https://www.reddit.com/api/v1/access_token",
                data={"grant_type": "client_credentials"}, auth=(cid, secret),
            )
            r.raise_for_status()
            self._token = r.json()["access_token"]
            self.client.headers["Authorization"] = f"Bearer {self._token}"
        return "https://oauth.reddit.com"

    def search(self, query: str, watch: Watch, since: datetime) -> list[Mention]:
        base = self._base()
        subs = "+".join(watch.subreddits)
        path = f"/r/{subs}/search" if subs else "/search"
        params = {"q": f'"{query}"', "sort": "new", "t": "week",
                  "limit": self.settings.get("limit", 50), "restrict_sr": bool(subs)}
        if base.startswith("https://www."):
            path += ".json"
        r = self.client.get(base + path, params=params)
        r.raise_for_status()
        out = []
        for child in r.json().get("data", {}).get("children", []):
            d = child["data"]
            out.append(Mention(
                source=self.name,
                native_id=d["name"],
                url="https://www.reddit.com" + d.get("permalink", ""),
                title=f"r/{d.get('subreddit', '')}: {d.get('title', '')}",
                text=d.get("selftext", ""),
                author=d.get("author", ""),
                published=datetime.fromtimestamp(d["created_utc"], tz=timezone.utc),
            ))
        return out
