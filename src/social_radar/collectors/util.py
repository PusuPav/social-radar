from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_TAGS = re.compile(r"<[^>]+>")


def parse_time(value: str | None) -> datetime | None:
    """Parse ISO-8601 or RFC-822 timestamps into aware UTC datetimes."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def strip_html(text: str | None) -> str:
    return html.unescape(_TAGS.sub(" ", text or "")).strip()
