#!/usr/bin/env bun
// CLI for external tools (Claude Code, scripts) to manage Molt.tui tasks
// Usage:
//   bun task-cli.ts add "Fix login bug" --priority high --tag backend
//   bun task-cli.ts done <task-id>
//   bun task-cli.ts wip <task-id>
//   bun task-cli.ts list [--status todo|in-progress|done]
//   bun task-cli.ts update <task-id> --status done --title "New title"

import { createTask, updateTask, listTasks, sortTasks, type Priority, type TaskStatus } from "./tasks/store.ts";
import { ensureDirs } from "./utils/config.ts";

ensureDirs();

const args = process.argv.slice(2);
const cmd = args[0];

function getFlag(name: string): string | undefined {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 && idx + 1 < args.length ? args[idx + 1] : undefined;
}

function hasFlag(name: string): boolean {
  return args.includes(`--${name}`);
}

if (!cmd) {
  console.log(`molt-tasks — CLI for Molt.tui task management

Commands:
  add <title>                Create a task
    --priority <low|med|high>
    --tag <tag>
    --due <YYYY-MM-DD>
    --description <text>

  done [id]                  Mark task done (latest in-progress if no id)
  wip [id]                   Mark task in-progress (latest todo if no id)
  todo [id]                  Mark task todo

  list                       List all tasks
    --status <todo|in-progress|done>
    --json                   Output as JSON

  update <id>                Update a task
    --title <text>
    --status <todo|in-progress|done>
    --priority <low|med|high>
    --tag <tag>
    --due <YYYY-MM-DD>`);
  process.exit(0);
}

if (cmd === "add") {
  const title = args[1];
  if (!title) { console.error("Usage: add <title>"); process.exit(1); }
  const prioRaw = getFlag("priority") || "med";
  if (!["low", "med", "high"].includes(prioRaw)) { console.error(`Invalid priority: ${prioRaw}. Use: low, med, high`); process.exit(1); }
  const priority = prioRaw as Priority;
  const tag = getFlag("tag");
  const due = getFlag("due") || "";
  const desc = getFlag("description") || "";
  const task = createTask({
    title,
    description: desc,
    priority,
    status: "todo",
    dueDate: due,
    tags: tag ? [tag] : [],
  });
  console.log(`✓ Created: ${task.title} (${task.id})`);
}

else if (cmd === "done" || cmd === "wip" || cmd === "todo") {
  const statusMap: Record<string, TaskStatus> = { done: "done", wip: "in-progress", todo: "todo" };
  const newStatus = statusMap[cmd]!;
  let id = args[1];

  if (!id) {
    // Find the latest matching task to transition
    const tasks = sortTasks(listTasks());
    const target = cmd === "done"
      ? tasks.find((t) => t.status === "in-progress") || tasks.find((t) => t.status === "todo")
      : cmd === "wip"
        ? tasks.find((t) => t.status === "todo")
        : tasks.find((t) => t.status === "in-progress") || tasks.find((t) => t.status === "done");
    if (!target) { console.error("No matching task found"); process.exit(1); }
    id = target.id;
  }

  const updated = updateTask(id, { status: newStatus });
  if (updated) {
    console.log(`✓ ${updated.title} → ${newStatus}`);
  } else {
    console.error(`Task not found: ${id}`);
    process.exit(1);
  }
}

else if (cmd === "list") {
  const statusFilter = getFlag("status") as TaskStatus | undefined;
  const asJson = hasFlag("json");
  let tasks = sortTasks(listTasks());
  if (statusFilter) tasks = tasks.filter((t) => t.status === statusFilter);

  if (asJson) {
    console.log(JSON.stringify(tasks, null, 2));
  } else {
    if (tasks.length === 0) { console.log("No tasks."); process.exit(0); }
    const icons: Record<TaskStatus, string> = { todo: "○", "in-progress": "◑", done: "●" };
    for (const t of tasks) {
      const due = t.dueDate ? ` due:${t.dueDate}` : "";
      const tags = t.tags.length ? ` [${t.tags.join(",")}]` : "";
      console.log(`${icons[t.status]} ${t.priority.padEnd(4)} ${t.title}${due}${tags}  (${t.id})`);
    }
  }
}

else if (cmd === "update") {
  const id = args[1];
  if (!id) { console.error("Usage: update <id> --field value"); process.exit(1); }
  const data: Partial<{ title: string; status: TaskStatus; priority: Priority; dueDate: string; tags: string[] }> = {};
  if (getFlag("title")) data.title = getFlag("title");
  if (getFlag("status")) {
    const s = getFlag("status")!;
    if (!["todo", "in-progress", "done"].includes(s)) { console.error(`Invalid status: ${s}. Use: todo, in-progress, done`); process.exit(1); }
    data.status = s as TaskStatus;
  }
  if (getFlag("priority")) {
    const p = getFlag("priority")!;
    if (!["low", "med", "high"].includes(p)) { console.error(`Invalid priority: ${p}. Use: low, med, high`); process.exit(1); }
    data.priority = p as Priority;
  }
  if (getFlag("due")) data.dueDate = getFlag("due");
  if (getFlag("tag")) data.tags = [getFlag("tag")!];

  const updated = updateTask(id, data);
  if (updated) {
    console.log(`✓ Updated: ${updated.title}`);
  } else {
    console.error(`Task not found: ${id}`);
    process.exit(1);
  }
}

else {
  console.error(`Unknown command: ${cmd}`);
  process.exit(1);
}
