#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

TWEET_URL = "https://x.com/karpathy/status/2036836816654147718"

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get(TWEET_URL)
    await asyncio.sleep(8)
    print('URL', getattr(page, 'url', None))
    try:
        html = await page.get_content()
        print('HAS_bookmark', 'bookmark' in html.lower())
        print(html[:4000])
    except Exception as e:
        print('HTML_ERR', e)
    try:
        buttons = await page.query_selector_all('button')
        print('BUTTONS', len(buttons))
        for i, b in enumerate(buttons[:20]):
            try:
                txt = await b.get_attribute('innerText')
                aria = await b.get_attribute('aria-label')
                testid = await b.get_attribute('data-testid')
                print(i, testid, aria, txt)
            except Exception as e:
                print('BTN_ERR', i, e)
    except Exception as e:
        print('BUTTON_ERR', e)

if __name__ == '__main__':
    asyncio.run(main())
