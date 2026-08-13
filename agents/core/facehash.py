"""
Facehash — deterministic face avatar from a string.

Port of facehash npm package logic to Pillow.
Generates a unique minimalist face from any username.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HOME = Path.home() / ".moltui"
IMAGE_DIR = HOME / "generated-images"
IMAGE_DIR.mkdir(exist_ok=True)

# Facehash color palette (from the npm package)
COLORS = [
    (255, 107, 107),   # red
    (255, 159, 67),    # orange
    (254, 202, 87),    # yellow
    (29, 209, 161),    # green
    (72, 219, 251),    # cyan
    (84, 160, 255),    # blue
    (95, 39, 205),     # indigo
    (200, 80, 192),    # purple
    (255, 121, 198),   # pink
    (0, 210, 211),     # teal
]

# 9 look directions (rotation offsets for the face)
LOOK_DIRS = [
    (-1, 1), (1, 1), (1, 0), (0, 1), (-1, 0),
    (0, 0), (0, -1), (-1, -1), (1, -1),
]


def _string_hash(s: str) -> int:
    """DJB2 hash - same as facehash npm."""
    h = 0
    for ch in s:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    return abs(h) if h < 0x80000000 else abs(h - 0x100000000)


def _draw_round_eyes(draw, cx, cy, spread, size, color):
    """Two filled circles."""
    draw.ellipse([cx - spread - size, cy - size, cx - spread + size, cy + size], fill=color)
    draw.ellipse([cx + spread - size, cy - size, cx + spread + size, cy + size], fill=color)


def _draw_cross_eyes(draw, cx, cy, spread, size, color):
    """Two + shaped eyes."""
    w = max(2, size // 3)
    for ox in [-spread, spread]:
        x, y = cx + ox, cy
        draw.rectangle([x - w, y - size, x + w, y + size], fill=color)
        draw.rectangle([x - size, y - w, x + size, y + w], fill=color)


def _draw_line_eyes(draw, cx, cy, spread, size, color):
    """Two horizontal line eyes with dots."""
    w = max(2, size // 3)
    for ox in [-spread, spread]:
        x, y = cx + ox, cy
        draw.ellipse([x - w, y - w, x + w, y + w], fill=color)
        draw.rectangle([x, y - w, x + size, y + w], fill=color)


def _draw_curved_eyes(draw, cx, cy, spread, size, color):
    """Two arc/curved eyes."""
    for ox in [-spread, spread]:
        x, y = cx + ox, cy
        # Draw a thick arc
        bbox = [x - size, y - size, x + size, y + size]
        draw.arc(bbox, start=200, end=340, fill=color, width=max(2, size // 3))


EYE_TYPES = [_draw_round_eyes, _draw_cross_eyes, _draw_line_eyes, _draw_curved_eyes]


def generate_facehash(
    name: str,
    size: int = 400,
    filename: str = None,
) -> Path:
    """Generate a facehash avatar for a username.

    Returns path to the PNG file.
    """
    h = _string_hash(name)

    # Deterministic selections from hash
    eye_type = EYE_TYPES[h % len(EYE_TYPES)]
    color = COLORS[h % len(COLORS)]
    look = LOOK_DIRS[h % len(LOOK_DIRS)]
    initial = name[0].upper()

    # Darken the color for background
    bg_color = tuple(max(0, c // 5) for c in color)

    img = Image.new("RGB", (size, size), bg_color)
    draw = ImageDraw.Draw(img)

    # Subtle radial gradient overlay
    center = size // 2
    for r in range(center, 0, -1):
        alpha = int(20 * (r / center))
        overlay_color = tuple(min(255, c + alpha) for c in bg_color)
        draw.ellipse([center - r, center - r, center + r, center + r], fill=overlay_color)

    # Face position (shifted by look direction)
    face_cx = center + look[0] * size // 20
    face_cy = center + look[1] * size // 20

    # Eyes
    eye_spread = size // 5
    eye_size = size // 14
    eye_y = face_cy - size // 10
    eye_type(draw, face_cx, eye_y, eye_spread, eye_size, color)

    # Initial letter (mouth area)
    try:
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        ]
        font = None
        for fp in font_candidates:
            if Path(fp).exists():
                font = ImageFont.truetype(fp, size // 4)
                break
        if not font:
            font = ImageFont.load_default(size // 4)
    except Exception:
        font = ImageFont.load_default(size // 4)

    bbox = font.getbbox(initial)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    text_x = face_cx - tw // 2
    text_y = face_cy + size // 12
    draw.text((text_x, text_y), initial, fill=color, font=font)

    if not filename:
        filename = f"facehash-{name}.png"
    path = IMAGE_DIR / filename
    img.save(path, "PNG")
    return path
