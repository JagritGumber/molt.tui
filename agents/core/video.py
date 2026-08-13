"""
Video generator — short clips with text overlays for X posts.

Three modes:
  1. "stock" — download a royalty-free clip from Pexels, add text overlay
  2. "custom" — use a clip from ~/.moltui/clips/, add text overlay
  3. "motion" — generate text animation (no source clip needed)

All output: MP4, 1080x1080 or 1280x720, under 30 seconds.
"""

import os
import json
import random
import urllib.request
from pathlib import Path

from moviepy import (
    VideoFileClip, TextClip, CompositeVideoClip,
    ColorClip, concatenate_videoclips, vfx,
)

HOME = Path.home() / ".moltui"
VIDEO_DIR = HOME / "generated-videos"
CLIPS_DIR = HOME / "clips"  # user drops source clips here
VIDEO_DIR.mkdir(exist_ok=True)
CLIPS_DIR.mkdir(exist_ok=True)

PEXELS_FALLBACK_QUERIES = ["coding", "computer", "terminal", "typing keyboard", "dark room monitor"]


def _get_font_path() -> str:
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(p).exists():
            return p
    return "DejaVu-Sans-Bold"


def _download_pexels_clip(query: str, duration: int = 10) -> Path | None:
    """Download a short royalty-free clip from Pexels. No API key needed for search."""
    try:
        # Pexels has a free video search - try to grab one
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&size=small"
        # Pexels requires an API key, but we can try the public endpoint
        # If no key, fall back to motion-only mode
        pexels_key = os.environ.get("PEXELS_API_KEY", "")
        if not pexels_key:
            return None

        req = urllib.request.Request(url, headers={"Authorization": pexels_key})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())

        videos = data.get("videos", [])
        if not videos:
            return None

        video = random.choice(videos)
        # Get smallest file
        files = video.get("video_files", [])
        files = [f for f in files if f.get("width", 9999) <= 1280]
        if not files:
            files = video.get("video_files", [])
        if not files:
            return None

        dl_url = files[0]["link"]
        out = CLIPS_DIR / f"pexels-{video['id']}.mp4"
        if not out.exists():
            urllib.request.urlretrieve(dl_url, out)
        return out
    except Exception:
        return None


def _get_random_clip() -> Path | None:
    """Get a random clip from the clips directory."""
    clips = list(CLIPS_DIR.glob("*.mp4")) + list(CLIPS_DIR.glob("*.webm")) + list(CLIPS_DIR.glob("*.mov"))
    return random.choice(clips) if clips else None


def make_text_video(
    text: str,
    subtitle: str = "@mobtwts",
    duration: float = 8.0,
    filename: str = None,
) -> Path:
    """Pure text animation on dark bg. No source clip needed.

    Text fades in, holds, handle appears at bottom.
    """
    size = (1080, 1080)
    font_path = _get_font_path()

    # Dark background
    bg = ColorClip(size, color=(12, 12, 12), duration=duration)

    # Main text - fade in
    txt = TextClip(
        text=text,
        font_size=42,
        color="white",
        font=font_path,
        text_align="center",
        size=(900, None),
        method="caption",
    )
    txt = txt.with_duration(duration).with_position("center").with_start(0.5)
    txt = txt.with_effects([vfx.CrossFadeIn(0.8)])

    # Handle at bottom
    handle = TextClip(
        text=subtitle,
        font_size=18,
        color="#555555",
        font=font_path,
    )
    handle = handle.with_duration(duration).with_position(("center", size[1] - 60)).with_start(1.5)
    handle = handle.with_effects([vfx.CrossFadeIn(0.5)])

    final = CompositeVideoClip([bg, txt, handle], size=size)

    if not filename:
        import time as _t
        filename = f"text-video-{int(_t.time())}.mp4"
    path = VIDEO_DIR / filename
    final.write_videofile(
        str(path), fps=24, codec="libx264",
        audio=False, logger=None,
        preset="ultrafast",
    )
    final.close()
    return path


def make_overlay_video(
    clip_path: str | Path,
    text: str,
    subtitle: str = "@mobtwts",
    max_duration: float = 12.0,
    filename: str = None,
) -> Path:
    """Take an existing clip, add text overlay at bottom."""
    font_path = _get_font_path()

    clip = VideoFileClip(str(clip_path))
    # Trim to max duration
    if clip.duration > max_duration:
        start = random.uniform(0, clip.duration - max_duration)
        clip = clip.subclipped(start, start + max_duration)

    # Resize to square 1080x1080
    w, h = clip.size
    if w != h:
        s = min(w, h)
        clip = clip.with_effects([vfx.Crop(
            x_center=w // 2, y_center=h // 2,
            width=s, height=s,
        )])
    clip = clip.with_effects([vfx.Resize((1080, 1080))])

    # Semi-transparent bottom bar
    bar_h = 200
    bar = ColorClip((1080, bar_h), color=(0, 0, 0)).with_opacity(0.7)
    bar = bar.with_duration(clip.duration).with_position(("center", 1080 - bar_h))

    # Text on the bar
    txt = TextClip(
        text=text,
        font_size=36,
        color="white",
        font=font_path,
        text_align="center",
        size=(950, None),
        method="caption",
    )
    txt = txt.with_duration(clip.duration).with_position(("center", 1080 - bar_h + 30))

    # Handle
    handle = TextClip(
        text=subtitle,
        font_size=16,
        color="#888888",
        font=font_path,
    )
    handle = handle.with_duration(clip.duration).with_position(("center", 1080 - 40))

    final = CompositeVideoClip([clip, bar, txt, handle])

    if not filename:
        import time as _t
        filename = f"overlay-video-{int(_t.time())}.mp4"
    path = VIDEO_DIR / filename
    final.write_videofile(
        str(path), fps=24, codec="libx264",
        audio=False, logger=None,
        preset="ultrafast",
    )
    for c in [final, clip]:
        c.close()
    return path


def make_video_for_draft(draft: dict) -> Path | None:
    """Auto-pick the best video type for a draft.

    1. If custom clips exist in ~/.moltui/clips/ → overlay video
    2. Otherwise → text animation video
    """
    text = draft.get("text", "")

    # Try custom clip first
    clip = _get_random_clip()
    if clip:
        try:
            return make_overlay_video(clip, text)
        except Exception:
            pass

    # Fall back to text animation
    try:
        return make_text_video(text)
    except Exception:
        return None
