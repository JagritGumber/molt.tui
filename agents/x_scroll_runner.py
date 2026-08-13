#!/usr/bin/env python3
"""
Single-run feed scrolling / engagement session using the existing zendriver X agent.

Purpose:
- open X with the existing x_browser stack
- run one bounded engagement session
- exit cleanly instead of looping forever

This is intended for scheduled background sessions so the account keeps
behaving like a real user browsing/interacting with the feed.
"""

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

from x_browser import ACTION_LOG, launch_browser, load_config, load_learnings, llm_reflect, scroll_and_engage

HOME_DIR = Path.home() / ".moltui"
SCROLL_RUNNER_LOG = HOME_DIR / "x-scroll-runner-log.json"
RANDOM_DELAY_MIN = 120
RANDOM_DELAY_MAX = 180


def _read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


def log_event(action: str, detail: str, status: str = "ok"):
    logs = _read_json(SCROLL_RUNNER_LOG, [])
    logs.append({
        "timestamp": int(time.time()),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "status": status,
        "detail": detail[:500],
    })
    logs = logs[-500:]
    _write_json(SCROLL_RUNNER_LOG, logs)
    print(f"[{status}] {action}: {detail}")


async def run_scroll_session() -> int:
    delay = random.randint(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
    log_event("delay", f"waiting {delay}s before feed session")
    await asyncio.sleep(delay)

    config = load_config()
    learnings = load_learnings()
    has_llm = True

    # Keep sessions human-like but randomly sized.
    # User explicitly wants large randomness in browsing duration.
    override = os.environ.get("X_SCROLL_SESSION_MINUTES")
    if override:
        session_minutes = int(override)
    else:
        session_minutes = random.randint(45, 75)
    config["session_duration_min"] = session_minutes
    config["session_duration_max"] = session_minutes
    config["max_likes_per_session"] = min(config.get("max_likes_per_session", 20), 10)
    # Ratio-sensitive mode: keep follows off by default so following doesn't outrun followers.
    config["max_follows_per_session"] = 0
    config["max_replies_per_session"] = min(config.get("max_replies_per_session", 3), 1)
    config["target_visits_per_session"] = min(config.get("target_visits_per_session", 3), 3)
    log_event("session", f"planned random session length: {session_minutes} min")

    browser = await launch_browser(headless=False)
    try:
        existing_log = _read_json(ACTION_LOG, [])
        session_log_start = len(existing_log)

        likes, follows, replies = await scroll_and_engage(browser, config, learnings)
        log_event("session", f"feed session ended: {likes} likes, {follows} follows, {replies} replies")

        try:
            full_log = _read_json(ACTION_LOG, [])
            session_entries = full_log[session_log_start:]
            if session_entries and has_llm:
                learnings = await llm_reflect(session_entries, learnings)
                log_event("learn", f"reflected on {len(session_entries)} actions")
        except Exception as e:
            log_event("learn", f"reflection failed: {str(e)[:120]}", "fail")

        return 0
    finally:
        # Keep the fragile Windows debug browser alive across runs.
        if "--windows" not in sys.argv:
            await browser.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_scroll_session()))
