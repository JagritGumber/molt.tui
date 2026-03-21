// Agents screen - list, create, edit, delete agent personalities

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawList, drawHR, type ListItem } from "../tui/components.ts";
import { listAgents, createAgent, deleteAgent, type AgentPersonality } from "../agents/personality.ts";
import type { KeyEvent } from "../tui/input.ts";

let agents: AgentPersonality[] = [];
let selectedIndex = 0;

function refreshAgents() {
  agents = listAgents();
}

function getItems(): ListItem[] {
  const short = (s: string, max: number) =>
    s.replace(/[\n\r\t]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);

  const items: ListItem[] = agents.map((a) => ({
    label: a.name,
    value: a.id,
    description: short(a.topics.slice(0, 3).join(", "), 40),
  }));
  items.push({ label: "+ Create New Agent", value: "__create__", description: "define a new personality" });
  return items;
}

export const agentsScreen: Screen = {
  name: "agents",
  statusHint: "↑↓ navigate • enter select/edit • d delete • esc back",

  onEnter() {
    refreshAgents();
    selectedIndex = 0;
  },

  render() {
    const { rows, cols } = getTermSize();
    const items = getItems();

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Agents${style.reset}  ${fg.gray}(${agents.length} total)${style.reset}`);

    drawHR(4, 3, Math.min(65, cols - 6));

    if (agents.length === 0) {
      cursor.to(6, 5);
      write(`${fg.gray}No agents yet. Create one to get started.${style.reset}`);
      drawList(8, 3, Math.min(65, cols - 6), items, selectedIndex, 1);
    } else {
      drawList(6, 3, Math.min(65, cols - 6), items, selectedIndex, Math.min(items.length, rows - 9));
    }

    // Agent info shown inline below list when selected
    if (selectedIndex < agents.length) {
      const agent = agents[selectedIndex]!;
      const infoRow = Math.min(6 + items.length + 1, rows - 5);
      const iw = Math.min(cols - 6, 70);
      const clip = (s: string, max: number) => {
        const clean = s.replace(/[\n\r\t]/g, " ").replace(/\s+/g, " ");
        return clean.length > max ? clean.slice(0, max - 1) + "…" : clean;
      };
      drawHR(infoRow, 3, iw);
      cursor.to(infoRow + 1, 3);
      write(`${fg.brightCyan}${style.bold}${clip(agent.name, iw)}${style.reset}\x1b[K`);
      cursor.to(infoRow + 2, 3);
      write(`${fg.gray}${clip(agent.tone + " • " + agent.topics.join(", "), iw)}${style.reset}\x1b[K`);
    }
  },

  onKey(key: KeyEvent) {
    const items = getItems();

    if (key.name === "up" || key.name === "k") {
      selectedIndex = Math.max(0, selectedIndex - 1);
      app.requestRender();
    } else if (key.name === "down" || key.name === "j") {
      selectedIndex = Math.min(items.length - 1, selectedIndex + 1);
      app.requestRender();
    } else if (key.name === "return") {
      const item = items[selectedIndex]!;
      if (item.value === "__create__") {
        app.navigate("create-agent");
      } else {
        // Navigate to edit with selected agent
        (globalThis as any).__selectedAgentId = item.value;
        app.navigate("edit-agent");
      }
    } else if (key.name === "d" && selectedIndex < agents.length) {
      const agent = agents[selectedIndex]!;
      deleteAgent(agent.id);
      refreshAgents();
      selectedIndex = Math.min(selectedIndex, Math.max(0, agents.length - 1));
      app.flash(`Deleted agent: ${agent.name}`);
    } else if (key.name === "escape") {
      app.back();
    }
  },
};
