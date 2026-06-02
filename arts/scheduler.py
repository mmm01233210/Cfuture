"""Simple scheduler — runs the pipeline on a fixed interval (default hourly).

Kept dependency-free on purpose. Each run is isolated: an exception in one run
is logged and the loop continues to the next interval.
"""
from __future__ import annotations

import time
from datetime import datetime

from .config import Config
from .pipeline import run_once
from .utils import get_logger

log = get_logger("scheduler")


def run_scheduler(cfg: Config | None = None) -> None:
    cfg = cfg or Config.load()
    interval_min = int(cfg.get("schedule.interval_minutes", 60))
    interval = max(60, interval_min * 60)
    log.info("scheduler started — running every %d minute(s)", interval_min)

    while True:
        started = datetime.now()
        log.info("=== scheduled run @ %s ===", started.isoformat(timespec="seconds"))
        try:
            result = run_once(cfg)
            log.info("run status: %s", result.get("status"))
        except KeyboardInterrupt:
            log.info("scheduler stopped by user")
            return
        except Exception as e:  # never let one failure kill the loop
            log.exception("run failed: %s", e)

        elapsed = (datetime.now() - started).total_seconds()
        sleep_for = max(5.0, interval - elapsed)
        log.info("sleeping %.0fs until next run", sleep_for)
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            log.info("scheduler stopped by user")
            return
