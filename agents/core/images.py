"""
Image generator — Carbon-style code cards, terminal screenshots,
tweet cards, metrics cards, milestone cards.

Optimal X dimensions: 1600x900 (16:9) or 1080x1080 (1:1).
"""

import random
import textwrap
import time as _time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HOME = Path.home() / ".moltui"
IMAGE_DIR = HOME / "generated-images"
IMAGE_DIR.mkdir(exist_ok=True)

# ── Gradient backgrounds for cards ──
GRADIENTS = [
    ((30, 20, 60), (60, 30, 80)),       # purple
    ((20, 35, 55), (25, 60, 80)),       # ocean
    ((40, 20, 30), (70, 30, 50)),       # warm
    ((15, 30, 35), (25, 55, 55)),       # teal
    ((25, 25, 40), (50, 40, 70)),       # indigo
    ((30, 30, 30), (50, 50, 50)),       # neutral
]

CORNER_RADIUS = 12
CARD_PADDING = 48  # outer padding around the card

# ── Code card colors ──
CODE_BG = (30, 30, 30)
CODE_HEADER = (42, 42, 42)
CODE_FG = (212, 212, 212)
CODE_KEYWORD = (198, 120, 221)
CODE_STRING = (152, 195, 121)
CODE_COMMENT = (92, 99, 112)
CODE_NUMBER = (209, 154, 102)
CODE_FUNCTION = (97, 175, 239)

# ── Accent colors for metrics/milestones ──
ACCENT_CYAN = (86, 182, 194)
ACCENT_GREEN = (152, 195, 121)
ACCENT_PURPLE = (198, 120, 221)
ACCENT_YELLOW = (229, 192, 123)
ACCENT_RED = (224, 108, 117)


def _font(size: int):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _bold(size: int):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return _font(size)


