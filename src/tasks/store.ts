// Task storage - CRUD for tasks stored as JSON in ~/.moltui/tasks/

import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, unlinkSync } from "fs";
import { join } from "path";
import { getConfigDir } from "../utils/config.ts";

export type Priority = "low" | "med" | "high";
export type TaskStatus = "todo" | "in-progress" | "done";

export interface Task {
  id: string;
  title: string;
  description: string;
  priority: Priority;
  status: TaskStatus;
  dueDate: string; // ISO date string or empty
  tags: string[];
  createdAt: string;
  updatedAt: string;
}

const TASKS_DIR = join(getConfigDir(), "tasks");

function ensureTasksDir() {
  if (!existsSync(TASKS_DIR)) mkdirSync(TASKS_DIR, { recursive: true });
}

function taskPath(id: string): string {
  return join(TASKS_DIR, `${id}.json`);
}

function generateId(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30) + "-" + Date.now().toString(36);
}

export function listTasks(): Task[] {
  ensureTasksDir();
  const files = readdirSync(TASKS_DIR).filter((f) => f.endsWith(".json"));
  return files
    .map((f) => {
      try {
        return JSON.parse(readFileSync(join(TASKS_DIR, f), "utf-8")) as Task;
      } catch {
        return null;
      }
    })
    .filter(Boolean) as Task[];
}

export function getTask(id: string): Task | null {
  const p = taskPath(id);
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf-8")) as Task;
  } catch {
    return null;
  }
}

export function createTask(data: Omit<Task, "id" | "createdAt" | "updatedAt">): Task {
  ensureTasksDir();
  const now = new Date().toISOString();
  const task: Task = { ...data, id: generateId(data.title), createdAt: now, updatedAt: now };
  writeFileSync(taskPath(task.id), JSON.stringify(task, null, 2));
  return task;
}

export function updateTask(id: string, data: Partial<Task>): Task | null {
  const task = getTask(id);
  if (!task) return null;
  const updated = { ...task, ...data, id, updatedAt: new Date().toISOString() };
  writeFileSync(taskPath(id), JSON.stringify(updated, null, 2));
  return updated;
}

export function deleteTask(id: string): boolean {
  const p = taskPath(id);
  if (!existsSync(p)) return false;
  unlinkSync(p);
  return true;
}

export function cycleStatus(status: TaskStatus): TaskStatus {
  const order: TaskStatus[] = ["todo", "in-progress", "done"];
  return order[(order.indexOf(status) + 1) % order.length]!;
}

export function cyclePriority(priority: Priority): Priority {
  const order: Priority[] = ["low", "med", "high"];
  return order[(order.indexOf(priority) + 1) % order.length]!;
}

export function sortTasks(tasks: Task[]): Task[] {
  const statusOrder: Record<TaskStatus, number> = { "in-progress": 0, "todo": 1, "done": 2 };
  const prioOrder: Record<Priority, number> = { "high": 0, "med": 1, "low": 2 };
  return [...tasks].sort((a, b) => {
    const s = statusOrder[a.status] - statusOrder[b.status];
    if (s !== 0) return s;
    const p = prioOrder[a.priority] - prioOrder[b.priority];
    if (p !== 0) return p;
    return a.createdAt < b.createdAt ? 1 : -1;
  });
}
