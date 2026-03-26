"""
X/Twitter Browser Agent — Hermes-inspired autonomous engagement agent.
Uses zendriver (undetectable CDP) + LLM decision-making (like Hermes Agent).

Architecture (inspired by Hermes Agent by Nous Research):
- LLM decides everything: like, skip, follow, reply, what to reply
- Post-session reflection: reviews actions, extracts learnings for next session
- Skill memory: successful patterns saved as files, loaded at session start
- Human-like behavior: randomized timing, pauses, tab closing between sessions

Usage:
  source .venv/bin/activate
  python agents/x_browser.py              # Run engagement agent
  python agents/x_browser.py --setup      # Login + VPN setup
  python agents/x_browser.py --seed       # Follow niche accounts to fix feed
  python agents/x_browser.py --windows    # Connect to Windows Chrome via CDP
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
LEARNINGS_FILE = HOME_DIR / "x-agent-learnings.json"
ZAI_CONFIG = HOME_DIR / "config.json"

DEFAULT_CONFIG = {
    "interests": ["AI", "databases", "postgres", "rust", "typescript", "infrastructure",
                   "developer tools", "LLM", "open source", "performance", "systems programming"],
    "target_accounts": [
        "mattpocockuk", "t3dotgg", "levelsio", "rauchg", "swyx",
        "jonhoo", "andy_pavlo", "karpathy", "kelseyhightower", "dhh",
        "ThePrimeagen", "fireship_dev",
    ],
    "seed_accounts": [
        # AI / ML
        "karpathy", "ylecun", "goodfellow_ian", "DrJimFan", "EMostaque",
        "ClementDelangue", "Yoshua_Bengio", "sama", "lexfridman",
        "realGeorgeHotz", "clattner_llvm",
        # Dev tools / Infra
        "rauchg", "kelseyhightower", "mitchellh", "solomonstre", "dhh", "youyuxi",
        # Rust
        "jonhoo", "ManishEarth",
        # TypeScript / Web
        "mattpocockuk", "t3dotgg", "ryanflorence", "kentcdodds", "dan_abramov2",
        # Databases
        "andy_pavlo", "mdcallag",
        # Indie makers
        "levelsio", "tibo_maker", "marc_louvion", "dannypostmaa",
        # Tech leaders
        "patrickc", "paulg", "naval",
        # AI agents / dev
        "hwchase17", "JeffDean", "Suhail",
        # Dev content
        "ThePrimeagen", "fireship_dev",
    ],
    "scroll_speed_min": 2.0,
    "scroll_speed_max": 8.0,
    "session_duration_min": 20,
    "session_duration_max": 45,
    "pause_between_sessions": 60,
    "max_likes_per_session": 20,
    "max_follows_per_session": 5,
    "max_replies_per_session": 3,
    "target_visits_per_session": 3,
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
    if len(logs) > 500:
        logs = logs[-500:]
    ACTION_LOG.write_text(json.dumps(logs, indent=2))
    print(f"  [{status}] {action}: {detail[:60]}")


def load_learnings() -> list[str]:
    if LEARNINGS_FILE.exists():
        try:
            return json.loads(LEARNINGS_FILE.read_text())
        except Exception:
            pass
    return []


def save_learnings(learnings: list[str]):
    if len(learnings) > 50:
        learnings = learnings[-50:]
    LEARNINGS_FILE.write_text(json.dumps(learnings, indent=2))


# ── LLM Integration (Z.ai) ──

def get_zai_config() -> tuple[str, str] | None:
    """Load Z.ai API key and model from moltui config."""
    if ZAI_CONFIG.exists():
        try:
            cfg = json.loads(ZAI_CONFIG.read_text())
            key = cfg.get("zaiApiKey", "")
            model = cfg.get("zaiModel", "GLM-4.7-FlashX")
            if key:
                return key, model
        except Exception:
            pass
    return None


async def llm_decide(tweet_text: str, author: str, learnings: list[str]) -> dict:
    """LLM decides what to do with a tweet. Returns {action, reply_text}."""
    zai = get_zai_config()
    if not zai:
        return {"action": "skip"}

    key, model = zai
    learnings_block = ""
    if learnings:
        learnings_block = "\n\nLEARNED FROM PAST SESSIONS:\n" + "\n".join(f"- {l}" for l in learnings[-10:])

    prompt = f"""You are a Twitter engagement strategist for @ItsRoboki (Jagrit), a developer who builds postgres extensions, Rust tools, and AI agents.

