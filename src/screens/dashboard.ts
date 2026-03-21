// Dashboard - neovim-style shortcut menu

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawHR, badge } from "../tui/components.ts";
import { listAgents } from "../agents/personality.ts";
import { loadConfig } from "../utils/config.ts";
import type { KeyEvent } from "../tui/input.ts";

interface MenuItem {
  key: string;       // shortcut key
  label: string;     // display name
  target: string;    // screen name or "quit"
  description: string;
  icon: string;
}

const MENU: MenuItem[] = [
  { key: "a", label: "Agents",        target: "agents",   description: "manage AI personalities",  icon: "🤖" },
  { key: "g", label: "Generate",      target: "generate", description: "create a post with AI",    icon: "✨" },
  { key: "p", label: "Post",          target: "post",     description: "publish to moltbook",      icon: "📤" },
  { key: "t", label: "Tasks",         target: "tasks",    description: "plan and track work",       icon: "📋" },
  { key: "f", label: "Feed",          target: "feed",     description: "browse moltbook posts",    icon: "📰" },
  { key: "s", label: "Settings",      target: "settings", description: "API keys & preferences",   icon: "⚙" },
  { key: "q", label: "Quit",          target: "quit",     description: "exit molt.tui",             icon: "👋" },
];

// Build a keymap for instant lookup
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
    write(`${fg.gray}  agent management for moltbook${style.reset}`);

    // Status badges
    const statusRow = logoRow + 5;
    cursor.to(statusRow, 3);
    const zaiStatus = config.zaiApiKey ? badge("Z.ai ✓", fg.brightGreen) : badge("Z.ai ✗", fg.brightRed);
    const moltStatus = config.moltbookApiKey ? badge("Moltbook ✓", fg.brightGreen) : badge("Moltbook ✗", fg.brightRed);
    const agentCount = badge(`${agents.length} agents`, fg.brightCyan);
    write(`  ${zaiStatus}  ${moltStatus}  ${agentCount}`);

    drawHR(statusRow + 1, 3, w);

    // Neovim-style menu
    const menuRow = statusRow + 3;
    MENU.forEach((item, i) => {
      if (menuRow + i >= rows - 2) return;
      cursor.to(menuRow + i, 5);

      // Highlighted shortcut key like neovim
      const keyBadge = `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} ${item.key} ${style.reset}`;
      const label = `${fg.brightWhite}${style.bold} ${item.label}${style.reset}`;
      const desc = `${fg.gray} ${item.description}${style.reset}`;

      write(`${keyBadge}${label}${desc}\x1b[K`);
    });
  },

  onKey(key: KeyEvent) {
    const item = KEYMAP.get(key.name);
    if (item) {
      if (item.target === "quit") {
        app.shutdown();
      } else {
        app.navigate(item.target);
      }
    }
  },
};
