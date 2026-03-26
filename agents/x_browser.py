"""
X/Twitter Browser Agent — autonomous background browser that acts like a human on X.
Uses zendriver (undetectable CDP) for stealth browser control.
Scrolls, likes, follows, and engages naturally with randomized human-like timing.

Usage:
  source .venv/bin/activate
  python agents/x_browser.py [--chrome | --opera] [--headless]

The agent:
1. Opens X.com in a real browser (Chrome or Opera)
2. Scrolls the feed like a human (variable speed, pauses)
3. Likes posts that match your interests
4. Follows accounts that post good content
5. Can post drafts you provide via a queue file
6. Logs all actions for the RL pipeline
"""

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

import zendriver as zd

# ── Config ──

HOME_DIR = Path.home() / ".moltui"
DRAFT_QUEUE = HOME_DIR / "tweet-drafts.json"
ACTION_LOG = HOME_DIR / "x-agent-log.json"
CONFIG_FILE = HOME_DIR / "x-agent-config.json"

DEFAULT_CONFIG = {
    "interests": ["AI", "databases", "postgres", "rust", "typescript", "infrastructure", "developer tools"],
    "like_probability": 0.3,       # 30% chance to like a relevant post
    "follow_probability": 0.1,     # 10% chance to follow a relevant author
    "scroll_speed_min": 2.0,       # seconds between scrolls
    "scroll_speed_max": 8.0,       # randomized human feel
    "session_duration_min": 20,    # minutes per session
    "session_duration_max": 45,
    "pause_between_sessions": 60,  # minutes between sessions
    "max_likes_per_session": 15,
    "max_follows_per_session": 5,
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    return DEFAULT_CONFIG


def log_action(action: str, detail: str, status: str = "ok"):
    """Append to action log — consumed by moltui's RL pipeline."""
    logs = []
    if ACTION_LOG.exists():
        try:
            logs = json.loads(ACTION_LOG.read_text())
        except Exception:
            logs = []
    logs.append({
        "time": time.strftime("%H:%M:%S"),
        "timestamp": int(time.time()),
        "action": action,
        "detail": detail[:100],
        "status": status,
    })
    # Keep last 500 entries
    if len(logs) > 500:
        logs = logs[-500:]
    ACTION_LOG.write_text(json.dumps(logs, indent=2))
    print(f"  [{status}] {action}: {detail[:60]}")


# ── Human-like behavior ──

async def human_delay(min_s: float = 0.5, max_s: float = 2.0):
    """Random delay that mimics human reaction time."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_scroll(page):
    """Scroll down like a human — variable distance, sometimes scroll up."""
    distance = random.randint(200, 600)
    # 10% chance to scroll up slightly (humans do this)
    if random.random() < 0.1:
        distance = -random.randint(50, 150)
    await page.evaluate(f"window.scrollBy(0, {distance})")
    await human_delay(0.3, 1.0)


async def human_type(element, text: str):
    """Type text with human-like speed — variable delays between keystrokes."""
    await element.clear_input()
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random.uniform(0.03, 0.12))  # 30-120ms per key


# ── Core agent logic ──

async def is_relevant(text: str, interests: list[str]) -> bool:
    """Check if post text matches user's interests."""
    lower = text.lower()
    return any(interest.lower() in lower for interest in interests)


async def scroll_and_engage(browser, config: dict):
    """Main engagement loop — scroll feed, like, follow."""
    page = await browser.get("https://x.com/home")
    await human_delay(3, 5)  # wait for page load

    session_start = time.time()
    session_minutes = random.randint(
        config["session_duration_min"],
        config["session_duration_max"]
    )
    likes_this_session = 0
    follows_this_session = 0

    log_action("session", f"started ({session_minutes} min planned)")
    print(f"\n  Session: {session_minutes} min, scrolling feed...")

    while True:
        elapsed = (time.time() - session_start) / 60
        if elapsed >= session_minutes:
            break

        # Scroll
        await human_scroll(page)
        scroll_wait = random.uniform(
            config["scroll_speed_min"],
            config["scroll_speed_max"]
        )
        await asyncio.sleep(scroll_wait)

        # Try to find tweet articles on the page
        try:
            articles = await page.query_selector_all('article[data-testid="tweet"]')
            if not articles:
                continue

            # Pick a random visible tweet to potentially engage with
            tweet = random.choice(articles[-5:]) if len(articles) > 5 else random.choice(articles)
            tweet_text = await tweet.get_attribute("innerText") or ""

            if not await is_relevant(tweet_text[:500], config["interests"]):
                continue

            # Like (with probability)
            if (random.random() < config["like_probability"]
                    and likes_this_session < config["max_likes_per_session"]):
                try:
                    like_btn = await tweet.query_selector('[data-testid="like"]')
                    if like_btn:
                        await human_delay(0.5, 1.5)
                        await like_btn.click()
                        likes_this_session += 1
                        snippet = tweet_text[:50].replace("\n", " ")
                        log_action("like", snippet)
                        await human_delay(1, 3)
                except Exception:
                    pass

            # Follow (with lower probability)
            if (random.random() < config["follow_probability"]
                    and follows_this_session < config["max_follows_per_session"]):
                try:
                    # Find the author link and follow button
                    follow_btn = await tweet.query_selector('[data-testid$="-follow"]')
                    if follow_btn:
                        btn_text = await follow_btn.get_attribute("innerText") or ""
                        if "Follow" in btn_text and "Following" not in btn_text:
                            await human_delay(1, 2)
                            await follow_btn.click()
                            follows_this_session += 1
                            log_action("follow", f"followed from feed")
                            await human_delay(2, 4)
                except Exception:
                    pass

        except Exception as e:
            # Page might have changed, just keep scrolling
            pass

        # Occasionally pause like a human reading (20% chance)
        if random.random() < 0.2:
            pause = random.uniform(5, 15)
            await asyncio.sleep(pause)

    log_action("session", f"ended — {likes_this_session} likes, {follows_this_session} follows")
    return likes_this_session, follows_this_session


async def post_draft(browser, config: dict):
    """Post a tweet from the draft queue if available."""
    if not DRAFT_QUEUE.exists():
        return False

    try:
        drafts = json.loads(DRAFT_QUEUE.read_text())
        if not drafts:
            return False

        draft = drafts.pop(0)
        DRAFT_QUEUE.write_text(json.dumps(drafts, indent=2))

        text = draft.get("text", "")
        if not text:
            return False

        page = await browser.get("https://x.com/compose/tweet")
        await human_delay(2, 3)

        # Find the tweet compose box
        compose = await page.query_selector('[data-testid="tweetTextarea_0"]')
        if not compose:
            compose = await page.query_selector('[role="textbox"]')

        if compose:
            await human_type(compose, text)
            await human_delay(1, 2)

            # Click the post button
            post_btn = await page.query_selector('[data-testid="tweetButtonInline"]')
            if not post_btn:
                post_btn = await page.query_selector('[data-testid="tweetButton"]')
            if post_btn:
                await post_btn.click()
                log_action("post", text[:50])
                await human_delay(2, 4)
                return True

    except Exception as e:
        log_action("post", f"failed: {str(e)[:50]}", "fail")

    return False


# ── Main loop ──

async def main():
    # Parse args
    use_opera = "--opera" in sys.argv
    headless = "--headless" in sys.argv

    config = load_config()
    print("X Browser Agent starting...")
    print(f"  Browser: {'Opera' if use_opera else 'Chrome'}")
    print(f"  Interests: {', '.join(config['interests'])}")
    print(f"  Like rate: {config['like_probability']*100:.0f}%")
    print(f"  Follow rate: {config['follow_probability']*100:.0f}%")

    # Launch browser
    browser_args = []
    browser_path = None

    # Browser priority: Opera (has VPN) > standalone Chromium > system Chromium
    browser_options = [
        ("/usr/bin/opera", "Opera"),
        (os.path.expanduser("~/.local/chromium/chrome-linux/chrome"), "Chromium (standalone)"),
        ("/usr/bin/chromium-browser", "Chromium (system)"),
    ]
    browser_name = "unknown"
    for path, name in browser_options:
        if os.path.exists(path):
            browser_path = path
            browser_name = name
            break

    if not browser_path:
        print("ERROR: No browser found. Install Opera (sudo apt install opera-stable) or Chromium.")
        sys.exit(1)

    # Persistent profile — pass as browser arg, not zendriver param (Opera compat)
    profile_dir = os.path.expanduser("~/.moltui/opera-profile")
    os.makedirs(profile_dir, exist_ok=True)

    print(f"  Browser: {browser_name} ({browser_path})")
    print(f"  Profile: {profile_dir}")
    print(f"  Headless: {headless}")
    print()

    browser = await zd.start(
        browser_executable_path=browser_path,
        headless=headless,
        no_sandbox=True,
        browser_args=[
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            f"--user-data-dir={profile_dir}",
        ],
    )

    print("Browser launched. Navigating to X.com...")
    print("Make sure you're logged in! If not, log in manually and restart.\n")

    session_count = 0

    try:
        while True:
            session_count += 1
            print(f"=== Session #{session_count} ===")

            # Check for drafts to post (before scrolling)
            posted = await post_draft(browser, config)
            if posted:
                await human_delay(5, 10)

            # Scroll and engage
            likes, follows = await scroll_and_engage(browser, config)

            # Pause between sessions
            pause_min = config["pause_between_sessions"]
            pause_actual = random.randint(int(pause_min * 0.7), int(pause_min * 1.3))
            print(f"\n  Pausing {pause_actual} min before next session...")
            log_action("pause", f"{pause_actual} min")
            await asyncio.sleep(pause_actual * 60)

    except KeyboardInterrupt:
        print("\nShutting down...")
        log_action("agent", "stopped by user")
    finally:
        await browser.stop()


async def setup_mode():
    """Launch browser for manual login and VPN setup. Session persists in Opera's default profile."""
    browser_path = "/usr/bin/opera"
    if not os.path.exists(browser_path):
        browser_path = os.path.expanduser("~/.local/chromium/chrome-linux/chrome")

    profile_dir = os.path.expanduser("~/.moltui/opera-profile")
    os.makedirs(profile_dir, exist_ok=True)

    print("Setup mode — log in and configure VPN")
    print(f"  Profile: {profile_dir}")
    print("  Press Ctrl+C when done.\n")

    browser = await zd.start(
        browser_executable_path=browser_path,
        headless=False,
        no_sandbox=True,
        browser_args=[
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            f"--user-data-dir={profile_dir}",
        ],
    )

    page = await browser.get("https://x.com/login")
    print("Browser open — log in, enable VPN, set location to Americas.")

    try:
        while True:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nSession saved. Run without --setup to start the agent.")
        await browser.stop()


if __name__ == "__main__":
    if "--setup" in sys.argv:
        asyncio.run(setup_mode())
    else:
        asyncio.run(main())
