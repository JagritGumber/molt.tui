"""Twitter Page — all X/Twitter interactions via zendriver CDP.

Zendriver API notes (verified against live):
  - page.select(css) / page.select_all(css) — wait + return Element(s)
  - page.query_selector(css) / query_selector_all(css) — instant, may be None/[]
  - page.find(text) — find by visible text content
  - page.evaluate(js) — run JS, return result
  - element.click() — click
  - element.send_keys(text) — type text
  - element.text — text content
  - element.query_selector(css) — find child by CSS
  - element.attrs — dict of attributes
  - browser.get(url) — navigate, returns Tab (page)
"""

import asyncio
import json
import random
import time

# ── Selectors (data-testid based) ──
SEL_COMPOSE_BUTTON = '[data-testid="SideNav_NewTweet_Button"]'
SEL_TEXTAREA = '[data-testid="tweetTextarea_0"]'
SEL_POST_BUTTON = '[data-testid="tweetButton"]'
SEL_POST_BUTTON_INLINE = '[data-testid="tweetButtonInline"]'
SEL_TWEET = 'article[data-testid="tweet"]'
SEL_LIKE = '[data-testid="like"]'
SEL_UNLIKE = '[data-testid="unlike"]'
SEL_REPLY = '[data-testid="reply"]'

# ── DraftJS text insertion JS ──
DRAFTJS_INSERT_JS = r'''
JSON.stringify((() => {
  const text = __TEXT__;
  const el = document.querySelector('[data-testid="tweetTextarea_0"][contenteditable="true"]')
           || document.querySelector('[role="textbox"][contenteditable="true"]');
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
  return {ok:true, exec_ok:execOk, text:(el.innerText || el.textContent || '').trim()};
})())
'''


