#!/usr/bin/env python3
import asyncio
import sys
from x_browser import launch_browser, send_page_shortcut

TWEET_URL = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'https://x.com/jerryjliu0/status/2037235302990053628'

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get(TWEET_URL)
    await asyncio.sleep(8)
    ok = await send_page_shortcut(page, 'b')
    print('BOOKMARK_SHORTCUT_SENT', ok, TWEET_URL)
    await asyncio.sleep(6)
    if '--windows' not in sys.argv:
        await browser.stop()
    return 0 if ok else 1

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
