// Create Agent screen - form to define a new agent personality

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawTextInput, drawHR } from "../tui/components.ts";
import { createAgent } from "../agents/personality.ts";
import type { KeyEvent } from "../tui/input.ts";

interface FormField {
  key: string;
  label: string;
  placeholder: string;
  value: string;
}

let fields: FormField[] = [];
let focusedField = 0;

function resetForm() {
  fields = [
    { key: "name", label: "Name", placeholder: "e.g. CyberSage", value: "" },
    { key: "tone", label: "Tone", placeholder: "e.g. witty, provocative, thoughtful", value: "" },
    { key: "topics", label: "Topics", placeholder: "comma-separated: AI, philosophy, tech", value: "" },
    { key: "style", label: "Style", placeholder: "e.g. concise hot takes, long-form essays", value: "" },
    { key: "bio", label: "Bio", placeholder: "a short bio for your agent", value: "" },
    { key: "constraints", label: "Constraints", placeholder: "optional: things to avoid", value: "" },
    { key: "submolts", label: "Submolts", placeholder: "comma-separated: s/technology, s/philosophy", value: "" },
  ];
  focusedField = 0;
}

export const createAgentScreen: Screen = {
  name: "create-agent",
  statusHint: "tab/↓ next field • shift+tab/↑ prev • enter create • esc cancel",
  handlesTextInput: true,

  onEnter() {
    resetForm();
  },

  render() {
    const { cols } = getTermSize();
    const w = cols - 6;

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Create New Agent${style.reset}`);
    drawHR(4, 3, w);

    fields.forEach((field, i) => {
      drawTextInput(6 + i * 2, 3, w, field.value, field.label, i === focusedField);
    });

    const submitRow = 6 + fields.length * 2 + 1;
    cursor.to(submitRow, 3);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to create or ${fg.brightCyan}Esc${fg.gray} to cancel${style.reset}`);
  },

  onKey(key: KeyEvent) {
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
      // Validate & create
      const name = fields.find((f) => f.key === "name")!.value.trim();
      const tone = fields.find((f) => f.key === "tone")!.value.trim();
      const topics = fields.find((f) => f.key === "topics")!.value.split(",").map((s) => s.trim()).filter(Boolean);
      const styleTxt = fields.find((f) => f.key === "style")!.value.trim();
      const bio = fields.find((f) => f.key === "bio")!.value.trim();
      const constraints = fields.find((f) => f.key === "constraints")!.value.trim();
      const submolts = fields.find((f) => f.key === "submolts")!.value.split(",").map((s) => s.trim()).filter(Boolean);

      if (!name) {
        app.flash("Name is required!");
        return;
      }
      if (!tone) {
        app.flash("Tone is required!");
        return;
      }

      createAgent({ name, tone, topics, style: styleTxt || "default", bio, constraints, submolts, moltbookAgentId: "" });
      app.flash(`Agent "${name}" created!`);
      app.back();
    } else if (key.name === "escape") {
      app.back();
    } else if (!key.ctrl && key.name.length === 1) {
      // Prevent name from getting absurdly long
      if (field.key === "name" && field.value.length >= 50) return;
      field.value += key.name;
      app.requestRender();
    }
  },
};
