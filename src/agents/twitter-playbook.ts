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
      template: "[Big specific number]\n\n[Context that makes it meaningful]\n\n[Your take]",
      example: "$1,000,000,000,000\n\nThat's not the only value this article has\n\nthere is a whole dimension of knowledge here",
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
      name: "quote-react",
      template: "[Strong 1-line reaction to someone else's take]",
      example: "We're so back!!! 😭",
      avgEngagement: 6,
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

// Pick a random pattern weighted by engagement score
export function pickPattern(playbook: Playbook, topics?: string[]): TweetPattern {
  let candidates = playbook.patterns;
  if (topics?.length) {
    const topicMatches = candidates.filter(p =>
      p.bestFor.some(b => topics.some(t => b.includes(t.toLowerCase())))
    );
    if (topicMatches.length > 0) candidates = topicMatches;
  }
  // Weighted random by engagement score
  const totalWeight = candidates.reduce((s, p) => s + p.avgEngagement, 0);
  let r = Math.random() * totalWeight;
  for (const p of candidates) {
    r -= p.avgEngagement;
    if (r <= 0) return p;
  }
  return candidates[candidates.length - 1]!;
}

// Build the system prompt for tweet generation using the playbook
export function buildTweetPrompt(playbook: Playbook, userStyle: string): string {
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

Write the tweet ONLY. No quotes, no meta-commentary. Max 280 chars.
Sound like a real person sharing genuine thoughts, not a content machine.`;
}
