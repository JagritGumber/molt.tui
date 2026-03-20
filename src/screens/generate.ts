// Generate Post screen - pick an agent, optionally provide a topic, generate via Z.ai

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawList, drawTextInput, drawTextArea, drawHR, drawSpinner, badge, type ListItem } from "../tui/components.ts";
import { listAgents, type AgentPersonality } from "../agents/personality.ts";
import { ZaiClient } from "../clients/zai.ts";
import { loadConfig } from "../utils/config.ts";
import type { KeyEvent } from "../tui/input.ts";

type Phase = "select-agent" | "input-topic" | "generating" | "preview";

let phase: Phase = "select-agent";
let agents: AgentPersonality[] = [];
let selectedAgent = 0;
let topic = "";
let generatedPost = "";
let generatedTitle = "";
let error = "";
let previewScroll = 0;

function reset() {
  phase = "select-agent";
  agents = listAgents();
  selectedAgent = 0;
  topic = "";
  generatedPost = "";
  generatedTitle = "";
  error = "";
  previewScroll = 0;
}

export const generateScreen: Screen = {
  name: "generate",
  statusHint: "",

  onEnter() {
    reset();
    const config = loadConfig();
    if (!config.zaiApiKey) {
      app.flash("Z.ai API key not set! Go to Settings first.");
    }
    if (agents.length === 0) {
      app.flash("No agents found! Create one first.");
    }
  },

  get statusHint() {
    switch (phase) {
      case "select-agent": return "↑↓ select agent • enter confirm • esc back";
      case "input-topic": return "type a topic (or leave empty for random) • enter generate • esc back";
      case "generating": return "generating post with Z.ai...";
      case "preview": return "p post to moltbook • r regenerate • e edit • esc back";
    }
  },

  render() {
    const { rows, cols } = getTermSize();
    const w = Math.min(75, cols - 6);

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Generate Post${style.reset}`);
    drawHR(4, 3, w);

    if (phase === "select-agent") {
      cursor.to(5, 3);
      write(`${fg.gray}Select an agent to generate a post:${style.reset}`);

      const items: ListItem[] = agents.map((a) => ({
        label: a.name,
        value: a.id,
        description: a.tone,
      }));

      if (items.length === 0) {
        cursor.to(7, 5);
        write(`${fg.yellow}No agents available. Create one first.${style.reset}`);
      } else {
        drawList(7, 3, w, items, selectedAgent, Math.min(items.length, rows - 10));
      }
    }

    if (phase === "input-topic") {
      const agent = agents[selectedAgent]!;
      cursor.to(5, 3);
      write(`${fg.gray}Agent: ${fg.brightWhite}${agent.name}${style.reset}`);

      drawTextInput(7, 3, w, topic, "Topic (optional)", true);

      cursor.to(9, 3);
      write(`${fg.gray}Leave empty for the agent to pick a topic based on its personality.${style.reset}`);
    }

    if (phase === "generating") {
      drawSpinner(6, 5, "Generating post with Z.ai...");
    }

    if (phase === "preview") {
      if (error) {
        cursor.to(6, 3);
        write(`${fg.brightRed}Error: ${error}${style.reset}`);
        cursor.to(8, 3);
        write(`${fg.gray}Press ${fg.brightCyan}r${fg.gray} to retry or ${fg.brightCyan}esc${fg.gray} to go back${style.reset}`);
        return;
      }

      const agent = agents[selectedAgent]!;
      cursor.to(5, 3);
      write(`${badge(agent.name, fg.brightCyan)}  ${fg.gray}→${style.reset}  ${fg.brightWhite}${style.bold}${generatedTitle}${style.reset}`);

      drawHR(6, 3, w);

      const lines = generatedPost.split("\n");
      const maxLines = rows - 11;
      drawTextArea(7, 3, w, maxLines, lines, previewScroll);

      const actionsRow = Math.min(7 + lines.length + 1, rows - 3);
      cursor.to(actionsRow, 3);
      write(
        `${fg.brightCyan}[p]${fg.white} post  ` +
        `${fg.brightCyan}[r]${fg.white} regenerate  ` +
        `${fg.brightCyan}[c]${fg.white} copy  ` +
        `${fg.brightCyan}[esc]${fg.white} back${style.reset}`
      );
    }
  },

  onKey(key: KeyEvent) {
    if (key.name === "escape") {
      if (phase === "select-agent") {
        app.back();
      } else if (phase === "generating") {
        // Can't cancel mid-request easily, just go back
        phase = "select-agent";
        app.requestRender();
      } else {
        phase = "select-agent";
        app.requestRender();
      }
      return;
    }

    if (phase === "select-agent") {
      if (key.name === "up" || key.name === "k") {
        selectedAgent = Math.max(0, selectedAgent - 1);
        app.requestRender();
      } else if (key.name === "down" || key.name === "j") {
        selectedAgent = Math.min(agents.length - 1, selectedAgent + 1);
        app.requestRender();
      } else if (key.name === "return" && agents.length > 0) {
        phase = "input-topic";
        topic = "";
        app.requestRender();
      }
    } else if (phase === "input-topic") {
      if (key.name === "backspace") {
        topic = topic.slice(0, -1);
        app.requestRender();
      } else if (key.name === "return") {
        doGenerate();
      } else if (!key.ctrl && key.name.length === 1) {
        topic += key.name;
        app.requestRender();
      }
    } else if (phase === "preview") {
      if (key.name === "r") {
        doGenerate();
      } else if (key.name === "p") {
        // Store for post screen
        (globalThis as any).__pendingPost = {
          title: generatedTitle,
          content: generatedPost,
          agentId: agents[selectedAgent]!.id,
          submolts: agents[selectedAgent]!.submolts,
        };
        app.navigate("post");
      } else if (key.name === "up" || key.name === "k") {
        previewScroll = Math.max(0, previewScroll - 1);
        app.requestRender();
      } else if (key.name === "down" || key.name === "j") {
        previewScroll++;
        app.requestRender();
      }
    }
  },
};

async function doGenerate() {
  const config = loadConfig();
  if (!config.zaiApiKey) {
    app.flash("Z.ai API key not configured!");
    return;
  }

  phase = "generating";
  error = "";
  app.requestRender();

  try {
    const agent = agents[selectedAgent]!;
    const client = new ZaiClient(config.zaiApiKey, config.zaiModel);

    generatedPost = await client.generatePost(
      {
        name: agent.name,
        tone: agent.tone,
        topics: agent.topics,
        style: agent.style,
        bio: agent.bio,
        constraints: agent.constraints,
      },
      topic || undefined
    );

    generatedTitle = await client.generatePostTitle(generatedPost);
    previewScroll = 0;
    phase = "preview";
  } catch (err: any) {
    error = err.message || "Unknown error";
    phase = "preview";
  }

  app.requestRender();
}
