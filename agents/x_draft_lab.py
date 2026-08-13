#!/usr/bin/env python3
"""
Batch X post-package generator + self-critique lab for @wyvernotwts.

Purpose:
- generate multiple draft packages from current trends
- score text-only and packaged-post quality separately
- keep iterating until it gets 5 strong packaged drafts in a row
- archive any 9/10 packaged drafts

Outputs:
- ~/.moltui/x-draft-lab-runs/<run_id>.json
- ~/.moltui/x-best-drafts.json
"""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

from x_browser import get_zai_config
from x_feedback_collector import collect_feedback
from x_signal_feeder import build_signals
from x_trend_analyzer import analyze

HOME_DIR = Path.home() / ".moltui"
RUNS_DIR = HOME_DIR / "x-draft-lab-runs"
BEST_DRAFTS = HOME_DIR / "x-best-drafts.json"

TARGET_STREAK = 5
MAX_ITERATIONS = 5
DRAFTS_PER_ITERATION = 8
STRONG_THRESHOLD = 8.6

THESIS_MACHINE_PATTERNS = [
    "the next wave",
    "the real opportunity",
    "the edge is",
    "tooling layer",
    "don't get caught",
    "the people who notice this now",
    "that’s where the moat is",
    "that's where the moat is",
    "the ones who",
    "this space",
    "you need to be paying attention",
    "major platform",
    "won the next cycle",
]

ABSTRACT_PATTERNS = [
    "paperwork",
    "regulations",
    "abstract",
    "research papers",
    "competitive battleground",
    "process the hundreds of pages",
    "understand the text",
]

VISUAL_PATTERNS = [
    "demo",
    "video",
    "clip",
    "screen",
    "game",
    "engine",
    "render",
    "agent",
    "workflow",
    "tool",
    "ship",
    "build",
    "ui",
    "before/after",
]

LOW_LEVEL_PATTERNS = [
    "infra",
    "runtime",
    "engine",
    "low-level",
    "systems",
    "compile",
    "latency",
    "render",
    "memory",
    "gamedev",
    "game dev",
]

MEDIA_TYPES = ["video", "image", "screenshot", "meme", "threadless-text"]


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


def choose_trend() -> dict:
    build_signals()
    trends = analyze().get("trends", [])
    if not trends:
        raise RuntimeError("no trends available")

    def trend_quality(t: dict) -> float:
        tags = [x.lower() for x in (t.get("tags") or [])]
        titles = " ".join(t.get("sample_titles") or []).lower()
        text = " ".join(tags) + " " + titles
        score = float(t.get("score", 0.0))
        if any(x in text for x in VISUAL_PATTERNS):
            score += 0.35
        if any(x in text for x in LOW_LEVEL_PATTERNS):
            score += 0.25
        if any(x in text for x in ABSTRACT_PATTERNS):
            score -= 0.45
        if "research" in tags and not any(x in text for x in ["demo", "tool", "engine", "workflow"]):
            score -= 0.35
        if any(x in text for x in ["paperwork", "regulations", "abstract"]):
            score -= 0.25
        return score

    ranked = sorted(trends, key=trend_quality, reverse=True)
    return ranked[0]


def load_policy() -> dict:
    return collect_feedback()


def llm_json(prompt: str, max_tokens: int = 1800, temperature: float = 0.9) -> dict | None:
    zai = get_zai_config()
    if not zai:
        return None
    key, model = zai
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.z.ai/api/paas/v4/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
            }).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        resp = urllib.request.urlopen(req, timeout=35)
        data = json.loads(resp.read())
        text = (data["choices"][0]["message"]["content"] or "").strip()
        return json.loads(text)
    except Exception:
        return None


def fallback_generate(trend: dict, n: int) -> list[dict]:
    topic = (trend.get("sample_titles") or [trend.get("trend_key", "this trend")])[0]
    mode = trend.get("recommended_mode", "FOMO")
    bases = [
        {
            "text": f"most people react to the feature. builders should react to the workflow it changes.",
            "angle": "workflow shift",
            "media_type": "video",
            "media_concept": f"6-10 second before/after clip showing {topic.lower()} collapsing a workflow.",
        },
        {
            "text": f"the interesting part of {trend.get('trend_key', 'this')} isn't the headline. it's what gets easier to ship now.",
            "angle": "what gets easier",
            "media_type": "screenshot",
            "media_concept": f"clean screenshot of the result or output that makes the shift obvious at a glance.",
        },
        {
            "text": f"a lot of these releases look like demos until someone turns them into a boring dependable workflow. that's usually where the value is.",
            "angle": "demo to workflow",
            "media_type": "video",
            "media_concept": "simple screen recording that shows the boring useful loop, not the flashy headline moment.",
        },
        {
            "text": f"most people chase the headline. i care more about what this changes in the product loop.",
            "angle": "product loop",
            "media_type": "image",
            "media_concept": "single visual comparing old loop vs new loop with one concrete output.",
        },
    ]
    random.shuffle(bases)
    out = []
    for item in bases[:n]:
        item["mode"] = mode
        out.append(item)
    return out


