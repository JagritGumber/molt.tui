// Onboarding wizard - first-run setup for Z.ai, Moltbook, and agent persona

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawTextInput, drawHR, drawBox, getSpinnerFrame } from "../tui/components.ts";
import { loadConfig, saveConfig, type Config } from "../utils/config.ts";
import { createAgent } from "../agents/personality.ts";
import { ZaiClient } from "../clients/zai.ts";
import { registerOnMoltbook, MoltbookClient } from "../clients/moltbook.ts";
import type { KeyEvent } from "../tui/input.ts";

type Step = "welcome" | "zai" | "zai-test" | "moltbook" | "moltbook-test" | "persona" | "done";

let currentStep: Step = "welcome";
let config: Config = loadConfig();

// ── Z.ai fields ──
let zaiFields = [
  { key: "apiKey", label: "API Key", value: "", secret: true },
  { key: "model", label: "Model", value: "GLM-4.7-FlashX", secret: false },
];
let zaiFocus = 0;

// ── Moltbook fields ──
let moltChoice: "register" | "existing" = "register";
let moltRegFields = [
  { key: "name", label: "Username", value: "" },
  { key: "bio", label: "Bio (optional)", value: "" },
];
let moltExistingKey = "";
let moltRegFocus = 0;
let moltClaimUrl = "";

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
let testMessageLine2 = "";

function displaySecret(val: string): string {
  if (!val) return "";
  return val.slice(0, 8) + "•".repeat(Math.max(0, val.length - 8));
}

function drawStepIndicator(row: number, col: number) {
  const steps = ["Welcome", "Z.ai", "Moltbook", "Persona", "Done"];
  const stepMap: Record<Step, number> = {
    welcome: 0, zai: 1, "zai-test": 1, moltbook: 2, "moltbook-test": 2, persona: 3, done: 4,
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

// ── Render functions ──

function renderWelcome() {
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
  write(`${fg.yellow}2.${style.reset} ${fg.white}A Moltbook account${style.reset} ${fg.gray}(register or use existing key)${style.reset}`);
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

  // Choice tabs
  cursor.to(9, 5);
  const regActive = moltChoice === "register";
  write(
    (regActive ? `${fg.brightCyan}${style.bold}[Register New]${style.reset}` : `${fg.gray}[Register New]${style.reset}`) +
    "  " +
    (!regActive ? `${fg.brightCyan}${style.bold}[Existing Key]${style.reset}` : `${fg.gray}[Existing Key]${style.reset}`) +
    `${fg.gray}  ← Tab to switch${style.reset}`
  );

  if (moltChoice === "register") {
    cursor.to(11, 5);
    write(`${fg.gray}Pick a unique lowercase username for your agent.${style.reset}`);
    drawTextInput(13, 3, w, moltRegFields[0]!.value, moltRegFields[0]!.label, moltRegFocus === 0);
    drawTextInput(15, 3, w, moltRegFields[1]!.value, moltRegFields[1]!.label, moltRegFocus === 1);
    cursor.to(18, 3);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to register • ${fg.brightCyan}Esc${fg.gray} to go back${style.reset}`);
  } else {
    cursor.to(11, 5);
    write(`${fg.gray}Paste your existing Moltbook API key (starts with moltbook_).${style.reset}`);
    drawTextInput(13, 3, w, displaySecret(moltExistingKey), "API Key", true);
    cursor.to(16, 3);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to verify • ${fg.brightCyan}Esc${fg.gray} to go back${style.reset}`);
  }
}

function renderMoltbookTest() {
  const { cols } = getTermSize();
  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 2: Moltbook Connection${style.reset}`);
  drawHR(6, 3, Math.min(65, cols - 6));

  cursor.to(8, 5);
  if (testStatus === "testing") {
    write(`${getSpinnerFrame()} ${fg.white}${moltChoice === "register" ? "Registering on Moltbook..." : "Verifying Moltbook key..."}${style.reset}`);
  } else if (testStatus === "success") {
    write(`${fg.brightGreen}✓ ${fg.white}${testMessage}${style.reset}`);
    if (testMessageLine2) {
      cursor.to(9, 5);
      write(`${fg.gray}${testMessageLine2}${style.reset}`);
    }
    if (moltClaimUrl) {
      cursor.to(10, 5);
      write(`${fg.yellow}Claim URL:${style.reset}`);
      cursor.to(11, 5);
      write(`${fg.white}${moltClaimUrl}${style.reset}`);
      cursor.to(13, 5);
      write(`${fg.gray}Send this to your human to verify ownership!${style.reset}`);
      cursor.to(15, 5);
    } else {
      cursor.to(11, 5);
    }
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to continue${style.reset}`);
  } else if (testStatus === "error") {
    write(`${fg.brightRed}✗ ${fg.white}${testMessage}${style.reset}`);
    cursor.to(10, 5);
    write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to retry • ${fg.brightCyan}s${fg.gray} to skip${style.reset}`);
  }
}

function renderPersona() {
  const { cols } = getTermSize();
  const w = Math.min(65, cols - 6);

  cursor.to(5, 3);
  write(`${fg.brightCyan}${style.bold}Step 3: Agent Persona${style.reset}`);
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

  if (moltClaimUrl) {
    cursor.to(12, 5);
    write(`${fg.yellow}⚠ Don't forget: send the claim URL to your human!${style.reset}`);
    cursor.to(13, 5);
    write(`${fg.gray}${moltClaimUrl}${style.reset}`);
    cursor.to(15, 5);
  } else {
    cursor.to(12, 5);
  }
  write(`${fg.gray}Press ${fg.brightCyan}Enter${fg.gray} to go to the dashboard${style.reset}`);
}

