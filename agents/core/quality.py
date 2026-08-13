"""
Post Quality Scorer — scores drafts against the 3 growth pillars.

Axes:
  banger  (0-10): Sharp, timely, first-mover take on a trending topic
  builder (0-10): Specific build-in-public content with concrete details
  sponsor (0-10): Niche authority, brand-safe, engagement-worthy
  overall (0-10): Weighted blend based on post mode

Flags: list of red-flag strings that should block or penalize a post.

No LLM needed — this is a heuristic scorer for fast, deterministic gating.
"""

import re

# ── Red flag detectors ──

_HASHTAG_RE = re.compile(r"#\w+")
_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    r"\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    r"\u2600-\u26FF\u2700-\u27BF]"
)
_FALSE_CLAIM_STARTERS = [
    "i just built", "i just shipped", "i just launched", "i created",
    "i shipped", "i launched", "my new project", "i've been working on",
    "just released my", "i made a",
]
_VAGUE_HYPE = [
    "big things coming", "stay tuned", "something big", "can't wait to share",
    "exciting news", "huge announcement", "game changer", "mind blown",
    "this changes everything",
]
_LOW_EFFORT_ENDINGS = ["thoughts?", "what do you think?", "agree?", "right?", "no?"]
_GENERIC_OPENERS = [
    "interesting news", "just saw", "wow", "breaking:", "this is huge",
    "this is interesting",
]
_SPECIFICITY_SIGNALS = [
    r"\d+%", r"\d+ms", r"\d+s\b", r"\d+x\b", r"v\d+\.\d+", r"\d+k\b",
    r"\d+M\b", r"\d+ QPS", r"\d+ req", r"\d+ users",
]
_BUILDER_VERBS = [
    "shipped", "built", "deployed", "migrated", "refactored", "optimized",
    "reduced", "improved", "fixed", "rewrote", "benchmarked", "profiled",
]
_NICHE_KEYWORDS = [
    "rust", "typescript", "postgres", "redis", "wasm", "llm", "inference",
    "compile", "latency", "throughput", "cold start", "benchmark", "cli",
    "api", "sdk", "agent", "runtime", "serverless", "edge", "gpu",
]
_BRAND_UNSAFE = [
    "is dead", "is trash", "sucks", "garbage", "worst", "hate",
    "clown", "scam", "fraud",
]


def _count_hashtags(text: str) -> int:
    return len(_HASHTAG_RE.findall(text))


def _count_emojis(text: str) -> int:
    return len(_EMOJI_RE.findall(text))


def _has_false_claim(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in _FALSE_CLAIM_STARTERS)


def _has_vague_hype(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in _VAGUE_HYPE)


def _specificity_score(text: str) -> float:
    """Count concrete details (numbers, versions, metrics). 0-1 scale."""
    hits = sum(1 for p in _SPECIFICITY_SIGNALS if re.search(p, text, re.I))
    return min(1.0, hits / 3)


def _builder_verb_count(text: str) -> int:
    lower = text.lower()
    return sum(1 for v in _BUILDER_VERBS if v in lower)


def _niche_keyword_count(text: str) -> int:
    lower = text.lower()
    return sum(1 for k in _NICHE_KEYWORDS if k in lower)


def _brand_safety(text: str) -> float:
    """1.0 = safe, 0.0 = very unsafe."""
    lower = text.lower()
    hits = sum(1 for p in _BRAND_UNSAFE if p in lower)
    return max(0.0, 1.0 - hits * 0.3)


