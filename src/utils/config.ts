import { homedir } from "os";
import { join } from "path";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";

export interface Config {
  zaiApiKey: string;
  zaiModel: string;
  moltbookApiKey: string;
  moltbookAgentId: string;
  dataDir: string;
}

const CONFIG_DIR = join(homedir(), ".moltui");
const CONFIG_FILE = join(CONFIG_DIR, "config.json");
const AGENTS_DIR = join(CONFIG_DIR, "agents");

export function ensureDirs() {
  for (const dir of [CONFIG_DIR, AGENTS_DIR]) {
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  }
}

export function getConfigDir() {
  return CONFIG_DIR;
}

export function getAgentsDir() {
  return AGENTS_DIR;
}

export function loadConfig(): Config {
  ensureDirs();
  if (!existsSync(CONFIG_FILE)) {
    const defaults: Config = {
      zaiApiKey: "",
      zaiModel: "glm-4.7-flashx",
      moltbookApiKey: "",
      moltbookAgentId: "",
      dataDir: CONFIG_DIR,
    };
    writeFileSync(CONFIG_FILE, JSON.stringify(defaults, null, 2));
    return defaults;
  }
  return JSON.parse(readFileSync(CONFIG_FILE, "utf-8"));
}

export function saveConfig(config: Config) {
  ensureDirs();
  writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
}
