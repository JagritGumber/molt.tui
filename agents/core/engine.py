"""
Engine — the main 24/7 loop that ties scheduler + tasks + browser together.

This is the single process that runs indefinitely:
  1. Scheduler decides what's due (trends, post, engage)
  2. Engine dispatches the task
  3. Task runs via browser or pure-compute
  4. Engine logs the result and loops

Usage:
  source .venv/bin/activate
  PYTHONPATH=. python agents/core/engine.py --windows
  PYTHONPATH=. python agents/core/engine.py --dry-run     # No browser, logs only
"""

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.core.config import (
    HOME, DRAFTS_FILE, SCHEDULER_LOG, POST_HISTORY,
    load_json, save_json, get_account_handle,
)
from agents.core.scheduler import Scheduler, ET
from agents.core.signals import SignalFeeder
from agents.core.trends import TrendAnalyzer
from agents.core.drafts import DraftGenerator
from agents.core.quality import PostScorer
from agents.core.llm import LLMClient

# ── Constants ──
STRONG_THRESHOLD = 5.0   # Minimum heuristic quality to queue (flags still block)
MAX_QUEUE_SIZE = 5        # Don't queue more than this many drafts
LOG_MAX_ENTRIES = 500     # Trim log file


def _log(msg: str):
    now = datetime.now(ET).strftime("%H:%M:%S ET")
    print(f"[{now}] {msg}", flush=True)


def _append_log(event: dict):
    log = load_json(SCHEDULER_LOG, [])
    log.append({**event, "logged_at": int(time.time())})
    if len(log) > LOG_MAX_ENTRIES:
        log = log[-LOG_MAX_ENTRIES:]
    save_json(SCHEDULER_LOG, log)


