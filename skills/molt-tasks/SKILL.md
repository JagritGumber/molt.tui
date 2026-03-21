---
name: molt-tasks
description: Manage Molt.tui tasks from Claude Code. Create, update, and track tasks that sync live to the Molt.tui dashboard. Use when the user asks to create tasks, track progress, mark things done, or manage their work.
---

# Molt.tui Task Management

You can manage tasks that appear in the user's Molt.tui dashboard. Tasks are stored as JSON files in `~/.moltui/tasks/` and the TUI auto-refreshes when files change.

## CLI (preferred)

Run from the molt.tui repo at `/mnt/d/moltui`:

```bash
# Create a task
bun run task add "Fix auth middleware" --priority high --tag backend --due 2026-04-01

# Mark latest in-progress task as done
bun run task done

# Mark latest todo as in-progress
bun run task wip

# List all tasks
bun run task list

# List as JSON (for scripting)
bun run task list --json

# Update a specific task
bun run task update <task-id> --status done --title "New title"
```

## Direct JSON (alternative)

Create a JSON file in `~/.moltui/tasks/<id>.json`:

```json
{
  "id": "fix-auth-mn1abc",
  "title": "Fix auth middleware",
  "description": "Token validation is broken on refresh",
  "priority": "high",
  "status": "todo",
  "dueDate": "2026-04-01",
  "tags": ["backend", "auth"],
  "createdAt": "2026-03-21T12:00:00.000Z",
  "updatedAt": "2026-03-21T12:00:00.000Z"
}
```

### Fields

| Field | Type | Values |
|-------|------|--------|
| `id` | string | unique, used as filename |
| `title` | string | task title |
| `description` | string | optional details |
| `priority` | string | `low`, `med`, `high` |
| `status` | string | `todo`, `in-progress`, `done` |
| `dueDate` | string | ISO date `YYYY-MM-DD` or empty |
| `tags` | string[] | any tags |
| `createdAt` | string | ISO timestamp |
| `updatedAt` | string | ISO timestamp |

## When to use

- When the user says "add a task", "track this", "remind me to", "todo"
- When completing work — mark tasks as done
- When starting work — mark tasks as in-progress
- Report task status when asked "what's left", "show tasks", "what am I working on"
