#!/usr/bin/env python3
"""
Lightweight RL-style feedback collector for @wyvernotwts posting policy.

Uses recent post history and any attached metadata/metrics to update
mode/source/trend weights in ~/.moltui/x-post-policy.json.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

HOME_DIR = Path.home() / ".moltui"
POST_HISTORY = HOME_DIR / "x-post-history.json"
POST_POLICY = HOME_DIR / "x-post-policy.json"

DEFAULT_POLICY = {
    "updated_at": 0,
    "mode_weights": {"FOMO": 1.0, "Creating": 1.0, "Knowledge": 1.0},
    "source_weights": {"x-visible-ingest": 1.0, "hacker-news": 1.0, "rss": 1.0},
    "trend_weights": {},
    "hook_style_weights": {"direct": 1.0, "thesis": 1.0, "hard-truth": 1.0},
    "notes": [
        "Prefer creator-centered interpretations over generic trend summaries.",
        "Use FOMO for fresh asymmetry, Creating for builder action, Knowledge for useful clarity.",
    ],
}


def _read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def compute_reward(item: dict) -> float:
    if item.get("status") != "posted":
        return -0.2
    if "reward" in item:
        try:
            return float(item["reward"])
        except Exception:
            pass
    likes = float(item.get("likes", 0) or 0)
    reposts = float(item.get("reposts", 0) or 0)
    replies = float(item.get("replies", 0) or 0)
    bookmarks = float(item.get("bookmarks", 0) or 0)
    profile_visits = float(item.get("profile_visits", 0) or 0)
    follower_delta = float(item.get("follower_delta", 0) or 0)
    manual_score = float(item.get("manual_score", 0) or 0)
    base = likes * 0.05 + reposts * 0.30 + replies * 0.20 + bookmarks * 0.25 + profile_visits * 0.02 + follower_delta * 0.50 + manual_score
    return max(-1.0, min(base, 3.0))


def update_weight(old: float, reward: float, step: float = 0.08) -> float:
    new = old + step * reward
    return round(max(0.5, min(new, 2.5)), 3)


def collect_feedback() -> dict:
    history = _read_json(POST_HISTORY, [])
    policy = _read_json(POST_POLICY, DEFAULT_POLICY)
    policy.setdefault("mode_weights", DEFAULT_POLICY["mode_weights"].copy())
    policy.setdefault("source_weights", DEFAULT_POLICY["source_weights"].copy())
    policy.setdefault("trend_weights", {})
    policy.setdefault("hook_style_weights", DEFAULT_POLICY["hook_style_weights"].copy())

    summary = {
        "posts_seen": 0,
        "posted_seen": 0,
        "reward_samples": [],
        "mode_updates": defaultdict(list),
        "source_updates": defaultdict(list),
        "trend_updates": defaultdict(list),
        "hook_updates": defaultdict(list),
    }

    recent = history[-50:]
    for item in recent:
        summary["posts_seen"] += 1
        reward = compute_reward(item)
        summary["reward_samples"].append(reward)
        if item.get("status") == "posted":
            summary["posted_seen"] += 1

        mode = item.get("mode")
        if mode:
            old = float(policy["mode_weights"].get(mode, 1.0))
            policy["mode_weights"][mode] = update_weight(old, reward)
            summary["mode_updates"][mode].append(reward)

        for source in item.get("source_labels", []) or []:
            old = float(policy["source_weights"].get(source, 1.0))
            policy["source_weights"][source] = update_weight(old, reward, step=0.05)
            summary["source_updates"][source].append(reward)

        trend_key = item.get("trend_key")
        if trend_key:
            old = float(policy["trend_weights"].get(trend_key, 1.0))
            policy["trend_weights"][trend_key] = update_weight(old, reward, step=0.04)
            summary["trend_updates"][trend_key].append(reward)

        hook_style = item.get("hook_style")
        if hook_style:
            old = float(policy["hook_style_weights"].get(hook_style, 1.0))
            policy["hook_style_weights"][hook_style] = update_weight(old, reward, step=0.05)
            summary["hook_updates"][hook_style].append(reward)

    policy["updated_at"] = int(time.time())
    policy["updated_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_json(POST_POLICY, policy)

    out = {
        "policy_path": str(POST_POLICY),
        "updated_at": policy["updated_at"],
        "posts_seen": summary["posts_seen"],
        "posted_seen": summary["posted_seen"],
        "avg_reward": round(sum(summary["reward_samples"]) / len(summary["reward_samples"]), 3) if summary["reward_samples"] else 0.0,
        "mode_weights": policy["mode_weights"],
        "source_weights": policy["source_weights"],
        "top_trend_weights": dict(sorted(policy["trend_weights"].items(), key=lambda kv: kv[1], reverse=True)[:10]),
    }
    return out


def main() -> int:
    out = collect_feedback()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
