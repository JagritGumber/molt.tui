"""
Diagram generator — clean, polished diagrams. No fake hand-drawn wobble.

Excalidraw-inspired: dark bg, rounded rects, clean arrows, good typography.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HOME = Path.home() / ".moltui"
IMAGE_DIR = HOME / "generated-images"
IMAGE_DIR.mkdir(exist_ok=True)

# Colors
BG = (20, 20, 25)
BOX_BG = (35, 35, 42)
BOX_BORDER = (70, 70, 85)
TEXT_PRIMARY = (230, 230, 235)
TEXT_DIM = (120, 120, 135)
ACCENT = (86, 182, 194)
ARROW_COLOR = (100, 100, 115)


def _font(size: int):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _bold(size: int):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return _font(size)


def _draw_box(draw, x, y, w, h, label, sublabel=None, radius=8):
    """Rounded rect with label."""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=BOX_BG, outline=BOX_BORDER, width=2)
    f = _font(15)
    bbox = f.getbbox(label)
    lw = bbox[2] - bbox[0]
    draw.text((x + (w - lw) // 2, y + h // 2 - 10), label, fill=TEXT_PRIMARY, font=f)
    if sublabel:
        sf = _font(11)
        sbbox = sf.getbbox(sublabel)
        sw = sbbox[2] - sbbox[0]
        draw.text((x + (w - sw) // 2, y + h + 6), sublabel, fill=TEXT_DIM, font=sf)


def _draw_arrow(draw, x1, y1, x2, y2, color=ARROW_COLOR):
    """Clean arrow with triangular head."""
    draw.line([(x1, y1), (x2, y2)], fill=color, width=2)
    angle = math.atan2(y2 - y1, x2 - x1)
    head = 10
    for da in [0.45, -0.45]:
        hx = x2 - head * math.cos(angle + da)
        hy = y2 - head * math.sin(angle + da)
        draw.line([(x2, y2), (int(hx), int(hy))], fill=color, width=2)


def _center_text(draw, x, y, w, text, font, color=TEXT_PRIMARY):
    """Draw text centered in a given width."""
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    draw.text((x + (w - tw) // 2, y), text, fill=color, font=font)


def diagram_flow(steps: list[str], title: str = "", sublabels: list[str] = None) -> Path:
    """Flow diagram: boxes connected by arrows in a row."""
    n = len(steps)
    box_w, box_h = 130, 50
    gap = 50
    padding = 40
    title_h = 50 if title else 0

    total_w = n * box_w + (n - 1) * gap
    width = total_w + padding * 2
    height = box_h + padding * 2 + title_h + 30  # 30 for sublabels

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if title:
        _center_text(draw, 0, 18, width, title, _bold(18))

    y = title_h + padding
    for i, step in enumerate(steps):
        x = padding + i * (box_w + gap)
        sub = sublabels[i] if sublabels and i < len(sublabels) else None
        _draw_box(draw, x, y, box_w, box_h, step, sublabel=sub)
        if i < n - 1:
            _draw_arrow(draw, x + box_w + 4, y + box_h // 2, x + box_w + gap - 4, y + box_h // 2)

    import time as _t
    path = IMAGE_DIR / f"diagram-{int(_t.time())}.png"
    img.save(path, "PNG")
    return path


def diagram_arch(title: str = "agent loop") -> Path:
    """Architecture diagram: signals → trends → drafts, with feedback loop to post."""
    width, height = 680, 320
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    _center_text(draw, 0, 16, width, title, _bold(20))

    box_w, box_h = 140, 55
    y1 = 70

    # Top row
    boxes = [
        (40, y1, "signals", "HN + RSS"),
        (250, y1, "trends", "cluster + score"),
        (460, y1, "drafts", "LLM generate"),
    ]
    for x, y, label, sub in boxes:
        _draw_box(draw, x, y, box_w, box_h, label, sublabel=sub)

    # Arrows between top row
    _draw_arrow(draw, 184, y1 + box_h // 2, 246, y1 + box_h // 2)
    _draw_arrow(draw, 394, y1 + box_h // 2, 456, y1 + box_h // 2)

    # Post box (bottom center)
    post_x, post_y = 250, 210
    _draw_box(draw, post_x, post_y, box_w, box_h, "post", sublabel="compose + upload")

    # Arrow: drafts → post
    _draw_arrow(draw, 530, y1 + box_h + 4, 390, post_y - 4, color=ACCENT)

    # Feedback arrow: post → signals
    _draw_arrow(draw, post_x - 4, post_y + box_h // 2, 110, y1 + box_h + 4, color=TEXT_DIM)

    # Feedback label
    draw.text((90, 175), "feedback", fill=TEXT_DIM, font=_font(11))

    import time as _t
    path = IMAGE_DIR / f"diagram-{int(_t.time())}.png"
    img.save(path, "PNG")
    return path


def diagram_compare(left: str, right: str, left_items: list[str], right_items: list[str], title: str = "") -> Path:
    """Side-by-side comparison diagram."""
    width, height = 620, max(200, 80 + len(max(left_items, right_items, key=len)) * 0 + max(len(left_items), len(right_items)) * 28 + 100)
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if title:
        _center_text(draw, 0, 16, width, title, _bold(18))

    col_w = 250
    left_x, right_x = 40, 330
    header_y = 60

    # Headers
    draw.text((left_x + 20, header_y), left, fill=ACCENT, font=_bold(16))
    draw.text((right_x + 20, header_y), right, fill=ACCENT, font=_bold(16))

    # Divider
    draw.line([(width // 2, header_y - 5), (width // 2, height - 20)], fill=BOX_BORDER, width=1)

    # Items
    f = _font(13)
    y = header_y + 35
    for item in left_items:
        draw.text((left_x + 20, y), f"· {item}", fill=TEXT_DIM, font=f)
        y += 26

    y = header_y + 35
    for item in right_items:
        draw.text((right_x + 20, y), f"· {item}", fill=TEXT_PRIMARY, font=f)
        y += 26

    import time as _t
    path = IMAGE_DIR / f"diagram-{int(_t.time())}.png"
    img.save(path, "PNG")
    return path


def diagram_stack(title: str, layers: list[str]) -> Path:
    """Vertical stack diagram - layers top to bottom."""
    box_w, box_h = 280, 45
    gap = 8
    padding = 40
    title_h = 50 if title else 0
    n = len(layers)

    width = box_w + padding * 2
    height = n * (box_h + gap) + padding * 2 + title_h

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if title:
        _center_text(draw, 0, 16, width, title, _bold(18))

    for i, layer in enumerate(layers):
        x = padding
        y = title_h + padding + i * (box_h + gap)
        _draw_box(draw, x, y, box_w, box_h, layer)
        if i < n - 1:
            _draw_arrow(draw, x + box_w // 2, y + box_h + 2, x + box_w // 2, y + box_h + gap - 2)

    import time as _t
    path = IMAGE_DIR / f"diagram-{int(_t.time())}.png"
    img.save(path, "PNG")
    return path
