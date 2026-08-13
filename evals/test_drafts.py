"""
Layer 3: Draft Generation Evals

Tests LLM-powered draft creation and critique.
Needs Z.ai access but no browser.
"""

import asyncio
import time

import pytest

pytestmark = pytest.mark.llm


def _run(coro):
    return asyncio.run(coro)


def _import_drafts():
    try:
        from agents.core.drafts import DraftGenerator
        return DraftGenerator
    except ImportError:
        pytest.skip("agents.core.drafts not built yet - eval defines the contract")


def _import_llm():
    try:
        from agents.core.llm import LLMClient
        return LLMClient
    except ImportError:
        pytest.skip("agents.core.llm not built yet - eval defines the contract")


SAMPLE_TREND = {
    "key": "ai-agents",
    "score": 0.75,
    "signals": [
        {"title": "New AI agent framework released", "source": "hn"},
        {"title": "Building autonomous coding agents", "source": "rss"},
    ],
    "creator_angle": "Builders shipping agent tools are capturing the next wave",
    "mode": "Creating",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-030: Draft from trend
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestDraftGeneration:
    def test_generates_draft(self):
        DraftGenerator = _import_drafts()

        async def _test():
            gen = DraftGenerator()
            draft = await gen.generate(SAMPLE_TREND)
            assert draft is not None, "Draft generation returned None"
            assert "text" in draft, "Draft missing 'text' field"
            assert 10 <= len(draft["text"]) <= 280, \
                f"Draft length {len(draft['text'])} out of [10, 280] range"

        _run(_test())

    def test_no_hashtags(self):
        """Style rule: no hashtags in generated drafts."""
        DraftGenerator = _import_drafts()

        async def _test():
            gen = DraftGenerator()
            # Generate a few to increase confidence
            for _ in range(3):
                draft = await gen.generate(SAMPLE_TREND)
                assert "#" not in draft["text"], \
                    f"Draft contains hashtag: {draft['text']}"

        _run(_test())

    def test_no_false_claims(self):
        """Style rule: no first-person false claims like 'I just built...'"""
        DraftGenerator = _import_drafts()
        false_claim_patterns = [
            "i just built", "i created", "i shipped", "i launched",
            "my new project", "i've been working on",
        ]

        async def _test():
            gen = DraftGenerator()
            for _ in range(3):
                draft = await gen.generate(SAMPLE_TREND)
                lower = draft["text"].lower()
                for pattern in false_claim_patterns:
                    assert pattern not in lower, \
                        f"Draft has false claim '{pattern}': {draft['text']}"

        _run(_test())

    def test_generation_speed(self):
        """Single draft should complete within 30 seconds."""
        DraftGenerator = _import_drafts()

        async def _test():
            gen = DraftGenerator()
            start = time.monotonic()
            await gen.generate(SAMPLE_TREND)
            elapsed = time.monotonic() - start
            assert elapsed < 30, \
                f"Draft generation took {elapsed:.0f}s, max is 30s"

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-031: Draft critique
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestDraftCritique:
    def test_scores_drafts(self):
        DraftGenerator = _import_drafts()

        async def _test():
            gen = DraftGenerator()
            drafts = []
            for _ in range(3):
                d = await gen.generate(SAMPLE_TREND)
                drafts.append(d)

            scored = await gen.critique(drafts)
            assert len(scored) == 3, f"Expected 3 scored drafts, got {len(scored)}"
            for s in scored:
                assert "overall" in s, "Scored draft missing 'overall' field"
                assert 0 <= s["overall"] <= 10, \
                    f"Score {s['overall']} out of [0, 10] range"

        _run(_test())

    def test_scores_discriminate(self):
        """Scores shouldn't all be identical (LLM should differentiate)."""
        DraftGenerator = _import_drafts()

        async def _test():
            gen = DraftGenerator()
            drafts = []
            for _ in range(3):
                d = await gen.generate(SAMPLE_TREND)
                drafts.append(d)

            scored = await gen.critique(drafts)
            scores = [s["overall"] for s in scored]
            # At least 2 distinct scores across 3 drafts
            assert len(set(scores)) >= 2, \
                f"All scores identical: {scores}. LLM not discriminating."

        _run(_test())

    def test_critique_speed(self):
        """Critiquing 3 drafts should complete within 60 seconds."""
        DraftGenerator = _import_drafts()

        async def _test():
            gen = DraftGenerator()
            drafts = [
                {"text": "AI agents are eating software. The ones who build the tools win."},
                {"text": "Every startup is an AI wrapper until it isn't."},
                {"text": "Rust + WASM + agents = the stack nobody asked for but everyone needs."},
            ]
            start = time.monotonic()
            await gen.critique(drafts)
            elapsed = time.monotonic() - start
            assert elapsed < 60, \
                f"Critique of 3 drafts took {elapsed:.0f}s, max is 60s"

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-032: LLM fallback when Z.ai is down
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLLMFallback:
    def test_graceful_failure(self):
        LLMClient = _import_llm()

        async def _test():
            # Point at a dead endpoint
            client = LLMClient(api_url="http://localhost:1/fake")
            result = await client.generate("test prompt", timeout=5)
            # Should return None or a fallback, NOT raise or hang
            assert result is None or isinstance(result, str), \
                f"Expected None or fallback string, got {type(result)}"

        _run(_test())

    def test_no_infinite_retry(self):
        """Failed LLM call should not retry forever."""
        LLMClient = _import_llm()

        async def _test():
            client = LLMClient(api_url="http://localhost:1/fake")
            start = time.monotonic()
            await client.generate("test prompt", timeout=5)
            elapsed = time.monotonic() - start
            assert elapsed < 30, \
                f"LLM failure took {elapsed:.0f}s - possible infinite retry"

        _run(_test())
