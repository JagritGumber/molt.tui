"""
Layer 2: Trend Analysis Pipeline Evals

No browser needed. Tests signal aggregation + trend clustering.
Only needs internet access for HN/RSS feeds.
"""

import asyncio
import time

import pytest

pytestmark = pytest.mark.network


def _run(coro):
    return asyncio.run(coro)


def _import_signals():
    try:
        from agents.core.signals import SignalFeeder
        return SignalFeeder
    except ImportError:
        pytest.skip("agents.core.signals not built yet - eval defines the contract")


def _import_trends():
    try:
        from agents.core.trends import TrendAnalyzer
        return TrendAnalyzer
    except ImportError:
        pytest.skip("agents.core.trends not built yet - eval defines the contract")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-020: Signal aggregation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSignalAggregation:
    def test_produces_signals(self):
        SignalFeeder = _import_signals()

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            assert len(signals) >= 10, \
                f"Expected >= 10 signals, got {len(signals)}"

        _run(_test())

    def test_signal_schema(self):
        SignalFeeder = _import_signals()
        required_fields = {"id", "source", "title", "timestamp", "tags"}

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            for s in signals[:10]:  # Check first 10
                missing = required_fields - set(s.keys())
                assert not missing, \
                    f"Signal missing fields: {missing}. Got: {list(s.keys())}"

        _run(_test())

    def test_source_diversity(self):
        """Must have signals from at least 2 different source types."""
        SignalFeeder = _import_signals()

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            source_types = {s.get("source_type", s.get("source")) for s in signals}
            assert len(source_types) >= 2, \
                f"Only 1 source type: {source_types}. Need diversity."

        _run(_test())

    def test_completes_within_timeout(self):
        """Signal fetch must complete within 120 seconds."""
        SignalFeeder = _import_signals()

        async def _test():
            feeder = SignalFeeder()
            start = time.monotonic()
            await feeder.fetch_all()
            elapsed = time.monotonic() - start
            assert elapsed < 120, \
                f"Signal fetch took {elapsed:.0f}s, max is 120s"

        _run(_test())

    def test_deduplication(self):
        """Running twice shouldn't produce duplicate signal IDs."""
        SignalFeeder = _import_signals()

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            ids = [s["id"] for s in signals]
            assert len(ids) == len(set(ids)), \
                f"Duplicate signal IDs found: {len(ids)} total, {len(set(ids))} unique"

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-021: Trend clustering
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTrendClustering:
    def test_produces_trends(self):
        SignalFeeder = _import_signals()
        TrendAnalyzer = _import_trends()

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            analyzer = TrendAnalyzer()
            trends = analyzer.analyze(signals)
            assert len(trends) >= 3, \
                f"Expected >= 3 trends, got {len(trends)}"

        _run(_test())

    def test_trend_schema(self):
        SignalFeeder = _import_signals()
        TrendAnalyzer = _import_trends()
        required_fields = {"key", "score", "signals", "creator_angle"}

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            analyzer = TrendAnalyzer()
            trends = analyzer.analyze(signals)
            for t in trends[:5]:
                missing = required_fields - set(t.keys())
                assert not missing, \
                    f"Trend missing fields: {missing}. Got: {list(t.keys())}"

        _run(_test())

    def test_scores_in_range(self):
        SignalFeeder = _import_signals()
        TrendAnalyzer = _import_trends()

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            analyzer = TrendAnalyzer()
            trends = analyzer.analyze(signals)
            for t in trends:
                assert 0 <= t["score"] <= 1, \
                    f"Trend '{t['key']}' score {t['score']} out of [0,1] range"

        _run(_test())

    def test_at_least_one_decent_trend(self):
        """At least 1 trend should score above 0.3 (something worth engaging)."""
        SignalFeeder = _import_signals()
        TrendAnalyzer = _import_trends()

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            analyzer = TrendAnalyzer()
            trends = analyzer.analyze(signals)
            top_score = max(t["score"] for t in trends) if trends else 0
            assert top_score >= 0.3, \
                f"No trend scored above 0.3, top was {top_score:.2f}"

        _run(_test())

    def test_clustering_within_timeout(self):
        """Trend analysis must complete within 30 seconds."""
        SignalFeeder = _import_signals()
        TrendAnalyzer = _import_trends()

        async def _test():
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            analyzer = TrendAnalyzer()
            start = time.monotonic()
            analyzer.analyze(signals)
            elapsed = time.monotonic() - start
            assert elapsed < 30, \
                f"Trend analysis took {elapsed:.0f}s, max is 30s"

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-022: Full pipeline timing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPipelineTiming:
    def test_end_to_end_within_5_minutes(self):
        SignalFeeder = _import_signals()
        TrendAnalyzer = _import_trends()

        async def _test():
            start = time.monotonic()
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            analyzer = TrendAnalyzer()
            trends = analyzer.analyze(signals)
            elapsed = time.monotonic() - start
            assert elapsed < 300, \
                f"Full pipeline took {elapsed:.0f}s, max is 300s (5 min)"
            # Also verify output is usable
            assert len(trends) >= 1, "Pipeline produced no trends"

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-023: Freshness (no stale cache)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFreshness:
    @pytest.mark.slow
    def test_signals_change_over_time(self):
        """Run twice 10 min apart - signals should differ (new data)."""
        SignalFeeder = _import_signals()

        async def _test():
            feeder = SignalFeeder()
            run1 = await feeder.fetch_all()
            ids1 = {s["id"] for s in run1}

            # Wait 10 minutes
            await asyncio.sleep(600)

            run2 = await feeder.fetch_all()
            ids2 = {s["id"] for s in run2}

            new_ids = ids2 - ids1
            assert len(new_ids) >= 1, \
                "No new signals after 10 min - data may be stale/cached"

        _run(_test())
