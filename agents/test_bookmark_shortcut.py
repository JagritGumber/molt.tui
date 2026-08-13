#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

TWEET_URL = "https://x.com/karpathy/status/2036836816654147718"

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get(TWEET_URL)
    await asyncio.sleep(8)
    try:
        await page.send_keys('b')
        print('SENT_B_SHORTCUT', TWEET_URL)
    except Exception as e:
        print('SHORTCUT_FAIL', e)
        return 1
    await asyncio.sleep(6)
    return 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
