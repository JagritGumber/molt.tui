// Twitter Playbook — patterns extracted from top creators via RL analysis
// Used by tweet generator to produce high-engagement content
// Sources: @mattpocockuk, @theo, @levelsio, @rauchg, @swyx, @tibo_maker

import { existsSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { getConfigDir, ensureDirs } from "../utils/config.ts";

export interface TweetPattern {
  name: string;
  template: string;
  example: string;
  avgEngagement: number; // relative score 1-10
  bestFor: string[];     // topics this pattern works for
}

export interface CreatorStyle {
  handle: string;
  avgLength: number;
  useEmoji: boolean;
  toneWords: string[];    // adjectives describing their voice
  hookStyle: string;
  signature: string;      // what makes them unique
}

export interface Playbook {
  patterns: TweetPattern[];
  styles: CreatorStyle[];
  rules: string[];         // hard rules from algorithm research
  avoid: string[];         // things that kill engagement
  updatedAt: string;
}

const PLAYBOOK_FILE = join(getConfigDir(), "twitter-playbook.json");

// Default playbook from research — will be refined by RL
const DEFAULT_PLAYBOOK: Playbook = {
  patterns: [
    {
      name: "bold-claim",
      template: "[Bold controversial statement about tech]\n\n[1-2 lines of reasoning]",
      example: "TypeScript strict mode should be the default. The fact that it isn't is why 90% of TS codebases have silent bugs.",
      avgEngagement: 9,
      bestFor: ["opinions", "tech", "hot-takes"],
    },
    {
      name: "short-aphorism",
      template: "[One powerful sentence under 60 chars]",
      example: "Code is an output. Taste is the input.",
      avgEngagement: 10,
      bestFor: ["philosophy", "leadership", "inspiration"],
    },
    {
      name: "build-in-public",
      template: "[What you built/did]\n\n[Specific numbers/results]\n\n[Casual reflection]",
      example: "just shipped a postgres extension that cuts memory 10x\n\nforgot sleeping\n\nbut it works",
      avgEngagement: 8,
      bestFor: ["projects", "progress", "results"],
    },
    {
      name: "contrarian",
      template: "You don't need [popular thing].\n\n[Why, with personal experience]",
      example: "You don't need microservices.\n\nA single PostgreSQL can handle 800M users. ChatGPT proved it.",
      avgEngagement: 9,
      bestFor: ["opinions", "architecture", "tools"],
    },
    {
      name: "discovery",
      template: "[Thing you found/realized]\n\n[Why it matters in 1-2 lines]",
      example: "just realized most \"AI agents\" are just while loops with an LLM call\n\nthe ones that work are the ones that know when to stop",
      avgEngagement: 7,
      bestFor: ["learning", "insights", "AI"],
    },
    {
      name: "numbers-hook",
      template: "[Specific number from YOUR real experience]\n\n[Why it matters]",
      example: "10x less memory usage on a single postgres extension\n\nno fancy infra. just understanding how the internals work.",
      avgEngagement: 8,
      bestFor: ["data", "business", "scale"],
    },
    {
      name: "frustration-share",
      template: "[Relatable frustration]\n\n[What you did about it]",
      example: "got bored with switching terminal tabs and how slow pwsh is\n\nso I created my zellij setup with alacritty",
      avgEngagement: 7,
      bestFor: ["tools", "developer-life", "building"],
    },
    {
      name: "hot-take-react",
      template: "[Your OWN strong opinion triggered by a trending topic — never copy/quote the source]",
      example: "every \"AI agent framework\" is just a for loop with a prompt. the actual hard part is knowing when to stop.",
      avgEngagement: 7,
      bestFor: ["reactions", "community", "trending"],
    },
  ],
  styles: [
    { handle: "theo", avgLength: 103, useEmoji: false, toneWords: ["punchy", "provocative", "declarative"], hookStyle: "short contrarian take", signature: "shortest tweets, highest engagement per char" },
    { handle: "rauchg", avgLength: 327, useEmoji: false, toneWords: ["grand", "philosophical", "authoritative"], hookStyle: "aphorisms and declarations", signature: "CEO-voice, sub-60-char aphorisms crush it" },
    { handle: "levelsio", avgLength: 266, useEmoji: false, toneWords: ["casual", "story-telling", "stream-of-consciousness"], hookStyle: "conversational opener mid-story", signature: "90% quote tweets with riffs, long single tweets" },
    { handle: "mattpocockuk", avgLength: 216, useEmoji: false, toneWords: ["educational", "conversational", "authoritative"], hookStyle: "personal experience lead", signature: "dash-list bullet points, process > promotion" },
    { handle: "swyx", avgLength: 200, useEmoji: false, toneWords: ["lowercase", "insider", "analytical"], hookStyle: "casual lowercase, curator voice", signature: "all lowercase, quotes industry news with context" },
    { handle: "tibo_maker", avgLength: 268, useEmoji: true, toneWords: ["energetic", "formatted", "CTA-heavy"], hookStyle: "pattern hooks: 'unpopular take:', 'in just X days'", signature: "heavy formatting, highest reply counts, engagement farming" },
  ],
  rules: [
    "Keep tweets 71-100 chars for highest engagement, max 280",
    "First line IS the hook — on mobile only 1-2 lines show before 'Show more'",
    "No external links — algorithm kills them (zero median engagement for non-Premium)",
    "No hashtags (3+ reduces engagement by 17%)",
    "One idea per line, line breaks between sentences",
    "Post between 9-11 AM local time on weekdays (Tuesday best)",
    "First 30 minutes determine algorithmic trajectory — engage with replies immediately",
    "Reply-to-reply is 75x a like in algorithm weight",
    "Images get 150% more retweets than text-only",
    "Negative/combative tone gets suppressed by Grok sentiment filter",
    "Be opinionated but constructive — strong takes with reasoning outperform generic advice",
    "Numbers and specific data points increase credibility and engagement",
  ],
  avoid: [
    "External links (algorithm depression)",
    "3+ hashtags (spammy, engagement drops)",
    "Wall of text without line breaks",
    "Generic hooks ('A thread about...')",
    "Only wins, no vulnerability",
    "Excessive emojis for tech audience",
    "Pitching products in replies",
    "Corporate/brand voice",
    "Vague claims without specifics",
    "Starting with 'I think' (boring hook, be declarative)",
  ],
  updatedAt: new Date().toISOString(),
};

export function loadPlaybook(): Playbook {
  ensureDirs();
  if (existsSync(PLAYBOOK_FILE)) {
    try {
      return JSON.parse(readFileSync(PLAYBOOK_FILE, "utf-8")) as Playbook;
    } catch { /* corrupt — use default */ }
  }
  savePlaybook(DEFAULT_PLAYBOOK);
  return DEFAULT_PLAYBOOK;
}

export function savePlaybook(playbook: Playbook) {
  ensureDirs();
  playbook.updatedAt = new Date().toISOString();
  writeFileSync(PLAYBOOK_FILE, JSON.stringify(playbook, null, 2));
}

// Simple weighted random fallback (no LLM)
export function pickPatternRandom(playbook: Playbook): TweetPattern {
  const totalWeight = playbook.patterns.reduce((s, p) => s + p.avgEngagement, 0);
  let r = Math.random() * totalWeight;
  for (const p of playbook.patterns) {
    r -= p.avgEngagement;
    if (r <= 0) return p;
  }
  return playbook.patterns[playbook.patterns.length - 1]!;
}

// Build a prompt for the LLM to analyze topics and pick the best pattern
export function buildPatternPickerPrompt(playbook: Playbook, trendingContent: string): string {
  const patternList = playbook.patterns.map(p =>
    `- ${p.name}: "${p.template}" (best for: ${p.bestFor.join(", ")})`
  ).join("\n");

  return `You are a content strategist. Analyze the trending topics below and pick the BEST tweet pattern for the user.

AVAILABLE PATTERNS:
${patternList}

TRENDING CONTENT:
${trendingContent}

TASK:
1. Which topic has the most VALUE for a developer audience? (not just engagement — actual insight depth)
2. Which pattern best fits that topic? (e.g. a deep insight needs "discovery", a strong opinion needs "contrarian", a project update needs "build-in-public")
3. What angle should the tweet take?

Respond in EXACTLY this format (3 lines, nothing else):
PATTERN: [pattern name]
TOPIC: [the topic to tweet about, in 5-10 words]
ANGLE: [the specific angle/take in one sentence]`;
}

// Build the system prompt for tweet generation using the playbook
// Strip AI-generated signatures that detection tools (Pangram, GPTZero) flag
export function sanitizeTweet(text: string): string {
  return text
    .replace(/—/g, "-")           // em dash → regular dash
    .replace(/–/g, "-")           // en dash → regular dash
    .replace(/"/g, '"')           // smart quotes → straight
    .replace(/"/g, '"')
    .replace(/'/g, "'")
    .replace(/'/g, "'")
    .replace(/…/g, "...")         // ellipsis char → three dots
    .replace(/\|/g, "")           // pipe chars (AI signature)
    .replace(/^\s*["']+|["']+\s*$/g, "") // strip wrapping quotes
    .replace(/\n{3,}/g, "\n\n")  // collapse triple+ newlines
    .trim()
    .slice(0, 280);
}

export function buildTweetPrompt(playbook: Playbook, userStyle: string, learnings?: string): string {
  const rules = playbook.rules.map(r => `- ${r}`).join("\n");
  const avoid = playbook.avoid.map(a => `- ${a}`).join("\n");
  const styleExamples = playbook.styles
    .filter(s => ["theo", "levelsio", "rauchg"].includes(s.handle))
    .map(s => `${s.handle}: ${s.hookStyle}, ${s.toneWords.join(", ")}, ~${s.avgLength} chars`)
    .join("\n");

  return `You write tweets for a developer on X/Twitter.

USER'S VOICE:
${userStyle}

WINNING PATTERNS (from top creators):
${styleExamples}

ALGORITHM RULES:
${rules}

AVOID:
${avoid}

CRITICAL — AI DETECTION AVOIDANCE:
- NEVER use em dash (—), use regular dash (-) or nothing
- NEVER use "Here's why:", "Here's the thing:", "Let me explain"
- NEVER use "In today's world", "It's worth noting", "At the end of the day"
- NEVER use semicolons in tweets
- NEVER start with "I think" or "I believe"
- Use contractions (don't, can't, won't) not formal forms
- Use sentence fragments, not complete sentences
- Typos and informal grammar are OK — makes it human
- Write like texting, not like writing an essay

Write the tweet ONLY. No quotes, no meta-commentary. Max 280 chars.${learnings || ""}`;
}
