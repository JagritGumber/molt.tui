// Tasks screen - task planner with command bar, shortcuts, and full CRUD

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize, fitWidth, visibleLength } from "../tui/ansi.ts";
import { drawHR, drawTextInput, drawDialog } from "../tui/components.ts";
import {
  listTasks, createTask, updateTask, deleteTask,
  cycleStatus, cyclePriority, sortTasks,
  type Task, type Priority, type TaskStatus,
} from "../tasks/store.ts";
import type { KeyEvent } from "../tui/input.ts";

type Mode = "list" | "create" | "edit" | "confirm-delete" | "command";

let mode: Mode = "list";
let tasks: Task[] = [];
let selectedIndex = 0;
let scrollOffset = 0;

// ── Command bar ──
let cmdInput = "";
let cmdHistory: string[] = [];
let cmdHistoryIdx = -1;

// ── Create/Edit form ──
interface FormField { key: string; label: string; value: string }
let formFields: FormField[] = [];
let formFocus = 0;
let editingTaskId = "";

// ── Filter ──
let filterStatus: TaskStatus | "all" = "all";

function reload() {
  let all = sortTasks(listTasks());
  if (filterStatus !== "all") all = all.filter((t) => t.status === filterStatus);
  tasks = all;
  if (selectedIndex >= tasks.length) selectedIndex = Math.max(0, tasks.length - 1);
}

function resetForm(task?: Task) {
  formFields = [
    { key: "title", label: "Title", value: task?.title || "" },
    { key: "description", label: "Description", value: task?.description || "" },
    { key: "priority", label: "Priority (low/med/high)", value: task?.priority || "med" },
    { key: "dueDate", label: "Due Date (YYYY-MM-DD)", value: task?.dueDate || "" },
    { key: "tags", label: "Tags (comma-sep)", value: task?.tags.join(", ") || "" },
  ];
  formFocus = 0;
}

// ── Rendering helpers ──

const STATUS_ICON: Record<TaskStatus, string> = {
  "todo": `${fg.gray}○${style.reset}`,
  "in-progress": `${fg.brightYellow}◑${style.reset}`,
  "done": `${fg.brightGreen}●${style.reset}`,
};

const PRIO_BADGE: Record<Priority, string> = {
  "high": `${fg.brightRed}▲${style.reset}`,
  "med": `${fg.brightYellow}■${style.reset}`,
  "low": `${fg.gray}▽${style.reset}`,
};

function renderList() {
  const { rows, cols } = getTermSize();
  const w = Math.min(80, cols - 4);
  const cmdBarHeight = mode === "command" ? 3 : 0;
  const maxVisible = rows - 8 - cmdBarHeight;

  cursor.to(3, 3);
  write(`${fg.brightCyan}${style.bold}Tasks${style.reset}`);

  // Filter tabs
  cursor.to(3, 12);
  const filters: { label: string; val: TaskStatus | "all" }[] = [
    { label: "All", val: "all" },
    { label: "Todo", val: "todo" },
    { label: "Active", val: "in-progress" },
    { label: "Done", val: "done" },
  ];
  write(filters.map((f) => {
    const active = filterStatus === f.val;
    return active
      ? `${fg.brightCyan}${style.bold}[${f.label}]${style.reset}`
      : `${fg.gray}[${f.label}]${style.reset}`;
  }).join(" "));

  drawHR(4, 3, w);

  if (tasks.length === 0) {
    cursor.to(6, 5);
    write(`${fg.gray}No tasks. Press ${fg.brightCyan}: ${fg.gray}and type ${fg.brightCyan}add Buy milk${fg.gray} or press ${fg.brightCyan}n${fg.gray}.${style.reset}`);
    return;
  }

  // Scroll
  if (selectedIndex < scrollOffset) scrollOffset = selectedIndex;
  if (selectedIndex >= scrollOffset + maxVisible) scrollOffset = selectedIndex - maxVisible + 1;

  for (let i = 0; i < maxVisible; i++) {
    const idx = scrollOffset + i;
    cursor.to(5 + i, 3);

    if (idx >= tasks.length) {
      write(" ".repeat(w));
      continue;
    }

    const task = tasks[idx]!;
    const isSelected = idx === selectedIndex;
    const num = `${fg.gray}${(idx + 1).toString().padStart(2)}${style.reset}`;
    const pointer = isSelected ? `${fg.brightCyan}❯` : " ";
    const icon = STATUS_ICON[task.status];
    const prio = PRIO_BADGE[task.priority];
    const titleColor = task.status === "done" ? `${fg.gray}${style.strikethrough}` : isSelected ? `${fg.brightWhite}${style.bold}` : `${fg.white}`;
    const title = `${titleColor}${task.title}${style.reset}`;

    let due = "";
    if (task.dueDate) {
      const today = new Date().toISOString().slice(0, 10);
      const isOverdue = task.dueDate < today && task.status !== "done";
      due = isOverdue
        ? ` ${fg.brightRed}⏰${task.dueDate}${style.reset}`
        : ` ${fg.gray}${task.dueDate}${style.reset}`;
    }

    const tags = task.tags.length > 0 ? ` ${fg.gray}${task.tags.map((t) => `#${t}`).join(" ")}${style.reset}` : "";

    write(fitWidth(`${num}${pointer}${icon} ${prio} ${title}${due}${tags}`, w));
  }

  // Count summary
  const allTasks = sortTasks(listTasks());
  const todoCount = allTasks.filter((t) => t.status === "todo").length;
  const activeCount = allTasks.filter((t) => t.status === "in-progress").length;
  const doneCount = allTasks.filter((t) => t.status === "done").length;

  cursor.to(rows - 2 - cmdBarHeight, 3);
  write(`${fg.gray}${todoCount} todo  ${fg.brightYellow}${activeCount} active${fg.gray}  ${fg.brightGreen}${doneCount} done${fg.gray}  │  ${allTasks.length} total${style.reset}`);

  // Command bar
  if (mode === "command") {
    renderCommandBar(rows, cols);
  }
}

