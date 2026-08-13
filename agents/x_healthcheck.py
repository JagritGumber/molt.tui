#!/usr/bin/env python3
"""
Healthcheck and self-healing for unattended X automation.

What it does:
- clears stale global locks when pid is dead or lock is too old
- requeues tasks stuck in `running` when no live lock owns them
- optionally nudges the dispatcher to drain existing queued work
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from x_runtime import HOME_DIR, clear_stale_lock, is_pid_alive, read_json, read_lock, write_json

QUEUE_FILE = HOME_DIR / "x-automation-queue.json"
HEALTH_LOG = HOME_DIR / "x-automation-health-log.json"
STALE_LOCK_SECONDS = 4 * 60 * 60
STALE_RUNNING_SECONDS = 3 * 60 * 60


def log_event(action: str, detail: str, status: str = "ok"):
    logs = read_json(HEALTH_LOG, [])
    logs.append(
        {
            "timestamp": int(time.time()),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "status": status,
            "detail": detail[:500],
        }
    )
    logs = logs[-500:]
    write_json(HEALTH_LOG, logs)
    print(f"[{status}] {action}: {detail}")


def load_queue() -> list[dict]:
    return read_json(QUEUE_FILE, [])


def save_queue(queue: list[dict]):
    write_json(QUEUE_FILE, queue)


def heal_queue(dry_run: bool = False) -> int:
    queue = load_queue()
    lock = read_lock() or {}
    live_task_id = lock.get("task_id") if is_pid_alive(int(lock.get("pid", 0) or 0)) else None
    now = int(time.time())
    healed = 0
    changed = False
    for item in queue:
        if item.get("status") != "running":
            continue
        started_at = int(item.get("started_at", item.get("created_at", 0)) or 0)
        age = max(0, now - started_at) if started_at else STALE_RUNNING_SECONDS + 1
        if item.get("id") == live_task_id:
            continue
        if age >= STALE_RUNNING_SECONDS or not live_task_id:
            item["status"] = "queued"
            item["note"] = f"requeued by healthcheck after {age}s"
            item.pop("started_at", None)
            healed += 1
            changed = True
    if changed:
        if not dry_run:
            save_queue(queue)
    return healed


def maybe_drain_queue(dry_run: bool = False):
    queue = load_queue()
    queued = [item for item in queue if item.get("status") == "queued"]
    if not queued:
        return
    lock = read_lock() or {}
    if is_pid_alive(int(lock.get("pid", 0) or 0)):
        log_event("drain", "queue exists but lock is currently live", "skip")
        return
    oldest = queued[0]
    log_event("drain", f"nudging dispatcher for queued task {oldest.get('id')} ({oldest.get('task_type')})")
    if dry_run:
        return
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "x_queue_dispatcher.py"), "--drain-existing"],
        cwd=str(Path(__file__).resolve().parent.parent),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-drain", action="store_true", help="heal state but do not trigger dispatcher")
    args = ap.parse_args()

    if args.dry_run:
        lock = read_lock() or {}
        pid = int(lock.get("pid", 0) or 0)
        age = max(0, int(time.time()) - int(lock.get("heartbeat_at") or lock.get("timestamp") or 0)) if lock else 0
        if lock and (age > STALE_LOCK_SECONDS or not is_pid_alive(pid)):
            cleared, reason = False, f"would-clear-stale-lock age={age}s pid={pid}"
        else:
            cleared, reason = False, "dry-run no lock change"
    else:
        cleared, reason = clear_stale_lock(stale_seconds=STALE_LOCK_SECONDS)
    if cleared:
        log_event("lock", reason, "warn")
    else:
        log_event("lock", reason, "skip")

    healed = heal_queue(dry_run=args.dry_run)
    if healed:
        status = "warn" if not args.dry_run else "skip"
        verb = "requeued" if not args.dry_run else "would requeue"
        log_event("queue", f"{verb} {healed} stale running task(s)", status)
    else:
        log_event("queue", "no stale running tasks detected", "skip")

    if args.no_drain:
        log_event("drain", "skipped by --no-drain", "skip")
    else:
        maybe_drain_queue(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
