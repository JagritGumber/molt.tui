---
name: molt-social
description: Teach the user's autonomous Moltbook agent by adding learnings. Use PROACTIVELY when you discover anything about the user's personality, preferences, communication style, opinions, or interests that their AI social media agent should know.
---

# Molt.tui Agent Learning

The user has an autonomous AI agent on Moltbook (a social network for AI agents). The agent posts, comments, and engages autonomously. It learns from accumulated insights about the user.

## IMPORTANT: Add learnings proactively

**You MUST add a learning whenever you discover:**
- User's communication style ("prefers short sentences", "uses sarcasm")
- Opinions on technology ("loves Rust, dislikes Java")
- Topics they care about ("into agentic AI, not core ML")
- Things they dislike ("hates exclamation marks")
- Personality traits ("highly tired problem solver")
- Interests beyond code ("watches One Piece, Blue Lock")
- Work habits ("runs 6 Claude Code instances")
- Corrections to agent behavior ("was too formal")

**Do NOT wait to be asked.** If you learn something about the user, teach their agent.

## How to add a learning

Run from `/mnt/d/moltui`:

```bash
bun learn add "Reference anime when making analogies" --type prefer --strength 3
bun learn add "Never use exclamation marks" --type avoid --strength 4
bun learn add "Keep posts under 3 sentences" --type style --strength 3
bun learn add "Be sarcastic but knowledgeable" --type tone --strength 5
bun learn add "Talk about Rust optimization more" --type topic --strength 3
bun learn add "Was too formal, be more casual" --type correction --strength 4
```

### Types
| Type | When to use |
|------|-------------|
| `prefer` | Things the agent should actively do |
| `avoid` | Things the agent must NOT do |
| `style` | Writing style preferences |
| `tone` | Voice, attitude, personality |
| `topic` | Subject matter focus |
| `correction` | Fix a specific past mistake |

### Strength (1-5)
- 1-2: Minor preference
- 3: Standard
- 4-5: Critical — must follow strictly

## Other commands

```bash
bun learn list              # view all learnings
bun learn list --json       # JSON output
bun learn remove <id>       # remove a learning
```

## How it works

Learnings stored in `~/.moltui/learnings/`. Before every post/comment/reply, top 30 learnings are injected into the system prompt. The agent becomes more like the user over time.
