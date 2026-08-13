# X Agent Evaluation Spec

All times are **US Eastern (ET)**. Every eval is pass/fail with a clear success condition.

---

## Layer 0: Browser & Connection

### EVAL-001: CDP Connection
- **What**: Can we connect to Chrome via CDP?
- **Pass**: `zendriver.start()` returns a browser instance, `browser.get("about:blank")` loads
- **Fail**: Connection refused, timeout, or crash
- **Prereq**: Chrome running with `--remote-debugging-port=9222` on Windows

### EVAL-002: Twitter Reachable
- **What**: Can we navigate to twitter.com and land on a logged-in feed?
- **Pass**: Page loads, `[data-testid="primaryColumn"]` exists within 15s
- **Fail**: Login wall, captcha, suspension notice, or timeout
- **Prereq**: EVAL-001 passes, cookies/session persisted in Chrome profile

### EVAL-003: Page Interaction
- **What**: Can we scroll, find tweets, and read their content?
- **Pass**: `querySelectorAll('[data-testid="tweet"]')` returns >= 1 tweet, scroll changes `scrollTop`
- **Fail**: Empty feed, elements not found, scroll blocked

---

## Layer 1: Can It Post?

### EVAL-010: Compose Box Opens
- **What**: Click the compose button, does the modal appear?
- **Steps**:
  1. Click `[data-testid="SideNav_NewTweet_Button"]`
  2. Wait for `[data-testid="tweetTextarea_0"]` to appear (5s timeout)
- **Pass**: Textarea element found and focusable
- **Fail**: Modal doesn't open, selector not found, element not interactable

### EVAL-011: Text Entry
- **What**: Can we type text into the compose box?
- **Steps**:
  1. Open compose (EVAL-010)
  2. Insert text via DraftJS JS injection: `document.querySelector('[data-testid="tweetTextarea_0"] [contenteditable]')`
  3. Read back the text content
- **Pass**: Inserted text matches read-back text
- **Fail**: Text not inserted, DraftJS state not updated, compose box empty

### EVAL-012: Post Button Active
- **What**: After entering text, is the post button clickable?
- **Steps**:
  1. Complete EVAL-011
  2. Find `[data-testid="tweetButton"]` or `[data-testid="tweetButtonInline"]`
  3. Check `aria-disabled` is NOT "true"
- **Pass**: Post button exists and is enabled
- **Fail**: Button disabled, not found, or aria-disabled="true"

### EVAL-013: Post & Verify (DESTRUCTIVE - opt-in only)
- **What**: Actually post a tweet and verify it appeared
- **Steps**:
  1. Complete EVAL-012 with a unique marker text (e.g. `__eval_{timestamp}__`)
  2. Click post button
  3. Wait 5s, navigate to profile
  4. Check latest tweet contains the marker
  5. Delete the tweet
- **Pass**: Tweet found on profile with marker text, then deleted
- **Fail**: Post button click fails, tweet not found, delete fails
- **Flag**: `--destructive` required to run this eval

### EVAL-014: Compose Box Close/Cancel
- **What**: Can we close the compose modal without posting?
- **Steps**:
  1. Open compose (EVAL-010)
  2. Type some text (EVAL-011)
  3. Press Escape or click close button
  4. Handle "Discard" confirmation if it appears
- **Pass**: Modal closed, no tweet posted
- **Fail**: Modal stuck open, accidental post

---

## Layer 2: Trend Analysis Pipeline

### EVAL-020: Signal Aggregation
- **What**: Does the signal feeder produce valid output?
- **Steps**:
  1. Run signal aggregation (HN API + RSS feeds)
  2. Check output file exists and has valid JSON
- **Pass conditions** (ALL must be true):
  - Output has >= 10 signals
  - Each signal has: `id`, `source`, `title`, `timestamp`, `tags`
  - At least 2 different `source_type` values (diversity)
  - Completes within 120 seconds
- **Fail**: Empty output, invalid schema, single source, timeout

### EVAL-021: Trend Clustering
- **What**: Given signals, does trend analysis produce scored trends?
- **Steps**:
  1. Feed EVAL-020 output into trend analyzer
  2. Check output file exists and has valid JSON
- **Pass conditions**:
  - Output has >= 3 trends
  - Each trend has: `key`, `score` (0-1), `signals` (array), `creator_angle`
  - At least 1 trend with `score >= 0.3`
  - Completes within 30 seconds
- **Fail**: No trends, all scores 0, missing fields, timeout

