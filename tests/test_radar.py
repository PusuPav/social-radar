from datetime import timedelta
from types import SimpleNamespace

import httpx
import respx

from social_radar.classifier import Classifier
from social_radar.collectors.hackernews import HackerNewsCollector
from social_radar.collectors.rss import RSSCollector, _unwrap_google
from social_radar.config import Config, Watch, load_config
from social_radar.models import Mention, utcnow
from social_radar.radar import run
from social_radar.store import Store


def make_cfg(tmp_path, **watch_kw):
    w = Watch(name="Acme", terms=["Acme Corp"], exclude=["acme anvil"], sources=["fake"], **watch_kw)
    return Config(watches=[w], sources={}, notify={"mode": "digest"}, classifier={},
                  lookback_hours=24, db_path=str(tmp_path / "t.db"))


class FakeCollector:
    def __init__(self, mentions):
        self.mentions = mentions

    def collect(self, watch, since):
        return [Mention(**m.__dict__) for m in self.mentions]


class FakeNotifier:
    name = "fake"

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, title, body, mentions):
        if self.fail:
            raise RuntimeError("down")
        self.sent.append((title, body, mentions))


class FakeLLM:
    """Mimics anthropic.Anthropic().messages.create returning a tool_use block."""

    def __init__(self, scores):
        self.scores = scores
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        items = [{"id": i, "relevance": s, "sentiment": "positive", "summary": f"summary {i}"}
                 for i, s in enumerate(self.scores)]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"assessments": items})])


def test_watch_matching_whole_words_and_excludes():
    w = Watch(name="Meta", terms=["Meta"], exclude=["meta-analysis"], hashtags=["MetaAI"])
    assert w.matches("Meta launched a model") == ["Meta"]
    assert w.matches("rich metadata everywhere") == []
    assert w.matches("Meta in a meta-analysis") == []
    assert w.matches("loving #metaai today") == ["MetaAI"]


def test_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("HOOK", "https://hooks.example/x")
    p = tmp_path / "w.yaml"
    p.write_text("watches:\n  - name: A\n    terms: [a]\nnotify:\n  slack:\n    webhook_url: ${HOOK}\n"
                 "  other: ${MISSING:-fallback}\n")
    cfg = load_config(p)
    assert cfg.notify["slack"]["webhook_url"] == "https://hooks.example/x"
    assert cfg.notify["other"] == "fallback"


def test_pipeline_dedupes_and_filters(tmp_path):
    cfg = make_cfg(tmp_path)
    mentions = [
        Mention(source="fake", url="https://x/1", text="Acme Corp raised a round", native_id="1"),
        Mention(source="fake", url="https://x/2", text="nothing relevant here", native_id="2"),
        Mention(source="fake", url="https://x/3", text="Acme Corp acme anvil sale", native_id="3"),
    ]
    store, notifier = Store(cfg.db_path), FakeNotifier()
    stats = run(cfg, store=store, classifier=Classifier(client=None, settings={"enabled": False}),
                collectors={"fake": FakeCollector(mentions)}, notifiers=[notifier])
    assert (stats.new, stats.alerted) == (1, 1)
    assert "Acme" in notifier.sent[0][0]

    # Second run: same items are not alerted again.
    stats = run(cfg, store=store, classifier=Classifier(client=None, settings={"enabled": False}),
                collectors={"fake": FakeCollector(mentions)}, notifiers=[notifier])
    assert stats.alerted == 0 and len(notifier.sent) == 1


def test_claude_triage_drops_low_relevance(tmp_path):
    cfg = make_cfg(tmp_path, min_relevance=0.6)
    mentions = [Mention(source="fake", url=f"https://x/{i}", text="Acme Corp news", native_id=str(i))
                for i in range(2)]
    notifier = FakeNotifier()
    stats = run(cfg, store=Store(cfg.db_path), classifier=Classifier(client=FakeLLM([0.9, 0.1])),
                collectors={"fake": FakeCollector(mentions)}, notifiers=[notifier])
    assert stats.relevant == 1
    assert notifier.sent[0][2][0].summary == "summary 0"


def test_failed_delivery_is_retried_next_run(tmp_path):
    cfg = make_cfg(tmp_path)
    mentions = [Mention(source="fake", url="https://x/1", text="Acme Corp", native_id="1")]
    store = Store(cfg.db_path)
    off = Classifier(client=None, settings={"enabled": False})
    run(cfg, store=store, classifier=off, collectors={"fake": FakeCollector(mentions)},
        notifiers=[FakeNotifier(fail=True)])
    ok = FakeNotifier()
    stats = run(cfg, store=store, classifier=off, collectors={"fake": FakeCollector(mentions)}, notifiers=[ok])
    assert stats.alerted == 1 and ok.sent


@respx.mock
def test_hackernews_collector_parses_hits():
    respx.get("https://hn.algolia.com/api/v1/search_by_date").mock(return_value=httpx.Response(200, json={
        "hits": [{"objectID": "42", "title": "Acme Corp launches", "author": "pg",
                  "comment_text": "It&#x27;s <p>great</p>",
                  "created_at_i": int(utcnow().timestamp())}]}))
    w = Watch(name="Acme", terms=["Acme Corp"])
    out = HackerNewsCollector().collect(w, utcnow() - timedelta(hours=1))
    assert out[0].url == "https://news.ycombinator.com/item?id=42" and out[0].author == "pg"
    assert out[0].text == "It's  great"


@respx.mock
def test_rss_collector_and_google_unwrap():
    feed = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <id>tag:1</id><title>Acme Corp on LinkedIn</title>
      <link href="https://www.google.com/url?rct=j&amp;url=https://www.linkedin.com/posts/abc&amp;ct=ga"/>
      <updated>2099-01-01T00:00:00Z</updated><content>post text</content></entry></feed>"""
    respx.get("https://alerts.example/feed").mock(return_value=httpx.Response(200, text=feed))
    c = RSSCollector({"feeds": [{"url": "https://alerts.example/feed", "watch": "Acme", "label": "ga"}]})
    out = c.collect(Watch(name="Acme", terms=["x"]), utcnow() - timedelta(days=1))
    assert out[0].url == "https://www.linkedin.com/posts/abc"
    assert out[0].matched_terms == ["feed:ga"]
    assert _unwrap_google("https://example.com") == "https://example.com"
