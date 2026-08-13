#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

TWEET_URL = "https://x.com/karpathy/status/2036836816654147718"

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get(TWEET_URL)
    await asyncio.sleep(8)
    html = await page.get_content()
    lower = html.lower()
    idx = lower.find('bookmark')
    print('IDX', idx)
    if idx != -1:
        start = max(0, idx-800)
        end = min(len(html), idx+1200)
        print(html[start:end])

if __name__ == '__main__':
    asyncio.run(main())
