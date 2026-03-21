#!/usr/bin/env bun
// CLI for external tools (Claude Code) to add learnings to Molt.tui agents
// Usage:
//   bun learn add "Never use exclamation marks" --type avoid --strength 4
//   bun learn add "Prefers short sentences" --type style
//   bun learn add "Loves Rust over Go" --type prefer --agent itsroboki
//   bun learn list [--agent <id>]
//   bun learn remove <learning-id> [--agent <id>]

import { getLearnings, addLearning, removeLearning, type Learning } from "./agents/learnings.ts";
import { listAgents } from "./agents/personality.ts";
import { ensureDirs } from "./utils/config.ts";

ensureDirs();

const args = process.argv.slice(2);
const cmd = args[0];

function getFlag(name: string): string | undefined {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 && idx + 1 < args.length ? args[idx + 1] : undefined;
}

function getDefaultAgentId(): string {
  const agents = listAgents();
  return agents[0]?.id || "";
}

if (!cmd || cmd === "help") {
  console.log(`molt-learn — teach your Moltbook agent

Commands:
  add <lesson>              Add a learning
    --type <type>           style|tone|topic|avoid|prefer|correction (default: prefer)
    --strength <1-5>        importance (default: 3)
    --context <text>        what triggered this learning
    --agent <id>            agent id (default: first agent)

  list                      List all learnings
    --agent <id>            agent id (default: first agent)
    --json                  output as JSON

  remove <learning-id>      Remove a learning
    --agent <id>            agent id (default: first agent)

Types:
  style       writing style preferences ("Uses short paragraphs")
  tone        voice/attitude ("Sarcastic but not mean")
  topic       subject matter ("Talks about Rust more than Go")
  avoid       things to NOT do ("Never use hashtags")
  prefer      things to DO ("Reference anime when relevant")
  correction  specific fix ("Was too formal, be more casual")`);
  process.exit(0);
}

const agentId = getFlag("agent") || getDefaultAgentId();
if (!agentId) {
  console.error("No agents found. Create one in Molt.tui first.");
  process.exit(1);
}

if (cmd === "add") {
  const lesson = args[1];
  if (!lesson) { console.error("Usage: add <lesson>"); process.exit(1); }

  const typeRaw = getFlag("type") || "prefer";
  const validTypes = ["style", "tone", "topic", "avoid", "prefer", "correction"];
  if (!validTypes.includes(typeRaw)) {
    console.error(`Invalid type: ${typeRaw}. Use: ${validTypes.join(", ")}`);
    process.exit(1);
  }

  const strengthRaw = getFlag("strength") || "3";
  const strength = Math.max(1, Math.min(5, parseInt(strengthRaw) || 3));
  const context = getFlag("context") || "";

  const entry = addLearning(agentId, {
    type: typeRaw as Learning["type"],
    lesson,
    context,
    strength,
  });

  console.log(`✓ Agent learned: [${typeRaw}] "${lesson}" (strength: ${strength})`);
  console.log(`  ID: ${entry.id}`);
}

else if (cmd === "list") {
  const learnings = getLearnings(agentId);
  const asJson = args.includes("--json");

  if (asJson) {
    console.log(JSON.stringify(learnings, null, 2));
    process.exit(0);
  }

  if (learnings.length === 0) {
    console.log("No learnings yet.");
    process.exit(0);
  }

  const icons: Record<string, string> = {
    avoid: "🚫", prefer: "✅", style: "🎨", tone: "🎭", topic: "📌", correction: "🔧",
  };

  for (const l of learnings) {
    const icon = icons[l.type] || "•";
    const stars = "★".repeat(l.strength) + "☆".repeat(5 - l.strength);
    console.log(`${icon} ${l.type.padEnd(11)} ${stars}  ${l.lesson}`);
    if (l.context) console.log(`  ${" ".repeat(12)}      ↳ ${l.context}`);
    console.log(`  ${" ".repeat(12)}      id: ${l.id}`);
  }
  console.log(`\n${learnings.length} learnings for agent ${agentId}`);
}

else if (cmd === "remove") {
  const id = args[1];
  if (!id) { console.error("Usage: remove <learning-id>"); process.exit(1); }
  if (removeLearning(agentId, id)) {
    console.log(`✓ Removed learning: ${id}`);
  } else {
    console.error(`Learning not found: ${id}`);
    process.exit(1);
  }
}

else {
  console.error(`Unknown command: ${cmd}. Run 'bun learn help' for usage.`);
  process.exit(1);
}
