#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

from x_browser import DRAFT_QUEUE
from x_draft_lab import STRONG_THRESHOLD, critique_batch, generate_batch
from x_feedback_collector import collect_feedback
from x_runtime import HOME_DIR, acquire_global_lock, read_json, release_global_lock, write_json
from x_signal_feeder import build_signals
from x_trend_analyzer import analyze
from x_trend_nudger import choose_candidate, generate_ideas
from x_just_in_time_post import build_draft_entry, queue_draft_entry

MISSION_STATE = HOME_DIR / 'x-mission-state.json'
MISSION_HISTORY = HOME_DIR / 'x-mission-history.json'
MISSION_LOG = HOME_DIR / 'x-mission-log.json'
POST_HISTORY = HOME_DIR / 'x-post-history.json'
STALE_LOCK_SECONDS = 4 * 60 * 60
MAX_ATTEMPTS_PER_MISSION = 6
MISSION_STALE_SECONDS = 18 * 60 * 60
TOP_DRAFTS_TO_KEEP = 5


def log_event(action: str, detail: str, status: str = 'ok'):
    logs = read_json(MISSION_LOG, [])
    logs.append({
        'timestamp': int(time.time()),
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'action': action,
        'status': status,
        'detail': detail[:800],
    })
    write_json(MISSION_LOG, logs[-500:])
    print(f'[{status}] {action}: {detail}')


def read_state() -> dict:
    data = read_json(MISSION_STATE, {})
    return data if isinstance(data, dict) else {}


def write_state(state: dict):
    write_json(MISSION_STATE, state)


def append_history(entry: dict):
    history = read_json(MISSION_HISTORY, [])
    history.append(entry)
    write_json(MISSION_HISTORY, history[-300:])


def mission_age_seconds(mission: dict) -> int:
    ts = int(mission.get('updated_at') or mission.get('created_at') or 0)
    return max(0, int(time.time()) - ts) if ts else 10**9


def queue_items() -> list[dict]:
    data = read_json(DRAFT_QUEUE, [])
    return data if isinstance(data, list) else []


def post_history_items() -> list[dict]:
    data = read_json(POST_HISTORY, [])
    return data if isinstance(data, list) else []


def draft_already_exists(text: str, trend_key: str) -> bool:
    norm = (text or '').strip()
    if not norm:
        return False
    for item in queue_items():
        if (item.get('text') or '').strip() == norm:
            return True
        if item.get('trend_key') == trend_key and (item.get('text') or '').strip() == norm:
            return True
    for item in post_history_items():
        if (item.get('text') or '').strip() == norm:
            return True
    return False


def notify(key: str, message: str, cooldown_seconds: int = 6 * 60 * 60):
    subprocess.run([
        sys.executable,
        str(Path(__file__).resolve().parent / 'x_alert.py'),
        '--key', key,
        '--message', message,
        '--cooldown-seconds', str(cooldown_seconds),
    ], cwd=str(Path(__file__).resolve().parent.parent), check=False)


def close_current_if_needed(state: dict, replacement_reason: str | None = None):
    current = state.get('current')
    if not isinstance(current, dict) or not current:
        return
    archived = dict(current)
    if replacement_reason and archived.get('status') not in {'queued-ready', 'done', 'abandoned', 'superseded'}:
        archived['status'] = 'superseded'
        archived['closed_reason'] = replacement_reason
    archived['closed_at'] = int(time.time())
    append_history(archived)
    state['current'] = None


def make_mission(trend: dict) -> dict:
    now = int(time.time())
    return {
        'mission_id': f"mission-{now}-{uuid.uuid4().hex[:8]}",
        'created_at': now,
        'updated_at': now,
        'status': 'scouted',
        'attempt_count': 0,
        'trend_key': trend.get('trend_key'),
        'trend': trend,
        'ideas': None,
        'top_drafts': [],
        'queued_draft_id': None,
        'last_error': None,
        'next_action': 'generate mission brief and draft candidates',
    }


