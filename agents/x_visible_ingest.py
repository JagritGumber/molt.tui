#!/usr/bin/env python3
"""
Visible X feed-ingestion session.

Purpose:
- attach to the working Windows debug browser
- bring the X home feed to the front visibly
- scroll a few times in a controlled way
- capture what posts were actually visible
- save screenshots + structured logs for verification

This is intentionally explicit and verifiable, not a vague background run.
"""

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

from x_browser import launch_browser

HOME_DIR = Path.home() / ".moltui"
RUNS_DIR = HOME_DIR / "x-visible-ingest-runs"
SUMMARY_LOG = HOME_DIR / "x-visible-ingest-log.json"


def _read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def append_summary(entry: dict):
    log = _read_json(SUMMARY_LOG, [])
    log.append(entry)
    log = log[-100:]
    _write_json(SUMMARY_LOG, log)


async def extract_visible_posts(page):
    raw = await page.evaluate(
        """
JSON.stringify((() => {
  const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
  const vh = window.innerHeight || document.documentElement.clientHeight || 0;
  return articles.map((a, idx) => {
    const r = a.getBoundingClientRect();
    const visible = r.bottom > 0 && r.top < vh;
    const text = (a.innerText || '').trim();
    const links = Array.from(a.querySelectorAll('a[href*="/status/"]')).map(x => x.getAttribute('href'));
    const authorLink = Array.from(a.querySelectorAll('a[role="link"]')).map(x => x.getAttribute('href')).find(Boolean) || null;
    return {
      index: idx,
      visible,
      top: Math.round(r.top),
      bottom: Math.round(r.bottom),
      height: Math.round(r.height),
      text: text.slice(0, 1200),
      status_links: Array.from(new Set(links)).slice(0, 3),
      author_link: authorLink,
    };
  }).filter(x => x.visible);
})())
"""
    )
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


async def run_ingest():
    ts = int(time.time())
    run_dir = RUNS_DIR / str(ts)
    run_dir.mkdir(parents=True, exist_ok=True)

    browser = await launch_browser(headless=False)
    try:
        page = await browser.get("https://x.com/home")
        await page.bring_to_front()
        await asyncio.sleep(8)

        steps = []
        for i in range(4):
            screenshot_path = str(run_dir / f"step_{i}.png")
            await page.save_screenshot(screenshot_path, full_page=False)
            posts = await extract_visible_posts(page)
            steps.append({
                "step": i,
                "timestamp": int(time.time()),
                "url": getattr(page, 'url', None),
                "screenshot": screenshot_path,
                "visible_posts": posts[:6],
            })

            if i < 3:
                distance = random.randint(500, 900)
                await page.evaluate(f"window.scrollBy(0, {distance})")
                await asyncio.sleep(random.uniform(3.0, 6.0))

        summary = {
            "run_id": ts,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "steps": len(steps),
            "run_dir": str(run_dir),
            "step_summaries": [
                {
                    "step": s["step"],
                    "screenshot": s["screenshot"],
                    "visible_count": len(s["visible_posts"]),
                    "sample_texts": [p.get("text", "")[:180] for p in s["visible_posts"][:3]],
                }
                for s in steps
            ],
        }

        _write_json(run_dir / "ingest.json", {"steps": steps})
        append_summary(summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    finally:
        # Keep the fragile Windows debug browser alive.
        if "--windows" not in sys.argv:
            await browser.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_ingest()))