def generate_batch(trend: dict, iteration: int, n: int = DRAFTS_PER_ITERATION) -> list[dict]:
    titles = "\n".join(f"- {t}" for t in (trend.get("sample_titles") or [])[:5])
    tags = ", ".join((trend.get("tags") or [])[:8])
    mode = trend.get("recommended_mode", "FOMO")
    prompt = f"""You are writing X post packages for @wyvernotwts.

Identity:
- creator with breadth across AI, low-level systems, tooling, and gamedev
- not an AI-only commentator
- sounds like a real builder with taste

Goal:
- produce {n} distinct X post packages
- each package must include text plus a media concept
- trend-aware but not source-regurgitated
- creator-centered, builder-human, sharp
- easy to understand in one scroll
- prefer packages that become much stronger with a clip/image/screenshot
- lowercase/casual is okay when natural

Hard bans:
- no em dashes
- no hashtags
- no emojis
- no 'Show HN' / 'Ask HN'
- no title-lifting
- no fake first-person claims
- no generic ai-thought-leader sludge
- no thesis-machine phrasing like 'the next wave is', 'the real opportunity is', 'the edge is', 'you need to be paying attention'

Trend:
- key: {trend.get('trend_key')}
- recommended mode: {mode}
- tags: {tags}
- creator angle: {trend.get('creator_angle')}
- sample titles:
{titles}

Needle to avoid:
- abstract paperwork/research discourse
- overexplaining
- sounding like an essay or blog post
- saying 'builders/infra/edge' without a concrete reason

Return strict JSON object with this shape:
{{
  "drafts": [
    {{
      "text": "...",
      "angle": "...",
      "mode": "{mode}",
      "media_type": "video|image|screenshot|meme|threadless-text",
      "media_concept": "...",
      "why_media_helps": "..."
    }}
  ]
}}
"""
    data = llm_json(prompt, max_tokens=2800, temperature=1.0)
    drafts = []
    if isinstance(data, dict):
        for item in data.get("drafts", []):
            text = (item.get("text") or "").strip()
            if text:
                drafts.append({
                    "text": text[:280],
                    "angle": (item.get("angle") or "").strip()[:120],
                    "mode": (item.get("mode") or mode).strip()[:40],
                    "media_type": (item.get("media_type") or "threadless-text").strip()[:40],
                    "media_concept": (item.get("media_concept") or "").strip()[:240],
                    "why_media_helps": (item.get("why_media_helps") or "").strip()[:240],
                })
    if not drafts:
        drafts = fallback_generate(trend, n)
    return drafts[:n]


def readability_score(text: str) -> float:
    lower = text.lower().strip()
    words = re.findall(r"\b\w+\b", lower)
    score = 6.5
    if len(words) <= 28:
        score += 1.0
    elif len(words) >= 45:
        score -= 1.0
    if lower.count(".") <= 2:
        score += 0.4
    if any(x in lower for x in ["everyone", "most people", "nobody", "the interesting part", "the useful way"]):
        score += 0.6
    if any(x in lower for x in THESIS_MACHINE_PATTERNS):
        score -= 1.8
    if any(x in lower for x in ABSTRACT_PATTERNS):
        score -= 1.6
    return max(1.0, min(10.0, score))


def visual_score(text: str, media_type: str, media_concept: str) -> float:
    lower = (text + " " + media_concept).lower()
    score = 4.0
    if media_type in ("video", "image", "screenshot", "meme"):
        score += 1.8
    if any(x in lower for x in VISUAL_PATTERNS):
        score += 1.5
    if any(x in lower for x in ["before/after", "clip", "screen recording", "screenshot", "ui"]):
        score += 1.0
    if any(x in lower for x in ABSTRACT_PATTERNS):
        score -= 1.4
    return max(1.0, min(10.0, score))


def source_distance_penalty(text: str, trend: dict) -> float:
    lower = text.lower()
    penalty = 0.0
    for title in trend.get("sample_titles") or []:
        title_words = set(re.findall(r"\b[a-z]{4,}\b", title.lower()))
        text_words = set(re.findall(r"\b[a-z]{4,}\b", lower))
        overlap = len(title_words & text_words)
        if overlap >= 5:
            penalty += 0.8
        elif overlap >= 3:
            penalty += 0.4
    return penalty