def ensure_current_mission(state: dict, trend: dict) -> tuple[dict, bool]:
    current = state.get('current')
    if isinstance(current, dict) and current:
        same_trend = current.get('trend_key') == trend.get('trend_key')
        fresh = mission_age_seconds(current) < MISSION_STALE_SECONDS
        active = current.get('status') not in {'queued-ready', 'done', 'abandoned', 'superseded'}
        if same_trend and fresh and active:
            return current, False
        close_current_if_needed(state, replacement_reason='replaced by a fresher or stronger trend')
    mission = make_mission(trend)
    state['current'] = mission
    write_state(state)
    return mission, True


def summarize_top_draft(draft: dict) -> str:
    if not draft:
        return 'none'
    return (
        f"score {draft.get('overall')} | {draft.get('media_type', 'threadless-text')} | "
        f"{(draft.get('text') or '')[:140]}"
    )


def refresh_mission_metadata(mission: dict, trend: dict):
    mission['trend_key'] = trend.get('trend_key')
    mission['trend'] = trend
    mission['updated_at'] = int(time.time())


def run_one_pass(mission: dict) -> dict:
    trend = mission['trend']
    mission['attempt_count'] = int(mission.get('attempt_count', 0)) + 1
    mission['status'] = 'drafting'
    mission['next_action'] = 'generate and critique post packages'
    mission['updated_at'] = int(time.time())

    ideas = mission.get('ideas') or generate_ideas(trend)
    mission['ideas'] = ideas
    mission['status'] = 'briefed'
    mission['next_action'] = 'search for a strong packaged draft'
    mission['updated_at'] = int(time.time())

    drafts = generate_batch(trend, mission['attempt_count'], n=6)
    critiques = critique_batch(trend, drafts)
    mission['top_drafts'] = critiques[:TOP_DRAFTS_TO_KEEP]
    mission['updated_at'] = int(time.time())

    top = critiques[0] if critiques else None
    if not top:
        mission['status'] = 'stalled'
        mission['last_error'] = 'no drafts generated'
        mission['next_action'] = 'retry mission pass later'
        return mission

    if float(top.get('overall', 0)) >= STRONG_THRESHOLD:
        mission['status'] = 'candidate-ready'
        mission['next_action'] = 'queue top draft unless duplicate'
    else:
        mission['status'] = 'needs-next-pass'
        mission['next_action'] = 'rerun mission later for a stronger draft'
    return mission


def queue_top_draft_if_ready(mission: dict) -> tuple[bool, str]:
    if mission.get('queued_draft_id'):
        return False, 'already queued earlier'
    top_drafts = mission.get('top_drafts') or []
    if not top_drafts:
        return False, 'no top drafts available'
    top = top_drafts[0]
    if float(top.get('overall', 0)) < STRONG_THRESHOLD:
        return False, f"top draft below threshold ({top.get('overall')})"
    if draft_already_exists(top.get('text', ''), mission.get('trend_key', '')):
        mission['status'] = 'queued-ready'
        mission['next_action'] = 'wait for existing equivalent draft to play out'
        return False, 'duplicate draft already queued or posted'

    entry = build_draft_entry(top.get('text', ''), mission['trend'], (top.get('angle') or 'mission-loop')[:40])
    entry['mission_id'] = mission['mission_id']
    entry['mission_status'] = mission['status']
    entry['media_type'] = top.get('media_type')
    entry['media_concept'] = top.get('media_concept')
    entry['why_media_helps'] = top.get('why_media_helps')
    entry['score'] = top.get('overall')
    entry['text_only_score'] = top.get('text_only')
    entry['operator_note'] = mission['ideas'].get('nudge')
    queue_draft_entry(entry, mission.get('trend_key', 'unknown'))
    mission['queued_draft_id'] = entry.get('draft_id')
    mission['status'] = 'queued-ready'
    mission['next_action'] = 'let normal post slots publish the queued draft'
    mission['updated_at'] = int(time.time())
    return True, entry.get('draft_id', '')


