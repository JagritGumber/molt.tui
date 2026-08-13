"""Trend Analyzer — clusters signals by keyword and scores for creator relevance."""

import re
import time

from agents.core.config import TRENDS_FILE, save_json

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than", "too",
    "very", "just", "about", "above", "after", "again", "against",
    "for", "from", "with", "into", "through", "during", "before",
    "between", "to", "of", "in", "on", "at", "by", "up", "out",
    "off", "over", "under", "then", "once", "here", "there", "when",
    "where", "why", "how", "what", "which", "who", "whom", "this",
    "that", "these", "those", "new", "like", "its", "also", "now",
}

CREATOR_KEYWORDS = {
    "build", "ship", "product", "tool", "agent", "launch", "deploy",
    "sdk", "api", "cli", "framework", "startup", "saas", "dev",
    "developer", "rust", "typescript", "infra", "open-source",
}


def _keywords(sig: dict) -> list[str]:
    text = f"{sig.get('title', '')} {' '.join(sig.get('tags', []))}".lower()
    words = re.findall(r"[a-z][a-z0-9_-]+", text)
    return [w for w in words if len(w) > 3 and w not in STOPWORDS]


def _cluster_key(sig: dict) -> str:
    tags = sig.get("tags", [])
    if tags:
        return tags[0]
    kws = _keywords(sig)
    if kws:
        return kws[0]
    title = (sig.get("title") or "misc").lower()
    return re.sub(r"[^a-z0-9]+", "-", title[:20]).strip("-") or "misc"


class TrendAnalyzer:
    def analyze(self, signals: list[dict]) -> list[dict]:
        """Cluster signals by topic and score each cluster."""
        # ── Cluster ──
        clusters: dict[str, list[dict]] = {}
        for sig in signals:
            key = _cluster_key(sig)
            clusters.setdefault(key, []).append(sig)

        # ── Score ──
        now = time.time()
        trends = []
        for key, sigs in clusters.items():
            if len(sigs) < 1:
                continue

            # Freshness (0-1): how recent are the signals?
            ages = [(now - s.get("timestamp", now)) / 3600 for s in sigs]
            avg_age = sum(ages) / len(ages) if ages else 24
            freshness = max(0, 1.0 - avg_age / 24)

            # Source diversity (0-1)
            sources = {s.get("source_type", s.get("source")) for s in sigs}
            diversity = min(1.0, len(sources) / 3)

            # Growth (0-1): aggregated growth hints
            growth = min(1.0, sum(s.get("growth_hint", 0) for s in sigs) / max(len(sigs), 1))

            # Creator relevance (0-1): do keywords match builder topics?
            all_tags = set()
            for s in sigs:
                all_tags.update(s.get("tags", []))
                all_tags.update(_keywords(s))
            creator_hits = len(all_tags & CREATOR_KEYWORDS)
            creator_relevance = min(1.0, creator_hits / 3)

            # Cluster size bonus
            size_bonus = min(0.2, len(sigs) * 0.05)

            # Overall score (0-1)
            score = (
                0.30 * freshness
                + 0.25 * diversity
                + 0.20 * growth
                + 0.15 * creator_relevance
                + 0.10 * size_bonus / 0.2  # Normalize to 0-1
            )

            # Creator angle
            creator_angle = self._make_creator_angle(key, all_tags, sigs)

            trends.append({
                "key": key,
                "score": round(score, 3),
                "signals": [{"id": s["id"], "title": s["title"]} for s in sigs[:5]],
                "creator_angle": creator_angle,
                "signal_count": len(sigs),
                "freshness": round(freshness, 2),
                "diversity": round(diversity, 2),
                "growth": round(growth, 2),
                "creator_relevance": round(creator_relevance, 2),
                "tags": list(all_tags)[:10],
            })

        trends.sort(key=lambda t: t["score"], reverse=True)
        result = trends[:25]

        save_json(TRENDS_FILE, {
            "generated_at": int(time.time()),
            "count": len(result),
            "trends": result,
        })

        return result

    def _make_creator_angle(self, key: str, tags: set, sigs: list[dict]) -> str:
        """Generate a short creator angle for this trend."""
        builder_tags = tags & CREATOR_KEYWORDS
        if builder_tags:
            return f"Builders working on {key} can leverage {', '.join(list(builder_tags)[:3])}"
        top_title = sigs[0]["title"] if sigs else key
        return f"Trend in {key}: {top_title[:80]}"
