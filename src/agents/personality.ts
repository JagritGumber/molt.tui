// Agent personality management - CRUD for agent profiles stored as JSON

import { existsSync, readFileSync, writeFileSync, readdirSync, unlinkSync } from "fs";
import { join } from "path";
import { getAgentsDir, ensureDirs } from "../utils/config.ts";

export interface AgentPersonality {
  id: string;
  name: string;
  tone: string;
  topics: string[];
  style: string;
  bio: string;
  constraints: string;
  submolts: string[];
  moltbookAgentId: string;
  createdAt: string;
  updatedAt: string;
}

function agentPath(id: string): string {
  return join(getAgentsDir(), `${id}.json`);
}

function generateId(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-" + Date.now().toString(36);
}

export function listAgents(): AgentPersonality[] {
  ensureDirs();
  const dir = getAgentsDir();
  const files = readdirSync(dir).filter((f) => f.endsWith(".json"));
  return files
    .map((f) => {
      try {
        return JSON.parse(readFileSync(join(dir, f), "utf-8")) as AgentPersonality;
      } catch {
        return null;
      }
    })
    .filter(Boolean) as AgentPersonality[];
}

export function getAgent(id: string): AgentPersonality | null {
  const p = agentPath(id);
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf-8")) as AgentPersonality;
  } catch {
    return null;
  }
}

export function createAgent(data: Omit<AgentPersonality, "id" | "createdAt" | "updatedAt">): AgentPersonality {
  ensureDirs();
  const now = new Date().toISOString();
  const agent: AgentPersonality = {
    ...data,
    id: generateId(data.name),
    createdAt: now,
    updatedAt: now,
  };
  writeFileSync(agentPath(agent.id), JSON.stringify(agent, null, 2));
  return agent;
}

export function updateAgent(id: string, data: Partial<AgentPersonality>): AgentPersonality | null {
  const agent = getAgent(id);
  if (!agent) return null;
  const updated = { ...agent, ...data, id, updatedAt: new Date().toISOString() };
  writeFileSync(agentPath(id), JSON.stringify(updated, null, 2));
  return updated;
}

export function deleteAgent(id: string): boolean {
  const p = agentPath(id);
  if (!existsSync(p)) return false;
  unlinkSync(p);
  return true;
}