class Engine:
    def __init__(self, dry_run: bool = False, cdp_port: int = 9222, cdp_host: str = "localhost"):
        self.dry_run = dry_run
        self.cdp_port = cdp_port
        self.cdp_host = cdp_host
        self.scheduler = Scheduler(dry_run=dry_run)
        self.feeder = SignalFeeder()
        self.analyzer = TrendAnalyzer()
        self.drafter = DraftGenerator()
        self.scorer = PostScorer()
        self._browser = None
        self._twitter = None

    async def _get_browser(self):
        """Lazy-connect to browser. Returns None in dry-run."""
        if self.dry_run:
            return None
        if self._browser is None:
            from agents.core.browser import BrowserManager
            self._browser = BrowserManager(cdp_port=self.cdp_port, cdp_host=self.cdp_host)
            await self._browser.connect()
        return self._browser

    async def _get_twitter(self):
        """Lazy-init TwitterPage. Returns None in dry-run."""
        if self.dry_run:
            return None
        if self._twitter is None:
            mgr = await self._get_browser()
            if mgr and mgr.browser:
                from agents.core.twitter import TwitterPage
                self._twitter = TwitterPage(mgr.browser)
        return self._twitter

    # ── Task handlers ──

    async def task_analyze_trends(self):
        """Fetch signals, cluster trends, optionally generate drafts."""
        _log("TRENDS: fetching signals...")
        signals = await self.feeder.fetch_all()
        _log(f"TRENDS: got {len(signals)} signals")

        trends = self.analyzer.analyze(signals)
        _log(f"TRENDS: {len(trends)} trends, top={trends[0]['key'] if trends else 'none'} ({trends[0]['score']:.2f})" if trends else "TRENDS: no trends")

        _append_log({
            "type": "analyze_trends",
            "signal_count": len(signals),
            "trend_count": len(trends),
            "top_trend": trends[0]["key"] if trends else None,
            "top_score": trends[0]["score"] if trends else 0,
        })

        # If queue is low and no recent post, generate a draft
        queue = load_json(DRAFTS_FILE, [])
        queued_count = sum(1 for d in queue if d.get("status") == "queued")

        # Check if we posted recently (don't over-generate)
        history = load_json(POST_HISTORY, [])
        last_posted = max((h.get("posted_at", 0) for h in history), default=0) if history else 0
        hours_since_post = (int(time.time()) - last_posted) / 3600 if last_posted else 999

        if queued_count >= MAX_QUEUE_SIZE:
            _log(f"TRENDS: queue full ({queued_count} drafts), skipping generation")
        elif hours_since_post < 2.0 and queued_count >= 1:
            _log(f"TRENDS: posted {hours_since_post:.1f}h ago + {queued_count} in queue, skipping")
        elif trends:
            best = trends[0]
            if best["score"] >= 0.3:
                await self._generate_and_queue(best)

    async def _generate_and_queue(self, trend: dict):
        """Generate drafts for a trend, critique, queue the best one."""
        _log(f"DRAFT: generating for trend '{trend['key']}'...")
        drafts = []
        for i in range(3):
            d = await self.drafter.generate(trend)
            if d:
                drafts.append(d)
            _log(f"DRAFT: {i+1}/3 generated")

        if not drafts:
            _log("DRAFT: all generations failed")
            return

        scored = await self.drafter.critique(drafts)
        best = max(scored, key=lambda d: d.get("overall", 0))
        quality = self.scorer.score(best)

        _log(f"DRAFT: best score={best.get('overall', 0):.1f}, quality={quality['overall']:.1f}, flags={quality['flags']}")

        llm_score = best.get("overall", 0)
        # Dual gate: heuristic must pass threshold AND no flags, LLM must score >= 6
        passes_heuristic = quality["overall"] >= STRONG_THRESHOLD and not quality["flags"]
        passes_llm = llm_score >= 6.0

        if passes_heuristic and passes_llm:
            # Generate image for the post
            from agents.core.media import pick_media_for_draft
            image_path = pick_media_for_draft(best)
            best["media_path"] = image_path
            _log(f"DRAFT: image generated ({image_path.split('/')[-1]})")

            entry = self.drafter.queue_draft(best, trend=trend)
            _log(f"DRAFT: queued '{best['text'][:60]}...'")
            _append_log({
                "type": "draft_queued",
                "trend_key": trend["key"],
                "text_preview": best["text"][:80],
                "quality_score": quality["overall"],
                "llm_score": llm_score,
            })
        else:
            reasons = []
            if not passes_heuristic:
                reasons.append(f"heuristic={quality['overall']:.1f}<{STRONG_THRESHOLD}")
            if quality["flags"]:
                reasons.append(f"flags={quality['flags']}")
            if not passes_llm:
                reasons.append(f"llm={llm_score:.1f}<6.0")
            _log(f"DRAFT: rejected ({', '.join(reasons)})")
            _append_log({
                "type": "draft_rejected",
                "trend_key": trend["key"],
                "quality_score": quality["overall"],
                "llm_score": llm_score,
                "flags": quality["flags"],
            })

    async def task_post(self):
        """Post the next queued draft."""
        # Check when we last posted (survives restarts)
        history = load_json(POST_HISTORY, [])
        now_ts = int(time.time())
        if history:
            last_posted = max((h.get("posted_at", 0) for h in history), default=0)
            gap_hours = (now_ts - last_posted) / 3600
            if gap_hours < 2.5:
                _log(f"POST: too soon - last post was {gap_hours:.1f}h ago (min 2.5h)")
                return

        queue = load_json(DRAFTS_FILE, [])
        draft = None
        idx = -1

        for i, d in enumerate(queue):
            if d.get("status") == "queued" and d.get("not_before", 0) <= now_ts:
                draft = d
                idx = i
                break

        if not draft:
            _log("POST: no eligible drafts in queue")
            return

        if self.dry_run:
            _log(f"POST [DRY]: would post '{draft['text'][:60]}...'")
            queue[idx]["status"] = "dry-run"
            save_json(DRAFTS_FILE, queue)
            _append_log({"type": "post_dry", "text_preview": draft["text"][:80]})
            return

        _log(f"POST: attempting '{draft['text'][:60]}...'")
        tw = await self._get_twitter()
        if not tw:
            _log("POST: no browser connection")
            return

        try:
            await tw.go_home()
            media = draft.get("media_path", "")
            if media:
                _log(f"POST: attaching image {media.split('/')[-1]}")
            posted = await tw.compose_and_post(draft["text"], media_path=media or None)
            if posted:
                post_time = int(time.time())
                queue[idx]["status"] = "done"
                queue[idx]["posted_at"] = post_time
                save_json(DRAFTS_FILE, queue)
                # Save to persistent history (survives restarts)
                history = load_json(POST_HISTORY, [])
                history.append({
                    "text": draft["text"],
                    "posted_at": post_time,
                    "draft_id": draft.get("draft_id", ""),
                    "trend_key": draft.get("trend_key", ""),
                })
                if len(history) > 200:
                    history = history[-200:]
                save_json(POST_HISTORY, history)
                _log("POST: success!")
                _append_log({
                    "type": "post_success",
                    "text_preview": draft["text"][:80],
                    "draft_id": draft.get("draft_id", ""),
                })
            else:
                queue[idx]["status"] = "failed"
                save_json(DRAFTS_FILE, queue)
                _log("POST: failed to post (compose or click didn't work)")
                _append_log({"type": "post_failed", "draft_id": draft.get("draft_id", "")})
        except Exception as e:
            _log(f"POST: error - {e}")
            _append_log({"type": "post_error", "error": str(e)})

    async def task_engage(self):
        """Run a feed engagement session."""
        if self.dry_run:
            duration = random.randint(2, 5)
            _log(f"ENGAGE [DRY]: would scroll for {duration} min")
            _append_log({"type": "engage_dry", "duration_min": duration})
            return

        tw = await self._get_twitter()
        if not tw:
            _log("ENGAGE: no browser connection")
            return

        duration_min = random.randint(15, 30)
        _log(f"ENGAGE: starting {duration_min} min session")

        try:
            await tw.go_home()
            actions = 0
            errors = 0
            start = time.monotonic()

            while (time.monotonic() - start) < duration_min * 60:
                try:
                    await tw.human_scroll(times=random.randint(1, 3))
                    tweets = await tw.get_visible_tweets()

                    if tweets and random.random() < 0.3:
                        liked = await tw.like_first_unliked()
                        if liked:
                            actions += 1
                            _log(f"ENGAGE: liked ({actions} actions)")
                except Exception as e:
                    errors += 1
                    _log(f"ENGAGE: action error ({errors}): {e}")
                    if errors > 5:
                        break

                await asyncio.sleep(random.uniform(5, 15))

            _log(f"ENGAGE: session done, {actions} actions in {duration_min} min")
            _append_log({
                "type": "engage_done",
                "actions": actions,
                "duration_min": duration_min,
            })
        except Exception as e:
            _log(f"ENGAGE: error - {e}")
            _append_log({"type": "engage_error", "error": str(e)})

    # ── Reels pipeline ──

    async def task_discover_reels(self):
        """Scrape Instagram for new reel IDs via zendriver CDP."""
        _log("REELS: discovering from Instagram feed...")
        try:
            from agents.core.reels import discover_reels_via_cdp
            mgr = await self._get_browser()
            if mgr:
                urls = await discover_reels_via_cdp(cdp_host=mgr.cdp_host, cdp_port=mgr.cdp_port)
                _append_log({"type": "reels_discovered", "count": len(urls)})
            else:
                _log("REELS: no browser connection")
        except Exception as e:
            _log(f"REELS: discover error - {e}")

    async def task_download_reels(self):
        """Download discovered reels via yt-dlp."""
        from agents.core.reels import discover_reels, download_reel
        urls = discover_reels(count=2)
        if not urls:
            _log("REELS: no new reels to download")
            return
        for url in urls[:2]:
            _log(f"REELS: downloading {url.split('/')[-2]}...")
            path = download_reel(url)
            if path:
                _log(f"REELS: downloaded {path.name} ({path.stat().st_size // 1024} KB)")
            else:
                _log(f"REELS: download failed")

    async def task_process_and_post_reel(self):
        """Process a reel (add caption + watermark) and post to X."""
        from agents.core.reels import process_reel, get_unposted_reels, mark_posted, MOTIVATIONAL_CAPTIONS
        import glob

        # Check post history - don't post too frequently
        history = load_json(POST_HISTORY, [])
        now_ts = int(time.time())
        if history:
            last_posted = max((h.get("posted_at", 0) for h in history), default=0)
            gap_hours = (now_ts - last_posted) / 3600
            if gap_hours < 1.5:
                _log(f"REELS: too soon - last post was {gap_hours:.1f}h ago (min 1.5h)")
                return

        # Check for unprocessed raw reels
        from pathlib import Path
        raw_dir = Path.home() / ".moltui" / "reels"
        processed_dir = Path.home() / ".moltui" / "reels-processed"
        unposted = get_unposted_reels()

        if not unposted:
            # Process a raw reel
            raw_files = sorted(raw_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not raw_files:
                _log("REELS: no raw reels to process")
                return
            raw = raw_files[0]
            caption = random.choice(MOTIVATIONAL_CAPTIONS)
            _log(f"REELS: processing {raw.name} with: {caption[:50]}...")
            try:
                processed = process_reel(raw, caption)
                _log(f"REELS: processed → {processed.name}")
                unposted = [processed]
            except Exception as e:
                _log(f"REELS: processing error - {e}")
                return

        if self.dry_run:
            _log(f"REELS [DRY]: would post {unposted[0].name}")
            mark_posted(unposted[0])
            return

        # Post to X
        tw = await self._get_twitter()
        if not tw:
            _log("REELS: no browser connection")
            return

        video_path = str(unposted[0])
        caption = random.choice(MOTIVATIONAL_CAPTIONS)
        _log(f"REELS: posting {unposted[0].name} with: {caption[:50]}...")

        try:
            await tw.go_home()
            posted = await tw.compose_and_post(caption, media_path=video_path)
            if posted:
                mark_posted(unposted[0])
                post_time = int(time.time())
                history = load_json(POST_HISTORY, [])
                history.append({
                    "text": caption,
                    "media_path": video_path,
                    "posted_at": post_time,
                    "type": "reel",
                })
                if len(history) > 200:
                    history = history[-200:]
                save_json(POST_HISTORY, history)
                _log("REELS: posted!")
                _append_log({"type": "reel_posted", "caption": caption[:80]})
            else:
                _log("REELS: post failed")
        except Exception as e:
            _log(f"REELS: post error - {e}")

    # ── Main loop ──

    async def run(self):
        """Main 24/7 loop."""
        _log(f"Engine starting (dry_run={self.dry_run}, handle={get_account_handle() or '?'})")
        _log(f"Active hours: 7 AM - 11 PM ET")

        # Connect browser on startup (unless dry-run)
        if not self.dry_run:
            try:
                mgr = await self._get_browser()
                _log(f"Browser connected (CDP {mgr.cdp_host}:{mgr.cdp_port})")
            except Exception as e:
                _log(f"WARNING: Browser connection failed: {e}")
                _log("Will retry on first task that needs it")

        task_handlers = {
            "analyze_trends": self.task_analyze_trends,
            "post": self.task_post,
            "engage": self.task_engage,
            "discover_reels": self.task_discover_reels,
            "download_reels": self.task_download_reels,
            "post_reel": self.task_process_and_post_reel,
        }

        while True:
            now = datetime.now(ET)

            if not self.scheduler.is_active(now):
                _log(f"Sleeping (inactive hours: {now.strftime('%H:%M ET')})")
                await asyncio.sleep(random.uniform(300, 600))
                continue

            # Check what's due - reels pipeline runs alongside original tasks
            all_tasks = ("analyze_trends", "discover_reels", "download_reels", "post_reel", "post", "engage")
            for task_type in all_tasks:
                if self.scheduler.can_run(task_type, now):
                    self.scheduler.record_task(task_type, now)
                    handler = task_handlers[task_type]
                    try:
                        await handler()
                    except Exception as e:
                        _log(f"ERROR in {task_type}: {e}")
                        _append_log({
                            "type": "task_error",
                            "task_type": task_type,
                            "error": str(e),
                        })

            # Tick with jitter
            tick = random.uniform(30, 90)
            await asyncio.sleep(tick)


async def main():
    parser = argparse.ArgumentParser(description="X Agent Engine")
    parser.add_argument("--dry-run", action="store_true", help="Log only, no browser actions")
    parser.add_argument("--windows", action="store_true", help="Connect to Windows Chrome CDP")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP port")
    parser.add_argument("--cdp-host", type=str, default="localhost", help="CDP host")
    args = parser.parse_args()

    if args.windows:
        # WSL2: try localhost first, then gateway IP
        args.cdp_host = "localhost"

    engine = Engine(
        dry_run=args.dry_run,
        cdp_port=args.cdp_port,
        cdp_host=args.cdp_host,
    )
    await engine.run()


if __name__ == "__main__":
    asyncio.run(main())
