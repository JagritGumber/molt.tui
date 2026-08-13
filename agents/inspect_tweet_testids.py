#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

TWEET_URL = "https://x.com/karpathy/status/2036836816654147718"

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get(TWEET_URL)
    await asyncio.sleep(8)
    data = await page.evaluate("""
() => Array.from(document.querySelectorAll('[data-testid], button, a[role="button"]')).slice(0,120).map(el => ({
  tag: el.tagName,
  testid: el.getAttribute('data-testid'),
  aria: el.getAttribute('aria-label'),
  text: (el.innerText || '').slice(0,80)
}))
""")
    for i, item in enumerate(data):
        print(i, item)

if __name__ == '__main__':
    asyncio.run(main())
