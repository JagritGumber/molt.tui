#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from x_runtime import HOME_DIR, get_account, read_json, read_lock

BASE = Path(__file__).resolve().parent
WATCHDOG_LOG = HOME_DIR / 'x-watchdog-log.json'
QUEUE_FILE = HOME_DIR / 'x-automation-queue.json'
RUNNER_LOG = HOME_DIR / 'x-post-runner-log.json'
JIT_LOG = HOME_DIR / 'x-jit-post-log.json'
SCROLL_LOG = HOME_DIR / 'x-scroll-runner-log.json'
POST_HISTORY = HOME_DIR / 'x-post-history.json'
STARTUP_LOG = Path('/mnt/c/x-agent-debug/startup.log')
BROWSER_BOOTSTRAP = 'D:\\moltui\\windows\\x_browser_bootstrap.ps1'
POWERSHELL = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def log_event(action: str, detail: str, status: str = 'ok'):
    logs = read_json(WATCHDOG_LOG, [])
    logs.append({
        'timestamp': int(time.time()),
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'action': action,
        'status': status,
        'detail': detail[:500],
    })
    logs = logs[-500:]
    write_json(WATCHDOG_LOG, logs)
    print(f'[{status}] {action}: {detail}')


def cdp_candidates() -> list[str]:
    urls = ['http://localhost:9222/json/version']
    try:
        import subprocess as sp
        host_ip = sp.check_output(['sh', '-lc', "ip route | awk '/default/ {print $3}' | head -n1"], text=True).strip()
        if host_ip:
            urls.append(f'http://{host_ip}:9222/json/version')
            urls.append(f'http://{host_ip}:9223/json/version')
    except Exception:
        pass
    return urls


def check_cdp() -> tuple[bool, str]:
    last = ''
    for url in cdp_candidates():
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            return True, f"{url} {data.get('Browser', 'ok')}"
        except Exception as e:
            last = f'{url} {e}'
    return False, last or 'no-endpoint'


def run_healthcheck() -> int:
    proc = subprocess.run([sys.executable, str(BASE / 'x_healthcheck.py')], cwd=str(BASE.parent))
    return proc.returncode


def restart_browser() -> int:
    log_event('browser', 'attempting Windows browser bootstrap', 'warn')
    proc = subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', BROWSER_BOOTSTRAP])
    return proc.returncode


def count_recent_failures(hours: int = 6) -> tuple[int, list[str]]:
    cutoff = int(time.time()) - hours * 3600
    reasons = []
    count = 0
    for path in (POST_HISTORY, RUNNER_LOG, JIT_LOG, SCROLL_LOG):
        items = read_json(path, [])
        if not isinstance(items, list):
            continue
        for item in items:
            ts = int(item.get('timestamp', 0) or 0)
            if ts < cutoff:
                continue
            status = str(item.get('status', ''))
            detail = str(item.get('detail', item.get('reason', '')))
            if status in ('fail', 'failed') or 'failed' in detail.lower() or 'error' in detail.lower():
                count += 1
                if detail:
                    reasons.append(detail[:120])
    return count, reasons[-5:]


def maybe_alert(key: str, message: str, cooldown_seconds: int = 6 * 60 * 60):
    subprocess.run([
        sys.executable,
        str(BASE / 'x_alert.py'),
        '--key', key,
        '--message', message,
        '--cooldown-seconds', str(cooldown_seconds),
    ], cwd=str(BASE.parent))


def summarize_state() -> str:
    account = get_account()
    queue = read_json(QUEUE_FILE, [])
    lock = read_lock() or {}
    posted = read_json(POST_HISTORY, [])
    last_posted = next((x for x in reversed(posted) if x.get('status') == 'posted'), None)
    return (
        f"account=@{account['handle']} queued={sum(1 for q in queue if q.get('status') == 'queued')} "
        f"running={sum(1 for q in queue if q.get('status') == 'running')} "
        f"lock={lock.get('task_type', 'none')}:{lock.get('task_id', 'none')} "
        f"last_post={(last_posted or {}).get('text', '')[:60]}"
    )


def main() -> int:
    ok, detail = check_cdp()
    if ok:
        log_event('cdp', f'healthy via {detail}')
    else:
        log_event('cdp', f'unreachable: {detail}', 'fail')
        rc = restart_browser()
        log_event('browser', f'bootstrap exit={rc}', 'ok' if rc == 0 else 'fail')
        time.sleep(8)
        ok2, detail2 = check_cdp()
        if not ok2:
            msg = f"X autopilot browser bridge is down. restart failed. {detail2}"
            log_event('cdp', msg, 'fail')
            maybe_alert('x-browser-down', msg)
        else:
            log_event('cdp', f'recovered via {detail2}', 'warn')
            maybe_alert('x-browser-recovered', f'X autopilot browser bridge recovered: {detail2}', 1800)

    rc = run_healthcheck()
    log_event('healthcheck', f'exit={rc}', 'ok' if rc == 0 else 'fail')

    fail_count, reasons = count_recent_failures(6)
    if fail_count >= 4:
        msg = 'X autopilot is seeing repeated failures in the last 6h. ' + '; '.join(reasons[:3])
        maybe_alert('x-repeated-failures', msg)
        log_event('alert', msg, 'warn')

    log_event('summary', summarize_state())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
