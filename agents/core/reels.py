"""
Reels pipeline — find motivational tech reels on Instagram, download, process, post on X.

Pipeline:
  1. Scrape reel URLs from source accounts
  2. Download via yt-dlp
  3. Add caption text overlay on top + @mobtwts watermark
  4. Post to X via zendriver
"""

import asyncio
import json
import os
import random
import subprocess
import time
from pathlib import Path

from moviepy import VideoFileClip, TextClip, CompositeVideoClip, ColorClip, concatenate_videoclips, vfx

HOME = Path.home() / ".moltui"
REELS_DIR = HOME / "reels"
REELS_DIR.mkdir(exist_ok=True)
PROCESSED_DIR = HOME / "reels-processed"
PROCESSED_DIR.mkdir(exist_ok=True)
REELS_DB = HOME / "reels-db.json"

# Source Instagram accounts for motivational tech content
SOURCE_ACCOUNTS = [
    "tom.developer",
    "tech.unicorn",
    "codewithharshad",
    "coding_unicorn",
    "ishansharma7390",
    "alexhormozi",
    "garyvee",
    "entrepreneurshipfacts",
    "foundr",
    "programer.life",
    "andresvidoza",
    "codeofthefuture",
]

# Hashtags to search
HASHTAGS = [
    "codingmotivation",
    "techmotivation",
    "programmermotivation",
    "startuplife",
    "codinglife",
    "devlife",
    "buildinpublic",
]

WATERMARK = "@mobtwts"
VENV_YTDLP = str(Path.home() / ".moltui" / ".." / "d" / "moltui" / ".venv" / "bin" / "yt-dlp")


def _get_ytdlp() -> str:
    """Find yt-dlp binary."""
    # Check venv first
    venv_path = Path("/mnt/d/moltui/.venv/bin/yt-dlp")
    if venv_path.exists():
        return str(venv_path)
    # Check system
    for p in ["/usr/local/bin/yt-dlp", "/usr/bin/yt-dlp"]:
        if Path(p).exists():
            return p
    return "yt-dlp"


def _get_font_path() -> str:
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(p).exists():
            return p
    return "DejaVu-Sans-Bold"


def _load_db() -> dict:
    if REELS_DB.exists():
        return json.loads(REELS_DB.read_text())
    return {"downloaded": [], "posted": [], "failed": []}


def _save_db(db: dict):
    REELS_DB.write_text(json.dumps(db, indent=2))


def discover_reels(account: str = None, count: int = 5) -> list[str]:
    """Get reel URLs by reading the captured-reels.json file.

    The capture happens separately via zendriver CDP (see discover_reels_via_cdp).
    This function just reads what was already captured.
    """
    db_path = HOME / "captured-reels.json"
    if not db_path.exists():
        return []
    data = json.loads(db_path.read_text())
    codes = data.get("reel_ids", [])
    # Filter out already downloaded
    reels_db = _load_db()
    downloaded = set(reels_db.get("downloaded", []))
    urls = [f"https://www.instagram.com/reel/{c}/" for c in codes
            if f"https://www.instagram.com/reel/{c}/" not in downloaded]
    return urls[:count]


async def discover_reels_via_cdp(cdp_host: str = "172.22.80.1", cdp_port: int = 9223) -> list[str]:
    """Scrape reel IDs from Instagram feed using zendriver CDP.

    Navigates to /reels/, scrolls, intercepts graphql responses.
    Saves results to captured-reels.json.
    """
    import re
    import zendriver as zd
    from zendriver import cdp as cdp_mod

    browser = await zd.start(host=cdp_host, port=cdp_port)
    page = await browser.get("https://www.instagram.com/reels/")
    await asyncio.sleep(5)

    await page.send(cdp_mod.network.enable(
        max_total_buffer_size=10000000,
        max_resource_buffer_size=5000000,
    ))

    request_map = {}
    all_codes = []

    async def on_response(event):
        url = event.response.url
        if "graphql" in url or "clips" in url:
            request_map[event.request_id] = url

    async def on_loaded(event):
        rid = event.request_id
        if rid in request_map:
            try:
                result = await page.send(cdp_mod.network.get_response_body(rid))
                body = result[0] if isinstance(result, tuple) else str(result)
                codes = re.findall(r'"code":"([A-Za-z0-9_-]{8,15})"', body)
                all_codes.extend(codes)
            except Exception:
                pass

    page.add_handler(cdp_mod.network.ResponseReceived, on_response)
    page.add_handler(cdp_mod.network.LoadingFinished, on_loaded)

    for _ in range(15):
        await page.evaluate("window.scrollBy(0, 400)")
        await asyncio.sleep(1.5)

    await asyncio.sleep(3)

    unique_codes = list(set(all_codes))

    # Merge with existing
    db_path = HOME / "captured-reels.json"
    existing = []
    if db_path.exists():
        existing = json.loads(db_path.read_text()).get("reel_ids", [])

    merged = list(set(existing + unique_codes))
    db_path.write_text(json.dumps({"reel_ids": merged}, indent=2))

    print(f"  REELS: discovered {len(unique_codes)} new, {len(merged)} total")
    return [f"https://www.instagram.com/reel/{c}/" for c in unique_codes]