def maybe_finalize_mission(mission: dict):
    if mission.get('status') == 'queued-ready':
        mission['done_at'] = int(time.time())
    elif int(mission.get('attempt_count', 0)) >= MAX_ATTEMPTS_PER_MISSION:
        mission['status'] = 'abandoned'
        mission['next_action'] = 'drop this trend and scout a fresher one'
        mission['done_at'] = int(time.time())


def build_update_message(mission: dict, created: bool, queued: bool, queue_result: str) -> str:
    top = (mission.get('top_drafts') or [{}])[0]
    prefix = 'New autonomous mission' if created else 'Autonomous mission update'
    lines = [
        f"{prefix} for @wyvernotwts",
        '',
        f"Trend: {mission.get('trend_key')}",
        f"Status: {mission.get('status')}",
        f"Attempts: {mission.get('attempt_count')}",
        f"Why now: {(mission.get('ideas') or {}).get('why_now', '')}",
        '',
        f"Executed: {(mission.get('ideas') or {}).get('build_idea', '')}",
        f"Top draft: {summarize_top_draft(top)}",
        f"Queue result: {queue_result}",
        f"Next: {mission.get('next_action')}",
    ]
    if queued:
        lines.insert(0, 'Queued a strong draft automatically.')
        lines.insert(1, '')
    return '\n'.join(lines).strip()


def main() -> int:
    lock_id = f"mission-loop-{int(time.time())}"
    acquired, info = acquire_global_lock('mission-loop', lock_id, stale_seconds=STALE_LOCK_SECONDS)
    if not acquired:
        log_event('lock', f"busy: {info.get('task_type', 'unknown')} {info.get('task_id', '')}", 'skip')
        return 0

    try:
        build_signals()
        trend_out = analyze()
        collect_feedback()
        trend = choose_candidate(trend_out.get('trends', []))
        if not trend:
            log_event('trend', 'no candidate trend met mission threshold', 'skip')
            return 0

        state = read_state()
        mission, created = ensure_current_mission(state, trend)
        refresh_mission_metadata(mission, trend)
        write_state(state)
        log_event('mission', f"using mission {mission['mission_id']} for trend {mission['trend_key']}")

        mission = run_one_pass(mission)
        queue_result = 'not attempted'
        queued = False
        if mission.get('status') == 'candidate-ready':
            queued, queue_result = queue_top_draft_if_ready(mission)
        elif mission.get('status') == 'needs-next-pass':
            queue_result = 'top draft not strong enough yet'
        elif mission.get('status') == 'stalled':
            queue_result = mission.get('last_error') or 'stalled'

        maybe_finalize_mission(mission)
        state['current'] = mission
        write_state(state)
        log_event('mission', f"status={mission.get('status')} top={summarize_top_draft((mission.get('top_drafts') or [{}])[0])}")

        if created or queued:
            notify(
                key=f"mission-{mission.get('trend_key')}",
                message=build_update_message(mission, created=created, queued=queued, queue_result=queue_result),
                cooldown_seconds=3 * 60 * 60 if queued else 6 * 60 * 60,
            )

        print(json.dumps({
            'mission_id': mission.get('mission_id'),
            'trend_key': mission.get('trend_key'),
            'status': mission.get('status'),
            'attempt_count': mission.get('attempt_count'),
            'queued_draft_id': mission.get('queued_draft_id'),
            'top_draft': (mission.get('top_drafts') or [None])[0],
            'next_action': mission.get('next_action'),
        }, indent=2, ensure_ascii=False))
        return 0
    finally:
        release_global_lock(lock_id)
        log_event('lock', 'released')


if __name__ == '__main__':
    raise SystemExit(main())
