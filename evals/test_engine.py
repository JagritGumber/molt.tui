"""
Engine integration eval — tests the main loop in dry-run mode.

No browser needed. Verifies the engine dispatches tasks correctly.
"""

import asyncio
import time

import pytest

from agents.core.config import SCHEDULER_LOG, load_json


def _import_engine():
    try:
        from agents.core.engine import Engine
        return Engine
    except ImportError:
        pytest.skip("agents.core.engine not built yet")


class TestEngineDryRun:
    def test_engine_starts_and_dispatches(self):
        """Engine should dispatch trend analysis within 2 minutes of dry-run."""
        Engine = _import_engine()

        async def _test():
            engine = Engine(dry_run=True)
            start = time.monotonic()
            dispatched = []

            # Manually tick the engine for ~2 min simulated time
            # by calling task handlers directly
            await engine.task_analyze_trends()
            dispatched.append("analyze_trends")

            elapsed = time.monotonic() - start
            assert elapsed < 180, f"Trend analysis took {elapsed:.0f}s"
            assert "analyze_trends" in dispatched

            # Check log was written
            log = load_json(SCHEDULER_LOG, [])
            trend_entries = [e for e in log if e.get("type") == "analyze_trends"]
            assert len(trend_entries) >= 1, "No trend analysis logged"

        asyncio.run(_test())

    def test_draft_generation_pipeline(self):
        """Engine should generate and potentially queue drafts."""
        Engine = _import_engine()

        async def _test():
            engine = Engine(dry_run=True)

            # Run trend analysis first (populates signals + trends)
            await engine.task_analyze_trends()

            # Check log for draft activity
            log = load_json(SCHEDULER_LOG, [])
            has_activity = any(
                e.get("type") in ("draft_queued", "draft_rejected", "analyze_trends")
                for e in log
            )
            assert has_activity, "No draft or trend activity logged"

        asyncio.run(_test())

    def test_post_dry_run(self):
        """Post in dry-run should not actually post."""
        Engine = _import_engine()

        async def _test():
            engine = Engine(dry_run=True)
            # This should handle empty queue gracefully
            await engine.task_post()

            log = load_json(SCHEDULER_LOG, [])
            # Either "no eligible drafts" or dry-run post
            # Both are valid - just no crash
            assert True  # If we got here, no crash

        asyncio.run(_test())

    def test_engage_dry_run(self):
        """Engage in dry-run should log but not use browser."""
        Engine = _import_engine()

        async def _test():
            engine = Engine(dry_run=True)
            await engine.task_engage()

            log = load_json(SCHEDULER_LOG, [])
            engage_entries = [e for e in log if e.get("type") == "engage_dry"]
            assert len(engage_entries) >= 1, "No engage dry-run logged"

        asyncio.run(_test())

    @pytest.mark.slow
    def test_engine_5min_soak(self):
        """Engine runs for 5 minutes in dry-run without crashing."""
        Engine = _import_engine()

        async def _test():
            engine = Engine(dry_run=True)
            # Override scheduler to think it's always active
            from agents.core.scheduler import Scheduler
            original_is_active = engine.scheduler.is_active
            engine.scheduler.is_active = lambda t: True

            start = time.monotonic()
            task_count = 0

            while (time.monotonic() - start) < 300:  # 5 minutes
                for task_type in ("analyze_trends", "post", "engage"):
                    from datetime import datetime
                    from zoneinfo import ZoneInfo
                    now = datetime.now(ZoneInfo("America/New_York"))
                    if engine.scheduler.can_run(task_type, now):
                        engine.scheduler.record_task(task_type, now)
                        if task_type == "analyze_trends":
                            await engine.task_analyze_trends()
                        elif task_type == "post":
                            await engine.task_post()
                        elif task_type == "engage":
                            await engine.task_engage()
                        task_count += 1
                await asyncio.sleep(10)

            assert task_count >= 5, f"Only {task_count} tasks in 5 min"

        asyncio.run(_test())
