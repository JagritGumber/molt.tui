"""
DOM Recorder — renders a webpage frame-by-frame into a video.

Uses Playwright headless to:
1. Open a URL
2. Screenshot every frame at target FPS
3. Stitch frames into MP4 with ffmpeg

No screen recording needed. Works fully headless on WSL2.
"""

import asyncio
import subprocess
import shutil
import time
from pathlib import Path

HOME = Path.home() / ".moltui"
VIDEO_DIR = HOME / "generated-videos"
VIDEO_DIR.mkdir(exist_ok=True)


async def record_page(
    url: str,
    output_filename: str = None,
    duration: float = 10.0,
    fps: int = 24,
    width: int = 1080,
    height: int = 1080,
    simulate_drag: bool = True,
) -> Path:
    """Record a webpage as a video by screenshotting each frame.

    Args:
        url: Page URL to record (http://localhost:... or file://)
        duration: Recording duration in seconds
        fps: Target frames per second (24 or 30 recommended)
        width, height: Viewport size
        simulate_drag: If True, moves mouse to simulate dragging elements
    """
    from playwright.async_api import async_playwright

    if not output_filename:
        output_filename = f"recording-{int(time.time())}.mp4"

    frames_dir = HOME / "recorder-frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir()

    frame_interval = 1.0 / fps
    total_frames = int(duration * fps)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(1000)  # Let animations start

        # Simulate interaction if requested
        if simulate_drag:
            # Move mouse to center, then drag in a slow circle
            cx, cy = width // 2, height // 2

        for i in range(total_frames):
            # Simulate mouse movement for drag interaction
            if simulate_drag and i > fps:  # Start dragging after 1 second
                t = (i - fps) / fps  # Time in seconds since drag started
                import math
                # Slow figure-8 path
                mx = cx + int(200 * math.sin(t * 0.8))
                my = cy + int(120 * math.sin(t * 1.2))
                await page.mouse.move(mx, my)

                # Press mouse on first drag frame, release near end
                if i == fps + 1:
                    await page.mouse.down()
                elif i >= total_frames - fps:
                    await page.mouse.up()

            # Screenshot
            frame_path = frames_dir / f"frame-{i:05d}.png"
            await page.screenshot(path=str(frame_path))

            # Pace to match real-time (roughly)
            if i % 10 == 0:
                print(f"  Recording: frame {i}/{total_frames} ({i * 100 // total_frames}%)")

        await browser.close()

    # Stitch with ffmpeg
    output_path = VIDEO_DIR / output_filename
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame-%05d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        str(output_path),
    ]
    print(f"  Stitching {total_frames} frames...")
    subprocess.run(cmd, capture_output=True)

    # Cleanup frames
    shutil.rmtree(frames_dir)

    size_kb = output_path.stat().st_size / 1024
    print(f"  Done: {output_path} ({size_kb:.0f} KB, {duration}s @ {fps}fps)")
    return output_path


async def record_pretext_demo(
    url: str = "http://localhost:3457",
    duration: float = 12.0,
    filename: str = None,
) -> Path:
    """Record the pretext editorial demo with simulated logo dragging."""
    return await record_page(
        url=url,
        output_filename=filename or f"pretext-demo-{int(time.time())}.mp4",
        duration=duration,
        fps=24,
        width=1280,
        height=720,
        simulate_drag=True,
    )
