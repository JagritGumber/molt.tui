"""
CLI for operator interaction with the X agent.

Usage:
  # Tell the agent something (direction, correction, preference)
  python -m agents.core.cli note "posts should be more controversial"
  python -m agents.core.cli note "never mention competitor X by name"
  python -m agents.core.cli note "focus on Rust content this week"

  # See what the agent suggests you do manually
  python -m agents.core.cli suggestions

  # See current profile
  python -m agents.core.cli profile

  # See post history
  python -m agents.core.cli history
"""

import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.core.profile import (
    load_profile, add_operator_note,
    get_pending_suggestions, PROFILE_FILE,
)
from agents.core.config import (
    POST_HISTORY, DRAFTS_FILE, SCHEDULER_LOG,
    load_json, save_json,
)

ET = ZoneInfo("America/New_York")


def cmd_note(text: str):
    add_operator_note(text)
    print(f"Saved. The agent will use this in future drafts.")
    print(f"  > {text}")


def cmd_suggestions():
    pending = get_pending_suggestions()
    if not pending:
        print("No pending suggestions.")
        return
    print(f"{len(pending)} pending suggestions:\n")
    for i, s in enumerate(pending, 1):
        ts = datetime.fromtimestamp(s["created_at"], ET).strftime("%b %d %H:%M")
        print(f"  {i}. [{s['category']}] {s['suggestion']}")
        print(f"     ({ts})")


def cmd_profile():
    profile = load_profile()
    print(json.dumps(profile, indent=2))
    print(f"\nEdit directly: {PROFILE_FILE}")


def cmd_history():
    history = load_json(POST_HISTORY, [])
    if not history:
        print("No post history.")
        return
    print(f"{len(history)} posts:\n")
    for h in history[-10:]:
        ts = datetime.fromtimestamp(h.get("posted_at", 0), ET).strftime("%b %d %H:%M ET")
        text = h.get("text", "")[:80]
        print(f"  [{ts}] {text}")


def cmd_queue():
    queue = load_json(DRAFTS_FILE, [])
    queued = [d for d in queue if d.get("status") == "queued"]
    print(f"{len(queued)} queued drafts:\n")
    for d in queued[:10]:
        print(f"  - {d['text'][:80]}")
        print(f"    trend={d.get('trend_key', '?')} quality={d.get('quality', {}).get('overall', '?')}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "note" and len(sys.argv) >= 3:
        cmd_note(" ".join(sys.argv[2:]))
    elif cmd == "suggestions":
        cmd_suggestions()
    elif cmd == "profile":
        cmd_profile()
    elif cmd == "history":
        cmd_history()
    elif cmd == "queue":
        cmd_queue()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