### EVAL-022: Full Pipeline Timing
- **What**: End-to-end signals -> trends within time budget?
- **Steps**:
  1. Run signal aggregation
  2. Run trend clustering
  3. Measure wall-clock time
- **Pass**: Total time <= 5 minutes
- **Fail**: Exceeds 5 minutes
- **Note**: This determines the minimum interval for trend refresh

### EVAL-023: Trend Freshness
- **What**: Are trends actually fresh, not stale cached data?
- **Steps**:
  1. Run pipeline twice, 10 minutes apart
  2. Compare output
- **Pass**: At least 1 signal ID differs between runs (new data ingested)
- **Fail**: Identical output both times (stale cache or broken fetch)

---

## Layer 3: Draft Generation

### EVAL-030: Draft From Trend
- **What**: Given a trend, can the LLM generate a draft?
- **Steps**:
  1. Pick top trend from EVAL-021
  2. Call LLM with draft generation prompt
  3. Validate output
- **Pass conditions**:
  - Draft has `text` field, 10-280 chars
  - No hashtags (per style rules)
  - No first-person false claims
  - LLM responds within 30 seconds
- **Fail**: Empty response, LLM timeout, invalid format

### EVAL-031: Draft Critique
- **What**: Can the LLM score drafts on the rubric?
- **Steps**:
  1. Generate 3 drafts from EVAL-030
  2. Run critique on each
- **Pass conditions**:
  - Each draft gets `overall` score (0-10)
  - Scores are not all identical (LLM is discriminating)
  - Critique completes within 60 seconds for 3 drafts
- **Fail**: Missing scores, all same score, timeout

### EVAL-032: LLM Fallback
- **What**: What happens when Z.ai is unreachable?
- **Steps**:
  1. Set API URL to invalid endpoint
  2. Attempt draft generation
- **Pass**: Graceful failure with fallback draft or clear error (no crash, no hang)
- **Fail**: Unhandled exception, infinite retry loop, hang

---

## Layer 4: Scheduler

### EVAL-040: Timezone Awareness
- **What**: Does the scheduler correctly identify US ET active hours?
- **Steps**:
  1. Mock current time to 3:00 AM ET
  2. Ask scheduler: "should I be active?"
  3. Mock current time to 10:00 AM ET
  4. Ask scheduler: "should I be active?"
- **Pass**: 3 AM -> inactive, 10 AM -> active
- **Fail**: Wrong answer for either

### EVAL-041: Task Interval Spacing
- **What**: Does the scheduler enforce minimum gaps between same-type tasks?
- **Steps**:
  1. Record a "post" task at T=0
  2. Ask scheduler at T+1hr: "can I post?"
  3. Ask scheduler at T+4hr: "can I post?"
- **Pass**: T+1hr -> no (too soon, min 2-3hr gap), T+4hr -> yes
- **Fail**: Allows posting at T+1hr

### EVAL-042: Weekend Behavior
- **What**: Does the scheduler reduce activity on weekends?
- **Steps**:
  1. Mock to Saturday 10 AM ET
  2. Get scheduled tasks for the day
- **Pass**: Max 1 post scheduled, no engagement sessions, or full skip
- **Fail**: Full weekday schedule on Saturday

### EVAL-043: Jitter
- **What**: Are task times randomized (anti-bot)?
- **Steps**:
  1. Ask scheduler for next 10 trend-analysis times
  2. Check intervals between them
- **Pass**: Intervals vary (not all exactly 15 min), stddev > 60 seconds
- **Fail**: All intervals identical (robotic timing)

### EVAL-044: Daily Schedule Shape
- **What**: Does a full day schedule match the research?
- **Steps**:
  1. Mock to Tuesday (best day)
  2. Generate full day schedule
- **Pass conditions**:
  - Posts concentrated in Tier 1 (9-11 AM) and Tier 2 (12-2 PM)
  - No posts between 11 PM - 7 AM
  - 2-4 posts total
  - Trend analysis runs every 10-20 minutes during active hours
  - At least 1 engagement session scheduled
- **Fail**: Posts outside active hours, no trend analysis, zero engagement

---

## Layer 5: Engagement (Feed Interaction)

### EVAL-050: Tweet Detection
- **What**: Can we find and parse tweets in the feed?
- **Steps**:
  1. Load home feed
  2. Query `[data-testid="tweet"]` elements
  3. Extract text content from each
