"""
Layer 1: Posting Evals

Tests the compose -> type -> post flow.
Non-destructive by default (stops before clicking Post).
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
        pytest.skip("agents.core.twitter not built yet - eval defines the contract")


def _import_browser():
    try:
        from agents.core.browser import BrowserManager
        return BrowserManager
    except ImportError:
        pytest.skip("agents.core.browser not built yet")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-010: Compose box opens
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestComposeBox:
    def test_compose_opens(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()
            opened = await tw.open_compose()
            assert opened, "Compose box did not open"
            # Verify textarea exists
            has_textarea = await page.evaluate(
                "!!document.querySelector('[data-testid=\"tweetTextarea_0\"]')"
            )
            assert has_textarea, "tweetTextarea_0 not found after opening compose"
            await tw.close_compose()
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-011: Text entry via DraftJS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTextEntry:
    def test_insert_text(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()
            await tw.open_compose()

            test_text = f"eval test {int(time.time())}"
            inserted = await tw.fill_compose(test_text)
            assert inserted, "fill_compose returned False"

            # Read back what's in the compose box
            content = await page.evaluate("""
                (() => {
                    const el = document.querySelector(
                        '[data-testid="tweetTextarea_0"] [contenteditable]'
                    );
                    return el ? el.textContent : null;
                })()
            """)
            assert content is not None, "Could not read compose box content"
            assert test_text in content, \
                f"Text mismatch: expected '{test_text}' in '{content}'"

            await tw.close_compose()
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-012: Post button becomes active
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPostButton:
    def test_button_enabled_after_text(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()
            await tw.open_compose()
            await tw.fill_compose("eval test button check")

            enabled = await tw.is_post_button_enabled()
            assert enabled, "Post button not enabled after entering text"

            await tw.close_compose()
            await mgr.close()

        _run(_test())

    def test_button_disabled_when_empty(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()
            await tw.open_compose()
            # Don't type anything
            enabled = await tw.is_post_button_enabled()
            assert not enabled, "Post button should be disabled when compose is empty"
            await tw.close_compose()
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-013: Post & Verify (DESTRUCTIVE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPostAndVerify:
    @pytest.mark.destructive
    def test_post_appears_on_profile(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()

            marker = f"__eval_{int(time.time())}__"
            test_text = f"testing automation {marker}"

            # Post
            posted = await tw.compose_and_post(test_text)
            assert posted, "compose_and_post returned False"

            # Verify on profile
            await asyncio.sleep(5)
            found = await tw.verify_post_on_profile(marker)
            assert found, f"Post with marker '{marker}' not found on profile"

            # Clean up
            deleted = await tw.delete_latest_post()
            assert deleted, "Failed to delete test post"

            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-014: Cancel compose without posting
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestComposeCancel:
    def test_close_without_posting(self, cdp_port):
        TwitterPage = _import_twitter()
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            tw = TwitterPage(browser)
            await tw.go_home()
            await tw.open_compose()
            await tw.fill_compose("this should NOT be posted")
            closed = await tw.close_compose()
            assert closed, "Failed to close compose modal"

            # Verify compose is gone
            has_textarea = await page.evaluate(
                "!!document.querySelector('[data-testid=\"tweetTextarea_0\"]')"
            )
            assert not has_textarea, "Compose box still open after close"
            await mgr.close()

        _run(_test())
