// Dashboard - main menu screen

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawList, drawBox, drawHR, badge, type ListItem } from "../tui/components.ts";
import { listAgents } from "../agents/personality.ts";
import { loadConfig } from "../utils/config.ts";
import type { KeyEvent } from "../tui/input.ts";

const MENU_ITEMS: ListItem[] = [
  { label: "Agents", value: "agents", description: "manage your AI agent personalities" },
  { label: "Generate Post", value: "generate", description: "create a new post with AI" },
  { label: "Post to Moltbook", value: "post", description: "publish generated content" },
  { label: "Tasks", value: "tasks", description: "plan and track your work" },
  { label: "Feed", value: "feed", description: "browse moltbook posts" },
  { label: "Settings", value: "settings", description: "configure API keys & preferences" },
  { label: "Quit", value: "quit", description: "exit moltui" },
];

let selectedIndex = 0;

export const dashboardScreen: Screen = {
  name: "dashboard",
  statusHint: "↑↓ navigate • enter select • q quit",

  render() {
    const { rows, cols } = getTermSize();
    const agents = listAgents();
    const config = loadConfig();

    // Logo area
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

    drawHR(statusRow + 1, 3, Math.min(60, cols - 6));

    // Menu
    const menuRow = statusRow + 3;
    drawList(menuRow, 3, Math.min(65, cols - 6), MENU_ITEMS, selectedIndex, Math.min(MENU_ITEMS.length, rows - menuRow - 2));
  },

  onKey(key: KeyEvent) {
    if (key.name === "up" || key.name === "k") {
      selectedIndex = Math.max(0, selectedIndex - 1);
      app.requestRender();
    } else if (key.name === "down" || key.name === "j") {
      selectedIndex = Math.min(MENU_ITEMS.length - 1, selectedIndex + 1);
      app.requestRender();
    } else if (key.name === "return") {
      const item = MENU_ITEMS[selectedIndex]!;
      if (item.value === "quit") {
        app.shutdown();
      } else {
        app.navigate(item.value);
      }
    } else if (key.name === "q") {
      app.shutdown();
    }
  },
};