def fallback_score(item: dict, trend: dict) -> dict:
    text = item["text"]
    media_type = item.get("media_type", "threadless-text")
    media_concept = item.get("media_concept", "")
    lower = text.lower().strip()
    penalties = 0.0
    if any(x in lower for x in ["show hn", "ask hn", "revolutionary", "game changer"]):
        penalties += 2.0
    penalties += 1.4 if any(x in lower for x in THESIS_MACHINE_PATTERNS) else 0.0
    penalties += 1.4 if any(x in lower for x in ABSTRACT_PATTERNS) else 0.0
    penalties += source_distance_penalty(text, trend)
    if len(lower) > 260:
        penalties += 0.7
    if lower.count(".") > 4:
        penalties += 0.5

    positives = 0.0
    if any(x in lower for x in ["workflow", "product", "ship", "build", "tool", "engine"]):
        positives += 1.2
    if any(x in lower for x in ["most people", "everyone", "nobody"]):
        positives += 0.5
    if any(x in lower for x in LOW_LEVEL_PATTERNS):
        positives += 0.6

    read = readability_score(text)
    visual = visual_score(text, media_type, media_concept)
    human = 6.0
    if any(x in lower for x in ["this space", "next major platform", "competitive battleground"]):
        human -= 1.3
    if "i'm watching the paperwork" in lower:
        human -= 1.2
    if "dont get caught unprepared" in lower or "don't get caught unprepared" in lower:
        human -= 1.0
    if any(x in lower for x in ["boring product behavior", "product loop", "what gets easier to ship"]):
        human += 0.8
    human = max(1.0, min(10.0, human))

    creator_fit = 5.0
    if any(x in lower for x in ["build", "ship", "workflow", "product", "engine", "tool"]):
        creator_fit += 1.2
    if any(x in lower for x in ["ai-models", "paperwork", "regulations"]):
        creator_fit -= 0.6
    if any(x in lower for x in ["engine", "systems", "runtime", "render", "low-level"]):
        creator_fit += 0.6
    creator_fit = max(1.0, min(10.0, creator_fit))

    text_only = 0.35 * read + 0.25 * human + 0.20 * creator_fit + 0.20 * max(1.0, min(10.0, 5.0 + positives - penalties))
    packaged = 0.27 * read + 0.20 * human + 0.18 * creator_fit + 0.25 * visual + 0.10 * max(1.0, min(10.0, 5.0 + positives - penalties))

    if media_type == "threadless-text":
        packaged = min(packaged, text_only)
    if visual < 5.5 and read < 7.5:
        packaged = min(packaged, 7.2)
    if any(x in lower for x in ABSTRACT_PATTERNS):
        text_only = min(text_only, 7.0)
        packaged = min(packaged, 7.4)
    if any(x in lower for x in THESIS_MACHINE_PATTERNS):
        text_only = min(text_only, 6.8)
        packaged = min(packaged, 7.0)

    verdict = "strong" if packaged >= STRONG_THRESHOLD else "weak"
    notes = []
    notes.append("easy to parse" if read >= 8 else "still too abstract")
    notes.append("strong package potential" if visual >= 7.5 else "media still weak")
    notes.append("creator-native" if creator_fit >= 6.2 else "not creator-specific enough")
    return {
        "text_only": round(max(1.0, min(10.0, text_only)), 1),
        "overall": round(max(1.0, min(10.0, packaged)), 1),
        "verdict": verdict,
        "hook": round(read, 1),
        "human": round(human, 1),
        "specificity": round(max(1.0, min(10.0, 5.0 + positives - penalties / 2)), 1),
        "creator_fit": round(creator_fit, 1),
        "visual": round(visual, 1),
        "notes": notes,
    }


