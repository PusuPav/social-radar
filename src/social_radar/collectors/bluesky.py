"""Bluesky post search via the AT Protocol. Searching requires a logged-in session:
create an app password at bsky.app → Settings → App passwords."""
from __future__ import annotations

from datetime import datetime

from ..config import Watch
from ..models import Mention
from .base import Collector
from .util import parse_time


class BlueskyCollector(Collector):
    name = "bluesky"
    PDS = "https://bsky.social/xrpc"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._jwt: str | None = None

    def enabled(self) -> bool:
        return super().enabled() and bool(self.settings.get("handle") and self.settings.get("app_password"))

    def _login(self) -> None:
        if self._jwt:
            return
        r = self.client.post(f"{self.PDS}/com.atproto.server.createSession", json={
            "identifier": self.settings["handle"], "password": self.settings["app_password"]})
        r.raise_for_status()
        self._jwt = r.json()["accessJwt"]

    def search(self, query: str, watch: Watch, since: datetime) -> list[Mention]:
        self._login()
        r = self.client.get(
            f"{self.PDS}/app.bsky.feed.searchPosts",
            params={"q": f'"{query}"', "sort": "latest", "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "limit": min(int(self.settings.get("limit", 50)), 100)},
            headers={"Authorization": f"Bearer {self._jwt}"},
        )
        r.raise_for_status()
        out = []
        for p in r.json().get("posts", []):
            handle = p["author"]["handle"]
            rkey = p["uri"].rsplit("/", 1)[-1]
            out.append(Mention(
                source=self.name,
                native_id=p["uri"],
                url=f"https://bsky.app/profile/{handle}/post/{rkey}",
                text=p.get("record", {}).get("text", ""),
                author=handle,
                published=parse_time(p.get("record", {}).get("createdAt") or p.get("indexedAt")),
            ))
        return out
