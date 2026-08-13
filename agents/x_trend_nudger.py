#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from x_browser import get_zai_config
from x_signal_feeder import build_signals
from x_trend_analyzer import analyze
from x_runtime import HOME_DIR, get_account

NUDGE_LOG = HOME_DIR / 'x-trend-nudges.json'
PC_NOTIFY = 'D:\\moltui\\windows\\x_pc_notify.ps1'
POWERSHELL = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'

HIGH_AFFINITY = {
    'agents', 'builders', 'infra', 'open-source', 'ai-models', 'demo', 'video',
    'rust', 'systems', 'workflow', 'sdk', 'tool', 'engine', 'gamedev', 'compiler',
}
LOW_AFFINITY = {
    'energy', 'desk', 'camera', 'people', 'cat', 'meow', 'microsoft', 'doj', 'fbi',
    'solar', 'politics', 'hacked', 'windows-account',
}
GENERIC_BUILD_PATTERNS = [
    'dashboard', 'gamify engagement', 'reward users', 'productivity insights',
    'marketplace', 'consumer app', 'analytics platform', 'community app',
]
BANNED_ANGLE_PATTERNS = [
    'viral growth tactics', 'app store', 'engagement loop', 'monetization using',
    'reward users', 'gamify', 'social currency',
]


def read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def recently_nudged(trend_key: str, cooldown_minutes: int = 240) -> bool:
    now = int(time.time())
    for item in reversed(read_json(NUDGE_LOG, [])):
        if item.get('trend_key') == trend_key:
            return now - int(item.get('timestamp', 0)) < cooldown_minutes * 60
    return False


def llm_json(prompt: str) -> dict | None:
    zai = get_zai_config()
    if not zai:
        return None
    key, model = zai
    try:
        req = urllib.request.Request(
            'https://api.z.ai/api/paas/v4/chat/completions',
            data=json.dumps({
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 650,
                'temperature': 0.85,
                'stream': False,
                'thinking': {'type': 'disabled'},
                'response_format': {'type': 'json_object'},
            }).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read())
        text = (data['choices'][0]['message']['content'] or '').strip()
        return json.loads(text)
    except Exception:
        return None


def clean_line(text: str, limit: int = 220) -> str:
    text = re.sub(r'\s+', ' ', (text or '').strip())
    return text[:limit]


def trend_fit_score(trend: dict) -> float:
    tags = {str(t).lower() for t in (trend.get('tags') or [])}
    text = ' '.join((trend.get('sample_titles') or [])).lower() + ' ' + ' '.join(tags)
    score = float(trend.get('score', 0.0))
    score += 0.12 * sum(1 for t in tags if t in HIGH_AFFINITY)
    score -= 0.10 * sum(1 for t in tags if t in LOW_AFFINITY)
    if any(k in text for k in ['rust', 'systems', 'engine', 'gamedev', 'sdk', 'workflow', 'open source', 'agent']):
        score += 0.18
    if any(k in text for k in ['consumer gimmick', 'cat', 'desk', 'camera']) and not any(k in text for k in ['sensor', 'engine', 'tool', 'sdk']):
        score -= 0.25
    if any(k in text for k in ['politics', 'fbi', 'doj', 'microsoft account']) and not any(k in text for k in ['developer', 'tool', 'workflow']):
        score -= 0.22
    return round(score, 3)


def fallback_ideas(trend: dict) -> dict:
    title = clean_line((trend.get('sample_titles') or [trend.get('trend_key', 'trend')])[0], 160)
    tags = [str(t) for t in (trend.get('tags') or [])[:4]]
    tag_text = ', '.join(tags) if tags else trend.get('trend_key', 'trend')
    return {
        'why_now': clean_line(f"{title} is fresh enough to matter now and can be reframed around builder leverage instead of headline chasing."),
        'build_idea': clean_line(f"Prototype a tiny devtool, systems demo, or creator workflow around {tag_text} that shows a concrete capability in under 30 seconds."),
        'post_idea': clean_line(f"Post the harsh truth behind {trend.get('trend_key')}: the real edge is not the headline, it is what suddenly became cheaper or faster to ship."),
        'original_angles': [
            'Translate the trend into a workflow shift builders can actually use.',
            'Look for the low-level constraint or infra bottleneck hidden underneath it.',
            'Find the demo, clip, or system behavior that makes it instantly legible.',
        ],
        'nudge': 'Worth either prototyping today or turning into a visual-first original post before the angle gets crowded.',
        'conviction': 'medium',
    }


def sanitize_ideas(ideas: dict, trend: dict) -> dict:
    out = {
        'why_now': clean_line(ideas.get('why_now', '')),
        'build_idea': clean_line(ideas.get('build_idea', '')),
        'post_idea': clean_line(ideas.get('post_idea', '')),
        'original_angles': [clean_line(x, 140) for x in (ideas.get('original_angles') or [])[:3]],
        'nudge': clean_line(ideas.get('nudge', ''), 180),
        'conviction': clean_line(ideas.get('conviction', 'medium'), 20).lower() or 'medium',
    }
    if len(out['original_angles']) < 3:
        out = fallback_ideas(trend)
    bad_text = ' '.join([out['build_idea'], out['post_idea'], out['why_now']] + out['original_angles']).lower()
    if any(p in bad_text for p in GENERIC_BUILD_PATTERNS + BANNED_ANGLE_PATTERNS):
        out = fallback_ideas(trend)
    if not out['post_idea']:
        out['post_idea'] = fallback_ideas(trend)['post_idea']
    if out['conviction'] not in {'low', 'medium', 'high'}:
        out['conviction'] = 'medium'
    return out


