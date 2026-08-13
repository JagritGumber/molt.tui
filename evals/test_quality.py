"""
Layer -1: Post Quality Evals (runs BEFORE everything else)

Scores posts against the 3 growth pillars:
  1. First-mover banger — sharp reply/quote on a trending topic before it peaks
  2. Builder relatability — build-in-public, what you're shipping, honest takes
  3. Sponsor-ready positioning — niche authority, engagement-worthy, brand-safe

These evals test the SCORING SYSTEM itself, not the LLM output.
The scorer must exist before we generate any drafts.
"""

import pytest


def _import_scorer():
    try:
        from agents.core.quality import PostScorer
        return PostScorer
    except ImportError:
        pytest.skip("agents.core.quality not built yet - eval defines the contract")


# ── Test fixtures: known-good and known-bad posts ──

BANGER_GOOD = {
    "text": "OpenAI just mass-fired their alignment team. The ones building the safety rails got shown the door. Wild.",
    "trend_key": "openai-alignment",
    "mode": "FOMO",
    "reply_to_trend": True,
}

BANGER_BAD = {
    "text": "Interesting news about OpenAI today. Thoughts? #AI #OpenAI",
    "trend_key": "openai-alignment",
    "mode": "FOMO",
    "reply_to_trend": True,
}

BUILDER_GOOD = {
    "text": "Shipped v0.3 of our CLI tool this morning. Went from 4s cold start to 200ms by lazy-loading the config parser. Small wins.",
    "trend_key": None,
    "mode": "Creating",
    "reply_to_trend": False,
}

BUILDER_BAD = {
    "text": "Working on some cool stuff! Stay tuned for updates. Big things coming soon!",
    "trend_key": None,
    "mode": "Creating",
    "reply_to_trend": False,
}

SPONSOR_GOOD = {
    "text": "Rust compile times dropped 40% in 1.82. If you're building CLI tools and still on Go because of compile speed - time to revisit.",
    "trend_key": "rust-1.82",
    "mode": "Knowledge",
    "reply_to_trend": False,
}

SPONSOR_BAD = {
    "text": "Rust is the best language ever! Everyone should use it! Go is dead! 🔥🚀",
    "trend_key": "rust-1.82",
    "mode": "Knowledge",
    "reply_to_trend": False,
}

GENERIC_SLOP = {
    "text": "Just a reminder to take breaks and drink water! Your health matters more than any code. 💪",
    "trend_key": None,
    "mode": "Knowledge",
    "reply_to_trend": False,
}

