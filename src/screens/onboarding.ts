// Onboarding wizard - first-run setup for Z.ai, Moltbook, and agent persona

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawTextInput, drawHR, drawBox, getSpinnerFrame } from "../tui/components.ts";
import { loadConfig, saveConfig, type Config } from "../utils/config.ts";
import { createAgent } from "../agents/personality.ts";
import { ZaiClient } from "../clients/zai.ts";
import { MoltbookClient } from "../clients/moltbook.ts";
import type { KeyEvent } from "../tui/input.ts";

type Step = "welcome" | "zai" | "zai-test" | "moltbook" | "moltbook-test" | "agent" | "persona" | "done";

let currentStep: Step = "welcome";
let config: Config = loadConfig();

// ── Z.ai fields ──
let zaiFields = [
  { key: "apiKey", label: "API Key", value: "", secret: true },
  { key: "model", label: "Model", value: "glm-4.7-flashx", secret: false },
];
let zaiFocus = 0;

// ── Moltbook fields ──
let moltbookFields = [
  { key: "apiKey", label: "API Key", value: "", secret: true },
];
let moltFocus = 0;

// ── Agent setup ──
let agentChoice: "register" | "existing" = "register";
let existingAgentId = "";

// ── Persona fields ──
let personaFields = [
  { key: "name", label: "Name", value: "", placeholder: "e.g. CyberSage" },
  { key: "tone", label: "Tone", value: "", placeholder: "e.g. witty, provocative" },
  { key: "topics", label: "Topics", value: "", placeholder: "comma-sep: AI, philosophy" },
  { key: "style", label: "Style", value: "", placeholder: "e.g. concise hot takes" },
  { key: "bio", label: "Bio", value: "", placeholder: "a short bio for your agent" },
  { key: "constraints", label: "Constraints", value: "", placeholder: "optional: things to avoid" },
  { key: "submolts", label: "Submolts", value: "", placeholder: "comma-sep: s/tech, s/philosophy" },
];
let personaFocus = 0;

// ── Connection test state ──
let testStatus: "idle" | "testing" | "success" | "error" = "idle";
let testMessage = "";

function displaySecret(val: string): string {
  if (!val) return "";
  return val.slice(0, 4) + "•".repeat(Math.max(0, val.length - 4));
}

function drawStepIndicator(row: number, col: number) {
  const steps = ["Welcome", "Z.ai", "Moltbook", "Agent", "Persona", "Done"];
  const stepMap: Record<Step, number> = {
    welcome: 0, zai: 1, "zai-test": 1, moltbook: 2, "moltbook-test": 2, agent: 3, persona: 4, done: 5,
  };
  const activeIdx = stepMap[currentStep];
  const parts = steps.map((s, i) => {
    if (i < activeIdx) return `${fg.brightGreen}● ${s}${style.reset}`;
    if (i === activeIdx) return `${fg.brightCyan}${style.bold}◉ ${s}${style.reset}`;
    return `${fg.gray}○ ${s}${style.reset}`;
  });
  cursor.to(row, col);
  write(parts.join(`${fg.gray} → ${style.reset}`));
}

// ── Render functions per step ──

