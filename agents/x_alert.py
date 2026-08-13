#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

HOME_DIR = Path.home() / ".moltui"
ALERT_LOG = HOME_DIR / "x-alert-log.json"
HERMES_ENV = Path.home() / ".hermes" / ".env"
CHANNEL_DIRECTORY = Path.home() / ".hermes" / "channel_directory.json"


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


def load_dotenv(path: Path) -> dict[str, str]:
    data = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def resolve_telegram_config() -> tuple[str | None, str | None]:
    env = dict(os.environ)
    env.update(load_dotenv(HERMES_ENV))
    token = env.get('TELEGRAM_BOT_TOKEN') or env.get('BOT_TOKEN')
    chat_id = env.get('HOME_TELEGRAM_CHAT_ID') or env.get('TELEGRAM_HOME_CHAT_ID')
    if not chat_id:
        directory = read_json(CHANNEL_DIRECTORY, {})
        telegram = directory.get('platforms', {}).get('telegram') if isinstance(directory, dict) else None
        if isinstance(telegram, list) and telegram:
            first = telegram[0]
            if isinstance(first, dict):
                chat_id = first.get('id')
        elif isinstance(telegram, dict):
            home = telegram.get('home')
            if isinstance(home, dict):
                chat_id = home.get('id')
    return token, str(chat_id) if chat_id else None


def log_alert(entry: dict):
    logs = read_json(ALERT_LOG, [])
    logs.append(entry)
    logs = logs[-500:]
    write_json(ALERT_LOG, logs)


def recently_sent(key: str, cooldown_seconds: int) -> bool:
    now = int(time.time())
    logs = read_json(ALERT_LOG, [])
    for item in reversed(logs):
        if item.get('key') == key and item.get('telegram_sent'):
            if now - int(item.get('timestamp', 0)) < cooldown_seconds:
                return True
            break
    return False


def send_telegram(message: str) -> bool:
    token, chat_id = resolve_telegram_config()
    if not token or not chat_id:
        return False
    data = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': message,
        'disable_web_page_preview': 'true',
    }).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
        return bool(payload.get('ok'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', required=True)
    ap.add_argument('--message', required=True)
    ap.add_argument('--cooldown-seconds', type=int, default=6 * 60 * 60)
    args = ap.parse_args()

    if recently_sent(args.key, args.cooldown_seconds):
        log_alert({
            'timestamp': int(time.time()),
            'key': args.key,
            'message': args.message,
            'telegram_sent': False,
            'status': 'suppressed',
        })
        print('suppressed')
        return 0

    sent = False
    error = None
    try:
        sent = send_telegram(args.message)
    except Exception as e:
        error = str(e)
    log_alert({
        'timestamp': int(time.time()),
        'key': args.key,
        'message': args.message,
        'telegram_sent': sent,
        'status': 'sent' if sent else 'logged',
        'error': error,
    })
    print('sent' if sent else 'logged')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
