#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get('https://x.com/home')
    await asyncio.sleep(6)
    print('url', getattr(page, 'url', None))
    body = await page.evaluate('(document.body.innerText || "").slice(0, 2000)')
    print('body', body)
    compose = await page.query_selector('[data-testid="tweetTextarea_0"]')
    textbox = await page.query_selector('[role="textbox"]')
    postbtn = await page.query_selector('[data-testid="tweetButtonInline"]')
    sidebtn = await page.query_selector('[data-testid="SideNav_NewTweet_Button"]')
    print('compose', bool(compose), 'textbox', bool(textbox), 'postbtn', bool(postbtn), 'sidebtn', bool(sidebtn))

if __name__ == '__main__':
    asyncio.run(main())
