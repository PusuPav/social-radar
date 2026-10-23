# Contributing

Thanks for helping! The most useful contributions are new sources, new alert channels, and better docs.

1. Fork and create a branch.
2. `pip install -e ".[dev]"`
3. Make your change with a test (see `tests/test_radar.py`; use `respx` to mock HTTP, never hit live APIs in tests).
4. `ruff check . && pytest -q`
5. Open a pull request describing what you changed and why.

## Ground rules for new sources

- Use official APIs, RSS feeds or search-engine APIs only. **No scraping of sites whose terms forbid it** (this includes LinkedIn), and no logging in with a user's personal password.
- Read credentials from `self.settings` (which comes from `${ENV}` values in the YAML), and return `False` from `enabled()` when they're missing.
- Respect rate limits and keep request volume modest.
- Fill `published` whenever the source provides a timestamp, so the lookback window works.

## Reporting issues

Please include your Python version, the command you ran with `-v`, and a redacted copy of your watchlist.
