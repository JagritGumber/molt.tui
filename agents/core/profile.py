"""
Profile Manager — stores account identity, tracks what needs manual action,
and collects operator input to guide the agent.

The agent can't change bio/pfp/banner via CDP (Twitter blocks it).
Instead it logs suggestions and takes direction from the operator.
"""

import time

from agents.core.config import HOME, load_json, save_json

PROFILE_FILE = HOME / "x-profile.json"
SUGGESTIONS_FILE = HOME / "x-suggestions.json"

DEFAULT_PROFILE = {
    "handle": "wyvernotwts",
    "identity": {
        "who": "builder/dev shipping tools in AI, Rust, and infra",
        "tone": "sharp, concise, internet-native. not corporate.",
        "topics": ["AI agents", "Rust", "dev tools", "infra", "open source"],
        "avoid": ["wellness slop", "motivational quotes", "vague hype", "hashtags"],
    },
    "goals": {
        "primary": "position account for sponsorships via niche authority",
        "growth_pillars": [
            "first-mover replies on trending posts",
            "build-in-public updates (short, specific)",
            "sharp takes that get screenshots",
        ],
        "target_audience": "tech devs, indie hackers, AI builders",
    },
    "content_rules": {
        "max_chars": 140,
        "ideal_chars": 80,
        "images_required": True,
        "video_priority": True,
        "post_style": "one punchy sentence, not essays",
    },
    "manual_actions_needed": [
        "Change profile picture from Blackswan to something authentic",
        "Change banner to something that shows what you build",
        "Rewrite bio to be specific: what you build, for whom, in what stack",
    ],
    "operator_notes": [],
}


def load_profile() -> dict:
    """Load profile, creating default if missing."""
    profile = load_json(PROFILE_FILE, None)
    if profile is None:
        save_json(PROFILE_FILE, DEFAULT_PROFILE)
        return DEFAULT_PROFILE
    return profile


def add_operator_note(note: str):
    """Operator tells the agent something (direction, correction, preference)."""
    profile = load_profile()
    profile.setdefault("operator_notes", []).append({
        "note": note,
        "added_at": int(time.time()),
    })
    # Keep last 50 notes
    profile["operator_notes"] = profile["operator_notes"][-50:]
    save_json(PROFILE_FILE, profile)


def add_suggestion(category: str, suggestion: str):
    """Agent suggests something the operator should do manually."""
    suggestions = load_json(SUGGESTIONS_FILE, [])
    suggestions.append({
        "category": category,
        "suggestion": suggestion,
        "created_at": int(time.time()),
        "status": "pending",
    })
    suggestions = suggestions[-100:]
    save_json(SUGGESTIONS_FILE, suggestions)


def get_pending_suggestions() -> list[dict]:
    """Get suggestions the operator hasn't acted on yet."""
    suggestions = load_json(SUGGESTIONS_FILE, [])
    return [s for s in suggestions if s.get("status") == "pending"]


def get_content_rules() -> dict:
    """Get content rules for draft generation."""
    profile = load_profile()
    return profile.get("content_rules", DEFAULT_PROFILE["content_rules"])


def get_identity() -> dict:
    """Get account identity for prompt building."""
    profile = load_profile()
    return profile.get("identity", DEFAULT_PROFILE["identity"])


def get_operator_notes() -> list[str]:
    """Get recent operator notes for context in prompts."""
    profile = load_profile()
    notes = profile.get("operator_notes", [])
    return [n["note"] for n in notes[-10:]]
