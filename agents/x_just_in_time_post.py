#!/usr/bin/env python3
"""
Just-in-time X posting pipeline for @wyvernotwts.

Single coordinated run:
- acquire global X automation lock
- refresh signals
- analyze trends
- refresh policy weights
- choose best trend/mode for creator-centered posting
- generate a draft
- queue it
- optionally post immediately
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path

from x_browser import DRAFT_QUEUE, get_zai_config
from x_feedback_collector import collect_feedback
from x_signal_feeder import build_signals
from x_trend_analyzer import analyze
from x_runtime import acquire_global_lock, get_account_handle, read_json, release_global_lock, write_json

HOME_DIR = Path.home() / ".moltui"
JIT_LOG = HOME_DIR / "x-jit-post-log.json"
POST_POLICY = HOME_DIR / "x-post-policy.json"
STALE_LOCK_SECONDS = 4 * 60 * 60


def _read_json(path: Path, default):
    return read_json(path, default)


def _write_json(path: Path, value):
    write_json(path, value)


def log_event(action: str, detail: str, status: str = "ok"):
    logs = _read_json(JIT_LOG, [])
    logs.append({
        "timestamp": int(time.time()),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "status": status,
        "detail": detail[:800],
    })
    logs = logs[-500:]
    _write_json(JIT_LOG, logs)
    print(f"[{status}] {action}: {detail}")


def load_policy() -> dict:
    return _read_json(POST_POLICY, {
        "mode_weights": {"FOMO": 1.0, "Creating": 1.0, "Knowledge": 1.0},
        "source_weights": {"x-visible-ingest": 1.0, "hacker-news": 1.0, "rss": 1.0},
        "trend_weights": {},
        "hook_style_weights": {"direct": 1.0, "thesis": 1.0, "hard-truth": 1.0},
    })


def choose_trend(trends: list[dict], policy: dict) -> dict | None:
    best = None
    best_score = -1.0
    for trend in trends:
        mode = trend.get("recommended_mode", "Knowledge")
        score = float(trend.get("score", 0.0))
        score *= float(policy.get("mode_weights", {}).get(mode, 1.0))
        score *= float(policy.get("trend_weights", {}).get(trend.get("trend_key", ""), 1.0))
        creator = float(trend.get("creator_relevance", 0.0))
        signal_count = int(trend.get("signal_count", 0))
        ttl = int(trend.get("ttl_minutes", 180))
        adjusted = score + 0.15 * creator + min(signal_count / 15.0, 0.15) + (0.08 if ttl <= 120 else 0.02)
        if adjusted > best_score:
            best = trend
            best_score = adjusted
    if best is not None:
        best = dict(best)
        best["policy_adjusted_score"] = round(best_score, 3)
    return best


def choose_hook_style(policy: dict, mode: str) -> str:
    weights = dict(policy.get("hook_style_weights", {}))
    if mode == "FOMO":
        weights["hard-truth"] = weights.get("hard-truth", 1.0) + 0.2
    elif mode == "Creating":
        weights["thesis"] = weights.get("thesis", 1.0) + 0.2
    else:
        weights["direct"] = weights.get("direct", 1.0) + 0.2
    return max(weights.items(), key=lambda kv: kv[1])[0]


def sanitize_generated_draft(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.strip().strip('"').strip()
    banned_prefixes = [
        "i built",
        "i shipped",
        "i deployed",
        "i made",
        "i launched",
        "i created",
        "we built",
        "we shipped",
        "we launched",
        "my project",
        "show hn",
        "ask hn",
    ]
    lower = cleaned.lower()
    if any(p in lower for p in banned_prefixes):
        return None
    return cleaned[:280]


def heuristic_draft(trend: dict, hook_style: str) -> str:
    title = (trend.get("sample_titles") or [trend.get("trend_key", "this trend")])[0]
    tags = trend.get("tags") or []
    tag_phrase = ", ".join(tags[:2]) if tags else trend.get("trend_key", "this")
    mode = trend.get("recommended_mode", "Knowledge")
    if mode == "FOMO":
        hooks = {
            "hard-truth": f"most people are still treating {tag_phrase} like a curiosity. it’s already becoming an advantage.",
            "thesis": f"{title} is one of those moments where the edge goes to the builders who react before the narrative gets crowded.",
            "direct": f"people are underreacting to {title.lower()}.",
        }
        body = "the real opportunity isn’t just watching the demo. it’s building the product layer and distribution around what this changes in user expectations."
    elif mode == "Creating":
        hooks = {
            "hard-truth": f"the gap is widening between people who watch {tag_phrase} and people who build on top of it.",
            "thesis": f"{title} matters because it expands what a small creator can ship fast.",
            "direct": f"{title} is less interesting as content than as a new building block.",
        }
        body = "this is the kind of shift that makes new workflows, products, and one-person tools feel suddenly viable."
    else:
        hooks = {
            "hard-truth": f"a lot of people are reading {tag_phrase} as hype when the more useful takeaway is what it reveals about the next product cycle.",
            "thesis": f"the non-obvious thing in {title} is what it teaches builders about where the market is moving.",
            "direct": f"the useful part of {title.lower()} isn’t the headline. it’s the shift underneath it.",
        }
        body = "understanding this early matters because better creators price the second-order effects before everyone else does."
    return f"{hooks.get(hook_style, next(iter(hooks.values())))} {body}"[:278]


def llm_generate_draft(trend: dict, hook_style: str) -> str | None:
    zai = get_zai_config()
    if not zai:
        return None
    key, model = zai
    mode = trend.get("recommended_mode", "Knowledge")
    titles = "\n".join(f"- {t}" for t in (trend.get("sample_titles") or [])[:4])
    tags = ", ".join((trend.get("tags") or [])[:6])
    creator_angle = trend.get("creator_angle", "Keep it creator-centered.")
    prompt = f"""You write posts for @wyvernotwts.

