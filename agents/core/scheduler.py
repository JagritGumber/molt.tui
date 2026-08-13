"""
Scheduler — US-timezone-aware task loop for the X agent.

Knows when the US East Coast is awake, enforces minimum gaps between tasks,
adds jitter to all timings (anti-bot), and reduces activity on weekends.

Research-backed schedule:
  Tier 1: 9-11 AM ET  (peak engagement)
  Tier 2: 12-2 PM ET  (lunch break)
  Tier 3: 3-5 PM ET   (afternoon)
  Tier 4: 7-9 PM ET   (evening, weekdays only)
  Dead:   11 PM-7 AM ET

Posting: 2-4/day weekdays, 0-1 weekends. Tue-Thu is the power zone.
Trends:  Every 10-20 min during active hours.
Engage:  Every 1-2 hrs, 45-75 min sessions.
"""

import asyncio
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ── Active hours ──
ACTIVE_START = 7   # 7 AM ET
ACTIVE_END = 23    # 11 PM ET

# ── Minimum gaps (seconds) ──
MIN_GAPS = {
    "post": 2.5 * 3600,          # 2.5 hours between posts
    "analyze_trends": 10 * 60,   # 10 minutes
    "engage": 60 * 60,           # 1 hour
    "discover_reels": 2 * 3600,  # 2 hours between Instagram scrapes
    "download_reels": 30 * 60,   # 30 minutes between download batches
    "post_reel": 1.5 * 3600,     # 1.5 hours between reel posts (3-5/day)
}

# ── Jitter range (fraction of interval) ──
JITTER_FRACTION = 0.20  # +/- 20%

# ── Weekend config ──
WEEKEND_MAX_POSTS = 1
SUNDAY_EVENING_START = 18  # Sunday posts only after 6 PM

# ── Post slots by day-of-week (0=Mon, 6=Sun) ──
# Weights determine how many posts per day (higher = more)
DAY_POST_WEIGHTS = {
    0: 3,  # Monday
    1: 4,  # Tuesday (best day)
    2: 4,  # Wednesday
    3: 4,  # Thursday
    4: 2,  # Friday
    5: 0,  # Saturday (skip or 1 max)
    6: 1,  # Sunday (evening only)
}

# Post time tiers (hour ranges, ET)
POST_TIERS = [
    (9, 11),   # Tier 1 - morning peak
    (12, 14),  # Tier 2 - lunch
    (15, 17),  # Tier 3 - afternoon
    (19, 21),  # Tier 4 - evening
]


class Scheduler:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._task_history: dict[str, list[datetime]] = {}

    def is_active(self, t: datetime) -> bool:
        """Is the given time within US ET active hours?"""
        et_time = t.astimezone(ET)
        hour = et_time.hour
        return ACTIVE_START <= hour < ACTIVE_END

    def record_task(self, task_type: str, t: datetime):
        """Record that a task ran at time t."""
        if task_type not in self._task_history:
            self._task_history[task_type] = []
        self._task_history[task_type].append(t)

    def can_run(self, task_type: str, t: datetime) -> bool:
        """Check if enough time has passed since last task of this type."""
        history = self._task_history.get(task_type, [])
        if not history:
            return True
        last = max(history)
        gap = (t - last).total_seconds()
        min_gap = MIN_GAPS.get(task_type, 600)
        return gap >= min_gap

    def get_day_schedule(self, date: datetime) -> list[dict]:
        """Generate a full day's task schedule for the given date."""
        et_date = date.astimezone(ET)
        dow = et_date.weekday()  # 0=Mon, 6=Sun
        tasks = []

        # ── Posts ──
        post_count = DAY_POST_WEIGHTS.get(dow, 2)
        if dow == 5:
            # Saturday: 0-1 posts
            post_count = random.randint(0, WEEKEND_MAX_POSTS)
        elif dow == 6:
            # Sunday: 1 evening post only
            post_count = 1

        posts_added = 0
        if dow == 6:
            # Sunday: only evening tier
            hour = random.randint(SUNDAY_EVENING_START, 21)
            minute = random.randint(0, 59)
            tasks.append({"type": "post", "hour": hour, "minute": minute})
            posts_added = 1
        else:
            # Distribute posts across tiers, favoring Tier 1
            available_tiers = list(POST_TIERS)
            # Friday: skip evening tier
            if dow == 4:
                available_tiers = available_tiers[:3]
            random.shuffle(available_tiers)
            for i in range(min(post_count, len(available_tiers))):
                tier_start, tier_end = available_tiers[i]
                hour = random.randint(tier_start, tier_end - 1)
                minute = random.randint(0, 59)
                tasks.append({"type": "post", "hour": hour, "minute": minute})
                posts_added += 1

            # Ensure at least 1 post in Tier 1 (morning peak) on power days
            if dow in (1, 2, 3) and posts_added > 0:
                morning_posts = [t for t in tasks if t["type"] == "post" and 9 <= t["hour"] <= 11]
                if not morning_posts:
                    # Replace last post with a morning one
                    tasks[-1] = {
                        "type": "post",
                        "hour": random.randint(9, 10),
                        "minute": random.randint(0, 59),
                    }

        # ── Trend analysis (every 10-20 min during active hours) ──
        if dow != 5 or random.random() < 0.3:  # Reduced on Saturday
            t = ACTIVE_START * 60  # Start in minutes
            end = ACTIVE_END * 60
            while t < end:
                hour = t // 60
                minute = t % 60
                tasks.append({"type": "analyze_trends", "hour": hour, "minute": minute})
                interval = random.randint(10, 20)
                t += interval

        # ── Engagement sessions ──
        if dow <= 4:  # Weekdays
            engage_count = random.randint(2, 4)
        elif dow == 5:
            engage_count = 0
        else:
            engage_count = 1

        engage_hours = random.sample(
            range(ACTIVE_START + 1, ACTIVE_END - 1),
            min(engage_count, ACTIVE_END - ACTIVE_START - 2),
        )
        for h in engage_hours:
            tasks.append({
                "type": "engage",
                "hour": h,
                "minute": random.randint(0, 59),
            })

        return sorted(tasks, key=lambda t: (t["hour"], t["minute"]))

    def get_next_n_times(self, task_type: str, base: datetime, n: int = 10) -> list[datetime]:
        """Get the next N scheduled times for a task type, with jitter."""
        times = []
        current = base
        base_interval = MIN_GAPS.get(task_type, 600)

        for _ in range(n):
            jitter = base_interval * random.uniform(-JITTER_FRACTION, JITTER_FRACTION)
            interval = max(60, base_interval + jitter)
            current = current + timedelta(seconds=interval)
            # Skip inactive hours
            while not self.is_active(current):
                current = current + timedelta(minutes=10)
            times.append(current)

        return times

    async def run(self, duration_seconds: int = 86400):
        """Main scheduler loop. Yields task events."""
        start = time.monotonic()

        while (time.monotonic() - start) < duration_seconds:
            now = datetime.now(ET)

            if not self.is_active(now):
                # Sleep until next active window
                yield {"type": "sleep", "time": now.isoformat(), "reason": "inactive_hours"}
                await asyncio.sleep(60)
                continue

            # Check what's due
            for task_type in ("analyze_trends", "post", "engage"):
                if self.can_run(task_type, now):
                    self.record_task(task_type, now)
                    event = {
                        "type": task_type,
                        "time": now.isoformat(),
                        "dry_run": self.dry_run,
                    }
                    yield event

                    if not self.dry_run:
                        # In real mode, tasks would execute here
                        pass

            # Tick every 30-90s with jitter
            await asyncio.sleep(random.uniform(30, 90))