function renderWelcome() {
  const { cols } = getTermSize();
  const w = Math.min(60, cols - 6);

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}  ╔╦╗╔═╗╦  ╔╦╗ ╔╦╗╦ ╦╦${style.reset}`);
  cursor.to(6, 3);
  write(`${fg.brightCyan}${style.bold}  ║║║║ ║║   ║   ║ ║ ║║${style.reset}`);
  cursor.to(7, 3);
  write(`${fg.brightCyan}${style.bold}  ╩ ╩╚═╝╩═╝ ╩${style.reset} ${fg.brightMagenta}${style.bold}·${style.reset} ${fg.brightCyan}${style.bold}╩ ╚═╝╩${style.reset}`);

  cursor.to(9, 5);
  write(`${fg.white}Welcome! Let's get you set up.${style.reset}`);
  cursor.to(10, 5);
  write(`${fg.gray}This wizard will connect your accounts and create your first agent.${style.reset}`);

  cursor.to(12, 5);
  write(`${fg.white}You'll need:${style.reset}`);
  cursor.to(13, 7);
  write(`${fg.yellow}1.${style.reset} ${fg.white}A Z.ai API key${style.reset} ${fg.gray}(for AI post generation)${style.reset}`);
  cursor.to(14, 7);
  write(`${fg.yellow}2.${style.reset} ${fg.white}A Moltbook API key${style.reset} ${fg.gray}(for posting to the network)${style.reset}`);
  cursor.to(15, 7);
  write(`${fg.yellow}3.${style.reset} ${fg.white}Your agent persona${style.reset} ${fg.gray}(personality, tone, topics)${style.reset}`);

  cursor.to(17, 5);
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to begin or ${fg.brightCyan}Esc${fg.gray} to skip setup${style.reset}`);
}

function renderZai() {
  const { cols } = getTermSize();
  const w = Math.min(65, cols - 6);

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 1: Z.ai Connection${style.reset}`);
  drawHR(6, 3, w);

  cursor.to(7, 3);
  write(`${fg.white}Z.ai provides the LLM that generates your posts.${style.reset}`);
  cursor.to(8, 3);
  write(`${fg.gray}Get your API key from the Z.ai dashboard.${style.reset}`);
  cursor.to(9, 3);
  write(`${fg.gray}Auth: API key sent as Bearer token (not OAuth).${style.reset}`);

  drawTextInput(11, 3, w, zaiFocus === 0 ? zaiFields[0]!.value : displaySecret(zaiFields[0]!.value), zaiFields[0]!.label, zaiFocus === 0);
  drawTextInput(13, 3, w, zaiFields[1]!.value, zaiFields[1]!.label, zaiFocus === 1);

  cursor.to(16, 3);
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to test connection • ${fg.brightCyan}Esc${fg.gray} to go back${style.reset}`);
}

function renderZaiTest() {
  const { cols } = getTermSize();

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 1: Z.ai Connection${style.reset}`);
  drawHR(6, 3, Math.min(65, cols - 6));

  cursor.to(8, 5);
  if (testStatus === "testing") {
    write(`${getSpinnerFrame()} ${fg.white}Testing Z.ai connection...${style.reset}`);
  } else if (testStatus === "success") {
    write(`${fg.brightGreen}✓ ${fg.white}Connected to Z.ai successfully!${style.reset}`);
    cursor.to(9, 5);
    write(`${fg.gray}${testMessage}${style.reset}`);
    cursor.to(11, 5);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to continue${style.reset}`);
  } else if (testStatus === "error") {
    write(`${fg.brightRed}✗ ${fg.white}Connection failed${style.reset}`);
    cursor.to(9, 5);
    write(`${fg.red}${testMessage}${style.reset}`);
    cursor.to(11, 5);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to retry • ${fg.brightCyan}s${fg.gray} to skip${style.reset}`);
  }
}

function renderMoltbook() {
  const { cols } = getTermSize();
  const w = Math.min(65, cols - 6);

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 2: Moltbook Connection${style.reset}`);
  drawHR(6, 3, w);

  cursor.to(7, 3);
  write(`${fg.white}Moltbook is the social network where your agent posts.${style.reset}`);
  cursor.to(8, 3);
  write(`${fg.gray}Get your API key from www.moltbook.com (developer settings).${style.reset}`);

  drawTextInput(10, 3, w, moltFocus === 0 ? moltbookFields[0]!.value : displaySecret(moltbookFields[0]!.value), moltbookFields[0]!.label, moltFocus === 0);

  cursor.to(13, 3);
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to test connection • ${fg.brightCyan}Esc${fg.gray} to go back${style.reset}`);
}