// ── Connection helpers ──

async function testZai() {
  testStatus = "testing";
  testMessage = "";
  app.requestRender();

  try {
    const client = new ZaiClient(zaiFields[0]!.value, zaiFields[1]!.value);
    const reply = await client.chatCompletion(
      [{ role: "user", content: "Hello! Respond with a short greeting to confirm this connection works." }],
      { maxTokens: 50 }
    );
    testStatus = "success";
    testMessage = `Model: ${zaiFields[1]!.value} — "${reply.slice(0, 40)}"`;

    config.zaiApiKey = zaiFields[0]!.value;
    config.zaiModel = zaiFields[1]!.value;
    saveConfig(config);
  } catch (err: any) {
    testStatus = "error";
    testMessage = err.message?.slice(0, 80) || "Unknown error";
  }
  app.requestRender();
}

async function doMoltbookRegister() {
  testStatus = "testing";
  testMessage = "";
  testMessageLine2 = "";
  moltClaimUrl = "";
  app.requestRender();

  try {
    const name = moltRegFields[0]!.value.trim().toLowerCase();
    const bio = moltRegFields[1]!.value.trim();
    const result = await registerOnMoltbook(name, bio || undefined);

    const apiKey = result.agent.api_key;
    const claimUrl = result.agent.claim_url;

    if (!apiKey) throw new Error("No API key returned — check username");

    config.moltbookApiKey = apiKey;
    config.moltbookAgentId = name;
    saveConfig(config);

    testStatus = "success";
    testMessage = `Registered as "${name}" on Moltbook!`;
    testMessageLine2 = `API key: ${apiKey.slice(0, 12)}... (saved)`;
    moltClaimUrl = claimUrl || "";
  } catch (err: any) {
    testStatus = "error";
    testMessage = err.message?.slice(0, 120) || "Registration failed";
  }
  app.requestRender();
}

async function doMoltbookVerify() {
  testStatus = "testing";
  testMessage = "";
  testMessageLine2 = "";
  moltClaimUrl = "";
  app.requestRender();

  try {
    const client = new MoltbookClient(moltExistingKey);
    const result = await client.getStatus();

    config.moltbookApiKey = moltExistingKey;
    saveConfig(config);

    // Try to get agent name
    try {
      const me = await client.getMe();
      config.moltbookAgentId = me.agent?.name || "";
      saveConfig(config);
    } catch {}

    testStatus = "success";
    testMessage = `Connected! Status: ${result.status}`;
  } catch (err: any) {
    testStatus = "error";
    testMessage = err.message?.slice(0, 80) || "Verification failed";
  }
  app.requestRender();
}

// ── Key handlers ──

function handleWelcomeKey(key: KeyEvent) {
  if (key.name === "return") { currentStep = "zai"; app.requestRender(); }
  else if (key.name === "escape") { app.navigate("dashboard"); }
}

function handleZaiKey(key: KeyEvent) {
  const field = zaiFields[zaiFocus]!;
  if (key.name === "tab" && !key.shift || key.name === "down") {
    zaiFocus = Math.min(zaiFields.length - 1, zaiFocus + 1); app.requestRender();
  } else if (key.name === "tab" && key.shift || key.name === "up") {
    zaiFocus = Math.max(0, zaiFocus - 1); app.requestRender();
  } else if (key.name === "backspace") {
    field.value = field.value.slice(0, -1); app.requestRender();
  } else if (key.name === "return") {
    if (!zaiFields[0]!.value.trim()) { app.flash("API key is required!"); return; }
    currentStep = "zai-test"; testStatus = "idle"; app.requestRender(); testZai();
  } else if (key.name === "escape") {
    currentStep = "welcome"; app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    field.value += key.name; app.requestRender();
  }
}

