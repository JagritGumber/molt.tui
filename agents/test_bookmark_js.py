#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

TWEET_URL = "https://x.com/karpathy/status/2036836816654147718"

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get(TWEET_URL)
    await asyncio.sleep(8)
    clicked = await page.evaluate("""
() => {
  const candidates = Array.from(document.querySelectorAll('button,[role="button"]'));
  const btn = candidates.find(el => {
    const testid = el.getAttribute('data-testid') || '';
    const aria = el.getAttribute('aria-label') || '';
    return testid.toLowerCase().includes('bookmark') || aria.toLowerCase().includes('bookmark');
  });
  if (!btn) return {ok:false, reason:'not found'};
  btn.click();
  return {ok:true, testid:btn.getAttribute('data-testid'), aria:btn.getAttribute('aria-label')};
}
""")
    print(clicked)
    await asyncio.sleep(6)

if __name__ == '__main__':
    asyncio.run(main())