class PostScorer:
    """Deterministic post quality scorer. No LLM, no network."""

    def score(self, post: dict) -> dict:
        text = post.get("text", "")
        mode = post.get("mode", "FOMO")
        has_trend = bool(post.get("trend_key"))
        is_reply = bool(post.get("reply_to_trend"))

        flags = self._detect_flags(text)
        banger = self._score_banger(text, has_trend, is_reply)
        builder = self._score_builder(text)
        sponsor = self._score_sponsor(text)

        # Penalty for flags
        flag_penalty = len(flags) * 1.5

        # Weighted blend based on mode
        if mode == "FOMO":
            overall = 0.50 * banger + 0.20 * builder + 0.30 * sponsor
        elif mode == "Creating":
            overall = 0.20 * banger + 0.50 * builder + 0.30 * sponsor
        else:  # Knowledge
            overall = 0.25 * banger + 0.25 * builder + 0.50 * sponsor

        overall = max(0, min(10, overall - flag_penalty))

        return {
            "banger": round(banger, 1),
            "builder": round(builder, 1),
            "sponsor": round(sponsor, 1),
            "overall": round(overall, 1),
            "flags": flags,
        }

    def _detect_flags(self, text: str) -> list[str]:
        flags = []
        if _count_hashtags(text) >= 3:
            flags.append("hashtag_spam")
        if _count_emojis(text) >= 4:
            flags.append("emoji_overuse")
        if _has_false_claim(text):
            flags.append("false_claim")
        if len(text.strip()) < 15:
            flags.append("too_short")
        if _has_vague_hype(text):
            flags.append("vague_hype")
        return flags

    def _score_banger(self, text: str, has_trend: bool, is_reply: bool) -> float:
        """Sharp, timely, first-mover quality."""
        score = 3.0  # Baseline

        # Trend linkage
        if has_trend:
            score += 2.0
        if is_reply:
            score += 1.0

        # Brevity is power for bangers (sweet spot: 40-140 chars)
        length = len(text)
        if 40 <= length <= 140:
            score += 1.5
        elif length <= 200:
            score += 0.5

        # Specificity (names, numbers = sharp take)
        score += _specificity_score(text) * 2.0

        # Niche relevance
        niche = _niche_keyword_count(text)
        score += min(1.5, niche * 0.5)

        # Penalize hashtags and emojis (real bangers never use hashtags)
        score -= _count_hashtags(text) * 1.0
        score -= _count_emojis(text) * 0.3

        # Penalize vagueness
        if _has_vague_hype(text):
            score -= 2.0

        # Penalize low-effort endings ("Thoughts?", "Agree?")
        lower = text.lower().strip()
        if any(lower.endswith(e) for e in _LOW_EFFORT_ENDINGS):
            score -= 2.0

        # Penalize generic openers ("Interesting news about...")
        if any(lower.startswith(g) for g in _GENERIC_OPENERS):
            score -= 2.0

        return max(0, min(10, score))

    def _score_builder(self, text: str) -> float:
        """Build-in-public specificity and relatability."""
        score = 2.0

        # Builder verbs (shipped, built, deployed, etc.)
        verbs = _builder_verb_count(text)
        score += min(3.0, verbs * 1.5)

        # Specificity (numbers, versions, metrics)
        score += _specificity_score(text) * 3.0

        # Niche keywords
        niche = _niche_keyword_count(text)
        score += min(2.0, niche * 0.7)

        # Penalize vague hype heavily on builder axis
        if _has_vague_hype(text):
            score -= 3.0

        # Penalize hashtags
        score -= _count_hashtags(text) * 0.5

        # Length sweet spot for builder posts: 80-240 chars
        length = len(text)
        if 80 <= length <= 240:
            score += 1.0

        return max(0, min(10, score))

    def _score_sponsor(self, text: str) -> float:
        """Niche authority + brand safety + engagement quality."""
        score = 3.0

        # Niche authority (keywords show domain expertise)
        niche = _niche_keyword_count(text)
        score += min(3.0, niche * 1.0)

        # Brand safety
        safety = _brand_safety(text)
        score += safety * 2.0

        # Specificity signals authority
        score += _specificity_score(text) * 2.0

        # Penalize hashtag spam (looks amateur to sponsors)
        score -= _count_hashtags(text) * 0.7

        # Penalize emoji overuse (looks unprofessional)
        score -= _count_emojis(text) * 0.4

        # Penalize generic/wellness content (no niche value)
        if niche == 0 and _builder_verb_count(text) == 0:
            score -= 2.0

        return max(0, min(10, score))
