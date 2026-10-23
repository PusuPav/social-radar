"""Command line entry point: `social-radar run`, `test-notify`, `history`, `validate`."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from . import __version__
from .config import load_config
from .notifiers import build_notifiers
from .radar import run
from .store import Store


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader so there's no extra dependency. Real env vars win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="social-radar", description="Get alerted when a topic, person or company is mentioned online.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-c", "--config", default="watchlist.yaml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="collect, triage and send alerts")
    r.add_argument("--dry-run", action="store_true", help="print alerts instead of sending; don't save state")
    r.add_argument("--every", type=int, metavar="MINUTES", help="keep running, repeating every N minutes")
    sub.add_parser("test-notify", help="send a test message to every configured channel")
    h = sub.add_parser("history", help="show recently alerted mentions")
    h.add_argument("-n", type=int, default=20)
    sub.add_parser("validate", help="check the watchlist and show which sources are ready")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _load_dotenv()
    cfg = load_config(args.config)

    if args.cmd == "run":
        while True:
            s = run(cfg, dry_run=args.dry_run)
            logging.getLogger("social_radar").info(
                "collected=%d new=%d relevant=%d alerted=%d", s.collected, s.new, s.relevant, s.alerted)
            if not args.every:
                return 0
            time.sleep(args.every * 60)

    if args.cmd == "test-notify":
        ns = build_notifiers(cfg.notify)
        for n in ns:
            n.send("social-radar test", "If you can read this, alerts will reach you here.", [])
            print(f"sent via {n.name}")
        return 0 if ns else 1

    if args.cmd == "history":
        for row in Store(cfg.db_path).recent(args.n):
            print(" | ".join("" if v is None else str(v) for v in row))
        return 0

    if args.cmd == "validate":
        from .classifier import Classifier
        from .collectors import REGISTRY
        print(f"{len(cfg.watches)} watch(es): " + ", ".join(w.name for w in cfg.watches))
        for name, cls in REGISTRY.items():
            ready = cls(cfg.sources.get(name, {}) or {}).enabled()
            print(f"  {'✓' if ready else '·'} {name}{'' if ready else '  (not configured)'}")
        print(f"  {'✓' if Classifier(cfg.classifier).active else '·'} Claude triage")
        print("channels: " + (", ".join(n.name for n in build_notifiers(cfg.notify)) or "none"))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
