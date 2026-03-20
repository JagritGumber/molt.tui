// Settings screen - configure API keys and preferences

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawTextInput, drawHR, badge } from "../tui/components.ts";
import { loadConfig, saveConfig, type Config } from "../utils/config.ts";
import type { KeyEvent } from "../tui/input.ts";

interface SettingField {
  key: keyof Config;
  label: string;
  secret: boolean;
  value: string;
}

let fields: SettingField[] = [];
let focusedField = 0;

function loadFields() {
  const config = loadConfig();
  fields = [
    { key: "zaiApiKey", label: "Z.ai API Key", secret: true, value: config.zaiApiKey },
    { key: "zaiModel", label: "Z.ai Model", secret: false, value: config.zaiModel },
    { key: "moltbookApiKey", label: "Moltbook API Key", secret: true, value: config.moltbookApiKey },
    { key: "moltbookAgentId", label: "Moltbook Agent ID", secret: false, value: config.moltbookAgentId },
  ];
  focusedField = 0;
}

function displayValue(field: SettingField): string {
  if (!field.value) return "";
  if (field.secret) return field.value.slice(0, 4) + "•".repeat(Math.max(0, field.value.length - 4));
  return field.value;
}

export const settingsScreen: Screen = {
  name: "settings",
  statusHint: "tab/↓ next • shift+tab/↑ prev • enter save • esc back",

  onEnter() {
    loadFields();
  },

  render() {
    const { cols } = getTermSize();
    const w = Math.min(70, cols - 6);

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Settings${style.reset}`);
    drawHR(4, 3, w);

    // Z.ai section
    cursor.to(5, 3);
    write(`${fg.gray}${style.bold}Z.ai (LLM Provider)${style.reset}`);

    drawTextInput(6, 3, w, focusedField === 0 ? fields[0]!.value : displayValue(fields[0]!), fields[0]!.label, focusedField === 0);
    drawTextInput(8, 3, w, fields[1]!.value, fields[1]!.label, focusedField === 1);

    // Moltbook section
    cursor.to(10, 3);
    write(`${fg.gray}${style.bold}Moltbook${style.reset}`);

    drawTextInput(11, 3, w, focusedField === 2 ? fields[2]!.value : displayValue(fields[2]!), fields[2]!.label, focusedField === 2);
    drawTextInput(13, 3, w, fields[3]!.value, fields[3]!.label, focusedField === 3);

    // Info
    cursor.to(16, 3);
    write(`${fg.gray}Config stored at: ~/.moltui/config.json${style.reset}`);

    cursor.to(18, 3);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to save or ${fg.brightCyan}Esc${fg.gray} to discard${style.reset}`);
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
      const config = loadConfig();
      for (const f of fields) {
        (config as any)[f.key] = f.value;
      }
      saveConfig(config);
      app.flash("Settings saved!");
      app.back();
    } else if (key.name === "escape") {
      app.back();
    } else if (!key.ctrl && key.name.length === 1) {
      field.value += key.name;
      app.requestRender();
    }
  },
};