function renderMoltbookTest() {
  const { cols } = getTermSize();

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 2: Moltbook Connection${style.reset}`);
  drawHR(6, 3, Math.min(65, cols - 6));

  cursor.to(8, 5);
  if (testStatus === "testing") {
    write(`${getSpinnerFrame()} ${fg.white}Verifying Moltbook identity...${style.reset}`);
  } else if (testStatus === "success") {
    write(`${fg.brightGreen}✓ ${fg.white}Connected to Moltbook!${style.reset}`);
    cursor.to(9, 5);
    write(`${fg.gray}${testMessage}${style.reset}`);
    cursor.to(11, 5);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to continue${style.reset}`);
  } else if (testStatus === "error") {
    write(`${fg.brightRed}✗ ${fg.white}Connection failed${style.reset}`);
    cursor.to(9, 5);
    write(`${fg.red}${testMessage}${style.reset}`);
    cursor.to(11, 5);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to retry • ${fg.brightCyan}s${fg.gray} to skip${style.reset}`);
  }
}

function renderAgent() {
  const { cols } = getTermSize();
  const w = Math.min(65, cols - 6);

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 3: Agent Identity${style.reset}`);
  drawHR(6, 3, w);

  cursor.to(7, 3);
  write(`${fg.white}How do you want to set up your Moltbook agent?${style.reset}`);

  const options = [
    { label: "Register a new agent", desc: "create a fresh agent on Moltbook" },
    { label: "Use existing agent ID", desc: "enter an agent ID you already have" },
  ];

  options.forEach((opt, i) => {
    cursor.to(9 + i * 2, 5);
    const selected = (i === 0 && agentChoice === "register") || (i === 1 && agentChoice === "existing");
    if (selected) {
      write(`${fg.brightCyan}${style.bold} ❯ ${fg.brightWhite}${opt.label}${style.reset}  ${fg.gray}${opt.desc}${style.reset}`);
    } else {
      write(`${fg.white}   ${opt.label}${style.reset}  ${fg.gray}${opt.desc}${style.reset}`);
    }
  });

  if (agentChoice === "existing") {
    drawTextInput(14, 3, w, existingAgentId, "Agent ID", true);
  }

  cursor.to(17, 3);
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to continue • ${fg.brightCyan}Esc${fg.gray} to go back${style.reset}`);
}

function renderPersona() {
  const { cols } = getTermSize();
  const w = Math.min(65, cols - 6);

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 4: Agent Persona${style.reset}`);
  drawHR(6, 3, w);

  cursor.to(7, 3);
  write(`${fg.gray}Define your agent's personality for post generation.${style.reset}`);

  personaFields.forEach((field, i) => {
    drawTextInput(9 + i * 2, 3, w, field.value || (i !== personaFocus ? `${fg.gray}${field.placeholder}` : ""), field.label, i === personaFocus);
  });

  const submitRow = 9 + personaFields.length * 2 + 1;
  cursor.to(submitRow, 3);
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to finish setup • ${fg.brightCyan}Esc${fg.gray} to go back${style.reset}`);
}

function renderDone() {
  cursor.to(5, 3);
  write(`${fg.brightGreen}${style.bold}✓ Setup Complete!${style.reset}`);

  cursor.to(7, 5);
  write(`${fg.white}Your Molt.tui is ready to go.${style.reset}`);

  cursor.to(9, 5);
  const zOk = config.zaiApiKey ? `${fg.brightGreen}✓` : `${fg.brightRed}✗`;
  write(`${zOk} ${fg.white}Z.ai${style.reset}`);

  cursor.to(10, 5);
  const mOk = config.moltbookApiKey ? `${fg.brightGreen}✓` : `${fg.brightRed}✗`;
  write(`${mOk} ${fg.white}Moltbook${style.reset}`);

  cursor.to(11, 5);
  const aOk = config.moltbookAgentId ? `${fg.brightGreen}✓` : `${fg.brightRed}✗`;
  write(`${aOk} ${fg.white}Agent: ${fg.gray}${config.moltbookAgentId || "not set"}${style.reset}`);

  cursor.to(13, 5);
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to go to the dashboard${style.reset}`);
}

// ── Connection test helpers ──

async function testZai() {
  testStatus = "testing";
  testMessage = "";
  app.requestRender();

  try {
    const client = new ZaiClient(zaiFields[0]!.value, zaiFields[1]!.value);
    const reply = await client.chatCompletion(
      [{ role: "user", content: "Say 'connected' in one word." }],
      { maxTokens: 10 }
    );
    testStatus = "success";
    testMessage = `Model: ${zaiFields[1]!.value} — response: "${reply.slice(0, 40)}"`;

    config.zaiApiKey = zaiFields[0]!.value;
    config.zaiModel = zaiFields[1]!.value;
    saveConfig(config);
  } catch (err: any) {
    testStatus = "error";
    testMessage = err.message?.slice(0, 80) || "Unknown error";
  }
  app.requestRender();
}

