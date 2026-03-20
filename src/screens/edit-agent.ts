// Edit Agent screen - modify existing agent personality

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawTextInput, drawHR } from "../tui/components.ts";
import { getAgent, updateAgent, type AgentPersonality } from "../agents/personality.ts";
import type { KeyEvent } from "../tui/input.ts";

interface FormField {
  key: string;
  label: string;
  value: string;
}

let agent: AgentPersonality | null = null;
let fields: FormField[] = [];
let focusedField = 0;

function loadForm() {
  const id = (globalThis as any).__selectedAgentId as string;
  agent = id ? getAgent(id) : null;
  if (!agent) return;

  fields = [
    { key: "name", label: "Name", value: agent.name },
    { key: "tone", label: "Tone", value: agent.tone },
    { key: "topics", label: "Topics", value: agent.topics.join(", ") },
    { key: "style", label: "Style", value: agent.style },
    { key: "bio", label: "Bio", value: agent.bio },
    { key: "constraints", label: "Constraints", value: agent.constraints },
    { key: "submolts", label: "Submolts", value: agent.submolts.join(", ") },
  ];
  focusedField = 0;
}

export const editAgentScreen: Screen = {
  name: "edit-agent",
  statusHint: "tab/↓ next • shift+tab/↑ prev • enter save • esc cancel",

  onEnter() {
    loadForm();
  },

  render() {
    const { cols } = getTermSize();
    const w = Math.min(70, cols - 6);

    if (!agent) {
      cursor.to(3, 3);
      write(`${fg.brightRed}Agent not found${style.reset}`);
      return;
    }

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Edit Agent: ${agent.name}${style.reset}`);
    drawHR(4, 3, w);

    fields.forEach((field, i) => {
      drawTextInput(6 + i * 2, 3, w, field.value, field.label, i === focusedField);
    });

    const submitRow = 6 + fields.length * 2 + 1;
    cursor.to(submitRow, 3);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to save or ${fg.brightCyan}Esc${fg.gray} to cancel${style.reset}`);
  },

  onKey(key: KeyEvent) {
    if (!agent) {
      if (key.name === "escape") app.back();
      return;
    }

    const field = fields[focusedField]!;

    if (key.name === "tab" && !key.shift || key.name === "down") {
      focusedField = Math.min(fields.length - 1, focusedField + 1);
      app.requestRender();
    } else if (key.name === "tab" && key.shift || key.name === "up") {
      focusedField = Math.max(0, focusedField - 1);
      app.requestRender();
    } else if (key.name === "backspace") {
      field.value = field.value.slice(0, -1);
      app.requestRender();
    } else if (key.name === "return") {
      const name = fields.find((f) => f.key === "name")!.value.trim();
      const tone = fields.find((f) => f.key === "tone")!.value.trim();
      const topics = fields.find((f) => f.key === "topics")!.value.split(",").map((s) => s.trim()).filter(Boolean);
      const styleTxt = fields.find((f) => f.key === "style")!.value.trim();
      const bio = fields.find((f) => f.key === "bio")!.value.trim();
      const constraints = fields.find((f) => f.key === "constraints")!.value.trim();
      const submolts = fields.find((f) => f.key === "submolts")!.value.split(",").map((s) => s.trim()).filter(Boolean);

      if (!name || !tone) {
        app.flash("Name and tone are required!");
        return;
      }

      updateAgent(agent.id, { name, tone, topics, style: styleTxt, bio, constraints, submolts });
      app.flash(`Agent "${name}" updated!`);
      app.back();
    } else if (key.name === "escape") {
      app.back();
    } else if (!key.ctrl && key.name.length === 1) {
      field.value += key.name;
      app.requestRender();
    }
  },
};
