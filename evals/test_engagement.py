"""
Layer 5: Feed Engagement Evals

Tests tweet detection, liking, replying, scrolling, and human-like timing.
Requires browser + CDP.
"""

import asyncio
import time

import pytest

pytestmark = pytest.mark.browser


def _run(coro):
    return asyncio.run(coro)


def _import_twitter():
    try:
        from agents.core.twitter import TwitterPage
        return TwitterPage
    except ImportError:
        pytest.skip("agents.core.twitter not built yet")


def _import_browser():
    try:
        from agents.core.browser import BrowserManager
        return BrowserManager
    except ImportError:
        pytest.skip("agents.core.browser not built yet")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-050: Tweet detection in feed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTweetDetection:
    def test_find_tweets(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()
            tweets = await tw.get_visible_tweets()
            assert len(tweets) >= 5, \
                f"Expected >= 5 tweets in feed, got {len(tweets)}"
            # Each tweet should have text content
            for t in tweets[:5]:
                assert t.get("text"), f"Tweet has no text: {t}"
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-051: Like action
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLikeAction:
    @pytest.mark.destructive
    def test_like_tweet(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()

            # Find an unliked tweet and like it
            liked = await tw.like_first_unliked()
            assert liked, "Could not find or like an unliked tweet"
            # Unlike it to clean up
            await tw.unlike_last_liked()
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-052: Reply action (DESTRUCTIVE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestReplyAction:
    @pytest.mark.destructive
    def test_reply_to_tweet(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()

            marker = f"__eval_reply_{int(time.time())}__"
            replied = await tw.reply_to_first_tweet(f"test {marker}")
            assert replied, "Reply action failed"

            # Clean up - delete the reply
            await asyncio.sleep(3)
            deleted = await tw.delete_latest_post()
            assert deleted, "Failed to delete test reply"
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-053: Scroll loads new tweets
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestScrollBehavior:
    def test_scroll_loads_new_content(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()

            before = await tw.get_visible_tweet_ids()
            await tw.human_scroll(times=3)
            after = await tw.get_visible_tweet_ids()

            new_tweets = set(after) - set(before)
            assert len(new_tweets) >= 1, \
                "Scrolling didn't load any new tweets"
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-054: Human-like timing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHumanTiming:
    def test_action_delays_are_human(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()

            timestamps = []
            for _ in range(6):
                timestamps.append(time.monotonic())
                await tw.human_scroll(times=1)

            intervals = [
                timestamps[i+1] - timestamps[i]
                for i in range(len(timestamps) - 1)
            ]

            # No action faster than 0.5s
            assert all(i >= 0.5 for i in intervals), \
                f"Action too fast: {min(intervals):.2f}s (min 0.5s)"

            # Average should be >= 2s (not rushing)
            avg = sum(intervals) / len(intervals)
            assert avg >= 2.0, \
                f"Average interval {avg:.1f}s too fast (min 2.0s)"

            # Not all identical (robotic)
            rounded = [round(i, 1) for i in intervals]
            assert len(set(rounded)) > 1, \
                f"All intervals identical: {rounded} - robotic timing"

            await mgr.close()

        _run(_test())