function renderCommandBar(rows: number, cols: number) {
  const w = Math.min(80, cols - 4);
  const barRow = rows - 3;

  cursor.to(barRow, 3);
  write(`${bg.rgb(30, 30, 50)}${fg.brightCyan}:${fg.brightWhite}${fitWidth(cmdInput, w - 2)}${style.reset}`);

  cursor.to(barRow + 1, 3);
  write(`${fg.gray}${fitWidth("add <title> • done/wip/todo • high/med/low • due <date> • tag <t> • clear done • help", w)}${style.reset}`);
}

function renderForm(title: string) {
  const { cols } = getTermSize();
  const w = Math.min(65, cols - 6);

  cursor.to(3, 3);
  write(`${fg.brightCyan}${style.bold}${title}${style.reset}`);
  drawHR(4, 3, w);

  formFields.forEach((field, i) => {
    drawTextInput(6 + i * 2, 3, w, field.value, field.label, i === formFocus);
  });

  const submitRow = 6 + formFields.length * 2 + 1;
  cursor.to(submitRow, 3);
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to save • ${fg.brightCyan}Esc${fg.gray} to cancel${style.reset}`);
}

function renderConfirmDelete() {
  const task = tasks[selectedIndex];
  if (!task) return;
  drawDialog("Delete Task", `Delete "${task.title}"?`, ["y = yes", "n = no"]);
}

// ── Command parser ──

function parseDate(input: string): string {
  const lower = input.toLowerCase().trim();
  const today = new Date();
  if (lower === "today") return today.toISOString().slice(0, 10);
  if (lower === "tomorrow" || lower === "tmr") {
    today.setDate(today.getDate() + 1);
    return today.toISOString().slice(0, 10);
  }
  if (lower === "next week" || lower === "nextweek") {
    today.setDate(today.getDate() + 7);
    return today.toISOString().slice(0, 10);
  }
  // Try parsing +Nd (e.g. +3d = 3 days from now)
  const relMatch = lower.match(/^\+(\d+)d$/);
  if (relMatch) {
    today.setDate(today.getDate() + parseInt(relMatch[1]!));
    return today.toISOString().slice(0, 10);
  }
  // ISO date
  if (/^\d{4}-\d{2}-\d{2}$/.test(lower)) return lower;
  return "";
}

function executeCommand(raw: string) {
  const input = raw.trim();
  if (!input) return;

  cmdHistory.unshift(input);
  if (cmdHistory.length > 50) cmdHistory.pop();

  // ── add / new ──
  const addMatch = input.match(/^(?:add|new|a)\s+(.+)$/i);
  if (addMatch) {
    const parsed = parseInlineTask(addMatch[1]!);
    createTask({
      title: parsed.title,
      description: "",
      priority: parsed.priority,
      status: "todo",
      dueDate: parsed.dueDate,
      tags: parsed.tags,
    });
    app.flash(`+ ${parsed.title}`);
    reload();
    return;
  }

  // ── done / x ──
  if (/^(?:done|x|finish|complete)(?:\s+(\d+))?$/i.test(input)) {
    const m = input.match(/(\d+)/);
    const idx = m ? parseInt(m[1]!) - 1 : selectedIndex;
    const task = tasks[idx];
    if (task) {
      updateTask(task.id, { status: "done" });
      app.flash(`✓ ${task.title}`);
      reload();
    }
    return;
  }

  // ── todo ──
  if (/^todo(?:\s+(\d+))?$/i.test(input)) {
    const m = input.match(/(\d+)/);
    const idx = m ? parseInt(m[1]!) - 1 : selectedIndex;
    const task = tasks[idx];
    if (task) {
      updateTask(task.id, { status: "todo" });
      app.flash(`○ ${task.title}`);
      reload();
    }
    return;
  }

  // ── wip / start / active ──
  if (/^(?:wip|start|active|begin|working)(?:\s+(\d+))?$/i.test(input)) {
    const m = input.match(/(\d+)/);
    const idx = m ? parseInt(m[1]!) - 1 : selectedIndex;
    const task = tasks[idx];
    if (task) {
      updateTask(task.id, { status: "in-progress" });
      app.flash(`◑ ${task.title}`);
      reload();
    }
    return;
  }

  // ── priority ──
  if (/^(?:high|med|low|h|m|l)(?:\s+(\d+))?$/i.test(input)) {
    const m = input.match(/(\d+)/);
    const idx = m ? parseInt(m[1]!) - 1 : selectedIndex;
    const task = tasks[idx];
    const prioMap: Record<string, Priority> = { h: "high", high: "high", m: "med", med: "med", l: "low", low: "low" };
    const prio = prioMap[input.replace(/\s+\d+$/, "").toLowerCase()];
    if (task && prio) {
      updateTask(task.id, { priority: prio });
      app.flash(`${task.title} → ${prio}`);
      reload();
    }
    return;
  }

  // ── due ──
  const dueMatch = input.match(/^due\s+(.+)$/i);
  if (dueMatch) {
    const task = tasks[selectedIndex];
    const date = parseDate(dueMatch[1]!);
    if (task && date) {
      updateTask(task.id, { dueDate: date });
      app.flash(`${task.title} due ${date}`);
      reload();
    } else if (!date) {
      app.flash("Bad date. Use: today, tomorrow, +3d, 2026-03-25");
    }
    return;
  }

  // ── tag ──
  const tagMatch = input.match(/^tag\s+(.+)$/i);
  if (tagMatch) {
    const task = tasks[selectedIndex];
    if (task) {
      const newTags = tagMatch[1]!.split(",").map((t) => t.trim().replace(/^#/, "")).filter(Boolean);
      const merged = [...new Set([...task.tags, ...newTags])];
      updateTask(task.id, { tags: merged });
      app.flash(`${task.title} +${newTags.join(" +")}`);
      reload();
    }
    return;
  }

  // ── untag ──
  const untagMatch = input.match(/^untag\s+(.+)$/i);
  if (untagMatch) {
    const task = tasks[selectedIndex];
    if (task) {
      const remove = untagMatch[1]!.split(",").map((t) => t.trim().replace(/^#/, ""));
      const filtered = task.tags.filter((t) => !remove.includes(t));
      updateTask(task.id, { tags: filtered });
      app.flash(`${task.title} -${remove.join(" -")}`);
      reload();
    }
    return;
  }

  // ── rename ──
  const renameMatch = input.match(/^(?:rename|title)\s+(.+)$/i);
  if (renameMatch) {
    const task = tasks[selectedIndex];
    if (task) {
      updateTask(task.id, { title: renameMatch[1]!.trim() });
      app.flash(`Renamed → ${renameMatch[1]!.trim()}`);
      reload();
    }
    return;
  }

  // ── del / rm ──
  if (/^(?:del|rm|delete|remove)(?:\s+(\d+))?$/i.test(input)) {
    const m = input.match(/(\d+)/);
    const idx = m ? parseInt(m[1]!) - 1 : selectedIndex;
    const task = tasks[idx];
    if (task) {
      deleteTask(task.id);
      app.flash(`Deleted "${task.title}"`);
      reload();
    }
    return;
  }

  // ── clear done ──
  if (/^clear\s+done$/i.test(input)) {
    const allTasks = listTasks();
    const done = allTasks.filter((t) => t.status === "done");
    done.forEach((t) => deleteTask(t.id));
    app.flash(`Cleared ${done.length} done tasks`);
    reload();
    return;
  }

  // ── filter ──
  const filterMatch = input.match(/^(?:filter|show|view)\s+(all|todo|active|wip|done|in-progress)$/i);
  if (filterMatch) {
    const map: Record<string, TaskStatus | "all"> = {
      all: "all", todo: "todo", active: "in-progress", wip: "in-progress",
      "in-progress": "in-progress", done: "done",
    };
    filterStatus = map[filterMatch[1]!.toLowerCase()] || "all";
    reload();
    app.flash(`Filter: ${filterStatus}`);
    return;
  }

  // ── goto ──
  if (/^\d+$/.test(input)) {
    const idx = parseInt(input) - 1;
    if (idx >= 0 && idx < tasks.length) {
      selectedIndex = idx;
      app.requestRender();
    }
    return;
  }

  // ── help ──
  if (/^(?:help|h|\?)$/i.test(input)) {
    app.flash("add <t> • done/wip/todo [n] • high/med/low • due <d> • tag/untag • del • clear done • filter • rename");
    return;
  }

  app.flash(`Unknown: "${input}" — type help for commands`);
}

// Parse inline task: "fix login !high @work due tomorrow"
function parseInlineTask(raw: string): { title: string; priority: Priority; dueDate: string; tags: string[] } {
  let priority: Priority = "med";
  let dueDate = "";
  const tags: string[] = [];
  const words: string[] = [];

  const parts = raw.split(/\s+/);
  let i = 0;
  while (i < parts.length) {
    const w = parts[i]!;
    if (w === "!high" || w === "!h") { priority = "high"; }
    else if (w === "!med" || w === "!m") { priority = "med"; }
    else if (w === "!low" || w === "!l") { priority = "low"; }
    else if (w.startsWith("@")) { tags.push(w.slice(1)); }
    else if (w.toLowerCase() === "due" && i + 1 < parts.length) {
      i++;
      // Collect the rest of the due phrase (e.g. "next week" = 2 words)
      let dateStr = parts[i]!;
      if (dateStr.toLowerCase() === "next" && i + 1 < parts.length) {
        i++;
        dateStr += " " + parts[i]!;
      }
      dueDate = parseDate(dateStr);
    }
    else { words.push(w); }
    i++;
  }

  return { title: words.join(" "), priority, dueDate, tags };
}

// ── Key handlers ──

function handleListKey(key: KeyEvent) {
  if (key.name === "up" || key.name === "k") {
    selectedIndex = Math.max(0, selectedIndex - 1);
    app.requestRender();
  } else if (key.name === "down" || key.name === "j") {
    selectedIndex = Math.min(tasks.length - 1, selectedIndex + 1);
    app.requestRender();
  } else if (key.name === ":" || key.name === "/") {
    mode = "command";
    cmdInput = "";
    cmdHistoryIdx = -1;
    app.requestRender();
  } else if (key.name === "n") {
    mode = "create";
    resetForm();
    app.requestRender();
  } else if (key.name === " ") {
    // Space = quick toggle status
    const task = tasks[selectedIndex];
    if (task) {
      updateTask(task.id, { status: cycleStatus(task.status) });
      reload();
      app.requestRender();
    }
  } else if (key.name === "x") {
    // x = mark done immediately
    const task = tasks[selectedIndex];
    if (task) {
      updateTask(task.id, { status: task.status === "done" ? "todo" : "done" });
      reload();
      app.requestRender();
    }
  } else if (key.name === "return") {
    const task = tasks[selectedIndex];
    if (task) {
      updateTask(task.id, { status: cycleStatus(task.status) });
      reload();
      app.requestRender();
    }
  } else if (key.name === "p") {
    const task = tasks[selectedIndex];
    if (task) {
      updateTask(task.id, { priority: cyclePriority(task.priority) });
      reload();
      app.requestRender();
    }
  } else if (key.name === "e") {
    const task = tasks[selectedIndex];
    if (task) {
      mode = "edit";
      editingTaskId = task.id;
      resetForm(task);
      app.requestRender();
    }
  } else if (key.name === "d" || key.name === "delete") {
    if (tasks.length > 0) {
      mode = "confirm-delete";
      app.requestRender();
    }
  } else if (key.name === "tab") {
    const order: (TaskStatus | "all")[] = ["all", "todo", "in-progress", "done"];
    filterStatus = order[(order.indexOf(filterStatus) + 1) % order.length]!;
    reload();
    app.requestRender();
  } else if (key.name === "g") {
    // g = go to top
    selectedIndex = 0;
    app.requestRender();
  } else if (key.name === "G") {
    // G = go to bottom
    selectedIndex = Math.max(0, tasks.length - 1);
    app.requestRender();
  } else if (key.name === "escape" || key.name === "q") {
    app.back();
  }
}

function handleCommandKey(key: KeyEvent) {
  if (key.name === "return") {
    executeCommand(cmdInput);
    mode = "list";
    app.requestRender();
  } else if (key.name === "escape") {
    mode = "list";
    app.requestRender();
  } else if (key.name === "backspace") {
    if (cmdInput.length === 0) {
      mode = "list";
    } else {
      cmdInput = cmdInput.slice(0, -1);
    }
    app.requestRender();
  } else if (key.name === "up") {
    // History navigation
    if (cmdHistory.length > 0 && cmdHistoryIdx < cmdHistory.length - 1) {
      cmdHistoryIdx++;
      cmdInput = cmdHistory[cmdHistoryIdx]!;
      app.requestRender();
    }
  } else if (key.name === "down") {
    if (cmdHistoryIdx > 0) {
      cmdHistoryIdx--;
      cmdInput = cmdHistory[cmdHistoryIdx]!;
    } else {
      cmdHistoryIdx = -1;
      cmdInput = "";
    }
    app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    cmdInput += key.name;
    app.requestRender();
  }
}

function handleFormKey(key: KeyEvent) {
  const field = formFields[formFocus]!;

  if (key.name === "tab" && !key.shift || key.name === "down") {
    formFocus = Math.min(formFields.length - 1, formFocus + 1);
    app.requestRender();
  } else if (key.name === "tab" && key.shift || key.name === "up") {
    formFocus = Math.max(0, formFocus - 1);
    app.requestRender();
  } else if (key.name === "backspace") {
    field.value = field.value.slice(0, -1);
    app.requestRender();
  } else if (key.name === "return") {
    const title = formFields.find((f) => f.key === "title")!.value.trim();
    if (!title) { app.flash("Title is required!"); return; }

    const description = formFields.find((f) => f.key === "description")!.value.trim();
    const priorityRaw = formFields.find((f) => f.key === "priority")!.value.trim().toLowerCase();
    const priority: Priority = (["low", "med", "high"].includes(priorityRaw) ? priorityRaw : "med") as Priority;
    const dueDate = formFields.find((f) => f.key === "dueDate")!.value.trim();
    const tags = formFields.find((f) => f.key === "tags")!.value.split(",").map((s) => s.trim()).filter(Boolean);

    if (mode === "create") {
      createTask({ title, description, priority, status: "todo", dueDate, tags });
      app.flash(`+ ${title}`);
    } else if (mode === "edit") {
      updateTask(editingTaskId, { title, description, priority, dueDate, tags });
      app.flash(`✓ ${title} updated`);
    }

    mode = "list";
    reload();
    app.requestRender();
  } else if (key.name === "escape") {
    mode = "list";
    app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    field.value += key.name;
    app.requestRender();
  }
}

function handleDeleteKey(key: KeyEvent) {
  if (key.name === "y") {
    const task = tasks[selectedIndex];
    if (task) {
      deleteTask(task.id);
      app.flash(`Deleted "${task.title}"`);
      reload();
    }
    mode = "list";
    app.requestRender();
  } else {
    mode = "list";
    app.requestRender();
  }
}

// ── Screen export ──

export const tasksScreen: Screen = {
  name: "tasks",
  statusHint: ": command bar • space toggle • x done • n new • p priority • tab filter • q back",

  onEnter() {
    mode = "list";
    reload();
  },

  render() {
    switch (mode) {
      case "list":
      case "command": renderList(); break;
      case "create": renderForm("New Task"); break;
      case "edit": renderForm("Edit Task"); break;
      case "confirm-delete": renderList(); renderConfirmDelete(); break;
    }
  },

  onKey(key: KeyEvent) {
    switch (mode) {
      case "list": handleListKey(key); break;
      case "command": handleCommandKey(key); break;
      case "create":
      case "edit": handleFormKey(key); break;
      case "confirm-delete": handleDeleteKey(key); break;
    }
  },
};
