// Agents screen - list, create, edit, delete agent personalities

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize, fitWidth } from "../tui/ansi.ts";
import { drawList, drawBox, drawTextInput, drawHR, badge, type ListItem } from "../tui/components.ts";
import { listAgents, createAgent, deleteAgent, type AgentPersonality } from "../agents/personality.ts";
import type { KeyEvent } from "../tui/input.ts";

let agents: AgentPersonality[] = [];
let selectedIndex = 0;

function refreshAgents() {
  agents = listAgents();
}

function getItems(): ListItem[] {
  const items: ListItem[] = agents.map((a) => ({
    label: a.name,
    value: a.id,
    description: `${a.tone} • ${a.topics.slice(0, 3).join(", ")}`,
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

    // Detail panel for selected agent (only if terminal is wide enough)
    if (selectedIndex < agents.length && cols > 90) {
      const agent = agents[selectedIndex]!;
      const detailRow = 6;
      const boxW = 34;
      const detailCol = cols - boxW - 2;
      // Maximum visible chars per line inside the box
      const lineW = boxW - 4;

      drawBox(detailRow - 1, detailCol, boxW, 12, agent.name);
      const dc = detailCol + 2;

      // Write a label:value line, truncated to fit inside the box
      const writeLine = (row: number, label: string, val: string) => {
        const maxVal = lineW - label.length;
        const clipped = maxVal <= 0 ? "" : val.length > maxVal ? val.slice(0, maxVal - 1) + "…" : val;
        cursor.to(row, dc);
        write(`${fg.gray}${label}${fg.white}${clipped}${style.reset}\x1b[K`);
      };

      writeLine(detailRow + 1, "Tone: ", agent.tone.replace(/[\n\r]/g, " "));
      writeLine(detailRow + 2, "Style: ", agent.style.replace(/[\n\r]/g, " "));
      cursor.to(detailRow + 3, dc); write(`${fg.gray}Topics:${style.reset}\x1b[K`);
      agent.topics.slice(0, 4).forEach((t, i) => {
        const maxT = lineW - 3;
        const ct = t.length > maxT ? t.slice(0, maxT - 1) + "…" : t;
        cursor.to(detailRow + 4 + i, dc + 1);
        write(`${fg.cyan}• ${fg.white}${ct}${style.reset}\x1b[K`);
      });
      writeLine(detailRow + 8, "Submolts: ", agent.submolts.join(", ") || "none");
      writeLine(detailRow + 9, "Molt ID: ", agent.moltbookAgentId || "unregistered");
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
