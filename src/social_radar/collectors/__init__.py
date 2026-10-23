from .base import Collector
from .bluesky import BlueskyCollector
from .hackernews import HackerNewsCollector
from .mastodon import MastodonCollector
from .reddit import RedditCollector
from .rss import RSSCollector
from .web import WebSearchCollector
from .x import XCollector

REGISTRY: dict[str, type[Collector]] = {
    c.name: c
    for c in [HackerNewsCollector, RedditCollector, BlueskyCollector, MastodonCollector,
              RSSCollector, WebSearchCollector, XCollector]
}

__all__ = ["Collector", "REGISTRY"]