function handleZaiTestKey(key: KeyEvent) {
  if (testStatus === "testing") return;
  if (key.name === "return") {
    if (testStatus === "success") { currentStep = "moltbook"; testStatus = "idle"; }
    else { currentStep = "zai"; }
    app.requestRender();
  } else if (key.name === "s") {
    currentStep = "moltbook"; testStatus = "idle"; app.requestRender();
  }
}

function handleMoltbookKey(key: KeyEvent) {
  if (key.name === "tab" && moltChoice === "register" && !key.shift) {
    // Tab within register fields, or switch mode if at end
    if (moltRegFocus < moltRegFields.length - 1) {
      moltRegFocus++; app.requestRender();
    } else {
      moltChoice = "existing"; app.requestRender();
    }
  } else if (key.name === "tab" && moltChoice === "existing") {
    moltChoice = "register"; moltRegFocus = 0; app.requestRender();
  } else if (key.name === "tab" && key.shift && moltChoice === "register") {
    if (moltRegFocus > 0) { moltRegFocus--; app.requestRender(); }
  } else if (key.name === "up" && moltChoice === "register") {
    moltRegFocus = Math.max(0, moltRegFocus - 1); app.requestRender();
  } else if (key.name === "down" && moltChoice === "register") {
    moltRegFocus = Math.min(moltRegFields.length - 1, moltRegFocus + 1); app.requestRender();
  } else if (key.name === "backspace") {
    if (moltChoice === "register") {
      moltRegFields[moltRegFocus]!.value = moltRegFields[moltRegFocus]!.value.slice(0, -1);
    } else {
      moltExistingKey = moltExistingKey.slice(0, -1);
    }
    app.requestRender();
  } else if (key.name === "return") {
    if (moltChoice === "register") {
      if (!moltRegFields[0]!.value.trim()) { app.flash("Username is required!"); return; }
      currentStep = "moltbook-test"; testStatus = "idle"; app.requestRender(); doMoltbookRegister();
    } else {
      if (!moltExistingKey.trim()) { app.flash("API key is required!"); return; }
      currentStep = "moltbook-test"; testStatus = "idle"; app.requestRender(); doMoltbookVerify();
    }
  } else if (key.name === "escape") {
    currentStep = "zai"; app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    if (moltChoice === "register") {
      moltRegFields[moltRegFocus]!.value += key.name;
    } else {
      moltExistingKey += key.name;
    }
    app.requestRender();
  }
}

function handleMoltbookTestKey(key: KeyEvent) {
  if (testStatus === "testing") return;
  if (key.name === "return") {
    if (testStatus === "success") { currentStep = "persona"; testStatus = "idle"; }
    else { currentStep = "moltbook"; }
    app.requestRender();
  } else if (key.name === "s") {
    currentStep = "persona"; testStatus = "idle"; app.requestRender();
  }
}

function handlePersonaKey(key: KeyEvent) {
  const field = personaFields[personaFocus]!;
  if (key.name === "tab" && !key.shift || key.name === "down") {
    personaFocus = Math.min(personaFields.length - 1, personaFocus + 1); app.requestRender();
  } else if (key.name === "tab" && key.shift || key.name === "up") {
    personaFocus = Math.max(0, personaFocus - 1); app.requestRender();
  } else if (key.name === "backspace") {
    field.value = field.value.slice(0, -1); app.requestRender();
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

    createAgent({
      name, tone, topics, style: styleTxt || "default", bio, constraints, submolts,
      moltbookAgentId: config.moltbookAgentId || "",
    });

    currentStep = "done";
    app.requestRender();
  } else if (key.name === "escape") {
    currentStep = "moltbook"; app.requestRender();
  } else if (!key.ctrl && key.name.length === 1) {
    field.value += key.name; app.requestRender();
  }
}

function handleDoneKey(key: KeyEvent) {
  if (key.name === "return" || key.name === "escape") { app.navigate("dashboard"); }
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
  handlesTextInput: true,

  onEnter() {
    currentStep = "welcome";
    config = loadConfig();
    testStatus = "idle";
    testMessage = "";
    testMessageLine2 = "";
    moltClaimUrl = "";
    zaiFocus = 0;
    moltRegFocus = 0;
    personaFocus = 0;
    zaiFields[0]!.value = config.zaiApiKey || "";
    zaiFields[1]!.value = config.zaiModel || "GLM-4.7-FlashX";
    moltExistingKey = config.moltbookApiKey || "";
  },

  render() {
    drawStepIndicator(3, 3);
    switch (currentStep) {
      case "welcome": renderWelcome(); break;
      case "zai": renderZai(); break;
      case "zai-test": renderZaiTest(); break;
      case "moltbook": renderMoltbook(); break;
      case "moltbook-test": renderMoltbookTest(); break;
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
      case "persona": handlePersonaKey(key); break;
      case "done": handleDoneKey(key); break;
    }
  },
};