def download_reel(url: str) -> Path | None:
    """Download a single reel. Returns path to downloaded file."""
    db = _load_db()
    if url in db["downloaded"] or url in db["failed"]:
        return None

    ytdlp = _get_ytdlp()
    output_template = str(REELS_DIR / "%(id)s.%(ext)s")

    try:
        result = subprocess.run(
            [
                ytdlp,
                "--format", "best[height<=1080]",
                "--output", output_template,
                "--no-playlist",
                "--max-filesize", "50M",
                url,
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            db["failed"].append(url)
            _save_db(db)
            return None

        # Find the downloaded file
        for line in result.stdout.split("\n"):
            if "Destination:" in line or "has already been downloaded" in line:
                path_str = line.split("Destination:")[-1].strip() if "Destination:" in line else ""
                if path_str and Path(path_str).exists():
                    db["downloaded"].append(url)
                    _save_db(db)
                    return Path(path_str)

        # Fallback: find newest file in reels dir
        files = sorted(REELS_DIR.glob("*.*"), key=os.path.getmtime, reverse=True)
        if files:
            db["downloaded"].append(url)
            _save_db(db)
            return files[0]

        return None
    except Exception:
        db["failed"].append(url)
        _save_db(db)
        return None


def process_reel(
    video_path: Path,
    caption: str,
    watermark: str = WATERMARK,
) -> Path:
    """Add caption text on top + watermark on bottom of video."""
    font_path = _get_font_path()

    clip = VideoFileClip(str(video_path))

    # Trim last 3 seconds (remove original creator's brand card/watermark)
    if clip.duration > 6:
        clip = clip.subclipped(0, clip.duration - 3)

    # Limit to 60 seconds for X
    if clip.duration > 60:
        clip = clip.subclipped(0, 60)

    w, h = clip.size

    # Caption text at the top
    txt = TextClip(
        text=caption,
        font_size=min(36, w // 20),
        color="white",
        font=font_path,
        text_align="center",
        size=(int(w * 0.85), None),
        method="caption",
        stroke_color="black",
        stroke_width=2,
    )
    txt = txt.with_duration(clip.duration).with_position(("center", int(h * 0.05)))

    # Watermark at bottom right
    wm = TextClip(
        text=watermark,
        font_size=min(20, w // 30),
        color="#999999",
        font=font_path,
    )
    wm = wm.with_duration(clip.duration).with_position((int(w * 0.7), int(h * 0.93)))

    main = CompositeVideoClip([clip, txt])

    # Outro card: @mobtwts on dark bg for 2.5 seconds
    outro_duration = 2.5
    w, h = clip.size
    outro_bg = ColorClip((w, h), color=(12, 12, 12), duration=outro_duration)

    outro_handle = TextClip(
        text=watermark,
        font_size=min(48, w // 12),
        color="white",
        font=font_path,
        text_align="center",
    )
    outro_handle = outro_handle.with_duration(outro_duration).with_position("center")

    outro = CompositeVideoClip([outro_bg, outro_handle], size=(w, h))

    # Combine main video + outro
    final = concatenate_videoclips([main, outro])

    output = PROCESSED_DIR / f"processed-{int(time.time())}.mp4"
    final.write_videofile(
        str(output),
        fps=min(30, clip.fps or 30),
        codec="libx264",
        audio_codec="aac",
        logger=None,
        preset="fast",
    )
    for c in [final, clip, main, outro]:
        try: c.close()
        except: pass

    return output


def get_unposted_reels() -> list[Path]:
    """Get processed reels that haven't been posted yet."""
    db = _load_db()
    posted_files = set(db.get("posted", []))
    files = sorted(PROCESSED_DIR.glob("*.mp4"), key=os.path.getmtime)
    return [f for f in files if str(f) not in posted_files]


def mark_posted(path: Path):
    db = _load_db()
    db.setdefault("posted", []).append(str(path))
    _save_db(db)


async def fetch_and_process_reel(caption: str = None) -> Path | None:
    """Full pipeline: pick account → discover → download → process."""
    account = random.choice(SOURCE_ACCOUNTS)
    print(f"  REELS: checking @{account}...")

    urls = discover_reels(account, count=3)
    if not urls:
        print(f"  REELS: no reels found for @{account}")
        return None

    url = random.choice(urls)
    print(f"  REELS: downloading {url[:60]}...")

    path = download_reel(url)
    if not path:
        print(f"  REELS: download failed")
        return None

    if not caption:
        caption = random.choice(MOTIVATIONAL_CAPTIONS)

    print(f"  REELS: processing with caption: {caption[:50]}...")
    processed = process_reel(path, caption)
    print(f"  REELS: done → {processed} ({processed.stat().st_size // 1024} KB)")
    return processed


# Pre-built motivational captions (LLM can generate more)
MOTIVATIONAL_CAPTIONS = [
    "the code doesn't care about your feelings. ship it.",
    "you're not behind. you're on your own timeline.",
    "every expert was once a beginner who didn't quit.",
    "the best time to start was yesterday. the second best is now.",
    "your comfort zone is a beautiful place but nothing grows there.",
    "debug your life like you debug your code.",
    "consistency beats talent when talent doesn't show up.",
    "the error is the lesson. the fix is the growth.",
    "stop waiting for motivation. discipline is what ships code.",
    "your future self is watching you through memories. make them proud.",
    "the only way to learn to code is to code.",
    "dream big. start small. act now.",
    "fall seven times. deploy eight.",
    "the grind is the gift.",
    "what you build today becomes your portfolio tomorrow.",
    "pain is temporary. a deployed project is forever.",
    "they laughed at my side project. now its my main project.",
    "your skills are your startup capital.",
    "less tutorial. more building.",
    "the gap between where you are and where you want to be is called work.",
]
