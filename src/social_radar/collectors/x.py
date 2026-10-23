"""X (Twitter) recent search, last 7 days. Requires a paid X API plan; set
X_BEARER_TOKEN to enable. Skipped automatically when no token is configured."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import Watch
from ..models import Mention
from .base import Collector
from .util import parse_time


class XCollector(Collector):
    name = "x"
    API = "https://api.x.com/2/tweets/search/recent"

    def enabled(self) -> bool:
        return super().enabled() and bool(self.settings.get("bearer_token"))

    def search(self, query: str, watch: Watch, since: datetime) -> list[Mention]:
        # The API rejects start_time older than 7 days or within the last 10s.
        floor = datetime.now(timezone.utc) - timedelta(days=6, hours=23)
        start = max(since, floor)
        r = self.client.get(
            self.API,
            headers={"Authorization": f"Bearer {self.settings['bearer_token']}"},
            params={"query": f'"{query}" -is:retweet', "max_results": 50,
                    "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "tweet.fields": "created_at,author_id", "expansions": "author_id",
                    "user.fields": "username"},
        )
        r.raise_for_status()
        body = r.json()
        users = {u["id"]: u["username"] for u in body.get("includes", {}).get("users", [])}
        out = []
        for t in body.get("data", []):
            user = users.get(t.get("author_id"), "i")
            out.append(Mention(
                source=self.name, native_id=t["id"],
                url=f"https://x.com/{user}/status/{t['id']}",
                text=t.get("text", ""), author=user,
                published=parse_time(t.get("created_at")),
            ))
        return out
