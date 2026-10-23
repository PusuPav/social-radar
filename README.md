# 📡 social-radar

**Get alerted when a topic, person or company is mentioned online, with Claude filtering out the noise.**

social-radar is a small, self-hosted social listening agent. You describe what to watch in one YAML file. On a schedule it searches Hacker News, Reddit, Bluesky, Mastodon, X, public LinkedIn posts and any RSS feed. Claude reads each hit, drops the false positives ("Apple" the fruit, a different "Jordan") and writes a one-line summary with sentiment. You get the result on your phone, in Slack, Discord, Telegram or email.

```
🟢 [Anthropic] reddit · @someuser · relevance 0.92
Developer compares Claude Code with other coding agents and prefers its planning mode.
https://www.reddit.com/r/LocalLLaMA/comments/...
```

It runs free on GitHub Actions, on any machine with Python, or in Docker. There is no server to maintain, and the only paid piece is optional.

---

## How it works

```
 watchlist.yaml
      │
      ▼
 ┌────────────┐   ┌───────────────┐   ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
 │ Collectors │──▶│ Keyword match │──▶│ De-duplicate│──▶│ Claude triage│──▶│   Notifiers  │
 │ HN, Reddit │   │ whole words,  │   │  (SQLite)   │   │ relevance,   │   │ ntfy, Slack, │
 │ Bluesky …  │   │ excludes      │   │             │   │ sentiment,   │   │ Discord, TG, │
 └────────────┘   └───────────────┘   └─────────────┘   │ summary      │   │ email        │
                                                         └──────────────┘   └──────────────┘
```

1. **Collect.** Each source is a small plugin that searches for every term in a watch, within `lookback_hours`.
2. **Match.** A hit must contain a term as a whole word and none of the `exclude` phrases.
3. **De-duplicate.** A local SQLite file remembers what you've seen, so each mention alerts once.
4. **Triage.** Claude scores each new mention against the watch's `context`. Anything below `min_relevance` is dropped. Without an API key this step is skipped and every keyword match is sent.
5. **Notify.** Send one digest per run, or one message per mention.

## Sources

| Source | What it covers | Needs |
|---|---|---|
| `hackernews` | Stories and comments | Nothing |
| `reddit` | Posts, optionally limited to `subreddits` | Nothing; [app keys](https://www.reddit.com/prefs/apps) recommended to avoid rate limits |
| `bluesky` | Posts | Handle + [app password](https://bsky.app/settings/app-passwords) |
| `mastodon` | Hashtags (no key); full-text search with a token | Optional access token |
| `web` | Public **LinkedIn** posts/articles, or any sites you list | [Brave Search API](https://brave.com/search/api/) key |
| `rss` | Google Alerts, news sites, blogs, hnrss.org | Feed URLs |
| `x` | Posts from the last 7 days | Paid X API bearer token |

Unconfigured sources are skipped automatically. Run `social-radar validate` to see what's ready.

### A note on LinkedIn

LinkedIn has no public API for keyword or mention monitoring, and its User Agreement prohibits scraping and automated access. **social-radar never logs in to or scrapes LinkedIn.** Instead it catches public LinkedIn posts and articles that search engines have indexed, in two compliant ways:

- **Google Alerts (free).** Create an alert for `site:linkedin.com "Your Company"`, set *Deliver to* to **RSS feed**, and add the feed URL under `sources.rss.feeds` with `watch:` set to that watch.
- **Brave Search API.** Configure the `web` source, which searches `linkedin.com/posts` and `linkedin.com/pulse` for each term.

Coverage is partial and lags by however long indexing takes. For mentions of *you* or *your* company page, LinkedIn's own notifications remain the most complete source.

## Quick start (local)

```bash
git clone https://github.com/<you>/social-radar && cd social-radar
python -m venv .venv && source .venv/bin/activate
pip install -e .

cp watchlist.example.yaml watchlist.yaml   # edit your watches
cp .env.example .env                       # add keys you have; blanks are skipped

social-radar validate          # shows which sources and channels are ready
social-radar run --dry-run     # prints what would be alerted; sends nothing, saves nothing
social-radar test-notify       # checks your alert channels
social-radar run               # the real thing
social-radar run --every 60    # keep running, once an hour
social-radar history           # what you've been alerted about
```

**Fastest phone alerts:** install the free [ntfy](https://ntfy.sh) app, subscribe to a hard-to-guess topic name, and set `NTFY_TOPIC` to the same name.

## Run it free on GitHub Actions

1. Fork this repo and edit `watchlist.yaml` (it contains no secrets; keys come from `${VARS}`).
2. Add your keys under **Settings → Secrets and variables → Actions** (`ANTHROPIC_API_KEY`, `NTFY_TOPIC`, …).
3. Under **Actions**, enable workflows. `.github/workflows/radar.yml` runs every hour, and you can also start it with **Run workflow**.

The SQLite state is kept between runs with the Actions cache. GitHub pauses scheduled workflows in repos with no activity for 60 days, so re-enable it if alerts stop. If your watchlist is private, keep your fork private (private repos have a monthly Actions minutes allowance).

## Docker

```bash
docker build -t social-radar .
docker run -d --name radar -v "$PWD:/data" social-radar          # hourly
docker run --rm -v "$PWD:/data" social-radar run --dry-run       # one-off
```

The mounted folder needs `watchlist.yaml` and `.env`. `radar.db` is written there too.

## Writing good watches

```yaml
- name: Jordan Lee            # label used in alerts
  type: person                # topic | person | company (helps Claude)
  terms: ["Jordan Lee", "@jordanlee"]
  context: "The fintech founder of Example Pay, based in Austin. Not the athlete."
  exclude: ["Jordan Lee basketball"]
  sources: [reddit, bluesky, rss, web]   # default: all
  subreddits: [fintech, startups]
  hashtags: [ExamplePay]
  min_relevance: 0.7          # raise for fewer, sharper alerts
```

- **`context` does the most work.** Say who or what you mean *and* what you don't mean.
- Use specific multi-word terms. A bare `"Claude"` matches every Claude on Earth; `"Claude Code"` doesn't.
- Start with `--dry-run`, then tune `min_relevance` and `exclude`.

## Cost

Everything except the classifier and the optional X and Brave APIs is free. Claude triage sends mentions in batches of 20 to a fast, inexpensive model (`claude-haiku-5-5` by default; change `classifier.model`). Only new, keyword-matched mentions are sent, so a few watches cost very little per month. Set `classifier.enabled: false` to turn it off.

## Extending

**Add a source.** Subclass `Collector` in `src/social_radar/collectors/`, implement `search(query, watch, since)` returning `Mention`s, and register it in `collectors/__init__.py` and `config.ALL_SOURCES`.

```python
class MySourceCollector(Collector):
    name = "mysource"

    def enabled(self):
        return bool(self.settings.get("api_key"))

    def search(self, query, watch, since):
        r = self.client.get("https://api.example.com/search", params={"q": query})
        r.raise_for_status()
        return [Mention(source=self.name, url=i["url"], text=i["text"], native_id=i["id"])
                for i in r.json()["items"]]
```

**Add a channel.** Subclass `Notifier` in `src/social_radar/notifiers/__init__.py`, implement `send(title, body, mentions)`, and add it to `REGISTRY`.

## Responsible use

This tool is for monitoring public conversation about topics, brands and public figures, like a press clipping service. Please don't use it to track or profile private individuals. Respect each platform's terms of service and API rate limits; the collectors only use official APIs, RSS and search-engine results.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
