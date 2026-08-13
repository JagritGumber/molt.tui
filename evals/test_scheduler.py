"""
Layer 4: Scheduler Evals

No browser, no LLM, no internet needed. Tests the scheduling brain in isolation.
These should pass anywhere, anytime.
"""

import statistics
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

# -- The scheduler logic we're evaluating --
# This module will be created at agents/core/scheduler.py
# For now, these tests define the CONTRACT that scheduler must satisfy.

ET = ZoneInfo("America/New_York")

# ── Helpers to import scheduler (fail clearly if not built yet) ──

def _import_scheduler():
    try:
        from agents.core.scheduler import Scheduler
        return Scheduler
    except ImportError:
        pytest.skip("agents.core.scheduler not built yet - eval defines the contract")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-040: Timezone awareness
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTimezoneAwareness:
    """Scheduler must know when US East Coast is awake."""

    def test_3am_et_is_inactive(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        t = datetime(2026, 3, 31, 3, 0, tzinfo=ET)  # Tuesday 3 AM ET
        assert not s.is_active(t), "3 AM ET should be inactive (sleep hours)"

    def test_10am_et_is_active(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        t = datetime(2026, 3, 31, 10, 0, tzinfo=ET)  # Tuesday 10 AM ET
        assert s.is_active(t), "10 AM ET should be active (peak hours)"

    def test_6am_et_is_inactive(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        t = datetime(2026, 3, 31, 6, 0, tzinfo=ET)  # Tuesday 6 AM ET
        assert not s.is_active(t), "6 AM ET should be inactive (too early)"

    def test_11pm_et_is_inactive(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        t = datetime(2026, 3, 31, 23, 30, tzinfo=ET)  # Tuesday 11:30 PM ET
        assert not s.is_active(t), "11:30 PM ET should be inactive"

    def test_7am_et_boundary(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        t = datetime(2026, 3, 31, 7, 0, tzinfo=ET)
        # 7 AM is the earliest edge - scheduler decides (either active or ramp-up)
        # Just verify it doesn't crash
        result = s.is_active(t)
        assert isinstance(result, bool)

    def test_active_window_boundaries(self):
        """Active window should be roughly 7-8 AM to 10-11 PM ET."""
        Scheduler = _import_scheduler()
        s = Scheduler()
        # Definitely active
        for hour in [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]:
            t = datetime(2026, 3, 31, hour, 0, tzinfo=ET)
            assert s.is_active(t), f"{hour}:00 ET on Tuesday should be active"
        # Definitely inactive
        for hour in [0, 1, 2, 3, 4, 5]:
            t = datetime(2026, 3, 31, hour, 0, tzinfo=ET)
            assert not s.is_active(t), f"{hour}:00 ET should be inactive"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-041: Task interval spacing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTaskSpacing:
    """Scheduler must enforce minimum gaps between same-type tasks."""

    def test_post_too_soon_rejected(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        now = datetime(2026, 3, 31, 10, 0, tzinfo=ET)
        s.record_task("post", now)
        # 1 hour later - too soon (min 2-3hr gap for posts)
        assert not s.can_run("post", now + timedelta(hours=1)), \
            "Should not allow posting 1hr after last post"

    def test_post_after_gap_allowed(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        now = datetime(2026, 3, 31, 10, 0, tzinfo=ET)
        s.record_task("post", now)
        # 4 hours later - should be fine
        assert s.can_run("post", now + timedelta(hours=4)), \
            "Should allow posting 4hr after last post"

    def test_trend_analysis_high_frequency(self):
        """Trend analysis can run every 10-20 min, not restricted like posts."""
        Scheduler = _import_scheduler()
        s = Scheduler()
        now = datetime(2026, 3, 31, 10, 0, tzinfo=ET)
        s.record_task("analyze_trends", now)
        # 15 minutes later should be fine
        assert s.can_run("analyze_trends", now + timedelta(minutes=15)), \
            "Trend analysis should be allowed every 10-20 minutes"

    def test_engage_spacing(self):
        """Engagement sessions need 1-2hr gaps."""
        Scheduler = _import_scheduler()
        s = Scheduler()
        now = datetime(2026, 3, 31, 10, 0, tzinfo=ET)
        s.record_task("engage", now)
        # 30 min later - too soon
        assert not s.can_run("engage", now + timedelta(minutes=30)), \
            "Engagement too soon after last session"
        # 2 hours later - ok
        assert s.can_run("engage", now + timedelta(hours=2)), \
            "Engagement should be allowed 2hr after last session"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-042: Weekend behavior
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWeekendBehavior:
    """Weekends should be low activity. Saturday near-skip, Sunday evening only."""

    def test_saturday_reduced(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        # Saturday 10 AM ET
        sat = datetime(2026, 3, 28, 10, 0, tzinfo=ET)  # This is a Saturday
        tasks = s.get_day_schedule(sat)
        post_count = sum(1 for t in tasks if t["type"] == "post")
        assert post_count <= 1, f"Saturday should have at most 1 post, got {post_count}"

    def test_sunday_evening_slot(self):
        """Sunday should have a reflective evening slot around 7-9 PM."""
        Scheduler = _import_scheduler()
        s = Scheduler()
        sun = datetime(2026, 3, 29, 12, 0, tzinfo=ET)  # Sunday
        tasks = s.get_day_schedule(sun)
        post_tasks = [t for t in tasks if t["type"] == "post"]
        if post_tasks:
            # Any Sunday posts should be evening (after 6 PM)
            for t in post_tasks:
                assert t["hour"] >= 18, \
                    f"Sunday posts should be evening only, got hour={t['hour']}"

    def test_tuesday_is_power_day(self):
        """Tuesday should have the most posts (research says best day)."""
        Scheduler = _import_scheduler()
        s = Scheduler()
        tue = datetime(2026, 3, 31, 10, 0, tzinfo=ET)  # Tuesday
        sat = datetime(2026, 3, 28, 10, 0, tzinfo=ET)  # Saturday
        tue_tasks = s.get_day_schedule(tue)
        sat_tasks = s.get_day_schedule(sat)
        tue_posts = sum(1 for t in tue_tasks if t["type"] == "post")
        sat_posts = sum(1 for t in sat_tasks if t["type"] == "post")
        assert tue_posts > sat_posts, \
            f"Tuesday ({tue_posts} posts) should have more posts than Saturday ({sat_posts})"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-043: Jitter (anti-bot randomness)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestJitter:
    """All timing must have randomness. Robotic intervals = bot detection."""

    def test_trend_intervals_have_variance(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        base = datetime(2026, 3, 31, 9, 0, tzinfo=ET)  # Tuesday 9 AM
        times = s.get_next_n_times("analyze_trends", base, n=10)
        intervals = [
            (times[i+1] - times[i]).total_seconds()
            for i in range(len(times) - 1)
        ]
        # Intervals should vary - not all exactly the same
        assert len(set(int(i) for i in intervals)) > 1, \
            f"All intervals identical ({intervals[0]}s) - too robotic"
        # Standard deviation should be meaningful (> 60 seconds)
        if len(intervals) >= 3:
            sd = statistics.stdev(intervals)
            assert sd > 30, \
                f"Interval stddev={sd:.0f}s too low - needs more jitter (> 30s)"

    def test_post_times_not_on_the_hour(self):
        """Posts shouldn't always land on :00 or :30."""
        Scheduler = _import_scheduler()
        s = Scheduler()
        base = datetime(2026, 3, 31, 9, 0, tzinfo=ET)
        times = s.get_next_n_times("post", base, n=5)
        minutes = [t.minute for t in times]
        # Not all on the same minute
        assert len(set(minutes)) > 1, \
            f"All posts at minute={minutes[0]} - too predictable"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-044: Full day schedule shape
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestDayScheduleShape:
    """A full Tuesday schedule must match US engagement research."""

    def test_no_posts_during_sleep(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        tue = datetime(2026, 3, 31, 0, 0, tzinfo=ET)
        tasks = s.get_day_schedule(tue)
        for t in tasks:
            if t["type"] == "post":
                assert 7 <= t["hour"] <= 22, \
                    f"Post scheduled at {t['hour']}:00 - outside active hours"

    def test_post_count_weekday(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        tue = datetime(2026, 3, 31, 0, 0, tzinfo=ET)
        tasks = s.get_day_schedule(tue)
        post_count = sum(1 for t in tasks if t["type"] == "post")
        assert 2 <= post_count <= 4, \
            f"Weekday should have 2-4 posts, got {post_count}"

    def test_trend_analysis_frequency(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        tue = datetime(2026, 3, 31, 0, 0, tzinfo=ET)
        tasks = s.get_day_schedule(tue)
        trend_count = sum(1 for t in tasks if t["type"] == "analyze_trends")
        # Active hours ~15hrs, every 10-20 min = ~45-90 runs
        assert trend_count >= 30, \
            f"Expected 30+ trend analyses per day, got {trend_count}"

    def test_engagement_sessions_exist(self):
        Scheduler = _import_scheduler()
        s = Scheduler()
        tue = datetime(2026, 3, 31, 0, 0, tzinfo=ET)
        tasks = s.get_day_schedule(tue)
        engage_count = sum(1 for t in tasks if t["type"] == "engage")
        assert engage_count >= 1, "Should have at least 1 engagement session per day"

    def test_posts_favor_morning(self):
        """At least 1 post should be in Tier 1 (9-11 AM)."""
        Scheduler = _import_scheduler()
        s = Scheduler()
        tue = datetime(2026, 3, 31, 0, 0, tzinfo=ET)
        tasks = s.get_day_schedule(tue)
        morning_posts = [
            t for t in tasks
            if t["type"] == "post" and 9 <= t["hour"] <= 11
        ]
        assert len(morning_posts) >= 1, \
            "Should have at least 1 post in the 9-11 AM peak window"