def _gradient_bg(w: int, h: int, colors=None) -> Image.Image:
    c1, c2 = colors or random.choice(GRADIENTS)
    img = Image.new("RGB", (w, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        ImageDraw.Draw(img).line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _paste_rounded(bg: Image.Image, card: Image.Image, x: int, y: int):
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=CORNER_RADIUS, fill=255)
    bg.paste(card, (x, y), mask)


def _save(img: Image.Image, filename: str = None, prefix: str = "img") -> Path:
    if not filename:
        filename = f"{prefix}-{int(_time.time())}.png"
    path = IMAGE_DIR / filename
    img.save(path, "PNG")
    return path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Code card (Carbon-style)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_code_card(
    code: str,
    filename_label: str = "main.rs",
    width: int = 800,
    output_filename: str = None,
) -> Path:
    font = _font(15)
    bold_f = _bold(15)
    hfont = _font(12)

    lines = code.strip().split("\n")
    wrapped = []
    max_chars = (width - 120) // 9
    for line in lines:
        if len(line) > max_chars:
            wrapped.extend(textwrap.wrap(line, max_chars, subsequent_indent="  "))
        else:
            wrapped.append(line)
    lines = wrapped

    pad = 24
    lh = 22
    header_h = 44
    card_h = header_h + len(lines) * lh + pad * 2

    card = Image.new("RGB", (width, card_h), CODE_BG)
    draw = ImageDraw.Draw(card)

    # Header
    draw.rectangle([0, 0, width, header_h], fill=CODE_HEADER)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([14 + i * 22, 13, 26 + i * 22, 25], fill=c)
    draw.text((90, 14), filename_label, fill=(150, 150, 150), font=hfont)

    # Code
    keywords = {"fn", "let", "mut", "if", "else", "for", "while", "return", "use",
                "struct", "impl", "pub", "async", "await", "def", "class", "import",
                "from", "const", "var", "function", "export", "match", "enum", "type",
                "self", "None", "True", "False", "in", "not", "and", "or", "try", "except"}

    y = header_h + pad
    for i, line in enumerate(lines):
        x = pad + 44
        draw.text((pad + 4, y), f"{i+1:>3}", fill=CODE_COMMENT, font=font)
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        x += indent * 9

        if stripped.startswith("//") or stripped.startswith("#"):
            draw.text((x, y), stripped, fill=CODE_COMMENT, font=font)
        elif stripped.startswith('"') or stripped.startswith("'") or stripped.startswith('`') or stripped.startswith('f"') or stripped.startswith("f'"):
            draw.text((x, y), stripped, fill=CODE_STRING, font=font)
        else:
            for word in stripped.split():
                clean = word.strip("(){}[];:,.<>=!+-*/|&@")
                if clean in keywords:
                    color, f = CODE_KEYWORD, bold_f
                elif clean.replace(".", "").replace("-", "").isdigit():
                    color, f = CODE_NUMBER, font
                elif "(" in word and clean not in keywords:
                    color, f = CODE_FUNCTION, font
                else:
                    color, f = CODE_FG, font
                draw.text((x, y), word + " ", fill=color, font=f)
                x += (len(word) + 1) * 9
        y += lh

    # Place on gradient bg
    outer_w = width + CARD_PADDING * 2
    outer_h = card_h + CARD_PADDING * 2
    bg = _gradient_bg(outer_w, outer_h)
    _paste_rounded(bg, card, CARD_PADDING, CARD_PADDING)
    return _save(bg, output_filename, "code")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Terminal screenshot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_terminal_image(
    lines: list[str],
    title: str = "terminal",
    width: int = 800,
    filename: str = None,
) -> Path:
    font = _font(16)
    bold_f = _bold(16)
    tfont = _font(13)

    pad = 24
    lh = 24
    title_h = 40
    card_h = title_h + len(lines) * lh + pad * 2

    card = Image.new("RGB", (width, card_h), (18, 18, 18))
    draw = ImageDraw.Draw(card)

    draw.rectangle([0, 0, width, title_h], fill=(38, 38, 38))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([14 + i * 22, 12, 28 + i * 22, 26], fill=c)
    bbox = tfont.getbbox(title)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, 13), title, fill=(102, 102, 102), font=tfont)

    y = title_h + pad
    colors = {
        "$": ((86, 182, 194), bold_f),
        "#": ((102, 102, 102), font),
        "✓": ((152, 195, 121), font),
        "ok": ((152, 195, 121), font),
        "✗": ((224, 108, 117), font),
        "ERR": ((224, 108, 117), font),
        "error": ((224, 108, 117), font),
        "WARN": ((229, 192, 123), font),
        "warning": ((229, 192, 123), font),
    }

    for line in lines:
        prefix = line.split(" ")[0] if line else ""
        if prefix == "$":
            draw.text((pad, y), "$ ", fill=(86, 182, 194), font=bold_f)
            draw.text((pad + 20, y), line[2:], fill=(204, 204, 204), font=bold_f)
        elif prefix in colors:
            c, f = colors[prefix]
            draw.text((pad, y), line, fill=c, font=f)
        elif "──" in line or "━━" in line:
            draw.text((pad, y), line, fill=(86, 182, 194), font=font)
        else:
            draw.text((pad, y), line, fill=(204, 204, 204), font=font)
        y += lh

    outer_w = width + CARD_PADDING * 2
    outer_h = card_h + CARD_PADDING * 2
    bg = _gradient_bg(outer_w, outer_h)
    _paste_rounded(bg, card, CARD_PADDING, CARD_PADDING)
    return _save(bg, filename, "terminal")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tweet quote card (square, centered)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_tweet_card(
    text: str,
    handle: str = "@mobtwts",
    size: int = 1080,
    filename: str = None,
) -> Path:
    font = _font(36)
    hfont = _font(22)

    img = Image.new("RGB", (size, size), (12, 12, 12))
    draw = ImageDraw.Draw(img)

    lines = textwrap.wrap(text, width=22)
    lh = 48
    total_h = len(lines) * lh
    start_y = (size - total_h - 60) // 2

    for line in lines:
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(((size - lw) // 2, start_y), line, fill=(235, 235, 235), font=font)
        start_y += lh

    hbox = hfont.getbbox(handle)
    hw = hbox[2] - hbox[0]
    draw.text(((size - hw) // 2, size - 70), handle, fill=(70, 70, 70), font=hfont)

    return _save(img, filename, "tweet-card")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Metrics card (stats with big numbers)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_metrics_card(
    metrics: list[tuple[str, str]],
    title: str = "",
    filename: str = None,
) -> Path:
    """metrics: list of (value, label) tuples. e.g. [("39", "signals"), ("24", "trends")]"""
    n = len(metrics)
    col_w = 200
    width = max(600, n * col_w + 80)
    height = 280

    bg = Image.new("RGB", (width, height), (18, 18, 22))
    draw = ImageDraw.Draw(bg)

    big = _bold(48)
    label_f = _font(16)
    title_f = _bold(18)

    if title:
        bbox = title_f.getbbox(title)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) // 2, 30), title, fill=(150, 150, 150), font=title_f)

    accents = [ACCENT_CYAN, ACCENT_GREEN, ACCENT_PURPLE, ACCENT_YELLOW, ACCENT_RED]
    start_x = (width - n * col_w) // 2
    y_val = 90 if title else 70

    for i, (value, label) in enumerate(metrics):
        x = start_x + i * col_w + col_w // 2
        accent = accents[i % len(accents)]

        vbox = big.getbbox(value)
        vw = vbox[2] - vbox[0]
        draw.text((x - vw // 2, y_val), value, fill=accent, font=big)

        lbox = label_f.getbbox(label)
        lw = lbox[2] - lbox[0]
        draw.text((x - lw // 2, y_val + 65), label, fill=(120, 120, 130), font=label_f)

    # Subtle dividers between metrics
    for i in range(1, n):
        dx = start_x + i * col_w
        draw.line([(dx, y_val + 10), (dx, y_val + 70)], fill=(50, 50, 55), width=1)

    return _save(bg, filename, "metrics")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Milestone card (day counter, streak, achievement)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_milestone_card(
    number: str,
    label: str,
    subtitle: str = "",
    filename: str = None,
) -> Path:
    """Big number + label. e.g. ("14", "days building jarvis", "and it still crashes")"""
    width, height = 1080, 1080

    bg = Image.new("RGB", (width, height), (15, 15, 20))
    draw = ImageDraw.Draw(bg)

    num_font = _bold(120)
    label_font = _font(28)
    sub_font = _font(18)

    # Big number centered
    nbox = num_font.getbbox(number)
    nw = nbox[2] - nbox[0]
    nh = nbox[3] - nbox[1]
    draw.text(((width - nw) // 2, height // 2 - nh - 40), number, fill=ACCENT_CYAN, font=num_font)

    # Label
    lbox = label_font.getbbox(label)
    lw = lbox[2] - lbox[0]
    draw.text(((width - lw) // 2, height // 2 + 30), label, fill=(200, 200, 205), font=label_font)

    # Subtitle
    if subtitle:
        sbox = sub_font.getbbox(subtitle)
        sw = sbox[2] - sbox[0]
        draw.text(((width - sw) // 2, height // 2 + 80), subtitle, fill=(90, 90, 100), font=sub_font)

    # Handle at bottom
    hfont = _font(14)
    handle = "@mobtwts"
    hbox = hfont.getbbox(handle)
    hw = hbox[2] - hbox[0]
    draw.text(((width - hw) // 2, height - 60), handle, fill=(50, 50, 55), font=hfont)

    return _save(bg, filename, "milestone")
