#!/usr/bin/env python3
"""arabic-research-tiktok-agent — command line entry point.

Usage:
  python main.py run                 # one full pipeline run
  python main.py discover            # list candidate papers (no rendering)
  python main.py schedule            # run continuously (hourly by default)

Options:
  --config PATH      use an alternate config.yaml
  --fields a,b,c     override the active fields for this invocation
"""
from __future__ import annotations

import argparse
import sys

from arts.config import Config
from arts.utils import get_logger

log = get_logger("main")


def _load_config(args) -> Config:
    cfg = Config.load(args.config)
    if args.fields:
        cfg.data["fields"] = [f.strip() for f in args.fields.split(",") if f.strip()]
    return cfg


def cmd_run(args) -> int:
    from arts.pipeline import run_once

    result = run_once(_load_config(args))
    status = result.get("status")
    if status == "ok":
        log.info("Run complete: %s", result.get("run_dir"))
        return 0
    log.warning("Run finished with status=%s", status)
    return 0 if status in ("ok", "no_papers", "below_threshold") else 1


def cmd_discover(args) -> int:
    from arts.agents.paper_fetcher import discover
    from arts.agents.scorer import heuristic_score

    cfg = _load_config(args)
    papers = discover(cfg)
    ranked = sorted(papers, key=lambda p: heuristic_score(p).total, reverse=True)
    print(f"\nDiscovered {len(papers)} candidate paper(s):\n")
    for p in ranked:
        print(f"  [{heuristic_score(p).total:>3}/100] ({p.field}) {p.title[:70]}")
        print(f"           {p.source} · {p.year} · OA={p.open_access} · {p.url}")
    return 0


def cmd_schedule(args) -> int:
    from arts.scheduler import run_scheduler

    run_scheduler(_load_config(args))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="arabic-research-tiktok-agent")
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.add_argument("--fields", default=None, help="comma-separated field override")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("run", help="run the pipeline once")
    sub.add_parser("discover", help="list candidate papers without rendering")
    sub.add_parser("schedule", help="run continuously on a schedule")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    return {"run": cmd_run, "discover": cmd_discover, "schedule": cmd_schedule}[command](args)


if __name__ == "__main__":
    sys.exit(main())
