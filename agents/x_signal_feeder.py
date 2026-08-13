#!/usr/bin/env python3
"""
Unified signal feeder for @wyvernotwts posting decisions.

Reads from:
- visible X ingest artifacts under ~/.moltui/x-visible-ingest-runs/
- Hacker News front page
- selected RSS/news/blog feeds

Writes normalized signals to ~/.moltui/x-signals.json
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from email.utils import parsedate_to_datetime
from pathlib import Path

HOME_DIR = Path.home() / ".moltui"
VISIBLE_INGEST_LOG = HOME_DIR / "x-visible-ingest-log.json"
VISIBLE_INGEST_RUNS = HOME_DIR / "x-visible-ingest-runs"
SIGNALS_FILE = HOME_DIR / "x-signals.json"

RSS_FEEDS = [
    ("openai-blog", "https://openai.com/news/rss.xml"),
    ("anthropic-news", "https://www.anthropic.com/news/rss.xml"),
    ("huggingface-blog", "https://huggingface.co/blog/feed.xml"),
    ("replicate-blog", "https://replicate.com/blog/rss.xml"),
    ("vercel-blog", "https://vercel.com/atom"),
]

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "into", "your", "have", "just", "will", "about", "they",
    "their", "what", "when", "where", "there", "would", "could", "should", "while", "than", "them", "then", "more",
    "some", "like", "much", "very", "really", "only", "over", "under", "through", "using", "used", "build", "building",
    "into", "onto", "also", "been", "being", "after", "before", "make", "made", "makes", "most", "still", "here",
}


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


def _clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", (text or "").lower())
    scored = []
    for w in words:
        if w in STOPWORDS or w.startswith("http"):
            continue
        scored.append(w)
    counts = Counter(scored)
    return [w for w, _ in counts.most_common(limit)]


def _infer_tags(text: str) -> list[str]:
    lower = (text or "").lower()
    tags = []
    mapping = {
        "agents": ["agent", "agents", "browser", "operator", "computer use"],
        "video": ["video", "editing", "clip", "film", "render"],
        "research": ["paper", "research", "benchmark", "arxiv", "model card"],
        "builders": ["builder", "founder", "ship", "startup", "product"],
        "infra": ["database", "postgres", "infra", "server", "deployment", "api"],
        "open-source": ["open source", "oss", "github", "repo"],
        "ai-models": ["model", "llm", "gpt", "claude", "gemini", "multimodal"],
        "demo": ["demo", "showcase", "launch", "release", "introducing"],
    }
    for tag, needles in mapping.items():
        if any(n in lower for n in needles):
            tags.append(tag)
    tags.extend(_extract_keywords(text, limit=4))
    deduped = []
    for t in tags:
        if t not in deduped:
            deduped.append(t)
    return deduped[:8]


def _ts_hours_ago(ts: int | float | None) -> float:
    if not ts:
        return 9999.0
    return max(0.0, (time.time() - float(ts)) / 3600.0)


def _request_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Hermes X Feeder"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _request_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Hermes X Feeder"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_x_visible_signals(limit_runs: int = 5) -> list[dict]:
    signals = []
    log = _read_json(VISIBLE_INGEST_LOG, [])
    recent = list(reversed(log[-limit_runs:]))
    for run_meta in recent:
        run_dir = Path(run_meta.get("run_dir", ""))
        ingest = _read_json(run_dir / "ingest.json", {})
        for step in ingest.get("steps", []):
            for post in step.get("visible_posts", []):
                text = _clean_text(post.get("text", ""))
                if not text:
                    continue
                status_links = post.get("status_links") or []
                author = (post.get("author_link") or "").strip("/").split("/")[-1] or "unknown"
                ts = int(step.get("timestamp") or run_meta.get("run_id") or time.time())
                signals.append({
                    "id": f"x-{ts}-{author}-{abs(hash(text[:80])) % 10**8}",
                    "source": "x-visible-ingest",
                    "source_type": "x",
                    "author": author,
                    "title": text.split("\n")[0][:160],
                    "text": text[:1400],
                    "url": f"https://x.com{status_links[0]}" if status_links else run_meta.get("run_dir"),
                    "timestamp": ts,
                    "freshness_hours": round(_ts_hours_ago(ts), 2),
                    "tags": _infer_tags(text),
                    "growth_hint": 1.0,
                    "raw": {"run_id": run_meta.get("run_id"), "step": step.get("step")},
                })
    return signals


def load_hn_signals(limit: int = 12) -> list[dict]:
    signals = []
    try:
        data = _request_json("https://hn.algolia.com/api/v1/search?tags=front_page")
        for item in data.get("hits", [])[:limit]:
            title = _clean_text(item.get("title") or item.get("story_title") or "")
            text = _clean_text((title + " " + (item.get("_highlightResult", {}).get("story_text", {}) or {}).get("value", "")).replace("<em>", "").replace("</em>", ""))
            created = item.get("created_at_i") or int(time.time())
            points = int(item.get("points") or 0)
            comments = int(item.get("num_comments") or 0)
            signals.append({
                "id": f"hn-{item.get('objectID')}",
                "source": "hacker-news",
                "source_type": "news",
                "author": item.get("author") or "hn",
                "title": title,
                "text": text[:1200],
                "url": item.get("url") or item.get("story_url") or f"https://news.ycombinator.com/item?id={item.get('objectID')}",
                "timestamp": int(created),
                "freshness_hours": round(_ts_hours_ago(created), 2),
                "tags": _infer_tags(text or title),
                "growth_hint": round(points / 100.0 + comments / 80.0, 2),
                "raw": {"points": points, "comments": comments},
            })
    except Exception as e:
        signals.append({
            "id": f"hn-error-{int(time.time())}",
            "source": "hacker-news",
            "source_type": "meta",
            "author": "system",
            "title": "HN fetch failed",
            "text": str(e),
            "url": "https://news.ycombinator.com/",
            "timestamp": int(time.time()),
            "freshness_hours": 0.0,
            "tags": ["meta"],
            "growth_hint": 0.0,
            "raw": {},
        })
    return signals


def _parse_rss_timestamp(item) -> int:
    for tag in ("pubDate", "published", "updated"):
        node = item.find(tag)
        if node is not None and node.text:
            try:
                return int(parsedate_to_datetime(node.text).timestamp())
            except Exception:
                try:
                    return int(time.mktime(time.strptime(node.text[:19], "%Y-%m-%dT%H:%M:%S")))
                except Exception:
                    pass
    return int(time.time())


def load_rss_signals(limit_per_feed: int = 6) -> list[dict]:
    signals = []
    for source_name, url in RSS_FEEDS:
        try:
            xml_text = _request_text(url)
            root = ET.fromstring(xml_text)
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            count = 0
            for item in items:
                title_node = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
                link_node = item.find("link") or item.find("{http://www.w3.org/2005/Atom}link")
                desc_node = item.find("description") or item.find("summary") or item.find("{http://www.w3.org/2005/Atom}summary")
                title = _clean_text(title_node.text if title_node is not None and title_node.text else "")
                if not title:
                    continue
                link = ""
                if link_node is not None:
                    link = link_node.text or link_node.attrib.get("href", "")
                text = _clean_text((title + " " + (desc_node.text if desc_node is not None and desc_node.text else ""))[:1400])
                ts = _parse_rss_timestamp(item)
                signals.append({
                    "id": f"rss-{source_name}-{abs(hash(title)) % 10**8}",
                    "source": source_name,
                    "source_type": "rss",
                    "author": source_name,
                    "title": title[:220],
                    "text": text,
                    "url": link or url,
                    "timestamp": ts,
                    "freshness_hours": round(_ts_hours_ago(ts), 2),
                    "tags": _infer_tags(text or title),
                    "growth_hint": 0.8,
                    "raw": {},
                })
                count += 1
                if count >= limit_per_feed:
                    break
        except Exception:
            continue
    return signals


def dedupe_signals(signals: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for sig in sorted(signals, key=lambda s: (s.get("timestamp", 0), s.get("growth_hint", 0)), reverse=True):
        key = ((sig.get("title") or "")[:120].lower(), sig.get("source"), sig.get("author"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sig)
    return deduped


def build_signals() -> dict:
    signals = []
    signals.extend(load_x_visible_signals())
    signals.extend(load_hn_signals())
    signals.extend(load_rss_signals())
    signals = dedupe_signals(signals)
    source_counts = Counter(sig.get("source") for sig in signals)
    x_author_counts = Counter(sig.get("author") for sig in signals if sig.get("source_type") == "x")
    payload = {
        "generated_at": int(time.time()),
        "generated_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "signals": signals[:200],
        "stats": {
            "total_signals": len(signals[:200]),
            "source_counts": dict(source_counts),
            "x_authors_seen": dict(x_author_counts.most_common(20)),
        },
    }
    _write_json(SIGNALS_FILE, payload)
    return payload


def main() -> int:
    payload = build_signals()
    print(json.dumps({
        "signals_written": len(payload.get("signals", [])),
        "path": str(SIGNALS_FILE),
        "top_sources": payload.get("stats", {}).get("source_counts", {}),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
