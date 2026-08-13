"""
Layer 0: Browser & Connection Evals

Tests that CDP works and Twitter is reachable + logged in.
Requires Chrome running with --remote-debugging-port on Windows.
"""

import asyncio

import pytest

pytestmark = pytest.mark.browser


def _run(coro):
    """Run async coroutine in sync test."""
    return asyncio.run(coro)


def _import_browser():
    try:
        from agents.core.browser import BrowserManager
        return BrowserManager
    except ImportError:
        pytest.skip("agents.core.browser not built yet - eval defines the contract")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-001: CDP Connection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCDPConnection:
    def test_connect_to_chrome(self, cdp_port):
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            assert browser is not None, "Browser connection returned None"
            # zendriver: browser.get() navigates and returns page
            page = await browser.get("about:blank")
            title = await page.evaluate("document.title")
            assert title is not None
            await mgr.close()

        _run(_test())

    def test_reconnect_after_disconnect(self, cdp_port):
        """Connection should be recoverable."""
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            await mgr.connect()
            await mgr.close()
            browser = await mgr.connect()
            assert browser is not None, "Failed to reconnect after close"
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-002: Twitter Reachable & Logged In
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTwitterReachable:
    def test_home_feed_loads(self, cdp_port):
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            page = await browser.get("https://x.com/home")
            # Wait for primary column (proves feed loaded, not login wall)
            el = await page.select('[data-testid="primaryColumn"]', timeout=15)
            assert el is not None, \
                "primaryColumn not found - likely login wall or suspension"
            await mgr.close()

        _run(_test())

    def test_not_suspended(self, cdp_port):
        """Check we're not on a suspension/locked page."""
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            page = await browser.get("https://x.com/home")
            await asyncio.sleep(3)
            url = await page.evaluate("window.location.href")
            assert "/account/access" not in url, "Account is locked/suspended"
            assert "/login" not in url, "Not logged in - redirected to login"
            # Check for suspension banner
            text = await page.evaluate("document.body.innerText")
            assert "suspended" not in text.lower()[:500], \
                "Suspension notice detected on page"
            await mgr.close()

        _run(_test())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EVAL-003: Page Interaction (scroll + find tweets)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPageInteraction:
    def test_tweets_visible_in_feed(self, cdp_port):
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            page = await browser.get("https://x.com/home")
            await page.wait_for('[data-testid="primaryColumn"]', timeout=15)
            await asyncio.sleep(2)  # Let feed populate
            count = await page.evaluate(
                "document.querySelectorAll('[data-testid=\"tweet\"]').length"
            )
            assert count >= 1, f"Expected tweets in feed, found {count}"
            await mgr.close()

        _run(_test())

    def test_scroll_loads_more(self, cdp_port):
        BrowserManager = _import_browser()

        async def _test():
            mgr = BrowserManager(cdp_port=cdp_port)
            browser = await mgr.connect()
            page = await browser.get("https://x.com/home")
            await page.wait_for('[data-testid="primaryColumn"]', timeout=15)
            await asyncio.sleep(2)

            before = await page.evaluate(
                "document.querySelectorAll('[data-testid=\"tweet\"]').length"
            )
            # Scroll down 3 times
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(1.5)

            after = await page.evaluate(
                "document.querySelectorAll('[data-testid=\"tweet\"]').length"
            )
            assert after > before, \
                f"Scrolling didn't load more tweets ({before} -> {after})"
            await mgr.close()

        _run(_test())