async function testMoltbook() {
  testStatus = "testing";
  testMessage = "";
  app.requestRender();

  try {
    const client = new MoltbookClient(moltbookFields[0]!.value);
    const result = await client.verifyIdentity();
    testStatus = "success";
    testMessage = `Verified! Agent ID: ${result.agentId}`;

    config.moltbookApiKey = moltbookFields[0]!.value;
    if (result.agentId) config.moltbookAgentId = result.agentId;
    saveConfig(config);
  } catch (err: any) {
    testStatus = "error";
    testMessage = err.message?.slice(0, 80) || "Unknown error";
  }
  app.requestRender();
}

// ── Key handlers per step ──

function handleWelcomeKey(key: KeyEvent) {
  if (key.name === "return") {
    currentStep = "zai";
    app.requestRender();
  } else if (key.name === "escape") {
    app.navigate("dashboard");
  }
}

function handleZaiKey(key: KeyEvent) {
  const field = zaiFields[zaiFocus]!;
  if (key.name === "tab" && !key.shift || key.name === "down") {
    zaiFocus = Math.min(zaiFields.length - 1, zaiFocus + 1);
    app.requestRender();
  } else if (key.name === "tab" && key.shift || key.name === "up") {
    zaiFocus = Math.max(0, zaiFocus - 1);
    app.requestRender();
  } else if (key.name === "backspace") {
    field.value = field.value.slice(0, -1);
    app.requestRender();
  } else if (key.name === "return") {
    if (!zaiFields[0]!.value.trim()) {
      app.flash("API key is required!");
      return;
    }
    currentStep = "zai-test";
    testStatus = "idle";
    app.requestRender();
    testZai();
  } else if (key.name === "escape") {
    currentStep = "welcome";
    app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    field.value += key.name;
    app.requestRender();
  }
}

function handleZaiTestKey(key: KeyEvent) {
  if (testStatus === "testing") return;
  if (key.name === "return") {
    if (testStatus === "success") {
      currentStep = "moltbook";
      testStatus = "idle";
    } else {
      currentStep = "zai";
    }
    app.requestRender();
  } else if (key.name === "s") {
    currentStep = "moltbook";
    testStatus = "idle";
    app.requestRender();
  }
}

function handleMoltbookKey(key: KeyEvent) {
  const field = moltbookFields[moltFocus]!;
  if (key.name === "backspace") {
    field.value = field.value.slice(0, -1);
    app.requestRender();
  } else if (key.name === "return") {
    if (!moltbookFields[0]!.value.trim()) {
      app.flash("API key is required!");
      return;
    }
    currentStep = "moltbook-test";
    testStatus = "idle";
    app.requestRender();
    testMoltbook();
  } else if (key.name === "escape") {
    currentStep = "zai";
    app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    field.value += key.name;
    app.requestRender();
  }
}

function handleMoltbookTestKey(key: KeyEvent) {
  if (testStatus === "testing") return;
  if (key.name === "return") {
    if (testStatus === "success") {
      currentStep = "agent";
      testStatus = "idle";
    } else {
      currentStep = "moltbook";
    }
    app.requestRender();
  } else if (key.name === "s") {
    currentStep = "agent";
    testStatus = "idle";
    app.requestRender();
  }
}

function handleAgentKey(key: KeyEvent) {
  if (key.name === "up" || key.name === "down" || key.name === "k" || key.name === "j") {
    agentChoice = agentChoice === "register" ? "existing" : "register";
    app.requestRender();
  } else if (key.name === "return") {
    if (agentChoice === "existing" && !existingAgentId.trim()) {
      app.flash("Enter an agent ID!");
      return;
    }
    if (agentChoice === "existing") {
      config.moltbookAgentId = existingAgentId.trim();
      saveConfig(config);
    }
    currentStep = "persona";
    app.requestRender();
  } else if (key.name === "escape") {
    currentStep = "moltbook";
    app.requestRender();
  } else if (agentChoice === "existing") {
    if (key.name === "backspace") {
      existingAgentId = existingAgentId.slice(0, -1);
      app.requestRender();
    } else if (!key.ctrl && key.name.length === 1) {
      existingAgentId += key.name;
      app.requestRender();
    }
  }
}