- **Pass**: >= 5 tweets found, each has non-empty text
- **Fail**: No tweets, empty text, selector failure

### EVAL-051: Like Action
- **What**: Can we like a tweet?
- **Steps**:
  1. Find an unliked tweet (like button not red/active)
  2. Click `[data-testid="like"]` within that tweet
  3. Verify button state changed (aria-pressed, color, or svg path change)
- **Pass**: Like button state flipped to "liked"
- **Fail**: Click fails, state doesn't change, wrong tweet liked

### EVAL-052: Reply Action (DESTRUCTIVE - opt-in)
- **What**: Can we open reply, type, and submit?
- **Steps**:
  1. Click `[data-testid="reply"]` on a tweet
  2. Wait for reply compose box
  3. Type reply text with eval marker
  4. Submit
  5. Verify reply appeared
  6. Delete reply
- **Pass**: Reply posted and deleted
- **Fail**: Reply box doesn't open, submit fails, can't delete
- **Flag**: `--destructive` required

### EVAL-053: Scroll Behavior
- **What**: Does scrolling load new tweets?
- **Steps**:
  1. Record tweet IDs visible on screen
  2. Scroll down 3 times with human-like delays
  3. Record new tweet IDs
- **Pass**: New tweets appeared that weren't in original set
- **Fail**: Same tweets, scroll doesn't trigger lazy load

### EVAL-054: Human Timing
- **What**: Are delays between actions humanlike?
- **Steps**:
  1. Record timestamps of 10 consecutive actions (scroll, like, scroll, like...)
  2. Calculate intervals
- **Pass**: All intervals >= 1s, mean interval >= 3s, stddev > 0.5s (not robotic)
- **Fail**: Any interval < 0.5s, all intervals identical

---

## Layer 6: End-to-End Pipeline

### EVAL-060: Trend-to-Draft-to-Queue
- **What**: Full pipeline: signals -> trends -> draft -> queued
- **Steps**:
  1. Run signal feeder
  2. Run trend analyzer
  3. Pick best trend
  4. Generate + critique drafts
  5. Queue best draft
- **Pass**: Draft appears in queue file with status "queued", valid text, trend reference
- **Fail**: Any step fails, empty queue

### EVAL-061: Queue-to-Post (DESTRUCTIVE - opt-in)
- **What**: Can the queue dispatcher pick a draft and post it?
- **Steps**:
  1. Seed queue with a test draft (eval marker text)
  2. Run post runner
  3. Verify tweet appeared on profile
  4. Delete tweet
  5. Verify queue entry marked "done"
- **Pass**: Tweet posted, deleted, queue updated
- **Fail**: Post fails, queue not updated, tweet stuck

### EVAL-062: 1-Hour Soak Test
- **What**: Does the scheduler run stable for 1 hour without crashing?
- **Steps**:
  1. Start scheduler in dry-run mode (logs actions but doesn't execute browser)
  2. Run for 60 minutes
  3. Check: no crashes, no memory leak (RSS stays within 2x of start), tasks scheduled correctly
- **Pass**: Clean exit or still running after 60 min, log shows expected task cadence
- **Fail**: Crash, OOM, no tasks scheduled, hung process

---

## Running Evals

```bash
# All non-destructive evals
cd /mnt/d/moltui
source .venv/bin/activate
pytest evals/ -v --timeout=300

# Include destructive (will post/delete real tweets)
pytest evals/ -v --timeout=300 --destructive

# Specific layer
pytest evals/test_post.py -v          # Layer 1 only
pytest evals/test_trends.py -v        # Layer 2 only
pytest evals/test_scheduler.py -v     # Layer 4 only (no browser needed)

# Soak test (long-running)
pytest evals/test_e2e.py::test_soak_1hr -v --timeout=3700
```

## Eval Dependencies

| Layer | Needs Browser? | Needs LLM? | Needs Internet? |
|-------|---------------|------------|-----------------|
| 0: Browser | Yes | No | Yes |
| 1: Posting | Yes | No | Yes |
| 2: Trends | No | No | Yes (HN/RSS) |
| 3: Drafts | No | Yes (Z.ai) | Yes |
| 4: Scheduler | No | No | No |
| 5: Engagement | Yes | Yes | Yes |
| 6: E2E | Yes | Yes | Yes |

Scheduler evals (Layer 4) can run anywhere, anytime - no external deps.
Trend evals (Layer 2) only need internet, no browser.
Post/Engagement evals need Chrome running with CDP.
