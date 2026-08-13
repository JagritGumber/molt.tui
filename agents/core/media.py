"""
Media picker — decides what media type fits a draft, generates it.

Types:
  Images: terminal, code, tweet card, metrics, milestone, diagram
  Video: text animation, overlay on custom clip

Video is prioritized when custom clips exist in ~/.moltui/clips/.
X algorithm favors video > image > text-only.
"""

import random
from pathlib import Path

from agents.core.images import (
    make_terminal_image, make_code_card, make_tweet_card,
    make_metrics_card, make_milestone_card,
)

CLIPS_DIR = Path.home() / ".moltui" / "clips"

# Terminal scenarios
TERMINAL_TEMPLATES = [
    {
        "title": "moltui — agent engine",
        "lines": [
            "$ python agents/core/engine.py --windows",
            "  CDP: connected to Chrome/145.0",
            "  TRENDS: {trend_count} trends, top={trend_key} ({score})",
            "  DRAFT: generating...",
            "✓ DRAFT: queued (quality={quality})",
            "✓ POST: success!",
            "  ENGAGE: liked ({likes} actions)",
        ],
    },
    {
        "title": "cargo build — particle-sys",
        "lines": [
            "$ cargo build --release",
            "   Compiling particle-sys v0.3.1",
            "   Compiling wgpu v24.0.1",
            "✓ Finished release target in 14.2s",
            "",
            "$ ./target/release/particle-sys",
            "  particles: 50,000 @ 60fps",
            "✓ stable",
        ],
    },
    {
        "title": "pytest — evals",
        "lines": [
            "$ pytest evals/ -v --timeout=300",
            "  test_quality.py ............ 21 passed",
            "  test_scheduler.py .......... 20 passed",
            "  test_trends.py ............. 11 passed",
            "  test_engine.py ............. 4 passed",
            "",
            "✓ 66 passed, 0 failed in 336s",
        ],
    },
]

CODE_SNIPPETS = [
    {
        "label": "scheduler.py",
        "code": """def is_active(self, t: datetime) -> bool:
    et_time = t.astimezone(ET)
    hour = et_time.hour
    return 7 <= hour < 23""",
    },
    {
        "label": "quality.py",
        "code": """def _score_banger(self, text, has_trend, is_reply):
    score = 3.0
    if has_trend: score += 2.0
    if is_reply: score += 1.0
    score += _specificity_score(text) * 2.0
    score -= _count_hashtags(text) * 1.0
    return max(0, min(10, score))""",
    },
    {
        "label": "engine.py",
        "code": """async def run(self):
    while True:
        now = datetime.now(ET)
        if not self.scheduler.is_active(now):
            await asyncio.sleep(300)
            continue
        for task in ("analyze_trends", "post", "engage"):
            if self.scheduler.can_run(task, now):
                await self.dispatch(task)""",
    },
    {
        "label": "signals.py",
        "code": """async def fetch_all(self) -> list[dict]:
    signals = []
    signals += await self._fetch_hn()
    for src, url in RSS_FEEDS.items():
        signals += self._parse_rss(url, src)
    return self._dedupe(signals)[:200]""",
    },
]


def _has_custom_clips() -> bool:
    if not CLIPS_DIR.exists():
        return False
    clips = list(CLIPS_DIR.glob("*.mp4")) + list(CLIPS_DIR.glob("*.webm")) + list(CLIPS_DIR.glob("*.mov"))
    return len(clips) > 0


def _fill_terminal_template(tmpl: dict, trend_key: str = "tech") -> list[str]:
    return [
        line.format(
            trend_key=trend_key,
            trend_count=random.randint(15, 30),
            score=f"{random.uniform(0.5, 0.9):.2f}",
            quality=f"{random.uniform(5.5, 8.0):.1f}",
            likes=random.randint(2, 8),
        )
        for line in tmpl["lines"]
    ]


def pick_media_for_draft(draft: dict) -> str:
    """Generate media for a draft. Returns file path.

    Priority: video (if clips exist) > image.
    Video gets 9x more engagement than text-only on X.
    """
    text = draft.get("text", "")
    trend_key = draft.get("trend_key", "tech")

    # 40% chance of video if custom clips exist, otherwise always image
    if _has_custom_clips() and random.random() < 0.4:
        try:
            from agents.core.video import make_video_for_draft
            path = make_video_for_draft(draft)
            if path:
                return str(path)
        except Exception:
            pass

    # Image selection based on content
    build_words = {"built", "shipped", "deploy", "compile", "rust", "python", "agent", "engine", "benchmark", "test", "pass"}
    opinion_words = {"every", "just", "why", "stop", "nobody", "wrapper", "stupid", "sick", "hate", "love"}
    metric_words = {"signals", "trends", "score", "passed", "failed", "percent", "%", "ms", "fps"}

    has_build = any(w in text.lower() for w in build_words)
    has_opinion = any(w in text.lower() for w in opinion_words)
    has_metrics = any(w in text.lower() for w in metric_words)

    if has_metrics:
        return str(make_metrics_card([
            (str(random.randint(20, 50)), "signals"),
            (str(random.randint(10, 30)), "trends"),
            (f"{random.uniform(6, 9):.1f}", "quality"),
            (str(random.randint(1, 5)), "queued"),
        ], title="moltui agent"))

    if has_build:
        if random.random() < 0.5:
            tmpl = random.choice(TERMINAL_TEMPLATES)
            lines = _fill_terminal_template(tmpl, trend_key)
            return str(make_terminal_image(lines, title=tmpl["title"]))
        else:
            snippet = random.choice(CODE_SNIPPETS)
            return str(make_code_card(snippet["code"], filename_label=snippet["label"]))

    if has_opinion:
        # 50/50 tweet card vs text video
        if _has_custom_clips() and random.random() < 0.3:
            try:
                from agents.core.video import make_text_video
                return str(make_text_video(text, duration=6))
            except Exception:
                pass
        return str(make_tweet_card(text))

    # Default: random image type
    choice = random.choice(["terminal", "code", "tweet"])
    if choice == "terminal":
        tmpl = random.choice(TERMINAL_TEMPLATES)
        lines = _fill_terminal_template(tmpl, trend_key)
        return str(make_terminal_image(lines, title=tmpl["title"]))
    elif choice == "code":
        snippet = random.choice(CODE_SNIPPETS)
        return str(make_code_card(snippet["code"], filename_label=snippet["label"]))
    else:
        return str(make_tweet_card(text))
