#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

from x_runtime import HOME_DIR, get_account, read_json, read_lock

QUEUE_FILE = HOME_DIR / 'x-automation-queue.json'
POST_HISTORY = HOME_DIR / 'x-post-history.json'
WATCHDOG_LOG = HOME_DIR / 'x-watchdog-log.json'
HEALTH_LOG = HOME_DIR / 'x-automation-health-log.json'
MISSION_STATE = HOME_DIR / 'x-mission-state.json'
STARTUP_LOG = Path('/mnt/c/x-agent-debug/startup.log')


def cdp_status() -> str:
    urls = ['http://localhost:9222/json/version']
    try:
        host_ip = subprocess.check_output(['sh', '-lc', "ip route | awk '/default/ {print $3}' | head -n1"], text=True).strip()
        if host_ip:
            urls += [f'http://{host_ip}:9222/json/version', f'http://{host_ip}:9223/json/version']
    except Exception:
        pass
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            return f'UP {url} {data.get("Browser", "")}'
        except Exception:
            continue
    return 'DOWN'


def last_entry(path: Path) -> dict:
    data = read_json(path, [])
    if isinstance(data, list) and data:
        return data[-1]
    return {}


def main() -> int:
    account = get_account()
    queue = read_json(QUEUE_FILE, [])
    lock = read_lock() or {}
    history = read_json(POST_HISTORY, [])
    last_posted = next((x for x in reversed(history) if x.get('status') == 'posted'), None)
    last_failed = next((x for x in reversed(history) if x.get('status') == 'failed'), None)
    cron = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    print('X AUTOPILOT STATUS')
    print(f'account: @{account["handle"]}')
    print(f'cdp: {cdp_status()}')
    print(f'queue queued: {sum(1 for q in queue if q.get("status") == "queued")}')
    print(f'queue running: {sum(1 for q in queue if q.get("status") == "running")}')
    print(f'lock: {lock.get("task_type", "none")} {lock.get("task_id", "")}'.strip())
    if last_posted:
        print(f'last posted: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(last_posted.get("timestamp", 0))))} | {(last_posted.get("text") or "")[:90]}')
    else:
        print('last posted: none')
    if last_failed:
        print(f'last failed: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(last_failed.get("timestamp", 0))))} | {(last_failed.get("reason") or "")[:90]}')
    else:
        print('last failed: none')
    wd = last_entry(WATCHDOG_LOG)
    hl = last_entry(HEALTH_LOG)
    mission = read_json(MISSION_STATE, {})
    current_mission = mission.get('current', {}) if isinstance(mission, dict) else {}
    st = STARTUP_LOG.read_text().splitlines()[-1] if STARTUP_LOG.exists() and STARTUP_LOG.read_text().splitlines() else ''
    print(f'watchdog: {wd.get("status", "n/a")} | {wd.get("action", "")} | {wd.get("detail", "")[:120]}')
    print(f'healthcheck: {hl.get("status", "n/a")} | {hl.get("action", "")} | {hl.get("detail", "")[:120]}')
    if current_mission:
        print(f'mission: {current_mission.get("status", "n/a")} | {current_mission.get("trend_key", "")} | attempts={current_mission.get("attempt_count", 0)} | next={current_mission.get("next_action", "")[:70]}')
    else:
        print('mission: none')
    print(f'windows bootstrap: {st[:120]}')
    print('cron installed: yes' if cron.returncode == 0 and 'WYVERNO-X-AUTO' in cron.stdout else 'cron installed: no')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
