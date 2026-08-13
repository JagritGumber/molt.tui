"""Draft Generator — LLM-powered draft creation, critique, and queueing."""

import json
import random
import time
import uuid

from agents.core.config import DRAFTS_FILE, load_json, save_json, get_account_handle
from agents.core.llm import LLMClient
from agents.core.quality import PostScorer
from agents.core.profile import get_identity, get_operator_notes, get_content_rules

ACCOUNT = get_account_handle() or "mobtwts"

DRAFT_PROMPT = """you are @{handle}. not ghostwriting. you ARE this person.

you: {identity_who}
tone: {identity_tone}
rules:
{personality_rules}
{operator_context}

you just saw this:
{signal_text}

react in ONE tweet. MUST be under 100 characters. thats like 12-15 words max.

rules:
- under 100 chars. hard limit. count them.
- no hashtags. no emojis. no links. no real name.
- no "bro", "no cap", "rizz", gen z slang. you find it idiotic.
- no capitalization unless YELLING about something stupid.
- dont explain. dont frame. just react.
- mild swearing ok sometimes but dont force it.

examples of the right length and vibe:
- "next.js HMR takes 15 seconds. thats not a feature thats a cry for help"
- "every ai startup is a wrapper until proven otherwise"
- "rust compile times dropped 40 percent. go devs in shambles"
- "solidjs does in 7kb what react needs 42kb for"

tweet (under 100 chars):"""

CRITIQUE_PROMPT = """Score these tweets 0-10. This is for a 20yo dev who is casual, sarcastic, anti-bloat.

Score HIGH if: short, punchy, sounds like a real person, has a specific take
Score LOW if: generic, sounds like AI, too long, uses slang like "bro", sounds like a brand

Tweets:
{tweets}

Return JSON: {{"scores": [{{"text": "...", "overall": N, "reason": "..."}}]}}"""


class DraftGenerator:
    def __init__(self, llm: LLMClient = None):
        self.llm = llm or LLMClient()
        self.scorer = PostScorer()

    async def generate(self, trend: dict) -> dict:
        """Generate one draft from a trend."""
        # Pick ONE random signal instead of dumping all 5 (prevents repetition)
        signals = trend.get("signals", [])
        if signals:
            sig = random.choice(signals)
            signal_text = sig.get("title", trend.get("key", "tech"))
        else:
            signal_text = trend.get("creator_angle", trend.get("key", "tech"))

        identity = get_identity()
        notes = get_operator_notes()

        operator_context = ""
        if notes:
            operator_context = "directions:\n" + "\n".join(f"- {n}" for n in notes[-5:])

        personality_rules = "\n".join(
            f"- {r}" for r in identity.get("personality_rules", [])
        )

        prompt = DRAFT_PROMPT.format(
            handle=ACCOUNT,
            identity_who=identity.get("who", "dev"),
            identity_tone=identity.get("tone", "casual, direct"),
            personality_rules=personality_rules or "- be real",
            operator_context=operator_context,
            signal_text=signal_text,
        )
        text = await self.llm.generate(prompt, max_tokens=100, temperature=0.9)
        if not text or len(text.strip()) < 10:
            # Retry once with simpler prompt
            simple = f"write a sarcastic one-liner tweet (under 100 chars) reacting to: {signal_text}"
            text = await self.llm.generate(simple, max_tokens=80, temperature=0.9)
        if not text or len(text.strip()) < 10:
            return None  # Let caller handle - don't queue garbage

        # Clean up
        text = text.strip('"').strip("'").strip()
        # Take only first line if LLM returned multiple
        if "\n" in text:
            text = text.split("\n")[0].strip()
        # Hard reject if over 140 (prompt asks for 100 but LLM drifts)
        if len(text) > 140:
            text = text[:137] + "..."

        draft = {
            "text": text,
            "trend_key": trend.get("key"),
            "mode": trend.get("mode", "FOMO"),
            "reply_to_trend": False,
            "draft_id": f"draft-{int(time.time())}-{uuid.uuid4().hex[:6]}",
        }

        quality = self.scorer.score(draft)
        draft["quality"] = quality
        return draft

    async def critique(self, drafts: list[dict]) -> list[dict]:
        """Score a batch of drafts via LLM. Falls back to heuristic scorer."""
        tweets_text = "\n".join(
            f"{i+1}. {d['text']}" for i, d in enumerate(drafts)
        )
        prompt = CRITIQUE_PROMPT.format(tweets=tweets_text)

        result = await self.llm.generate_json(prompt, max_tokens=1000, temperature=0.4)
        if result and "scores" in result:
            scored = []
            for i, s in enumerate(result["scores"][:len(drafts)]):
                d = {**drafts[i]}
                d["overall"] = max(0, min(10, float(s.get("overall", 5))))
                d["critique_reason"] = s.get("reason", "")
                scored.append(d)
            return scored

        # Fallback: heuristic
        scored = []
        for d in drafts:
            q = self.scorer.score(d)
            scored.append({**d, "overall": q["overall"], "critique_reason": f"heuristic: flags={q['flags']}"})
        return scored

    def queue_draft(self, draft: dict, trend: dict = None, raw: bool = False) -> dict:
        """Add a draft to the queue file."""
        queue = load_json(DRAFTS_FILE, [])

        if raw:
            entry = draft
        else:
            entry = {
                "text": draft.get("text", ""),
                "media_path": draft.get("media_path", ""),
                "status": "queued",
                "draft_id": draft.get("draft_id", f"draft-{int(time.time())}"),
                "trend_key": (trend or {}).get("key", draft.get("trend_key", "")),
                "mode": draft.get("mode", ""),
                "not_before": 0,
                "created_at": int(time.time()),
            }

        if entry.get("status") != "queued":
            entry["status"] = "queued"

        queue.append(entry)
        save_json(DRAFTS_FILE, queue)
        return entry

    def get_queue_entry(self, draft_id: str) -> dict:
        """Look up a queue entry by draft_id."""
        queue = load_json(DRAFTS_FILE, [])
        for entry in queue:
            if entry.get("draft_id") == draft_id:
                return entry
        return {}