def critique_batch(trend: dict, drafts: list[dict]) -> list[dict]:
    payload = {"drafts": drafts}
    prompt = f"""Critique these X post packages for @wyvernotwts.

Important scoring rules:
- be harsh
- score text-only and packaged-post separately
- text-only abstract drafts rarely deserve above 7/10
- if a package becomes much stronger with the attached image/video idea, packaged score can be much higher
- if a draft is hard to parse in one scroll, downscore hard
- if it sounds like AI discourse or builder-thesis sludge, downscore hard
- reward visual compatibility, instant readability, and creator-native voice

Return strict JSON:
{{
  "results": [
    {{
      "text": "exact text",
      "text_only": 0-10,
      "overall": 0-10,
      "hook": 0-10,
      "human": 0-10,
      "specificity": 0-10,
      "creator_fit": 0-10,
      "visual": 0-10,
      "verdict": "strong" or "weak",
      "notes": ["...", "..."]
    }}
  ]
}}

Drafts:
{json.dumps(payload, ensure_ascii=False)}
"""
    data = llm_json(prompt, max_tokens=2600, temperature=0.6)
    results = []
    if isinstance(data, dict):
        for item in data.get("results", []):
            text = (item.get("text") or "").strip()
            if text:
                results.append(item)
    if not results:
        results = []
        for d in drafts:
            r = fallback_score(d, trend)
            r["text"] = d["text"]
            r["angle"] = d.get("angle", "")
            r["mode"] = d.get("mode", trend.get("recommended_mode", "FOMO"))
            results.append(r)
    by_text = {d["text"]: d for d in drafts}
    merged = []
    for r in results:
        text = (r.get("text") or "").strip()
        src = by_text.get(text, {})
        merged.append({
            "text": text,
            "angle": src.get("angle", r.get("angle", "")),
            "mode": src.get("mode", r.get("mode", trend.get("recommended_mode", "FOMO"))),
            "media_type": src.get("media_type", "threadless-text"),
            "media_concept": src.get("media_concept", ""),
            "why_media_helps": src.get("why_media_helps", ""),
            "text_only": float(r.get("text_only", fallback_score(src or {"text": text}, trend).get("text_only", 0))),
            "overall": float(r.get("overall", 0)),
            "hook": float(r.get("hook", 0)),
            "human": float(r.get("human", 0)),
            "specificity": float(r.get("specificity", 0)),
            "creator_fit": float(r.get("creator_fit", 0)),
            "visual": float(r.get("visual", fallback_score(src or {"text": text}, trend).get("visual", 0))),
            "verdict": r.get("verdict", "weak"),
            "notes": r.get("notes", []),
        })
    merged.sort(key=lambda x: (x["overall"], x.get("visual", 0), x["human"], x["hook"]), reverse=True)
    return merged


def archive_best(run_id: int, trend: dict, critiques: list[dict]):
    best = _read_json(BEST_DRAFTS, [])
    for item in critiques:
        if float(item.get("overall", 0)) >= 9.0:
            best.append({
                "run_id": run_id,
                "timestamp": int(time.time()),
                "trend_key": trend.get("trend_key"),
                "mode": item.get("mode"),
                "text": item.get("text"),
                "media_type": item.get("media_type"),
                "media_concept": item.get("media_concept"),
                "text_only": item.get("text_only"),
                "score": item.get("overall"),
                "notes": item.get("notes", []),
            })
    deduped = []
    seen = set()
    for item in reversed(best):
        key = item.get("text")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.reverse()
    _write_json(BEST_DRAFTS, deduped[-200:])


def run_lab() -> dict:
    trend = choose_trend()
    policy = load_policy()
    run_id = int(time.time())
    streak = 0
    iterations = []
    best_seen = []
    for iteration in range(1, MAX_ITERATIONS + 1):
        drafts = generate_batch(trend, iteration)
        critiques = critique_batch(trend, drafts)
        local_streak = 0
        for item in critiques:
            if float(item.get("overall", 0)) >= STRONG_THRESHOLD and item.get("verdict") == "strong":
                local_streak += 1
            else:
                break
        streak = max(streak, local_streak)
        archive_best(run_id, trend, critiques)
        best_seen.extend(critiques[:3])
        iterations.append({
            "iteration": iteration,
            "drafts": critiques,
            "strong_count": len([c for c in critiques if float(c.get("overall", 0)) >= STRONG_THRESHOLD and c.get("verdict") == "strong"]),
            "leading_streak": local_streak,
            "best_streak_so_far": streak,
        })
        if local_streak >= TARGET_STREAK:
            break
    best_seen.sort(key=lambda x: (x.get("overall", 0), x.get("visual", 0)), reverse=True)
    out = {
        "run_id": run_id,
        "generated_at": int(time.time()),
        "trend": trend,
        "policy_snapshot": policy,
        "target_streak": TARGET_STREAK,
        "achieved_streak": streak,
        "iterations": iterations,
        "top_drafts": best_seen[:10],
        "best_archive_path": str(BEST_DRAFTS),
    }
    _write_json(RUNS_DIR / f"{run_id}.json", out)
    return out


def main() -> int:
    out = run_lab()
    print(json.dumps({
        "run_id": out["run_id"],
        "trend_key": out["trend"].get("trend_key"),
        "achieved_streak": out["achieved_streak"],
        "top_drafts": out["top_drafts"][:5],
        "best_archive_path": out["best_archive_path"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
