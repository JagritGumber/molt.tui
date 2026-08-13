#!/usr/bin/env python3
import asyncio
from x_browser import launch_browser

JS = r'''
JSON.stringify((() => {
  const pick = (els) => Array.from(els).map((el, i) => {
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return {
      i,
      tag: el.tagName,
      testid: el.getAttribute('data-testid'),
      role: el.getAttribute('role'),
      aria: el.getAttribute('aria-label'),
      contenteditable: el.getAttribute('contenteditable'),
      visible: !!(r.width && r.height && style.display !== 'none' && style.visibility !== 'hidden'),
      top: Math.round(r.top),
      left: Math.round(r.left),
      width: Math.round(r.width),
      height: Math.round(r.height),
      text: (el.innerText || el.textContent || '').trim().slice(0, 180)
    };
  });
  return {
    url: location.href,
    title: document.title,
    body: (document.body.innerText || '').slice(0, 3000),
    textboxes: pick(document.querySelectorAll('[role="textbox"]')),
    tweetareas: pick(document.querySelectorAll('[data-testid="tweetTextarea_0"]')),
    buttons: pick(document.querySelectorAll('[data-testid="tweetButton"], [data-testid="tweetButtonInline"], [data-testid="SideNav_NewTweet_Button"], [role="button"]')),
    dialogs: pick(document.querySelectorAll('[role="dialog"]')),
  };
})())
'''

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get('https://x.com/home')
    await asyncio.sleep(8)
    btn = await page.query_selector('[data-testid="SideNav_NewTweet_Button"]')
    print('btn', bool(btn))
    if btn:
        await btn.click()
    await asyncio.sleep(5)
    raw = await page.evaluate(JS)
    print(raw)

if __name__ == '__main__':
    asyncio.run(main())