def generate_ideas(trend: dict) -> dict:
    titles = '\n'.join(f"- {t}" for t in (trend.get('sample_titles') or [])[:4])
    tags = ', '.join((trend.get('tags') or [])[:6])
    account = get_account()['handle']
    prompt = f"""You are a trend scout for @{account}.

The user wants nudges only when a trend can plausibly become:
- a sharp original X post
- a tiny build, demo, tool, engine, workflow, or experiment

The user taste is NOT generic SaaS.
Strong fits:
- AI systems
- devtools
- low-level/software infrastructure
- Rust/workflows/codegen/systems
- gamedev/engine/demo angles
- visual-first creator-native posts

Weak fits:
- generic dashboards
- generic consumer app ideas
- productivity app mush
- broad business advice
- title-lifted commentary

Return strict JSON with keys:
- why_now
- build_idea
- post_idea
- original_angles (array of exactly 3 strings)
- nudge
- conviction

Context:
- trend key: {trend.get('trend_key')}
- mode: {trend.get('recommended_mode')}
- score: {trend.get('score')}
- creator angle: {trend.get('creator_angle')}
- tags: {tags}
- sample titles:
{titles}

Rules:
- sharp, concise, sponsor-safe
- no em dashes
- no fake first-person claims
- do not just restate the source headline
- build_idea must feel like something this user would actually build
- post_idea must feel like an original creator-native post, ideally visual or demo compatible
- original_angles should be distinct and non-generic
- conviction must be one of: low, medium, high
"""
    return sanitize_ideas(llm_json(prompt) or fallback_ideas(trend), trend)


def send_telegram_message(key: str, message: str, cooldown_seconds: int = 3 * 60 * 60):
    subprocess.run([
        sys.executable,
        str(Path(__file__).resolve().parent / 'x_alert.py'),
        '--key', key,
        '--message', message,
        '--cooldown-seconds', str(cooldown_seconds),
    ], cwd=str(Path(__file__).resolve().parent.parent))


def send_pc_notification(title: str, message: str):
    subprocess.run([
        POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', PC_NOTIFY,
        '-Title', title,
        '-Message', message,
    ])


def format_message(trend: dict, ideas: dict) -> str:
    angles = ideas.get('original_angles') or []
    angle_block = '\n'.join(f"- {a}" for a in angles[:3])
    return (
        f"Trend nudge for @{get_account()['handle']}\n\n"
        f"Trend: {trend.get('trend_key')}\n"
        f"Mode: {trend.get('recommended_mode')}\n"
        f"Score: {trend.get('score')}\n"
        f"Fit: {trend.get('fit_score')}\n"
        f"Conviction: {ideas.get('conviction', 'medium')}\n"
        f"Why now: {ideas.get('why_now', '')}\n\n"
        f"Build idea: {ideas.get('build_idea', '')}\n\n"
        f"Post idea: {ideas.get('post_idea', '')}\n\n"
        f"Original angles:\n{angle_block}\n\n"
        f"Nudge: {ideas.get('nudge', '')}"
    )


def record_nudge(entry: dict):
    logs = read_json(NUDGE_LOG, [])
    logs.append(entry)
    logs = logs[-300:]
    write_json(NUDGE_LOG, logs)


def choose_candidate(trends: list[dict]) -> dict | None:
    ranked = []
    for trend in trends:
        fit = trend_fit_score(trend)
        trend = dict(trend)
        trend['fit_score'] = fit
        if float(trend.get('score', 0)) < 0.56:
            continue
        if fit < 0.68:
            continue
        if int(trend.get('signal_count', 0)) < 2 and fit < 0.82:
            continue
        if recently_nudged(trend.get('trend_key', '')):
            continue
        ranked.append(trend)
    ranked.sort(key=lambda t: (t['fit_score'], float(t.get('score', 0)), int(t.get('signal_count', 0))), reverse=True)
    return ranked[0] if ranked else None


def main() -> int:
    build_signals()
    trend_out = analyze()
    trend = choose_candidate(trend_out.get('trends', []))
    if not trend:
        print('no-nudge')
        return 0
    ideas = generate_ideas(trend)
    message = format_message(trend, ideas)
    send_telegram_message(f"trend-nudge-{trend.get('trend_key')}", message)
    send_pc_notification('Wyverno trend nudge', f"{trend.get('trend_key')} | {ideas.get('nudge', '')[:180]}")
    entry = {
        'timestamp': int(time.time()),
        'trend_key': trend.get('trend_key'),
        'trend': trend,
        'ideas': ideas,
        'message': message,
    }
    record_nudge(entry)
    print(json.dumps({'nudged': True, 'trend_key': trend.get('trend_key'), 'message': message}, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