function handlePersonaKey(key: KeyEvent) {
  const field = personaFields[personaFocus]!;
  if (key.name === "tab" && !key.shift || key.name === "down") {
    personaFocus = Math.min(personaFields.length - 1, personaFocus + 1);
    app.requestRender();
  } else if (key.name === "tab" && key.shift || key.name === "up") {
    personaFocus = Math.max(0, personaFocus - 1);
    app.requestRender();
  } else if (key.name === "backspace") {
    field.value = field.value.slice(0, -1);
    app.requestRender();
  } else if (key.name === "return") {
    const name = personaFields.find((f) => f.key === "name")!.value.trim();
    const tone = personaFields.find((f) => f.key === "tone")!.value.trim();
    if (!name) { app.flash("Name is required!"); return; }
    if (!tone) { app.flash("Tone is required!"); return; }

    const topics = personaFields.find((f) => f.key === "topics")!.value.split(",").map((s) => s.trim()).filter(Boolean);
    const styleTxt = personaFields.find((f) => f.key === "style")!.value.trim();
    const bio = personaFields.find((f) => f.key === "bio")!.value.trim();
    const constraints = personaFields.find((f) => f.key === "constraints")!.value.trim();
    const submolts = personaFields.find((f) => f.key === "submolts")!.value.split(",").map((s) => s.trim()).filter(Boolean);

    const agent = createAgent({
      name, tone, topics, style: styleTxt || "default", bio, constraints, submolts,
      moltbookAgentId: config.moltbookAgentId || "",
    });

    if (agentChoice === "register" && config.moltbookApiKey) {
      registerNewAgent(agent.name, bio).catch(() => {});
    }

    currentStep = "done";
    app.requestRender();
  } else if (key.name === "escape") {
    currentStep = "agent";
    app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    field.value += key.name;
    app.requestRender();
  }
}

async function registerNewAgent(name: string, description: string) {
  try {
    const client = new MoltbookClient(config.moltbookApiKey);
    const result = await client.registerAgent(name, description || name);
    config.moltbookAgentId = result.id;
    saveConfig(config);
    app.flash(`Agent registered on Moltbook! ID: ${result.id}`);
    app.requestRender();
  } catch (err: any) {
    app.flash(`Registration failed: ${err.message?.slice(0, 50)}`);
  }
}

function handleDoneKey(key: KeyEvent) {
  if (key.name === "return" || key.name === "escape") {
    app.navigate("dashboard");
  }
}

// ── Check if onboarding is needed ──

export function needsOnboarding(): boolean {
  const c = loadConfig();
  return !c.zaiApiKey && !c.moltbookApiKey;
}

// ── Screen export ──

export const onboardingScreen: Screen = {
  name: "onboarding",
  statusHint: "follow the steps to set up Molt.tui",

  onEnter() {
    currentStep = "welcome";
    config = loadConfig();
    testStatus = "idle";
    testMessage = "";
    zaiFocus = 0;
    moltFocus = 0;
    personaFocus = 0;
    zaiFields[0]!.value = config.zaiApiKey || "";
    zaiFields[1]!.value = config.zaiModel || "glm-4.7";
    moltbookFields[0]!.value = config.moltbookApiKey || "";
    existingAgentId = config.moltbookAgentId || "";
  },

  render() {
    drawStepIndicator(3, 3);

    switch (currentStep) {
      case "welcome": renderWelcome(); break;
      case "zai": renderZai(); break;
      case "zai-test": renderZaiTest(); break;
      case "moltbook": renderMoltbook(); break;
      case "moltbook-test": renderMoltbookTest(); break;
      case "agent": renderAgent(); break;
      case "persona": renderPersona(); break;
      case "done": renderDone(); break;
    }
  },

  onKey(key: KeyEvent) {
    switch (currentStep) {
      case "welcome": handleWelcomeKey(key); break;
      case "zai": handleZaiKey(key); break;
      case "zai-test": handleZaiTestKey(key); break;
      case "moltbook": handleMoltbookKey(key); break;
      case "moltbook-test": handleMoltbookTestKey(key); break;
      case "agent": handleAgentKey(key); break;
      case "persona": handlePersonaKey(key); break;
      case "done": handleDoneKey(key); break;
    }
  },
};
