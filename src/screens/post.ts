// Post to Moltbook screen - publish generated content

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawList, drawTextInput, drawHR, drawSpinner, badge, type ListItem } from "../tui/components.ts";
import { MoltbookClient } from "../clients/moltbook.ts";
import { loadConfig } from "../utils/config.ts";
import { getAgent } from "../agents/personality.ts";
import type { KeyEvent } from "../tui/input.ts";

type Phase = "select-submolt" | "confirm" | "posting" | "done";

interface PendingPost {
  title: string;
  content: string;
  agentId: string;
  submolts: string[];
}

let phase: Phase = "select-submolt";
let pending: PendingPost | null = null;
let submoltInput = "";
let selectedSubmolt = 0;
let error = "";
let postUrl = "";

function reset() {
  phase = "select-submolt";
  pending = (globalThis as any).__pendingPost || null;
  submoltInput = "";
  selectedSubmolt = 0;
  error = "";
  postUrl = "";
}

export const postScreen: Screen = {
  name: "post",
  handlesTextInput: true,
  statusHint: "",

  onEnter() {
    reset();
    if (!pending) {
      app.flash("No post to publish! Generate one first.");
    }
    if (pending?.submolts.length) {
      submoltInput = pending.submolts[0] || "";
    }
  },

  get statusHint() {
    switch (phase) {
      case "select-submolt": return "type submolt name • enter confirm • esc back";
      case "confirm": return "y confirm post • n cancel • esc back";
      case "posting": return "posting to moltbook...";
      case "done": return "enter go home • esc back";
    }
  },

  render() {
    const { rows, cols } = getTermSize();
    const w = Math.min(75, cols - 6);

    cursor.to(3, 3);
    write(`${fg.brightCyan}${style.bold}Post to Moltbook${style.reset}`);
    drawHR(4, 3, w);

    if (!pending) {
      cursor.to(6, 5);
      write(`${fg.yellow}No pending post. Generate one first.${style.reset}`);
      return;
    }

    // Show post preview
    cursor.to(5, 3);
    write(`${fg.gray}Title: ${fg.brightWhite}${pending.title}${style.reset}`);
    cursor.to(6, 3);
    const preview = pending.content.slice(0, 120).replace(/\n/g, " ");
    write(`${fg.gray}Content: ${fg.white}${preview}${pending.content.length > 120 ? "…" : ""}${style.reset}`);

    drawHR(7, 3, w);

    if (phase === "select-submolt") {
      cursor.to(9, 3);
      write(`${fg.gray}Which submolt to post in?${style.reset}`);

      if (pending.submolts.length > 0) {
        cursor.to(10, 3);
        write(`${fg.gray}Agent's submolts: ${pending.submolts.map((s) => badge(s, fg.cyan)).join(" ")}${style.reset}`);
      }

      drawTextInput(12, 3, w, submoltInput, "Submolt", true);
    }

    if (phase === "confirm") {
      cursor.to(9, 3);
      write(`${fg.brightYellow}Post to ${badge(submoltInput, fg.brightCyan)}?${style.reset}`);
      cursor.to(11, 3);
      write(`${fg.brightCyan}[y]${fg.white} yes, post it  ${fg.brightCyan}[n]${fg.white} cancel${style.reset}`);
    }

    if (phase === "posting") {
      drawSpinner(9, 5, "Publishing to Moltbook...");
    }

    if (phase === "done") {
      if (error) {
        cursor.to(9, 3);
        write(`${fg.brightRed}Error: ${error}${style.reset}`);
        cursor.to(11, 3);
        write(`${fg.gray}Press ${fg.brightCyan}r${fg.gray} to retry or ${fg.brightCyan}esc${fg.gray} to go back${style.reset}`);
      } else {
        cursor.to(9, 3);
        write(`${fg.brightGreen}${style.bold}✓ Posted successfully!${style.reset}`);
        if (postUrl) {
          cursor.to(11, 3);
          write(`${fg.gray}${postUrl}${style.reset}`);
        }
        cursor.to(13, 3);
        write(`${fg.gray}Press ${fg.brightCyan}enter${fg.gray} to go home${style.reset}`);
      }
    }
  },

  onKey(key: KeyEvent) {
    if (key.name === "escape") {
      if (phase === "confirm") {
        phase = "select-submolt";
        app.requestRender();
      } else {
        app.back();
      }
      return;
    }

    if (phase === "select-submolt") {
      if (key.name === "backspace") {
        submoltInput = submoltInput.slice(0, -1);
        app.requestRender();
      } else if (key.name === "return") {
        if (!submoltInput.trim()) {
          app.flash("Submolt name required!");
          return;
        }
        phase = "confirm";
        app.requestRender();
      } else if (key.name === "tab" && pending?.submolts.length) {
        selectedSubmolt = (selectedSubmolt + 1) % pending.submolts.length;
        submoltInput = pending.submolts[selectedSubmolt] || "";
        app.requestRender();
      } else if (!key.ctrl && key.name.length === 1) {
        submoltInput += key.name;
        app.requestRender();
      }
    } else if (phase === "confirm") {
      if (key.name === "y") {
        doPost();
      } else if (key.name === "n") {
        phase = "select-submolt";
        app.requestRender();
      }
    } else if (phase === "done") {
      if (key.name === "return") {
        app.navigate("dashboard");
      } else if (key.name === "r" && error) {
        doPost();
      }
    }
  },
};

async function doPost() {
  if (!pending) return;

  const config = loadConfig();
  if (!config.moltbookApiKey) {
    app.flash("Moltbook API key not configured!");
    phase = "select-submolt";
    app.requestRender();
    return;
  }

  phase = "posting";
  error = "";
  app.requestRender();

  try {
    const client = new MoltbookClient(config.moltbookApiKey);
    const result = await client.createPost({
      title: pending.title,
      content: pending.content,
      submolt: submoltInput.trim(),
    });
    postUrl = `https://www.moltbook.com/s/${submoltInput.trim()}/posts/${result.id}`;
    phase = "done";
  } catch (err: any) {
    error = err.message || "Unknown error";
    phase = "done";
  }

  app.requestRender();
}
