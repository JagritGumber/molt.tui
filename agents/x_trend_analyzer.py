#!/usr/bin/env python3
"""
Trend analyzer for @wyvernotwts.

Reads normalized signals from ~/.moltui/x-signals.json and writes ranked,
creator-centered trends to ~/.moltui/x-trends.json.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

HOME_DIR = Path.home() / ".moltui"
SIGNALS_FILE = HOME_DIR / "x-signals.json"
TRENDS_FILE = HOME_DIR / "x-trends.json"

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "have", "just", "they", "their", "about", "would", "could",
    "should", "there", "after", "before", "while", "still", "when", "where", "more", "into", "using", "used", "your",
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


def _keywords(sig: dict) -> list[str]:
    tags = list(sig.get("tags") or [])
    text = f"{sig.get('title', '')} {sig.get('text', '')}".lower()
    for w in re.findall(r"[a-z][a-z0-9\-]{3,}", text):
        if w not in STOPWORDS and w not in tags:
            tags.append(w)
    return tags[:10]


def _freshness_score(hours: float) -> float:
    if hours <= 1:
        return 1.0
    if hours <= 6:
        return 0.85
    if hours <= 24:
        return 0.65
    if hours <= 72:
        return 0.4
    return 0.15


def _creator_relevance(sig: dict) -> float:
    text = f"{sig.get('title', '')} {sig.get('text', '')}".lower()
    score = 0.2
    boosts = {
        "build": 0.15, "builder": 0.15, "founder": 0.15, "startup": 0.12,
        "ship": 0.18, "product": 0.14, "workflow": 0.14, "tool": 0.12,
        "agent": 0.12, "video": 0.10, "demo": 0.15, "open source": 0.12,
        "github": 0.10, "launch": 0.10,
    }
    for needle, weight in boosts.items():
        if needle in text:
            score += weight
    return min(score, 1.0)


def _mode_scores(sig: dict) -> dict:
    text = f"{sig.get('title', '')} {sig.get('text', '')}".lower()
    freshness = _freshness_score(float(sig.get("freshness_hours", 9999)))
    growth = min(float(sig.get("growth_hint", 0.0)) / 3.0, 1.0)
    creator = _creator_relevance(sig)

    fomo = 0.25 + 0.35 * freshness + 0.25 * growth
    creating = 0.25 + 0.40 * creator
    knowledge = 0.20 + 0.20 * creator

    if any(x in text for x in ["launch", "release", "introducing", "viral", "hot", "breakthrough", "new model"]):
        fomo += 0.18
    if any(x in text for x in ["tool", "workflow", "build", "ship", "api", "sdk", "open source", "repo"]):
        creating += 0.20
    if any(x in text for x in ["paper", "research", "benchmark", "understanding", "why", "guide", "explains"]):
        knowledge += 0.18

    if sig.get("source_type") in ("news", "rss"):
        fomo += 0.08
        knowledge += 0.08
    if sig.get("source_type") == "x":
        creating += 0.08

    return {
        "FOMO": round(min(fomo, 1.0), 3),
        "Creating": round(min(creating, 1.0), 3),
        "Knowledge": round(min(knowledge, 1.0), 3),
    }


def _cluster_key(sig: dict) -> str:
    tags = [t for t in _keywords(sig) if len(t) > 3]
    if tags:
        return tags[0]
    title = (sig.get("title") or "misc").lower()
    return re.sub(r"[^a-z0-9]+", "-", title[:20]).strip("-") or "misc"


def analyze() -> dict:
    payload = _read_json(SIGNALS_FILE, {})
    signals = payload.get("signals", [])
    grouped = defaultdict(list)
    for sig in signals:
        grouped[_cluster_key(sig)].append(sig)

    trends = []
    for key, items in grouped.items():
        if not items:
            continue
        source_diversity = len({i.get("source") for i in items})
        freshness = max(_freshness_score(float(i.get("freshness_hours", 9999))) for i in items)
        creator = max(_creator_relevance(i) for i in items)
        growth = sum(float(i.get("growth_hint", 0.0)) for i in items)
        size_boost = min(math.log(len(items) + 1, 2) / 3.0, 0.8)
        mode_totals = Counter()
        author_counts = Counter()
        tags = Counter()
        sample_titles = []
        sample_urls = []
        for sig in sorted(items, key=lambda s: (s.get("growth_hint", 0), -float(s.get("freshness_hours", 9999))), reverse=True)[:8]:
            for mode, score in _mode_scores(sig).items():
                mode_totals[mode] += score
            author_counts[sig.get("author") or "unknown"] += 1
            for t in sig.get("tags") or []:
                tags[t] += 1
            if sig.get("title"):
                sample_titles.append(sig.get("title"))
            if sig.get("url"):
                sample_urls.append(sig.get("url"))

        best_mode = mode_totals.most_common(1)[0][0] if mode_totals else "Knowledge"
        score = round(
            0.30 * freshness +
            0.25 * min(source_diversity / 3.0, 1.0) +
            0.20 * min(growth / 6.0, 1.0) +
            0.15 * creator +
            0.10 * size_boost,
            3,
        )
        trends.append({
            "trend_key": key,
            "score": score,
            "signal_count": len(items),
            "source_diversity": source_diversity,
            "creator_relevance": round(creator, 3),
            "freshness_score": round(freshness, 3),
            "growth_score": round(min(growth / 6.0, 1.0), 3),
            "recommended_mode": best_mode,
            "mode_scores": dict(mode_totals),
            "tags": [t for t, _ in tags.most_common(8)],
            "top_authors": [a for a, _ in author_counts.most_common(5)],
            "sample_titles": sample_titles[:5],
            "sample_urls": sample_urls[:5],
            "creator_angle": build_creator_angle(best_mode, key, sample_titles[:2], [t for t, _ in tags.most_common(4)]),
            "ttl_minutes": ttl_minutes(best_mode, freshness),
        })

    trends.sort(key=lambda t: (t["score"], t["creator_relevance"], t["signal_count"]), reverse=True)
    recommended_accounts = recommend_accounts(payload.get("stats", {}).get("x_authors_seen", {}), trends)
    out = {
        "generated_at": int(time.time()),
        "generated_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trend_count": len(trends),
        "trends": trends[:25],
        "recommended_accounts": recommended_accounts,
    }
    _write_json(TRENDS_FILE, out)
    return out


def ttl_minutes(best_mode: str, freshness_score: float) -> int:
    if best_mode == "FOMO":
        return 45 if freshness_score >= 0.85 else 120
    if best_mode == "Creating":
        return 180
    return 360


def build_creator_angle(mode: str, key: str, sample_titles: list[str], tags: list[str]) -> str:
    topic = sample_titles[0] if sample_titles else key
    tag_block = ", ".join(tags[:3]) if tags else key
    if mode == "FOMO":
        return f"Use {topic} to show why builders who notice {tag_block} early get an edge before the crowd catches up."
    if mode == "Creating":
        return f"Frame {topic} around what creators can now build, ship, or productize faster because of {tag_block}."
    return f"Teach the non-obvious lesson inside {topic}, then connect it to what better builders should understand next about {tag_block}."


def recommend_accounts(author_counts: dict, trends: list[dict]) -> list[dict]:
    recommendations = []
    trend_keys = {t["trend_key"] for t in trends[:10]}
    for author, count in sorted(author_counts.items(), key=lambda kv: kv[1], reverse=True)[:12]:
        value = round(min(count / 3.0, 1.0), 3)
        reason = "appeared repeatedly in recent visible ingest"
        if any(author in trend.get("top_authors", []) for trend in trends[:10]):
            value = round(min(value + 0.15, 1.0), 3)
            reason = "appeared repeatedly and sits inside current high-scoring trends"
        recommendations.append({
            "author": author,
            "watch_score": value,
            "reason": reason,
            "linked_trends": [k for k in trend_keys if author in next((t.get("top_authors", []) for t in trends if t["trend_key"] == k), [])][:4],
        })
    return recommendations


def main() -> int:
    out = analyze()
    print(json.dumps({
        "trend_count": out.get("trend_count", 0),
        "path": str(TRENDS_FILE),
        "top_trends": [
            {
                "trend": t["trend_key"],
                "score": t["score"],
                "mode": t["recommended_mode"],
            }
            for t in out.get("trends", [])[:5]
        ],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
