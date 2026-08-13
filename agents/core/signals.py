"""Signal Feeder — aggregates signals from HN, RSS feeds, and X artifacts."""

import hashlib
import json
import re
import time
import urllib.request
from typing import Optional

from agents.core.config import HOME, SIGNALS_FILE, save_json

# ── RSS sources ──
RSS_FEEDS = {
    "openai-blog": "https://openai.com/blog/rss.xml",
    "anthropic-blog": "https://www.anthropic.com/rss.xml",
    "huggingface-blog": "https://huggingface.co/blog/feed.xml",
    "vercel-blog": "https://vercel.com/atom",
}

# ── Tag inference patterns ──
TAG_PATTERNS = {
    "agents": r"\bagent|agentic|autonomous\b",
    "llm": r"\bllm|language model|gpt|claude|gemini\b",
    "video": r"\bvideo|clip|stream\b",
    "research": r"\bresearch|paper|arxiv|findings\b",
    "demo": r"\bdemo|showcase|prototype|proof\b",
    "infra": r"\binfra|infrastructure|deploy|kubernetes|docker\b",
    "rust": r"\brust|cargo|crate\b",
    "open-source": r"\bopen.?source|oss|github|apache|mit license\b",
    "ai-models": r"\bmodel|fine.?tun|train|weights|checkpoint\b",
    "tools": r"\btool|sdk|cli|framework|library\b",
    "performance": r"\bperformance|benchmark|latency|throughput|speed\b",
}


def _sig_id(source: str, title: str) -> str:
    h = hashlib.sha256(f"{source}:{title[:120]}".encode()).hexdigest()[:12]
    return f"{source}-{h}"


def _infer_tags(text: str) -> list[str]:
    tags = []
    lower = text.lower()
    for tag, pattern in TAG_PATTERNS.items():
        if re.search(pattern, lower):
            tags.append(tag)
    return tags


def _fetch_json(url: str, timeout: int = 15) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MoltSignalBot/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception:
        return None


def _fetch_text(url: str, timeout: int = 15) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MoltSignalBot/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_rss_items(xml: str, source: str) -> list[dict]:
    """Minimal RSS/Atom parser — extracts title + link from items."""
    items = []
    # Try Atom <entry> first, then RSS <item>
    for tag in ("entry", "item"):
        pattern = re.compile(
            rf"<{tag}[^>]*>(.*?)</{tag}>", re.DOTALL
        )
        for match in pattern.findall(xml):
            title_m = re.search(r"<title[^>]*>(.*?)</title>", match, re.DOTALL)
            link_m = re.search(r'<link[^>]*href="([^"]*)"', match) or \
                     re.search(r"<link[^>]*>(.*?)</link>", match, re.DOTALL)
            title = (title_m.group(1) if title_m else "").strip()
            title = re.sub(r"<!\[CDATA\[|\]\]>", "", title).strip()
            url = ""
            if link_m:
                url = link_m.group(1).strip()
            if title:
                text = title
                desc_m = re.search(
                    r"<(?:description|summary|content)[^>]*>(.*?)</(?:description|summary|content)>",
                    match, re.DOTALL,
                )
                if desc_m:
                    desc = re.sub(r"<[^>]+>", "", desc_m.group(1))
                    desc = re.sub(r"<!\[CDATA\[|\]\]>", "", desc).strip()
                    text = f"{title}. {desc[:500]}"

                items.append({
                    "id": _sig_id(source, title),
                    "source": source,
                    "source_type": "rss",
                    "author": source,
                    "title": title[:220],
                    "text": text[:1400],
                    "url": url,
                    "timestamp": int(time.time()),
                    "freshness_hours": 0,
                    "tags": _infer_tags(text),
                    "growth_hint": 0.3,
                    "raw": {},
                })
    return items[:8]  # Max 8 per feed


class SignalFeeder:
    async def fetch_all(self) -> list[dict]:
        """Fetch and normalize signals from all sources."""
        signals = []

        # ── Hacker News ──
        hn_data = _fetch_json(
            "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=15"
        )
        if hn_data and "hits" in hn_data:
            now = time.time()
            for hit in hn_data["hits"][:15]:
                title = hit.get("title", "")
                if not title:
                    continue
                ts = hit.get("created_at_i", int(now))
                text = f"{title}. {hit.get('story_text', '')[:500]}"
                signals.append({
                    "id": _sig_id("hacker-news", title),
                    "source": "hacker-news",
                    "source_type": "news",
                    "author": hit.get("author", ""),
                    "title": title[:220],
                    "text": text[:1400],
                    "url": hit.get("url", f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"),
                    "timestamp": ts,
                    "freshness_hours": round((now - ts) / 3600, 1),
                    "tags": _infer_tags(text),
                    "growth_hint": min(1.0, (hit.get("points", 0) or 0) / 500),
                    "raw": {},
                })

        # ── RSS feeds ──
        for source, url in RSS_FEEDS.items():
            xml = _fetch_text(url, timeout=10)
            if xml:
                items = _parse_rss_items(xml, source)
                signals.extend(items)

        # ── Deduplicate by ID ──
        seen = set()
        deduped = []
        for s in signals:
            if s["id"] not in seen:
                seen.add(s["id"])
                deduped.append(s)

        # Save to disk
        save_json(SIGNALS_FILE, {
            "generated_at": int(time.time()),
            "count": len(deduped),
            "signals": deduped[:200],
        })

        return deduped[:200]
