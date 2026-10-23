"""The pipeline: collect → keyword match → de-duplicate → Claude triage → alert."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from .classifier import Classifier
from .collectors import REGISTRY as COLLECTORS
from .config import Config
from .models import Mention, utcnow
from .notifiers import build_notifiers, format_digest, format_mention
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class RunStats:
    collected: int = 0
    new: int = 0
    relevant: int = 0
    alerted: int = 0
    skipped_sources: list[str] = field(default_factory=list)


def run(cfg: Config, dry_run: bool = False, store: Store | None = None,
        classifier: Classifier | None = None, collectors: dict | None = None,
        notifiers: list | None = None) -> RunStats:
    stats = RunStats()
    since = utcnow() - timedelta(hours=cfg.lookback_hours)
    store = store or Store(cfg.db_path)
    classifier = classifier or Classifier(cfg.classifier)
    notifiers = notifiers if notifiers is not None else build_notifiers(cfg.notify)

    if collectors is None:
        collectors = {}
        for name, cls in COLLECTORS.items():
            c = cls(cfg.sources.get(name, {}) or {})
            if c.enabled():
                collectors[name] = c
            else:
                stats.skipped_sources.append(name)
    if stats.skipped_sources:
        log.info("Skipping unconfigured sources: %s", ", ".join(stats.skipped_sources))
    if not classifier.active:
        log.info("No ANTHROPIC_API_KEY set: alerting on keyword matches without AI triage")

    to_alert: list[Mention] = []
    for watch in cfg.watches:
        fresh: list[Mention] = []
        for src in watch.sources:
            if src not in collectors:
                continue
            for m in collectors[src].collect(watch, since):
                stats.collected += 1
                m.watch = watch.name
                if not m.matched_terms:
                    m.matched_terms = watch.matches(f"{m.title} {m.text} {m.url}")
                if m.matched_terms and store.is_new(m):
                    fresh.append(m)
        stats.new += len(fresh)
        if not fresh:
            continue
        classifier.assess(watch, fresh)
        for m in fresh:
            if (m.relevance or 0) >= watch.min_relevance:
                to_alert.append(m)
            elif not dry_run:
                store.save(m, notified=False)  # remember rejects so they aren't re-scored
    stats.relevant = len(to_alert)

    cap = int(cfg.notify.get("max_alerts_per_run", 25))
    to_alert.sort(key=lambda m: m.relevance or 0, reverse=True)
    batch, overflow = to_alert[:cap], to_alert[cap:]

    if dry_run:
        for m in batch:
            print(format_mention(m), end="\n\n")
        return stats

    if batch and notifiers:
        sent = _deliver(cfg, batch, notifiers)
        stats.alerted = len(batch) if sent else 0
        for m in batch:
            if sent:
                store.save(m, notified=True)
            # unsent mentions are left unsaved so the next run retries them
    for m in overflow:
        store.save(m, notified=False)
    if overflow:
        log.warning("%d more relevant mentions over max_alerts_per_run were not alerted", len(overflow))
    return stats


def _deliver(cfg: Config, batch: list[Mention], notifiers: list) -> bool:
    mode = cfg.notify.get("mode", "digest")
    ok = False
    for n in notifiers:
        try:
            if mode == "instant":
                for m in batch:
                    n.send(f"New mention: {m.watch}", format_mention(m), [m])
            else:
                watches = sorted({m.watch for m in batch})
                n.send(f"social-radar: {len(batch)} new mention(s) · {', '.join(watches)}",
                       format_digest(batch), batch)
            ok = True
        except Exception as e:  # noqa: BLE001 - one broken channel must not block the others
            log.error("Notifier %s failed: %s", n.name, e)
    return ok
