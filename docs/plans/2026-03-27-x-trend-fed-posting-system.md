# X Trend-Fed Creator-Centered Posting System Implementation Plan

> For Hermes: implement this plan task-by-task, reusing the existing zendriver-based X stack.

Goal: Build a trend-aware, creator-centered posting pipeline that gathers signals from X + external sources, ranks trends, chooses the best post mode (FOMO / Creating / Knowledge), queues a draft, and optionally posts it immediately.

Architecture: A feeder layer normalizes fresh signals from visible X ingest, Hacker News, RSS/news, and optional local artifacts into ~/.moltui/x-signals.json. A trend analyzer clusters and scores those signals into creator-relevant trends in ~/.moltui/x-trends.json. A JIT pipeline selects the strongest fresh trend, generates a creator-centered draft, writes it to ~/.moltui/tweet-drafts.json, and can hand off to x_post_runner.py for publication. A lightweight feedback collector updates posting-policy weights from recent post outcomes.

Tech Stack: Python stdlib, existing Z.ai API config in x_browser.py, existing X browser runners in /mnt/d/moltui/agents.

---

### Task 1: Create signal feeder
Objective: Normalize X ingest artifacts and external signal sources into one JSON feed.
Files:
- Create: /mnt/d/moltui/agents/x_signal_feeder.py
- Output: ~/.moltui/x-signals.json

### Task 2: Create trend analyzer
Objective: Cluster and score signals into creator-centered trends with recommended post modes.
Files:
- Create: /mnt/d/moltui/agents/x_trend_analyzer.py
- Output: ~/.moltui/x-trends.json

### Task 3: Create feedback collector
Objective: Update posting-policy weights from recent post outcomes.
Files:
- Create: /mnt/d/moltui/agents/x_feedback_collector.py
- Output: ~/.moltui/x-post-policy.json

### Task 4: Create JIT posting pipeline
Objective: Run feeder -> analyzer -> draft generation -> queue -> optional immediate post under one lock.
Files:
- Create: /mnt/d/moltui/agents/x_just_in_time_post.py
- Reuse: /mnt/d/moltui/agents/x_post_runner.py
- Output: ~/.moltui/tweet-drafts.json, ~/.moltui/x-jit-post-log.json

### Task 5: Add fast-post mode to x_post_runner
Objective: Allow JIT posting to skip the normal 120-180s randomized delay when freshness matters.
Files:
- Modify: /mnt/d/moltui/agents/x_post_runner.py

### Task 6: Verify with dry-run execution
Objective: Confirm feeder/trend/draft generation works without posting.
Files:
- Run: python3 agents/x_signal_feeder.py
- Run: python3 agents/x_trend_analyzer.py
- Run: python3 agents/x_just_in_time_post.py --dry-run

### Task 7: Wire future cron to JIT pipeline
Objective: Replace queue-only evening posting with just-in-time creator-centered posting once dry-run output looks strong.
Files:
- Update cron separately after verifying generated drafts and logs.
