#!/usr/bin/env python3
"""
Single-run X draft poster using the existing x_agent browser stack.

Uses the existing zendriver-based browser launcher from agents/x_browser.py,
which the user reports avoids the automation detection issues seen elsewhere.

Behavior:
- waits a random 120-180 seconds before acting
- posts at most one eligible draft per run
- skips if the most recent successful post was within the last 6 hours
- supports text-only or media drafts
- only removes a draft from the queue after successful posting
- logs outcomes to ~/.moltui/x-post-runner-log.json

Draft queue format (~/.moltui/tweet-drafts.json):
[
  {
    "text": "post text",
    "media_path": "/abs/path/to/file.mp4",
    "alt": "optional alt text for images/videos",
    "not_before": 1710000000,
    "status": "queued"
  }
]
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

from x_browser import DRAFT_QUEUE, launch_browser
from x_runtime import get_account, read_json, write_json

HOME_DIR = Path.home() / ".moltui"
RUNNER_LOG = HOME_DIR / "x-post-runner-log.json"
POST_HISTORY = HOME_DIR / "x-post-history.json"
MIN_GAP_SECONDS = 6 * 60 * 60
RANDOM_DELAY_MIN = 120
RANDOM_DELAY_MAX = 180


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-delay", action="store_true", help="skip the humanized pre-post delay")
    ap.add_argument("--delay-seconds", type=int, help="override pre-post delay seconds")
    ap.add_argument("--windows", action="store_true", help="attach to the existing Windows debug browser")
    ap.add_argument("--ignore-spacing", action="store_true", help="bypass the 6-hour spacing guard for explicit tests")
    ap.add_argument("--draft-id", help="post only the specified draft id")
    return ap.parse_args()


def _read_json(path: Path, default):
    return read_json(path, default)


def _write_json(path: Path, value):
    write_json(path, value)


def log_event(action: str, detail: str, status: str = "ok"):
    logs = _read_json(RUNNER_LOG, [])
    logs.append({
        "timestamp": int(time.time()),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "status": status,
        "detail": detail[:500],
    })
    logs = logs[-500:]
    _write_json(RUNNER_LOG, logs)
    print(f"[{status}] {action}: {detail}")


def last_successful_post_ts() -> int | None:
    history = _read_json(POST_HISTORY, [])
    for item in reversed(history):
        if item.get("status") == "posted":
            return int(item.get("timestamp", 0))
    return None


def append_history(entry: dict):
    history = _read_json(POST_HISTORY, [])
    history.append(entry)
    history = history[-500:]
    _write_json(POST_HISTORY, history)


def load_queue() -> list[dict]:
    return _read_json(DRAFT_QUEUE, [])


def save_queue(queue: list[dict]):
    _write_json(DRAFT_QUEUE, queue)


def compute_retry_time(attempt_count: int) -> int:
    backoff = min(6 * 60 * 60, 15 * 60 * max(1, 2 ** max(0, attempt_count - 1)))
    return int(time.time()) + backoff


def pick_eligible_draft(queue: list[dict], draft_id: str | None = None) -> tuple[int, dict] | tuple[None, None]:
    now = int(time.time())
    for idx, draft in enumerate(queue):
        if draft_id and draft.get("draft_id") != draft_id:
            continue
        if draft.get("status", "queued") not in ("queued", "retry"):
            continue
        not_before = int(draft.get("not_before", 0) or 0)
        if not_before and now < not_before:
            continue
        next_retry_at = int(draft.get("next_retry_at", 0) or 0)
        if next_retry_at and now < next_retry_at:
            continue
        text = (draft.get("text") or "").strip()
        if not text:
            continue
        return idx, draft
    return None, None


def claim_draft(queue: list[dict], idx: int) -> dict:
    draft = dict(queue[idx])
    draft.setdefault("draft_id", f"draft-{int(time.time())}-{idx}")
    draft["status"] = "posting"
    draft["claimed_at"] = int(time.time())
    draft["claim_pid"] = os.getpid()
    draft["attempt_count"] = int(draft.get("attempt_count", 0) or 0) + 1
    queue[idx] = draft
    save_queue(queue)
    return draft


def mark_draft_failed(draft_id: str | None, reason: str, permanent: bool = False):
    if not draft_id:
        return
    queue = load_queue()
    changed = False
    for idx, draft in enumerate(queue):
        if draft.get("draft_id") != draft_id:
            continue
        attempts = int(draft.get("attempt_count", 1) or 1)
        draft["last_error"] = reason[:200]
        draft["failed_at"] = int(time.time())
        draft.pop("claimed_at", None)
        draft.pop("claim_pid", None)
        if permanent:
            draft["status"] = "failed"
            draft["next_retry_at"] = None
        else:
            draft["status"] = "retry"
            draft["next_retry_at"] = compute_retry_time(attempts)
        queue[idx] = draft
        changed = True
        break
    if changed:
        save_queue(queue)


def remove_draft(draft_id: str | None):
    if not draft_id:
        return
    queue = [draft for draft in load_queue() if draft.get("draft_id") != draft_id]
    save_queue(queue)


async def wait_for_post_button(page, timeout_s: int = 120):
    start = time.time()
    while time.time() - start < timeout_s:
        btn = await page.query_selector('[data-testid="tweetButtonInline"]')
        if not btn:
            btn = await page.query_selector('[data-testid="tweetButton"]')
        if btn:
            try:
                disabled = await btn.get("aria-disabled")
            except Exception:
                disabled = None
            if disabled in (None, "false"):
                return btn
        await asyncio.sleep(2)
    return None


async def verify_post_appeared(browser, expected_text: str, current_page=None, timeout_s: int = 45):
    target = (expected_text or '').strip()
    if not target:
        return False
    needle = target[:80]
    account = get_account()
    start = time.time()

    async def page_confirms_success(page) -> bool:
        try:
            raw = await page.evaluate(
                r'''JSON.stringify((() => {
                    const body = (document.body.innerText || '').slice(0, 12000);
                    const texts = Array.from(document.querySelectorAll('article[data-testid="tweet"] [lang]'))
                      .map(el => (el.innerText || el.textContent || '').trim())
                      .filter(Boolean);
                    return {
                        body,
                        sent: body.includes('Your post was sent.'),
                        exact: texts.some(t => t === __EXACT__),
                        needle: texts.some(t => t.includes(__NEEDLE__)) || body.includes(__NEEDLE__),
                    };
                })())'''.replace('__NEEDLE__', json.dumps(needle)).replace('__EXACT__', json.dumps(target))
            )
            data = json.loads(raw) if raw else {}
            return bool(data.get('sent') or data.get('exact') or data.get('needle'))
        except Exception:
            return False

    if current_page is not None and await page_confirms_success(current_page):
        return True

    urls = [
        account["profile_url"],
        'https://x.com/home',
    ]
    while time.time() - start < timeout_s:
        for url in urls:
            try:
                page = await browser.get(url)
                await asyncio.sleep(6)
                if not await page_looks_hydrated(page):
                    try:
                        await page.reload()
                        await asyncio.sleep(6)
                    except Exception:
                        pass
                if await page_confirms_success(page):
                    return True
            except Exception:
                continue
        await asyncio.sleep(3)
    return False


async def fill_compose(page, text: str):
    compose = await find_visible_compose(page)
    if not compose:
        return False

    try:
        await compose.click()
        await asyncio.sleep(0.5)
    except Exception:
        pass

    inserted = await insert_text_draftjs(page, text)
    if not inserted:
        return False

    current = await read_compose_text(page)
    return bool(current and text.strip() in current)


async def read_compose_text(page):
    try:
        return await page.evaluate(
            r'''(() => {
                const el = document.querySelector('[data-testid="tweetTextarea_0"][contenteditable="true"]');
                if (!el) return '';
                return (el.innerText || el.textContent || '').trim();
            })()'''
        )
    except Exception:
        return ''


async def insert_text_draftjs(page, text: str):
    import json
    js = r'''
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
  return {ok:true, exec_ok:execOk, text:(el.innerText || el.textContent || '').trim()};
})())
'''.replace('__TEXT__', json.dumps(text))
    try:
        raw = await page.evaluate(js)
        data = json.loads(raw) if raw else {}
        return bool(data.get('ok') and text.strip() in (data.get('text') or ''))
    except Exception:
        return False


async def find_visible_compose(page):
    compose = await page.query_selector('[data-testid="tweetTextarea_0"]')
    if compose:
        return compose
    compose = await page.query_selector('[role="textbox"]')
    if compose:
        return compose
    return None


async def page_looks_hydrated(page):
    try:
        raw = await page.evaluate(
            r'''JSON.stringify((() => {
                const body = (document.body.innerText || '').trim();
                return {
                    url: location.href,
                    body_len: body.length,
                    has_for_you: body.includes('For you'),
                    has_following: body.includes('Following'),
                    has_whats_happening: body.includes("What’s happening?") || body.includes("What's happening?"),
                    has_compose: !!document.querySelector('[data-testid="tweetTextarea_0"], [role="textbox"], [data-testid="SideNav_NewTweet_Button"]'),
                };
            })())'''
        )
        data = json.loads(raw) if raw else {}
        if data.get('has_compose'):
            return True
        body_len = int(data.get('body_len', 0) or 0)
        signal_hits = sum(
            1 for key in ('has_for_you', 'has_following', 'has_whats_happening')
            if data.get(key)
        )
        return body_len > 300 and signal_hits >= 2
    except Exception:
        return False


async def get_hydrated_home_page(browser, attempts: int = 4):
    last_page = None
    for attempt in range(attempts):
        page = await browser.get('https://x.com/home')
        last_page = page
        await asyncio.sleep(6 + attempt)
        if await page_looks_hydrated(page):
            return page
        try:
            await page.reload()
            await asyncio.sleep(8 + attempt)
        except Exception:
            pass
        if await page_looks_hydrated(page):
            return page
    return last_page


async def ensure_compose_ready(page):
    compose = await find_visible_compose(page)
    if compose:
        return compose

    for _ in range(4):
        if not await page_looks_hydrated(page):
            try:
                await page.reload()
                await asyncio.sleep(10)
            except Exception:
                pass
        compose = await find_visible_compose(page)
        if compose:
            return compose
        try:
            clicked = await page.evaluate(
                r'''(() => {
                    const btn = document.querySelector('[data-testid="SideNav_NewTweet_Button"]');
                    if (!btn) return false;
                    btn.click();
                    return true;
                })()'''
            )
            if clicked:
                await asyncio.sleep(4)
        except Exception:
            pass
        compose = await find_visible_compose(page)
        if compose:
            return compose
    return await find_visible_compose(page)


async def maybe_upload_media(page, media_path: str | None):
    if not media_path:
        return True, "no media"
    if not os.path.exists(media_path):
        return False, f"media missing: {media_path}"

    file_input = await page.query_selector('input[type="file"]')
    if not file_input:
        return False, "no file input found"

    await file_input.send_file(media_path)
    await asyncio.sleep(8)

    # Give X extra time to process larger uploads.
    for _ in range(45):
        body = await page.evaluate("document.body.innerText")
        if "Uploaded (100%)" in body or "Edit" in body:
            return True, "media uploaded"
        if "Upload failed" in body or "Try again" in body:
            return False, "upload failed"
        await asyncio.sleep(2)

    return True, "media upload likely complete"


async def post_one_draft(no_delay: bool = False, delay_seconds: int | None = None, ignore_spacing: bool = False, target_draft_id: str | None = None) -> int:
    queue = load_queue()
    idx, draft = pick_eligible_draft(queue, draft_id=target_draft_id)
    if draft is None:
        detail = f"draft {target_draft_id} not eligible" if target_draft_id else "no eligible queued draft"
        log_event("draft", detail, "skip")
        return 0
    draft = claim_draft(queue, idx)
    draft_id = draft.get("draft_id")

    last_post = last_successful_post_ts()
    now = int(time.time())
    if (not ignore_spacing) and last_post and (now - last_post) < MIN_GAP_SECONDS:
        gap_left = MIN_GAP_SECONDS - (now - last_post)
        log_event("spacing", f"skipping due to min gap; {gap_left}s remaining", "skip")
        return 0

    env_delay = os.environ.get("X_POST_DELAY_SECONDS")
    if delay_seconds is None and env_delay not in (None, ""):
        try:
            delay_seconds = int(env_delay)
        except Exception:
            delay_seconds = None

    if no_delay:
        delay = 0
    elif delay_seconds is not None:
        delay = max(0, int(delay_seconds))
    else:
        delay = random.randint(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)

    log_event("delay", f"waiting {delay}s before posting")
    if delay > 0:
        await asyncio.sleep(delay)

    text = draft.get("text", "").strip()
    media_path = draft.get("media_path")
    browser = await launch_browser(headless=False)
    try:
        page = await get_hydrated_home_page(browser)
        await asyncio.sleep(2)

        compose = await ensure_compose_ready(page)
        ok = False
        if compose:
            ok = await fill_compose(page, text)
        if not ok:
            log_event("compose", "compose box not found", "fail")
            mark_draft_failed(draft_id, "compose box missing")
            append_history({
                "timestamp": now,
                "status": "failed",
                "reason": "compose box missing",
                "text": text[:200],
                "mode": draft.get("mode"),
                "trend_key": draft.get("trend_key"),
                "hook_style": draft.get("hook_style"),
                "source_labels": draft.get("source_labels", []),
                "tags": draft.get("tags", []),
            })
            return 1

        media_ok, media_msg = await maybe_upload_media(page, media_path)
        log_event("media", media_msg, "ok" if media_ok else "fail")
        if not media_ok:
            mark_draft_failed(draft_id, media_msg, permanent=("missing" in media_msg.lower()))
            append_history({
                "timestamp": now,
                "status": "failed",
                "reason": media_msg,
                "text": text[:200],
                "media_path": media_path,
                "mode": draft.get("mode"),
                "trend_key": draft.get("trend_key"),
                "hook_style": draft.get("hook_style"),
                "source_labels": draft.get("source_labels", []),
                "tags": draft.get("tags", []),
            })
            return 1

        btn = await wait_for_post_button(page)
        if not btn:
            log_event("post", "post button never became enabled", "fail")
            mark_draft_failed(draft_id, "button disabled")
            append_history({
                "timestamp": now,
                "status": "failed",
                "reason": "button disabled",
                "text": text[:200],
                "media_path": media_path,
                "mode": draft.get("mode"),
                "trend_key": draft.get("trend_key"),
                "hook_style": draft.get("hook_style"),
                "source_labels": draft.get("source_labels", []),
                "tags": draft.get("tags", []),
            })
            return 1

        await btn.click()
        await asyncio.sleep(8)

        verified = await verify_post_appeared(browser, text, current_page=page)
        if not verified:
            log_event("post", "post click happened but verification failed", "fail")
            mark_draft_failed(draft_id, "post verification failed")
            append_history({
                "timestamp": int(time.time()),
                "status": "failed",
                "reason": "post verification failed",
                "text": text[:200],
                "media_path": media_path,
                "mode": draft.get("mode"),
                "trend_key": draft.get("trend_key"),
                "hook_style": draft.get("hook_style"),
                "source_labels": draft.get("source_labels", []),
                "tags": draft.get("tags", []),
            })
            return 1

        remove_draft(draft_id)

        append_history({
            "timestamp": int(time.time()),
            "status": "posted",
            "text": text[:280],
            "media_path": media_path,
            "mode": draft.get("mode"),
            "trend_key": draft.get("trend_key"),
            "hook_style": draft.get("hook_style"),
            "source_labels": draft.get("source_labels", []),
            "source_urls": draft.get("source_urls", []),
            "tags": draft.get("tags", []),
        })
        log_event("post", f"posted draft: {text[:80]}")
        return 0
    finally:
        # Keep the fragile Windows debug browser alive across runs.
        if "--windows" not in sys.argv:
            await browser.stop()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(post_one_draft(no_delay=args.no_delay, delay_seconds=args.delay_seconds, ignore_spacing=args.ignore_spacing, target_draft_id=args.draft_id)))
