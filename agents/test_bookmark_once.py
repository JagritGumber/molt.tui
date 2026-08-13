#!/usr/bin/env python3
import asyncio
import sys

from x_browser import launch_browser

TWEET_URL = "https://x.com/karpathy/status/2036836816654147718"

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get(TWEET_URL)
    await asyncio.sleep(6)

    # Try visible bookmark button on tweet page.
    btn = await page.query_selector('[data-testid="bookmark"]')
    if not btn:
        btn = await page.query_selector('button[aria-label*="Bookmark"]')
    if not btn:
        print('BOOKMARK_BUTTON_NOT_FOUND')
        return 1

    await btn.click()
    print('BOOKMARK_CLICKED', TWEET_URL)
    await asyncio.sleep(8)
    return 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
