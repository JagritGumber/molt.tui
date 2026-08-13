#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get('https://x.com/home')
    await asyncio.sleep(8)
    data = await page.evaluate("""
() => ({
  articleTweet: document.querySelectorAll('article[data-testid="tweet"]').length,
  articleAny: document.querySelectorAll('article').length,
  divCell: document.querySelectorAll('[data-testid="cellInnerDiv"]').length,
  primaryColumn: !!document.querySelector('[data-testid="primaryColumn"]'),
  bodyText: (document.body.innerText || '').slice(0,2000)
})
""")
    print(data)

if __name__ == '__main__':
    asyncio.run(main())