async def _human_delay(min_s: float = 0.5, max_s: float = 2.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _safe_click(element, delay: float = 0.15):
    """Scroll into view then click — fixes zendriver's off-screen click bug."""
    try:
        await element.scroll_into_view()
    except Exception:
        pass
    await asyncio.sleep(delay)
    await element.click()


class TwitterPage:
    def __init__(self, browser):
        """Takes the zendriver browser object."""
        self.browser = browser
        self.page = None
        self._last_liked_tweet = None

    async def _nav(self, url: str):
        """Navigate and update page reference."""
        self.page = await self.browser.get(url)
        return self.page

    async def _wait_for(self, selector: str, timeout: int = 15):
        """Poll for element. Returns Element or None."""
        try:
            return await self.page.select(selector, timeout=timeout)
        except Exception:
            return None

    async def _find_all(self, selector: str, timeout: int = 10) -> list:
        """Find all matching elements with timeout."""
        try:
            return await self.page.select_all(selector, timeout=timeout)
        except Exception:
            return []

    async def go_home(self):
        """Navigate to home feed and wait for tweets to load."""
        await self._nav("https://x.com/home")
        await _human_delay(3, 5)

    # ── Compose ──

    async def open_compose(self) -> bool:
        """Click compose button, wait for textarea."""
        btn = await self._wait_for(SEL_COMPOSE_BUTTON, timeout=10)
        if not btn:
            # Fallback: navigate to compose URL
            await self._nav("https://x.com/compose/post")
            await _human_delay(1, 2)
        else:
            await _safe_click(btn)
            await _human_delay(0.5, 1.5)
        # Wait for textarea
        ta = await self._wait_for(SEL_TEXTAREA, timeout=10)
        return ta is not None

    async def fill_compose(self, text: str) -> bool:
        """Insert text into compose box via DraftJS injection."""
        js = DRAFTJS_INSERT_JS.replace('__TEXT__', json.dumps(text))
        try:
            raw = await self.page.evaluate(js)
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            return bool(data.get('ok') and text.strip() in (data.get('text') or ''))
        except Exception:
            return False

    async def is_post_button_enabled(self) -> bool:
        """Check if the post button is clickable."""
        for sel in (SEL_POST_BUTTON, SEL_POST_BUTTON_INLINE):
            btn = await self.page.query_selector(sel)
            if btn:
                attrs = btn.attrs or {}
                if attrs.get("aria-disabled") != "true":
                    return True
        return False

    async def close_compose(self) -> bool:
        """Close compose modal via Escape key."""
        try:
            body = await self.page.query_selector("body")
            if body:
                await body.send_keys("\x1b")
            await _human_delay(0.5, 1.0)
            discard = await self.page.query_selector('[data-testid="confirmationSheetConfirm"]')
            if discard:
                await _safe_click(discard)
                await _human_delay(0.3, 0.5)
            return True
        except Exception:
            return False

    async def upload_media(self, media_path: str) -> bool:
        """Upload an image/video to the compose box."""
        if not media_path:
            return True  # No media is fine
        from pathlib import Path
        if not Path(media_path).exists():
            print(f"  [media] file missing: {media_path}")
            return False
        try:
            file_input = await self.page.query_selector('input[type="file"]')
            if not file_input:
                print("  [media] no file input found in compose")
                return False
            await file_input.send_file(media_path)
            await _human_delay(3, 5)
            # Wait for upload to process
            for _ in range(20):
                body_text = await self.page.evaluate("document.body.innerText") or ""
                if "Uploaded" in body_text or "Alt" in body_text:
                    return True
                await asyncio.sleep(1)
            # If no upload indicator, assume it worked (small images are instant)
            return True
        except Exception as e:
            print(f"  [media] upload error: {e}")
            return False

    async def compose_and_post(self, text: str, media_path: str = None) -> bool:
        """Full compose -> type -> (optional media) -> post flow."""
        if not await self.open_compose():
            print("  [post] compose box failed to open")
            return False
        if media_path:
            media_ok = await self.upload_media(media_path)
            if not media_ok:
                print("  [post] media upload failed, posting text-only")
        if not await self.fill_compose(text):
            print("  [post] text insertion failed")
            return False
        await _human_delay(0.5, 1.5)
        # Find and click post button
        for sel in (SEL_POST_BUTTON, SEL_POST_BUTTON_INLINE):
            btn = await self._wait_for(sel, timeout=5)
            if btn:
                attrs = btn.attrs or {}
                if attrs.get("aria-disabled") != "true":
                    await _safe_click(btn)
                    await _human_delay(2.0, 4.0)
                    return True
                else:
                    print(f"  [post] button found but disabled: {sel}")
            else:
                print(f"  [post] button not found: {sel}")
        return False

    # ── Verification ──

    async def verify_post_on_profile(self, marker: str) -> bool:
        """Check if latest tweet on profile contains marker."""
        from agents.core.config import get_account_handle
        handle = get_account_handle()
        await self._nav(f"https://x.com/{handle}" if handle else "https://x.com/home")
        await _human_delay(2.0, 4.0)
        text = await self.page.evaluate("document.body.innerText")
        return marker in (text or "")

    async def delete_latest_post(self) -> bool:
        """Delete the most recent post on profile."""
        try:
            tweets = await self._find_all(SEL_TWEET, timeout=10)
            if not tweets:
                return False
            caret = await tweets[0].query_selector('[data-testid="caret"]')
            if not caret:
                return False
            await _safe_click(caret)
            await _human_delay(0.5, 1.0)
            delete_btn = await self.page.query_selector('[data-testid="Dropdown"] [role="menuitem"]')
            if delete_btn and "delete" in (delete_btn.text or "").lower():
                await _safe_click(delete_btn)
                await _human_delay(0.5, 1.0)
                confirm = await self.page.query_selector('[data-testid="confirmationSheetConfirm"]')
                if confirm:
                    await _safe_click(confirm)
                    await _human_delay(1.0, 2.0)
                    return True
            return False
        except Exception:
            return False

    # ── Feed interaction ──

    async def get_visible_tweets(self) -> list[dict]:
        """Get visible tweets with text content."""
        articles = await self._find_all(SEL_TWEET, timeout=10)
        results = []
        for tw in articles[:20]:
            results.append({"text": (tw.text or "").strip(), "element": tw})
        return results

    async def get_visible_tweet_ids(self) -> list[str]:
        """Rough IDs for dedup (first 80 chars of text)."""
        tweets = await self.get_visible_tweets()
        return [t["text"][:80] for t in tweets if t["text"]]

    async def like_first_unliked(self) -> bool:
        """Find and like the first unliked tweet."""
        articles = await self._find_all(SEL_TWEET, timeout=10)
        for tw in articles[:10]:
            like_btn = await tw.query_selector(SEL_LIKE)
            if like_btn:
                await _human_delay(0.5, 1.5)
                await _safe_click(like_btn)
                self._last_liked_tweet = tw
                return True
        return False

    async def unlike_last_liked(self) -> bool:
        """Unlike the last liked tweet."""
        if not self._last_liked_tweet:
            return False
        unlike_btn = await self._last_liked_tweet.query_selector(SEL_UNLIKE)
        if unlike_btn:
            await _safe_click(unlike_btn)
            return True
        return False

    async def reply_to_first_tweet(self, reply_text: str) -> bool:
        """Reply to the first tweet in feed."""
        articles = await self._find_all(SEL_TWEET, timeout=10)
        if not articles:
            return False
        reply_btn = await articles[0].query_selector(SEL_REPLY)
        if not reply_btn:
            return False
        await _safe_click(reply_btn)
        await _human_delay(1.0, 2.0)
        if not await self.fill_compose(reply_text):
            return False
        await _human_delay(0.5, 1.0)
        for sel in (SEL_POST_BUTTON, SEL_POST_BUTTON_INLINE):
            btn = await self._wait_for(sel, timeout=5)
            if btn:
                attrs = btn.attrs or {}
                if attrs.get("aria-disabled") != "true":
                    await _safe_click(btn)
                    await _human_delay(2.0, 3.0)
                    return True
        return False

    async def human_scroll(self, times: int = 1):
        """Scroll with human-like jitter."""
        for _ in range(times):
            distance = random.randint(200, 600)
            if random.random() < 0.1:
                distance = -random.randint(50, 150)
            await self.page.evaluate(f"window.scrollBy(0, {distance})")
            await _human_delay(1.0, 3.0)

    async def post_from_queue(self) -> bool:
        """Pick first queued draft and post it."""
        from agents.core.config import DRAFTS_FILE, load_json, save_json
        queue = load_json(DRAFTS_FILE, [])
        draft = None
        idx = -1
        for i, d in enumerate(queue):
            if d.get("status") == "queued":
                draft = d
                idx = i
                break
        if not draft:
            return False
        await self.go_home()
        posted = await self.compose_and_post(draft["text"])
        if posted:
            queue[idx]["status"] = "done"
            queue[idx]["posted_at"] = int(time.time())
            save_json(DRAFTS_FILE, queue)
        return posted