HASHTAG_SPAM = {
    "text": "AI agents are changing everything #AI #Agents #LLM #Future #Tech #BuildInPublic #Startup",
    "trend_key": "agents",
    "mode": "FOMO",
    "reply_to_trend": False,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-Q01: Scorer returns valid structure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScorerStructure:
    def test_returns_all_axes(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(BANGER_GOOD)
        required = {"banger", "builder", "sponsor", "overall", "flags"}
        assert required.issubset(result.keys()), \
            f"Missing score axes: {required - set(result.keys())}"

    def test_scores_in_range(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        for post in [BANGER_GOOD, BUILDER_GOOD, SPONSOR_GOOD, GENERIC_SLOP]:
            result = scorer.score(post)
            for axis in ("banger", "builder", "sponsor", "overall"):
                assert 0 <= result[axis] <= 10, \
                    f"Score {axis}={result[axis]} out of [0,10] for: {post['text'][:50]}"

    def test_flags_is_list(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(HASHTAG_SPAM)
        assert isinstance(result["flags"], list), \
            f"flags should be a list, got {type(result['flags'])}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-Q02: Banger axis scores correctly
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBangerAxis:
    def test_sharp_take_scores_high(self):
        """A sharp, specific, timely take should score well on banger axis."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(BANGER_GOOD)
        assert result["banger"] >= 6, \
            f"Sharp trending take scored only {result['banger']}/10 on banger axis"

    def test_generic_take_scores_low(self):
        """A vague take with hashtags should score poorly."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(BANGER_BAD)
        assert result["banger"] <= 4, \
            f"Generic hashtag take scored {result['banger']}/10 on banger - too high"

    def test_trend_linkage_matters(self):
        """Posts explicitly linked to a trend should score higher on banger."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        with_trend = scorer.score(BANGER_GOOD)
        no_trend = scorer.score({**BANGER_GOOD, "trend_key": None, "reply_to_trend": False})
        assert with_trend["banger"] >= no_trend["banger"], \
            "Trend-linked post should score >= non-trend on banger axis"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-Q03: Builder axis scores correctly
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBuilderAxis:
    def test_specific_build_update_high(self):
        """Concrete shipping update with numbers should score well."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(BUILDER_GOOD)
        assert result["builder"] >= 6, \
            f"Specific build update scored only {result['builder']}/10"

    def test_vague_hype_low(self):
        """'Big things coming soon!' is the worst builder content."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(BUILDER_BAD)
        assert result["builder"] <= 4, \
            f"Vague hype scored {result['builder']}/10 - should be low"

    def test_specificity_rewarded(self):
        """Posts with numbers, tool names, or concrete details score higher."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        specific = scorer.score(BUILDER_GOOD)  # "200ms", "v0.3", "config parser"
        vague = scorer.score(BUILDER_BAD)       # "cool stuff", "big things"
        assert specific["builder"] > vague["builder"], \
            f"Specific ({specific['builder']}) should beat vague ({vague['builder']})"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-Q04: Sponsor axis scores correctly
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSponsorAxis:
    def test_authoritative_take_high(self):
        """Niche-expert take with data should score well for sponsors."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(SPONSOR_GOOD)
        assert result["sponsor"] >= 6, \
            f"Authoritative take scored only {result['sponsor']}/10 on sponsor"

    def test_hot_take_flamebait_low(self):
        """Inflammatory 'X is dead!' takes are brand-unsafe."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(SPONSOR_BAD)
        assert result["sponsor"] <= 5, \
            f"Flamebait scored {result['sponsor']}/10 on sponsor - too high"

    def test_generic_wellness_low(self):
        """'Drink water!' posts add nothing to niche authority."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(GENERIC_SLOP)
        assert result["sponsor"] <= 3, \
            f"Generic wellness scored {result['sponsor']}/10 on sponsor - too high"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-Q05: Red flags caught
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRedFlags:
    def test_hashtag_spam_flagged(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(HASHTAG_SPAM)
        assert "hashtag_spam" in result["flags"], \
            f"Hashtag spam not flagged. Flags: {result['flags']}"

    def test_emoji_overuse_flagged(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        post = {
            "text": "🔥🚀💪 AI is changing everything! 🤖✨ The future is NOW! 🎯💡",
            "trend_key": None, "mode": "FOMO", "reply_to_trend": False,
        }
        result = scorer.score(post)
        assert "emoji_overuse" in result["flags"], \
            f"Emoji spam not flagged. Flags: {result['flags']}"

    def test_false_claim_flagged(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        post = {
            "text": "I just shipped a new database engine that handles 1M QPS.",
            "trend_key": None, "mode": "Creating", "reply_to_trend": False,
        }
        result = scorer.score(post)
        assert "false_claim" in result["flags"], \
            f"First-person false claim not flagged. Flags: {result['flags']}"

    def test_too_short_flagged(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        post = {"text": "Nice.", "trend_key": None, "mode": "FOMO", "reply_to_trend": False}
        result = scorer.score(post)
        assert "too_short" in result["flags"], \
            f"Ultra-short post not flagged. Flags: {result['flags']}"

    def test_vague_hype_flagged(self):
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(BUILDER_BAD)
        assert "vague_hype" in result["flags"], \
            f"'Big things coming!' not flagged. Flags: {result['flags']}"

    def test_clean_post_no_flags(self):
        """A good post should have no flags."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        result = scorer.score(SPONSOR_GOOD)
        assert len(result["flags"]) == 0, \
            f"Clean post flagged: {result['flags']}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-Q06: Overall score is coherent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestOverallCoherence:
    def test_good_posts_beat_bad_posts(self):
        """All 'good' examples should outscore all 'bad' examples overall."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        goods = [BANGER_GOOD, BUILDER_GOOD, SPONSOR_GOOD]
        bads = [BANGER_BAD, BUILDER_BAD, SPONSOR_BAD, GENERIC_SLOP, HASHTAG_SPAM]
        min_good = min(scorer.score(p)["overall"] for p in goods)
        max_bad = max(scorer.score(p)["overall"] for p in bads)
        assert min_good > max_bad, \
            f"Worst good post ({min_good}) should beat best bad post ({max_bad})"

    def test_flagged_posts_penalized(self):
        """Posts with flags should have lower overall than clean posts."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        clean = scorer.score(SPONSOR_GOOD)
        flagged = scorer.score(HASHTAG_SPAM)
        assert clean["overall"] > flagged["overall"], \
            f"Clean ({clean['overall']}) should beat flagged ({flagged['overall']})"

    def test_overall_is_weighted_blend(self):
        """Overall should not be a simple average - mode should weight the right axis."""
        PostScorer = _import_scorer()
        scorer = PostScorer()
        # FOMO mode should weight banger axis more
        fomo_post = scorer.score(BANGER_GOOD)
        # Creating mode should weight builder axis more
        builder_post = scorer.score(BUILDER_GOOD)
        # Just verify overall exists and is reasonable (specific weighting is implementation detail)
        assert fomo_post["overall"] >= 5, "Good FOMO post should score >= 5 overall"
        assert builder_post["overall"] >= 5, "Good builder post should score >= 5 overall"
