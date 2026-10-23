"""Alert channels. Each one is a small class with send(title, body, mentions)."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from ..models import Mention

log = logging.getLogger(__name__)
EMOJI = {"positive": "🟢", "negative": "🔴", "mixed": "🟡", "neutral": "⚪"}


def format_mention(m: Mention) -> str:
    mood = EMOJI.get(m.sentiment or "", "")
    head = f"{mood} [{m.watch}] {m.source}" + (f" · @{m.author}" if m.author else "")
    score = f" · relevance {m.relevance:.2f}" if m.relevance is not None and m.relevance < 1 else ""
    return f"{head}{score}\n{m.summary or m.snippet(240)}\n{m.url}"


def format_digest(mentions: list[Mention]) -> str:
    return "\n\n".join(format_mention(m) for m in mentions)


class Notifier:
    name = ""

    def __init__(self, settings: dict, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=20)

    def enabled(self) -> bool:
        return True

    def send(self, title: str, body: str, mentions: list[Mention]) -> None:
        raise NotImplementedError


class Slack(Notifier):
    name = "slack"

    def enabled(self):
        return bool(self.settings.get("webhook_url"))

    def send(self, title, body, mentions):
        self.client.post(self.settings["webhook_url"], json={"text": f"*{title}*\n{body}"}).raise_for_status()


class Discord(Notifier):
    name = "discord"

    def enabled(self):
        return bool(self.settings.get("webhook_url"))

    def send(self, title, body, mentions):
        text = f"**{title}**\n{body}"
        for i in range(0, len(text), 1900):  # Discord caps messages at 2000 chars
            self.client.post(self.settings["webhook_url"], json={"content": text[i:i + 1900]}).raise_for_status()


class Telegram(Notifier):
    name = "telegram"

    def enabled(self):
        return bool(self.settings.get("bot_token") and self.settings.get("chat_id"))

    def send(self, title, body, mentions):
        url = f"https://api.telegram.org/bot{self.settings['bot_token']}/sendMessage"
        text = f"{title}\n\n{body}"
        for i in range(0, len(text), 4000):
            self.client.post(url, json={"chat_id": self.settings["chat_id"], "text": text[i:i + 4000],
                                        "disable_web_page_preview": True}).raise_for_status()


class Ntfy(Notifier):
    """Free phone push notifications via ntfy.sh (or your self-hosted server)."""
    name = "ntfy"

    def enabled(self):
        return bool(self.settings.get("topic"))

    def send(self, title, body, mentions):
        server = self.settings.get("server", "https://ntfy.sh").rstrip("/")
        headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Tags": "satellite"}
        if len(mentions) == 1:
            headers["Click"] = mentions[0].url
        if self.settings.get("token"):
            headers["Authorization"] = f"Bearer {self.settings['token']}"
        url = f"{server}/{self.settings['topic']}"
        self.client.post(url, content=body.encode(), headers=headers).raise_for_status()


class Email(Notifier):
    name = "email"

    def enabled(self):
        return all(self.settings.get(k) for k in ("smtp_host", "from", "to"))

    def send(self, title, body, mentions):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = title, self.settings["from"], self.settings["to"]
        msg.set_content(body)
        with smtplib.SMTP(self.settings["smtp_host"], int(self.settings.get("smtp_port", 587))) as s:
            s.starttls()
            if self.settings.get("username"):
                s.login(self.settings["username"], self.settings["password"])
            s.send_message(msg)


class Console(Notifier):
    name = "console"

    def send(self, title, body, mentions):
        print(f"\n=== {title} ===\n{body}\n")


REGISTRY = {n.name: n for n in [Slack, Discord, Telegram, Ntfy, Email, Console]}


def build_notifiers(notify_cfg: dict) -> list[Notifier]:
    out = []
    for name in notify_cfg.get("channels", ["console"]):
        cls = REGISTRY.get(name)
        if not cls:
            raise ValueError(f"Unknown notify channel: {name}")
        n = cls(notify_cfg.get(name, {}) or {})
        if n.enabled():
            out.append(n)
        else:
            log.warning("Channel %s is listed but not configured; skipping", name)
    return out
