"""Centralized config and paths for the X agent."""

import json
from pathlib import Path

HOME = Path.home() / ".moltui"
HOME.mkdir(exist_ok=True)

# ── File paths ──
CONFIG_FILE = HOME / "config.json"
ACCOUNT_FILE = HOME / "x-account.json"
SIGNALS_FILE = HOME / "x-signals.json"
TRENDS_FILE = HOME / "x-trends.json"
DRAFTS_FILE = HOME / "tweet-drafts.json"
POST_HISTORY = HOME / "x-post-history.json"
POLICY_FILE = HOME / "x-post-policy.json"
LOCK_FILE = HOME / "x-automation.lock"
SCHEDULER_LOG = HOME / "x-scheduler-log.json"

# ── LLM config ──
ZAI_URL = "https://api.z.ai/api/paas/v4/chat/completions"


def load_json(path: Path, default=None):
    if path.exists():
        return json.loads(path.read_text())
    return default if default is not None else {}


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_zai_key() -> str:
    cfg = load_json(CONFIG_FILE)
    return cfg.get("zaiApiKey", "")


def get_zai_model() -> str:
    cfg = load_json(CONFIG_FILE)
    return cfg.get("zaiModel", "GLM-4.7-FlashX")


def get_account_handle() -> str:
    acc = load_json(ACCOUNT_FILE)
    return acc.get("handle", "")