Goal:
- center the account on a creator/builder identity
- use current trends as inputs, not as the whole personality
- write one concise X post in the mode: {mode}
- hook style preference: {hook_style}

Audience feelings to optimize for:
- FOMO
- Creating
- Knowledge

Hard constraints:
- 1 post only
- under 260 chars preferred, absolute max 280
- no hashtags
- no emojis
- no generic hype wording
- should sound sharp, internet-native, sponsor-safe
- trend first, but always connect back to builders/creators/projects
- do NOT claim the user built, shipped, deployed, launched, or used something unless explicitly given that fact
- do NOT fabricate first-person experience
- do NOT use Hacker News-native wording like 'Show HN' or 'Ask HN'
- do NOT open with a source title copied into the post

Trend info:
- trend key: {trend.get('trend_key')}
- tags: {tags}
- creator angle: {creator_angle}
- sample titles:
{titles}

Write only the post text."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.z.ai/api/paas/v4/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 180,
                "temperature": 0.9,
                "stream": False,
                "thinking": {"type": "disabled"},
            }).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        text = (data["choices"][0]["message"]["content"] or "").strip()
        return text.strip('"').strip()[:280] if text else None
    except Exception as e:
        log_event("llm", f"draft generation failed: {str(e)[:120]}", "fail")
        return None


def build_draft_entry(text: str, trend: dict, hook_style: str) -> dict:
    account_handle = get_account_handle()
    entry = {
        "draft_id": uuid.uuid4().hex[:16],
        "text": text,
        "status": "queued",
        "created_at": int(time.time()),
        "not_before": int(time.time()),
        "mode": trend.get("recommended_mode"),
        "trend_key": trend.get("trend_key"),
        "hook_style": hook_style,
        "source_labels": sorted({u.split('/')[2] if u.startswith('http') else trend.get('recommended_mode', 'unknown') for u in trend.get('sample_urls', [])[:3]}),
        "source_urls": trend.get("sample_urls", [])[:5],
        "tags": trend.get("tags", [])[:8],
        "creator_angle": trend.get("creator_angle"),
        "account_handle": account_handle,
    }
    return entry


def queue_draft_entry(entry: dict, trend_key: str):
    queue = _read_json(DRAFT_QUEUE, [])
    queue.append(entry)
    _write_json(DRAFT_QUEUE, queue)
    log_event("queue", f"queued draft for trend {trend_key}: {entry.get('text', '')[:120]}")


async def maybe_post_now(post_now: bool, draft_id: str | None):
    if not post_now:
        return 0
    env = os.environ.copy()
    env["X_POST_DELAY_SECONDS"] = "0"
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "x_post_runner.py"), "--windows", "--no-delay"]
    if draft_id:
        cmd += ["--draft-id", draft_id]
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(Path(__file__).resolve().parent.parent), env=env)
    return await proc.wait()


async def run_pipeline(args) -> int:
    lock_id = f"jit-{int(time.time())}"
    lock_acquired = False
    if not args.lock_already_held:
        acquired, info = acquire_global_lock("jit-post", lock_id, stale_seconds=STALE_LOCK_SECONDS)
        if not acquired:
            log_event("lock", f"busy: {info.get('task_type', 'unknown')} {info.get('task_id', '')}", "skip")
            return 0
        lock_acquired = True
        log_event("lock", "acquired")
    try:
        signals = build_signals()
        trends_out = analyze()
        policy_out = collect_feedback()
        policy = load_policy()
        trend = choose_trend(trends_out.get("trends", []), policy)
        if not trend:
            log_event("trend", "no trend selected", "fail")
            return 1

        hook_style = choose_hook_style(policy, trend.get("recommended_mode", "Knowledge"))
        draft = sanitize_generated_draft(llm_generate_draft(trend, hook_style)) or heuristic_draft(trend, hook_style)
        draft = draft.strip()
        if not draft:
            log_event("draft", "empty draft generated", "fail")
            return 1
        if len(draft) > 280:
            draft = draft[:277] + "..."

        queued = build_draft_entry(draft, trend, hook_style)
        if not args.dry_run:
            queue_draft_entry(queued, trend.get("trend_key", "unknown"))
        out = {
            "selected_trend": trend,
            "draft": draft,
            "queued": queued,
            "signals_seen": signals.get("stats", {}).get("total_signals", 0),
            "policy_snapshot": policy_out,
            "dry_run": bool(args.dry_run),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))

        if args.dry_run:
            return 0

        if args.post_now:
            rc = await maybe_post_now(True, queued.get("draft_id"))
            log_event("post-now", f"x_post_runner exited {rc}", "ok" if rc == 0 else "fail")
            return rc
        return 0
    finally:
        if lock_acquired:
            release_global_lock(lock_id)
            log_event("lock", "released")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Generate and queue draft, but do not post")
    ap.add_argument("--post-now", action="store_true", help="Post immediately after queueing using x_post_runner")
    ap.add_argument("--lock-already-held", action="store_true", help="skip taking the global lock because the dispatcher already holds it")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    raise SystemExit(main())
