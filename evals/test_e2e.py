"""
Layer 6: End-to-End Pipeline Evals

Tests the full flow: signals -> trends -> draft -> queue -> post.
Also includes the 1-hour soak test for scheduler stability.
"""

import asyncio
import os
import time

import pytest


def _run(coro):
    return asyncio.run(coro)


def _skip_if_missing(module_path, name):
    try:
        __import__(module_path)
    except ImportError:
        pytest.skip(f"{name} not built yet")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-060: Trend -> Draft -> Queue
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTrendToDraftToQueue:
    @pytest.mark.network
    @pytest.mark.llm
    def test_full_pipeline_queues_draft(self):
        _skip_if_missing("agents.core.signals", "signals")
        _skip_if_missing("agents.core.trends", "trends")
        _skip_if_missing("agents.core.drafts", "drafts")

        from agents.core.signals import SignalFeeder
        from agents.core.trends import TrendAnalyzer
        from agents.core.drafts import DraftGenerator

        async def _test():
            # Step 1: Signals
            feeder = SignalFeeder()
            signals = await feeder.fetch_all()
            assert len(signals) >= 1, "No signals"

            # Step 2: Trends
            analyzer = TrendAnalyzer()
            trends = analyzer.analyze(signals)
            assert len(trends) >= 1, "No trends"

            # Step 3: Pick best trend
            best = max(trends, key=lambda t: t["score"])

            # Step 4: Generate + critique
            gen = DraftGenerator()
            drafts = []
            for _ in range(3):
                d = await gen.generate(best)
                drafts.append(d)
            scored = await gen.critique(drafts)
            top_draft = max(scored, key=lambda d: d["overall"])

            # Step 5: Queue it
            queued = gen.queue_draft(top_draft, trend=best)
            assert queued, "Failed to queue draft"
            assert queued["status"] == "queued", \
                f"Expected status 'queued', got '{queued['status']}'"
            assert len(queued["text"]) >= 10, \
                f"Queued draft text too short: {len(queued['text'])} chars"
            assert queued.get("trend_key") == best["key"], \
                "Queued draft doesn't reference the trend"

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-061: Queue -> Post (DESTRUCTIVE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestQueueToPost:
    @pytest.mark.destructive
    @pytest.mark.browser
    def test_queue_dispatch_posts(self, cdp_port):
        _skip_if_missing("agents.core.twitter", "twitter")
        _skip_if_missing("agents.core.browser", "browser")
        _skip_if_missing("agents.core.drafts", "drafts")

        from agents.core.browser import BrowserManager
        from agents.core.twitter import TwitterPage
        from agents.core.drafts import DraftGenerator

        async def _test():
            # Seed queue with test draft
            gen = DraftGenerator()
            marker = f"__eval_e2e_{int(time.time())}__"
            test_draft = {
                "text": f"e2e eval pipeline test {marker}",
                "status": "queued",
                "trend_key": "eval-test",
                "draft_id": f"eval-{int(time.time())}",
            }
            gen.queue_draft(test_draft, raw=True)

            # Post it
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)

            posted = await tw.post_from_queue()
            assert posted, "post_from_queue returned False"

            # Verify
            await asyncio.sleep(5)
            found = await tw.verify_post_on_profile(marker)
            assert found, f"Posted tweet with marker '{marker}' not on profile"

            # Cleanup
            deleted = await tw.delete_latest_post()
            assert deleted, "Failed to delete e2e test tweet"

            # Verify queue entry updated
            entry = gen.get_queue_entry(test_draft["draft_id"])
            assert entry["status"] == "done", \
                f"Queue entry status is '{entry['status']}', expected 'done'"

            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-062: 1-Hour Soak Test (scheduler stability)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSoakTest:
    @pytest.mark.slow
    def test_scheduler_1hr_dry_run(self):
        """Scheduler runs for 1 hour in dry-run mode without crashing."""
        _skip_if_missing("agents.core.scheduler", "scheduler")

        from agents.core.scheduler import Scheduler
        import resource

        async def _test():
            s = Scheduler(dry_run=True)
            rss_start = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

            start = time.monotonic()
            task_log = []

            # Run scheduler loop for 1 hour
            async for event in s.run(duration_seconds=3600):
                task_log.append(event)
                elapsed = time.monotonic() - start
                if elapsed >= 3600:
                    break

            elapsed = time.monotonic() - start
            rss_end = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

            # Did it run the full hour?
            assert elapsed >= 3500, \
                f"Scheduler exited early at {elapsed:.0f}s (expected ~3600s)"

            # Were tasks scheduled?
            assert len(task_log) >= 10, \
                f"Only {len(task_log)} events in 1 hour - too few"

            # Memory check: RSS shouldn't double (leak indicator)
            rss_ratio = rss_end / max(rss_start, 1)
            assert rss_ratio < 2.0, \
                f"Memory grew {rss_ratio:.1f}x during soak test (possible leak)"

            # Check task diversity
            task_types = {e.get("type") for e in task_log}
            assert "analyze_trends" in task_types, \
                "No trend analysis scheduled in 1 hour"

        _run(_test())
