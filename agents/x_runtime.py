#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from pathlib import Path

HOME_DIR = Path.home() / ".moltui"
LOCK_FILE = HOME_DIR / "x-automation.lock"
ACCOUNT_FILE = HOME_DIR / "x-account.json"

DEFAULT_ACCOUNT = {
    "handle": "wyvernotwts",
    "profile_url": "https://x.com/wyvernotwts",
}


def read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def get_account() -> dict:
    cfg = read_json(ACCOUNT_FILE, {})
    if not isinstance(cfg, dict):
        cfg = {}
    handle = (cfg.get("handle") or DEFAULT_ACCOUNT["handle"]).lstrip("@")
    return {
        "handle": handle,
        "profile_url": cfg.get("profile_url") or f"https://x.com/{handle}",
    }


def get_account_handle() -> str:
    return get_account()["handle"]


def is_pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def read_lock() -> dict | None:
    data = read_json(LOCK_FILE, None)
    return data if isinstance(data, dict) else None


def clear_lock() -> bool:
    try:
        LOCK_FILE.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def clear_stale_lock(stale_seconds: int = 4 * 60 * 60) -> tuple[bool, str]:
    if not LOCK_FILE.exists():
        return False, "no-lock"
    data = read_lock() or {}
    pid = int(data.get("pid", 0) or 0)
    ts = int(data.get("heartbeat_at") or data.get("timestamp") or 0)
    age = max(0, int(time.time()) - ts) if ts else stale_seconds + 1
    if age <= stale_seconds and is_pid_alive(pid):
        return False, "lock-live"
    clear_lock()
    return True, f"cleared-stale-lock age={age}s pid={pid}"


def acquire_global_lock(task_type: str, task_id: str, stale_seconds: int = 4 * 60 * 60) -> tuple[bool, dict]:
    payload = {
        "task_id": task_id,
        "task_type": task_type,
        "timestamp": int(time.time()),
        "heartbeat_at": int(time.time()),
        "pid": os.getpid(),
    }
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(LOCK_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2)
            return True, payload
        except FileExistsError:
            cleared, reason = clear_stale_lock(stale_seconds=stale_seconds)
            if not cleared:
                current = read_lock() or {}
                current["reason"] = reason
                return False, current
        except Exception as e:
            return False, {"reason": str(e)}
    current = read_lock() or {}
    current.setdefault("reason", "lock-busy")
    return False, current


def refresh_global_lock(task_type: str | None = None, task_id: str | None = None):
    data = read_lock() or {}
    if not data:
        return
    data["heartbeat_at"] = int(time.time())
    if task_type:
        data["task_type"] = task_type
    if task_id:
        data["task_id"] = task_id
    write_json(LOCK_FILE, data)


def release_global_lock(expected_task_id: str | None = None):
    data = read_lock() or {}
    if expected_task_id and data and data.get("task_id") not in (None, expected_task_id):
        return
    clear_lock()