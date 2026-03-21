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

    // Detail panel for selected agent
    if (selectedIndex < agents.length) {
      const agent = agents[selectedIndex]!;
      const detailRow = 6;
      const detailCol = Math.min(70, cols - 35);
      const boxW = Math.min(35, cols - detailCol - 1);
      if (detailCol > 40 && boxW > 10) {
        drawBox(detailRow - 1, detailCol, boxW, 12, agent.name);
        const dc = detailCol + 2;
        const tw = boxW - 4; // text width inside box
        const clip = (s: string) => s.length > tw ? s.slice(0, tw - 1) + "…" : s.padEnd(tw);
        cursor.to(detailRow + 1, dc); write(`${fg.gray}Tone: ${fg.white}${clip(agent.tone)}${style.reset}`);
        cursor.to(detailRow + 2, dc); write(`${fg.gray}Style: ${fg.white}${clip(agent.style)}${style.reset}`);
        cursor.to(detailRow + 3, dc); write(`${fg.gray}Topics:${" ".repeat(Math.max(0, tw - 7))}${style.reset}`);
        agent.topics.slice(0, 4).forEach((t, i) => {
          cursor.to(detailRow + 4 + i, dc + 1);
          write(`${fg.cyan}• ${fg.white}${clip(t)}${style.reset}`);
        });
        cursor.to(detailRow + 8, dc); write(`${fg.gray}Submolts: ${fg.white}${clip(agent.submolts.join(", ") || "none")}${style.reset}`);
        cursor.to(detailRow + 9, dc); write(`${fg.gray}Molt ID: ${fg.white}${clip(agent.moltbookAgentId || "unregistered")}${style.reset}`);
      }
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