GOAL: Build authentic relationships in tech Twitter by engaging meaningfully.
{learnings_block}

TWEET by @{author}:
"{tweet_text[:400]}"

Decide ONE action. Reply with EXACTLY one of these formats:
LIKE - this tweet is relevant and worth engaging with
REPLY: [your reply text, max 200 chars, casual lowercase, no hashtags]
FOLLOW - this person posts consistently valuable content in our niche
SKIP - not relevant or not worth engaging with

Rules for REPLY (the most valuable action — 75x engagement weight):
- Only reply if you can add genuine value or a unique perspective
- Sound like a real dev, not a bot — casual, lowercase, opinionated
- Reference your own experience when possible (postgres, rust, AI agents)
- Never be generic ("great post!", "so true!")
- Never use hashtags or emojis in replies"""

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.z.ai/api/paas/v4/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 80,
                "temperature": 0.9,
                "stream": False,
                "thinking": {"type": "disabled"},
            }).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        answer = data["choices"][0]["message"]["content"].strip()

        if answer.startswith("REPLY:"):
            reply_text = answer[6:].strip().strip('"').strip("'")[:200]
            # Sanitize AI signatures
            reply_text = reply_text.replace("—", "-").replace(""", '"').replace(""", '"')
            return {"action": "reply", "reply_text": reply_text}
        elif answer.startswith("LIKE"):
            return {"action": "like"}
        elif answer.startswith("FOLLOW"):
            return {"action": "follow"}
        else:
            return {"action": "skip"}
    except Exception as e:
        log_action("llm", f"decide failed: {str(e)[:40]}", "fail")
        return {"action": "skip"}


async def llm_reflect(session_log: list[dict], learnings: list[str]) -> list[str]:
    """Post-session reflection — extract learnings from what happened."""
    zai = get_zai_config()
    if not zai:
        return learnings

    key, model = zai
    log_summary = "\n".join(
        f"[{e['action']}] {e['detail']}" for e in session_log[-30:]
    )

    prompt = f"""Review this Twitter engagement session and extract 1-3 learnings.

SESSION LOG:
{log_summary}

EXISTING LEARNINGS:
{chr(10).join(f'- {l}' for l in learnings[-10:]) if learnings else '(none yet)'}

What patterns worked? What should we do more of? What should we avoid?
Reply with 1-3 bullet points, each on its own line starting with "- ".
Keep each under 80 chars. Only write genuinely new insights, not repeats."""

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.z.ai/api/paas/v4/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.7,
                "stream": False,
                "thinking": {"type": "disabled"},
            }).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        answer = data["choices"][0]["message"]["content"].strip()

        new_learnings = [
            line.lstrip("- ").strip()[:80]
            for line in answer.split("\n")
            if line.strip().startswith("-") and len(line.strip()) > 5
        ]
        for l in new_learnings:
            if l not in learnings:
                learnings.append(l)
                log_action("learn", l)

        save_learnings(learnings)
    except Exception as e:
        log_action("reflect", f"failed: {str(e)[:40]}", "fail")

    return learnings


# ── Human-like behavior ──

async def human_delay(min_s: float = 0.5, max_s: float = 2.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_scroll(page):
    distance = random.randint(200, 600)
    if random.random() < 0.1:
        distance = -random.randint(50, 150)
    await page.evaluate(f"window.scrollBy(0, {distance})")
    await human_delay(0.3, 1.0)


async def human_type(element, text: str):
    await element.clear_input()
    for char in text:
        await element.send_keys(char)
        await asyncio.sleep(random.uniform(0.03, 0.12))


# ── Core agent logic ──

async def engage_target_account(browser, handle: str, config: dict, learnings: list[str]) -> tuple[int, int, int]:
    """Visit a target creator's profile and engage intelligently."""
    likes, follows, replies = 0, 0, 0
    try:
        page = await browser.get(f"https://x.com/{handle}")
        await human_delay(3, 5)
        log_action("visit", f"@{handle} profile")

        for scroll_i in range(random.randint(3, 6)):
            await human_scroll(page)
            await asyncio.sleep(random.uniform(2, 5))

            try:
                articles = await page.query_selector_all('article[data-testid="tweet"]')
                if not articles:
                    continue

                tweet = articles[min(scroll_i, len(articles) - 1)]
                tweet_text = await tweet.get_attribute("innerText") or ""
                if not tweet_text.strip():
                    continue

                # LLM decides what to do
                decision = await llm_decide(tweet_text[:500], handle, learnings)

                if decision["action"] == "like" and likes < 3:
                    try:
                        like_btn = await tweet.query_selector('[data-testid="like"]')
                        if like_btn:
                            await human_delay(0.5, 1.5)
                            await like_btn.click()
                            likes += 1
                            log_action("like", f"@{handle}: {tweet_text[:40].replace(chr(10), ' ')}")
                            await human_delay(1, 3)
                    except Exception:
                        pass

                elif decision["action"] == "reply" and replies < config.get("max_replies_per_session", 3):
                    try:
                        reply_btn = await tweet.query_selector('[data-testid="reply"]')
                        if reply_btn:
                            await human_delay(1, 2)
                            await reply_btn.click()
                            await human_delay(1, 2)
                            # Find reply compose box
                            compose = await page.query_selector('[data-testid="tweetTextarea_0"]')
                            if compose:
                                await human_type(compose, decision["reply_text"])
                                await human_delay(1, 2)
                                send_btn = await page.query_selector('[data-testid="tweetButton"]')
                                if send_btn:
                                    await send_btn.click()
                                    replies += 1
                                    log_action("reply", f"@{handle}: {decision['reply_text'][:40]}")
                                    await human_delay(2, 4)
                    except Exception:
                        pass

                elif decision["action"] == "follow":
                    try:
                        follow_btns = await page.query_selector_all('[data-testid$="-follow"]')
                        for btn in follow_btns:
                            btn_text = await btn.get_attribute("innerText") or ""
                            if btn_text.strip() == "Follow":
                                await human_delay(1, 2)
                                await btn.click()
                                follows += 1
                                log_action("follow", f"@{handle}")
                                break
                    except Exception:
                        pass

            except Exception:
                pass

            if random.random() < 0.2:
                await asyncio.sleep(random.uniform(5, 12))

    except Exception as e:
        log_action("visit", f"@{handle} failed: {str(e)[:40]}", "fail")

    return likes, follows, replies


async def scroll_and_engage(browser, config: dict, learnings: list[str]):
    """Main engagement loop — visit targets first, then scroll feed with LLM decisions."""

    total_likes, total_follows, total_replies = 0, 0, 0

    # Phase 1: Visit target accounts
    target_accounts = config.get("target_accounts", [])
    if target_accounts:
        targets = random.sample(target_accounts, min(config.get("target_visits_per_session", 3), len(target_accounts)))
        print(f"  Phase 1: Visiting {len(targets)} target accounts...")
        for handle in targets:
            l, f, r = await engage_target_account(browser, handle, config, learnings)
            total_likes += l
            total_follows += f
            total_replies += r
            await human_delay(3, 8)

    # Phase 2: Scroll home feed with LLM decisions
    print(f"  Phase 2: Scrolling home feed (LLM-guided)...")
    page = await browser.get("https://x.com/home")
    await human_delay(3, 5)

    session_start = time.time()
    session_minutes = random.randint(config["session_duration_min"], config["session_duration_max"])
    log_action("session", f"started ({session_minutes} min)")

    while True:
        elapsed = (time.time() - session_start) / 60
        if elapsed >= session_minutes:
            break

        await human_scroll(page)
        await asyncio.sleep(random.uniform(config["scroll_speed_min"], config["scroll_speed_max"]))

        try:
            articles = await page.query_selector_all('article[data-testid="tweet"]')
            if not articles:
                continue

            tweet = random.choice(articles[-5:]) if len(articles) > 5 else random.choice(articles)
            tweet_text = await tweet.get_attribute("innerText") or ""
            if not tweet_text.strip():
                continue

            # LLM decides
            decision = await llm_decide(tweet_text[:500], "feed", learnings)

            if decision["action"] == "like" and total_likes < config["max_likes_per_session"]:
                try:
                    like_btn = await tweet.query_selector('[data-testid="like"]')
                    if like_btn:
                        await human_delay(0.5, 1.5)
                        await like_btn.click()
                        total_likes += 1
                        log_action("like", tweet_text[:50].replace("\n", " "))
                        await human_delay(1, 3)
                except Exception:
                    pass

            elif decision["action"] == "reply" and total_replies < config.get("max_replies_per_session", 3):
                try:
                    reply_btn = await tweet.query_selector('[data-testid="reply"]')
                    if reply_btn:
                        await human_delay(1, 2)
                        await reply_btn.click()
                        await human_delay(1, 2)
                        compose = await page.query_selector('[data-testid="tweetTextarea_0"]')
                        if compose:
                            await human_type(compose, decision["reply_text"])
                            await human_delay(1, 2)
                            send_btn = await page.query_selector('[data-testid="tweetButton"]')
                            if send_btn:
                                await send_btn.click()
                                total_replies += 1
                                log_action("reply", decision["reply_text"][:50])
                                await human_delay(2, 4)
                except Exception:
                    pass

            elif decision["action"] == "follow" and total_follows < config["max_follows_per_session"]:
                try:
                    follow_btn = await tweet.query_selector('[data-testid$="-follow"]')
                    if follow_btn:
                        btn_text = await follow_btn.get_attribute("innerText") or ""
                        if btn_text.strip() == "Follow":
                            await human_delay(1, 2)
                            await follow_btn.click()
                            total_follows += 1
                            log_action("follow", "from feed")
                            await human_delay(2, 4)
                except Exception:
                    pass

        except Exception:
            pass

        if random.random() < 0.2:
            await asyncio.sleep(random.uniform(5, 15))

    log_action("session", f"ended — {total_likes}L {total_follows}F {total_replies}R")
    return total_likes, total_follows, total_replies


async def post_draft(browser, config: dict):
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
        compose = await page.query_selector('[data-testid="tweetTextarea_0"]')
        if not compose:
            compose = await page.query_selector('[role="textbox"]')
        if compose:
            await human_type(compose, text)
            await human_delay(1, 2)
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
    headless = "--headless" in sys.argv
    config = load_config()
    learnings = load_learnings()

    has_llm = get_zai_config() is not None
    print("X Browser Agent starting...")
    print(f"  LLM brain: {'Z.ai connected' if has_llm else 'OFFLINE (keyword matching only)'}")
    print(f"  Learnings: {len(learnings)} from past sessions")
    print(f"  Targets: {len(config.get('target_accounts', []))} accounts")

    browser = await launch_browser(headless=headless)
    print("Browser launched.\n")

    session_count = 0
    session_log_start = 0

    try:
        while True:
            session_count += 1
            print(f"=== Session #{session_count} ===")

            # Track where this session's log entries start
            try:
                existing_log = json.loads(ACTION_LOG.read_text()) if ACTION_LOG.exists() else []
                session_log_start = len(existing_log)
            except Exception:
                session_log_start = 0

            # Post drafts
            posted = await post_draft(browser, config)
            if posted:
                await human_delay(5, 10)

            # Engage
            likes, follows, replies = await scroll_and_engage(browser, config, learnings)

            # Post-session reflection (Hermes-inspired)
            try:
                full_log = json.loads(ACTION_LOG.read_text()) if ACTION_LOG.exists() else []
                session_entries = full_log[session_log_start:]
                if session_entries and has_llm:
                    print("  Reflecting on session...")
                    learnings = await llm_reflect(session_entries, learnings)
            except Exception:
                pass

            # Pause
            pause_min = config["pause_between_sessions"]
            pause_actual = random.randint(int(pause_min * 0.7), int(pause_min * 1.3))
            print(f"\n  Closing tab, pausing {pause_actual} min...")
            log_action("pause", f"{pause_actual} min")
            page = await browser.get("about:blank")
            await asyncio.sleep(pause_actual * 60)
            print(f"  Resuming...")

    except KeyboardInterrupt:
        print("\nShutting down...")
        log_action("agent", "stopped by user")
    finally:
        await browser.stop()


async def setup_mode():
    print("Setup mode — log in and configure VPN")
    print("  Press Ctrl+C when done.\n")
    browser = await launch_browser(headless=False)
    page = await browser.get("https://x.com/login")
    print("Browser open — log in, enable VPN, set location to Americas.")
    try:
        while True:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nSession saved.")
        await browser.stop()


async def seed_mode():
    config = load_config()
    seed_accounts = config.get("seed_accounts", [])
    if not seed_accounts:
        print("No seed accounts configured.")
        return

    print(f"Seed mode — following {len(seed_accounts)} accounts to fix your feed\n")
    browser = await launch_browser(headless=False)
    followed = 0

    for handle in seed_accounts:
        try:
            page = await browser.get(f"https://x.com/{handle}")
            await human_delay(2, 4)
            follow_btns = await page.query_selector_all('[data-testid$="-follow"]')
            for btn in follow_btns:
                btn_text = await btn.get_attribute("innerText") or ""
                if btn_text.strip() == "Follow":
                    await human_delay(1, 2)
                    await btn.click()
                    followed += 1
                    print(f"  [{followed}/{len(seed_accounts)}] Followed @{handle}")
                    log_action("seed-follow", f"@{handle}")
                    break
            else:
                print(f"  [skip] @{handle}")
            await asyncio.sleep(random.uniform(3, 8))
        except Exception as e:
            print(f"  [fail] @{handle}: {str(e)[:40]}")

    print(f"\nDone! Followed {followed} new accounts.")
    await browser.stop()


async def launch_browser(headless=False):
    profile_dir = os.path.expanduser("~/.moltui/opera-profile")
    os.makedirs(profile_dir, exist_ok=True)

    if "--windows" in sys.argv:
        print("  Connecting to Windows Chrome via CDP (localhost:9222)...")
        import urllib.request
        try:
            resp = urllib.request.urlopen("http://localhost:9222/json/version")
            data = json.loads(resp.read())
            ws_url = data["webSocketDebuggerUrl"]
            browser = await zd.start(browser_websocket_url=ws_url)
            print(f"  Connected to {data.get('Browser', 'Chrome')}")
            return browser
        except Exception:
            print("  ERROR: Launch Chrome first with: chrome.exe --remote-debugging-port=9222")
            sys.exit(1)

    browser_options = [
        ("/usr/bin/opera", "Opera"),
        (os.path.expanduser("~/.local/chromium/chrome-linux/chrome"), "Chromium"),
    ]
    browser_path = None
    for path, name in browser_options:
        if os.path.exists(path):
            browser_path = path
            print(f"  Browser: {name}")
            break

    if not browser_path:
        print("ERROR: No browser found.")
        sys.exit(1)

    return await zd.start(
        browser_executable_path=browser_path,
        headless=headless,
        no_sandbox=True,
        browser_args=[
            "--disable-dev-shm-usage",
            "--no-first-run",
            f"--user-data-dir={profile_dir}",
            "--enable-unsafe-swiftshader",
            "--ignore-gpu-blocklist",
        ],
    )


if __name__ == "__main__":
    if "--setup" in sys.argv:
        asyncio.run(setup_mode())
    elif "--seed" in sys.argv:
        asyncio.run(seed_mode())
    else:
        asyncio.run(main())
