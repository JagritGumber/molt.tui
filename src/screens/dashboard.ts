// Dashboard - neovim-style shortcut menu

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawHR, badge } from "../tui/components.ts";
import { listAgents } from "../agents/personality.ts";
import { loadConfig } from "../utils/config.ts";
import type { KeyEvent } from "../tui/input.ts";

interface MenuItem {
  key: string;
  label: string;
  target: string;
  description: string;
}

const MENU: MenuItem[] = [
  { key: "g", label: "Git",      target: "git",      description: "repos, branches, PRs, commits" },
  { key: "s", label: "Social",   target: "social",   description: "autonomous moltbook agent" },
  { key: "a", label: "Agents",   target: "agents",   description: "manage AI personalities" },
  { key: "t", label: "Tasks",    target: "tasks",    description: "plan and track work" },
  { key: "c", label: "Settings", target: "settings", description: "API keys & preferences" },
];

const KEYMAP = new Map(MENU.map((m) => [m.key, m]));

export const dashboardScreen: Screen = {
  name: "dashboard",
  statusHint: "press a highlighted key to navigate",

  render() {
    const { rows, cols } = getTermSize();
    const agents = listAgents();
    const config = loadConfig();
    const w = Math.min(60, cols - 6);

    // Logo
    const logoRow = 3;
    cursor.to(logoRow, 3);
    write(`${fg.brightCyan}${style.bold}  ╔╦╗╔═╗╦  ╔╦╗ ╔╦╗╦ ╦╦${style.reset}`);
    cursor.to(logoRow + 1, 3);
    write(`${fg.brightCyan}${style.bold}  ║║║║ ║║   ║   ║ ║ ║║${style.reset}`);
    cursor.to(logoRow + 2, 3);
    write(`${fg.brightCyan}${style.bold}  ╩ ╩╚═╝╩═╝ ╩${style.reset} ${fg.brightMagenta}${style.bold}·${style.reset} ${fg.brightCyan}${style.bold}╩ ╚═╝╩${style.reset}`);
    cursor.to(logoRow + 3, 3);
    write(`${fg.gray}  your autonomous workspace${style.reset}`);

    // Status badges
    const statusRow = logoRow + 5;
    cursor.to(statusRow, 3);
    const zaiStatus = config.zaiApiKey ? badge("Z.ai ✓", fg.brightGreen) : badge("Z.ai ✗", fg.brightRed);
    const moltStatus = config.moltbookApiKey ? badge("Moltbook ✓", fg.brightGreen) : badge("Moltbook ✗", fg.brightRed);
    const agentCount = badge(`${agents.length} agents`, fg.brightCyan);
    write(`  ${zaiStatus}  ${moltStatus}  ${agentCount}`);

    drawHR(statusRow + 1, 3, w);

    // Menu
    const menuRow = statusRow + 3;
    MENU.forEach((item, i) => {
      if (menuRow + i >= rows - 2) return;
      cursor.to(menuRow + i, 5);
      const keyBadge = `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} ${item.key} ${style.reset}`;
      const label = `${fg.brightWhite}${style.bold} ${item.label}${style.reset}`;
      const desc = `${fg.gray} ${item.description}${style.reset}`;
      write(`${keyBadge}${label}${desc}\x1b[K`);
    });
  },

  onKey(key: KeyEvent) {
    const item = KEYMAP.get(key.name);
    if (item) {
      app.navigate(item.target);
    }
  },
};
