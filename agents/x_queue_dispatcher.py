#!/usr/bin/env python3
"""
Queue-aware dispatcher for X automation tasks.

Usage:
  python3 agents/x_queue_dispatcher.py post
  python3 agents/x_queue_dispatcher.py scroll
  python3 agents/x_queue_dispatcher.py --drain-existing

Behavior:
- enqueue the requested task
- if another X automation task is active, exit after queueing
- otherwise acquire a global lock and execute queued work
- drain up to a small bounded number of queued tasks so delayed post slots can still run
"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

from x_runtime import acquire_global_lock, read_json, refresh_global_lock, release_global_lock, write_json

HOME_DIR = Path.home() / ".moltui"
QUEUE_FILE = HOME_DIR / "x-automation-queue.json"
DISPATCH_LOG = HOME_DIR / "x-automation-dispatch-log.json"
STALE_LOCK_SECONDS = 4 * 60 * 60
MAX_TASKS_PER_INVOCATION = 2
MAX_TOTAL_SECONDS = 2 * 60 * 60

VALID_TASKS = {"post", "scroll"}


def _read_json(path: Path, default):
    return read_json(path, default)


def _write_json(path: Path, value):
    write_json(path, value)


def log_event(action: str, detail: str, status: str = "ok"):
    logs = _read_json(DISPATCH_LOG, [])
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
    _write_json(DISPATCH_LOG, logs)
    print(f"[{status}] {action}: {detail}")


def load_queue() -> list[dict]:
    return _read_json(QUEUE_FILE, [])


def save_queue(queue: list[dict]):
    _write_json(QUEUE_FILE, queue)


def enqueue(task_type: str) -> dict:
    queue = load_queue()
    now = int(time.time())
    for item in reversed(queue[-10:]):
        if item.get("task_type") == task_type and item.get("status") == "queued" and now - int(item.get("created_at", 0)) < 30 * 60:
            log_event("queue", f"deduped recent queued {task_type} task")
            return item
    item = {
        "id": uuid.uuid4().hex[:12],
        "task_type": task_type,
        "status": "queued",
        "created_at": now,
    }
    queue.append(item)
    save_queue(queue)
    log_event("queue", f"enqueued {task_type} task {item['id']}")
    return item


def pop_oldest_queued() -> dict | None:
    queue = load_queue()
    for idx, item in enumerate(queue):
        if item.get("status") == "queued":
            item["status"] = "running"
            item["started_at"] = int(time.time())
            queue[idx] = item
            save_queue(queue)
            return item
    return None


def finalize_task(task_id: str, final_status: str, note: str = ""):
    queue = load_queue()
    for idx, item in enumerate(queue):
        if item.get("id") == task_id:
            item["status"] = final_status
            item["finished_at"] = int(time.time())
            if note:
                item["note"] = note[:500]
            queue[idx] = item
            break
    queue = [
        q
        for q in queue
        if q.get("status") in ("queued", "running") or int(time.time()) - int(q.get("finished_at", 0)) < 24 * 60 * 60
    ]
    save_queue(queue)


def run_task(task: dict) -> int:
    base = Path(__file__).resolve().parent
    if task["task_type"] == "post":
        cmd = [sys.executable, str(base / "x_just_in_time_post.py"), "--post-now", "--lock-already-held"]
    elif task["task_type"] == "scroll":
        cmd = [sys.executable, str(base / "x_scroll_runner.py"), "--windows", "--lock-already-held"]
    else:
        raise ValueError(f"unknown task type {task['task_type']}")

    log_event("run", f"starting {task['task_type']} {task['id']}")
    proc = subprocess.run(cmd, cwd=str(base.parent))
    log_event("run", f"finished {task['task_type']} {task['id']} with exit {proc.returncode}", "ok" if proc.returncode == 0 else "fail")
    return proc.returncode


def drain_queue() -> int:
    start = time.time()
    dispatch_id = f"dispatch-{uuid.uuid4().hex[:10]}"
    acquired, info = acquire_global_lock("dispatcher", dispatch_id, stale_seconds=STALE_LOCK_SECONDS)
    if not acquired:
        detail = f"another task already active; lock busy ({info.get('task_type', 'unknown')} {info.get('task_id', '')})"
        log_event("dispatch", detail, "skip")
        return 0

    log_event("lock", f"acquired for dispatcher {dispatch_id}")
    tasks_run = 0
    rc = 0
    try:
        while tasks_run < MAX_TASKS_PER_INVOCATION and (time.time() - start) < MAX_TOTAL_SECONDS:
            task = pop_oldest_queued()
            if not task:
                if tasks_run == 0:
                    log_event("dispatch", "nothing queued", "skip")
                break
            refresh_global_lock(task_type=task["task_type"], task_id=task["id"])
            task_rc = run_task(task)
            finalize_task(task["id"], "done" if task_rc == 0 else "failed", f"exit={task_rc}")
            rc = task_rc if task_rc != 0 else rc
            tasks_run += 1
            refresh_global_lock(task_type="dispatcher", task_id=dispatch_id)
            if task_rc != 0:
                break
        remaining = sum(1 for item in load_queue() if item.get("status") == "queued")
        if remaining:
            log_event("dispatch", f"left {remaining} queued task(s) for a later invocation", "warn")
        return rc
    finally:
        release_global_lock(dispatch_id)
        log_event("lock", "released")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 agents/x_queue_dispatcher.py [post|scroll|--drain-existing]")
        return 2
    if sys.argv[1] == "--drain-existing":
        return drain_queue()
    if sys.argv[1] not in VALID_TASKS:
        print("usage: python3 agents/x_queue_dispatcher.py [post|scroll|--drain-existing]")
        return 2

    enqueue(sys.argv[1])
    return drain_queue()


if __name__ == "__main__":
    raise SystemExit(main())
