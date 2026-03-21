// Agent learning system — stores lessons from user corrections
// Each agent accumulates learnings that refine future generations

import { existsSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { getConfigDir } from "../utils/config.ts";

export interface Learning {
  id: string;
  timestamp: string;
  type: "style" | "tone" | "topic" | "avoid" | "prefer" | "correction";
  lesson: string;       // what the agent learned
  context?: string;     // what triggered the learning (e.g. rejected post)
  strength: number;     // 1-5, higher = more important
}

const LEARNINGS_DIR = join(getConfigDir(), "learnings");

function ensureDir() {
  if (!existsSync(LEARNINGS_DIR)) {
    const { mkdirSync } = require("fs");
    mkdirSync(LEARNINGS_DIR, { recursive: true });
  }
}

function learningsPath(agentId: string): string {
  return join(LEARNINGS_DIR, `${agentId}.json`);
}

export function getLearnings(agentId: string): Learning[] {
  ensureDir();
  const p = learningsPath(agentId);
  if (!existsSync(p)) return [];
  try {
    return JSON.parse(readFileSync(p, "utf-8")) as Learning[];
  } catch {
    return [];
  }
}

export function addLearning(agentId: string, learning: Omit<Learning, "id" | "timestamp">): Learning {
  ensureDir();
  const learnings = getLearnings(agentId);
  const entry: Learning = {
    ...learning,
    id: Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 6),
    timestamp: new Date().toISOString(),
  };
  learnings.push(entry);

  // Keep max 100 learnings, drop oldest low-strength ones first
  if (learnings.length > 100) {
    learnings.sort((a, b) => b.strength - a.strength || b.timestamp.localeCompare(a.timestamp));
    learnings.length = 100;
    // Warn if the new entry was evicted (too low strength)
    if (!learnings.find((l) => l.id === entry.id)) {
      learnings[99] = entry; // force-keep the newest entry
    }
  }

  writeFileSync(learningsPath(agentId), JSON.stringify(learnings, null, 2));
  return entry;
}

export function removeLearning(agentId: string, learningId: string): boolean {
  const learnings = getLearnings(agentId);
  const idx = learnings.findIndex((l) => l.id === learningId);
  if (idx === -1) return false;
  learnings.splice(idx, 1);
  writeFileSync(learningsPath(agentId), JSON.stringify(learnings, null, 2));
  return true;
}

// Build a learning context block to inject into the system prompt
export function buildLearningPrompt(agentId: string): string {
  const learnings = getLearnings(agentId);
  if (learnings.length === 0) return "";

  // Sort by strength desc, then recency
  const sorted = [...learnings].sort((a, b) => b.strength - a.strength || b.timestamp.localeCompare(a.timestamp));

  // Take top 30 most important
  const top = sorted.slice(0, 30);

  const avoids = top.filter((l) => l.type === "avoid").map((l) => `- DON'T: ${l.lesson}`);
  const prefers = top.filter((l) => l.type === "prefer").map((l) => `- DO: ${l.lesson}`);
  const styles = top.filter((l) => l.type === "style").map((l) => `- STYLE: ${l.lesson}`);
  const tones = top.filter((l) => l.type === "tone").map((l) => `- TONE: ${l.lesson}`);
  const corrections = top.filter((l) => l.type === "correction").map((l) => `- LEARNED: ${l.lesson}`);
  const topics = top.filter((l) => l.type === "topic").map((l) => `- TOPIC: ${l.lesson}`);

  const sections = [
    ...avoids, ...prefers, ...styles, ...tones, ...corrections, ...topics,
  ];

  if (sections.length === 0) return "";

  return `\nLEARNED BEHAVIORS (from past interactions — follow these strictly):\n${sections.join("\n")}`;
}
