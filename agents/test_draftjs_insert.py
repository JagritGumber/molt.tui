#!/usr/bin/env python3
import asyncio
import json
from x_browser import launch_browser

TEST_TEXT = "draftjs probe text from hermes"

JS_STATE = r'''
JSON.stringify((() => {
  const el = document.querySelector('[data-testid="tweetTextarea_0"][contenteditable="true"]');
  const side = document.querySelector('[data-testid="SideNav_NewTweet_Button"]');
  const btn = document.querySelector('[data-testid="tweetButtonInline"]');
  return {
    url: location.href,
    body: (document.body.innerText || '').slice(0, 2000),
    has_editor: !!el,
    has_side_btn: !!side,
    has_post_btn: !!btn,
    text: el ? (el.innerText || el.textContent || '').trim() : ''
  };
})())
'''

JS_INSERT_TMPL = r'''
JSON.stringify((() => {
  const text = __TEXT__;
  const el = document.querySelector('[data-testid="tweetTextarea_0"][contenteditable="true"]');
  if (!el) return {ok:false, reason:'not-found'};
  el.focus();
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  sel.removeAllRanges();
  sel.addRange(range);
  let execOk = false;
  try { execOk = document.execCommand('insertText', false, text); } catch (e) {}
  try { el.dispatchEvent(new InputEvent('beforeinput', {bubbles:true, cancelable:true, inputType:'insertText', data:text})); } catch (e) {}
  try { el.dispatchEvent(new InputEvent('input', {bubbles:true, cancelable:true, inputType:'insertText', data:text})); } catch (e) {}
  return {ok:true, exec_ok:execOk, text:(el.innerText || el.textContent || '').trim(), html:el.innerHTML};
})())
'''

async def main():
    browser = await launch_browser(headless=False)
    page = await browser.get('https://x.com/home')
    await asyncio.sleep(6)
    try:
        await page.reload()
    except Exception:
        pass
    await asyncio.sleep(10)

    state = await page.evaluate(JS_STATE)
    print('STATE1', state)

    side = await page.query_selector('[data-testid="SideNav_NewTweet_Button"]')
    if side:
        try:
            await side.click()
            await asyncio.sleep(4)
        except Exception as e:
            print('SIDE_CLICK_ERR', repr(e))

    state2 = await page.evaluate(JS_STATE)
    print('STATE2', state2)

    el = await page.query_selector('[data-testid="tweetTextarea_0"][contenteditable="true"]')
    print('ELEMENT', bool(el))
    if el:
        try:
            await el.click()
            await asyncio.sleep(1)
            await el.send_keys(TEST_TEXT)
            await asyncio.sleep(2)
            after_keys = await page.evaluate(JS_STATE)
            print('AFTER_SEND_KEYS', after_keys)
        except Exception as e:
            print('SEND_KEYS_ERR', repr(e))

    js_insert = JS_INSERT_TMPL.replace('__TEXT__', json.dumps(TEST_TEXT))
    after_js = await page.evaluate(js_insert)
    print('AFTER_JS', after_js)

    state3 = await page.evaluate(JS_STATE)
    print('STATE3', state3)

if __name__ == '__main__':
    asyncio.run(main())
