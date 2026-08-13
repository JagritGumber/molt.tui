#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

async def dump(page, label):
    body = await page.evaluate('(document.body.innerText || "").slice(0, 2000)')
    compose = await page.query_selector('[data-testid="tweetTextarea_0"]')
    textbox = await page.query_selector('[role="textbox"]')
    postbtn = await page.query_selector('[data-testid="tweetButtonInline"]')
    sidebtn = await page.query_selector('[data-testid="SideNav_NewTweet_Button"]')
    print(label, 'url', getattr(page, 'url', None), 'compose', bool(compose), 'textbox', bool(textbox), 'postbtn', bool(postbtn), 'sidebtn', bool(sidebtn))
    print(label, 'body', body)

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get('https://x.com/home')
    await asyncio.sleep(6)
    await dump(page, 'initial')
    try:
        await page.reload()
    except Exception as e:
        print('reload_err', e)
    await asyncio.sleep(10)
    await dump(page, 'reloaded')

if __name__ == '__main__':
    asyncio.run(main())
