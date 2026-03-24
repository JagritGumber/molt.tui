// Twitter RL (Reinforcement Learning) Pipeline
// Tracks tweet performance and adjusts pattern weights over time
//
// Flow: post → track ID + pattern → wait 24h → fetch metrics → update weight
// Patterns that get engagement go UP, patterns that flop go DOWN
// This compounds: over weeks the system learns what actually works for YOUR audience

import { existsSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { getConfigDir, ensureDirs } from "../utils/config.ts";
import { loadPlaybook, savePlaybook, type Playbook } from "./twitter-playbook.ts";

// A tracked tweet — maps a tweet to the pattern that generated it
export interface TrackedTweet {
  tweetId: string;         // X tweet ID (from bird CLI output)
  pattern: string;         // pattern name used to generate it
  content: string;         // the tweet text
  postedAt: number;        // epoch ms
  measured: boolean;       // has engagement been fetched?
  likes: number;
  retweets: number;
  replies: number;
  impressions: number;     // if available
  score: number;           // computed engagement score
}

const RL_FILE = join(getConfigDir(), "twitter-rl.json");
const MEASURE_AFTER_MS = 24 * 60 * 60 * 1000; // 24 hours — engagement stabilizes
const WEIGHT_DECAY = 0.95; // smoothing — don't overreact to single data points
const WEIGHT_BOOST = 0.3;  // how much a win boosts the pattern
const WEIGHT_PENALTY = 0.15; // how much a flop penalizes

// ── Persistence ──

export function loadTracked(): TrackedTweet[] {
  ensureDirs();
  if (existsSync(RL_FILE)) {
    try { return JSON.parse(readFileSync(RL_FILE, "utf-8")) as TrackedTweet[]; }
    catch { /* corrupt */ }
  }
  return [];
}

function saveTracked(tweets: TrackedTweet[]) {
  // Keep last 100 tracked tweets
  if (tweets.length > 100) tweets = tweets.slice(-100);
  try { writeFileSync(RL_FILE, JSON.stringify(tweets, null, 2)); } catch { /* non-fatal */ }
}

// ── Track a new tweet ──

export function trackTweet(tweetId: string, pattern: string, content: string) {
  const tweets = loadTracked();
  tweets.push({
    tweetId,
    pattern,
    content,
    postedAt: Date.now(),
    measured: false,
    likes: 0, retweets: 0, replies: 0, impressions: 0, score: 0,
  });
  saveTracked(tweets);
}

// ── Measure engagement for tweets older than 24h ──

export function getTweetsToMeasure(): TrackedTweet[] {
  const tweets = loadTracked();
  const cutoff = Date.now() - MEASURE_AFTER_MS;
  return tweets.filter(t => !t.measured && t.postedAt < cutoff);
}

// Update a tweet's metrics after fetching from bird CLI
export function recordMetrics(tweetId: string, likes: number, retweets: number, replies: number, impressions = 0) {
  const tweets = loadTracked();
  const tweet = tweets.find(t => t.tweetId === tweetId);
  if (!tweet) return;

  tweet.likes = likes;
  tweet.retweets = retweets;
  tweet.replies = replies;
  tweet.impressions = impressions;
  // Score: replies worth most (75x in algo), retweets > likes
  tweet.score = (replies * 5) + (retweets * 3) + likes;
  tweet.measured = true;
  saveTracked(tweets);
}

// ── Update pattern weights based on measured tweets ──

export function updatePatternWeights(): { updated: number; changes: string[] } {
  const tweets = loadTracked();
  const measured = tweets.filter(t => t.measured);
  if (measured.length < 3) return { updated: 0, changes: [] }; // need baseline

  // Compute average score across all measured tweets
  const avgScore = measured.reduce((s, t) => s + t.score, 0) / measured.length;
  if (avgScore === 0) return { updated: 0, changes: [] };

  // Group by pattern
  const byPattern = new Map<string, TrackedTweet[]>();
  for (const t of measured) {
    const arr = byPattern.get(t.pattern) || [];
    arr.push(t);
    byPattern.set(t.pattern, arr);
  }

  const playbook = loadPlaybook();
  const changes: string[] = [];
  let updated = 0;

  for (const [patternName, patternTweets] of byPattern) {
    const pattern = playbook.patterns.find(p => p.name === patternName);
    if (!pattern) continue;

    const patternAvg = patternTweets.reduce((s, t) => s + t.score, 0) / patternTweets.length;
    const ratio = patternAvg / avgScore; // >1 = above average, <1 = below

    const oldWeight = pattern.avgEngagement;

    if (ratio > 1.3) {
      // Winner — boost weight (with decay to prevent runaway)
      pattern.avgEngagement = Math.min(10, oldWeight * WEIGHT_DECAY + WEIGHT_BOOST * ratio);
      changes.push(`${patternName}: ${oldWeight.toFixed(1)} → ${pattern.avgEngagement.toFixed(1)} (winner, ${ratio.toFixed(1)}x avg)`);
    } else if (ratio < 0.5) {
      // Flop — reduce weight (floor at 1 so pattern never dies completely)
      pattern.avgEngagement = Math.max(1, oldWeight * WEIGHT_DECAY - WEIGHT_PENALTY);
      changes.push(`${patternName}: ${oldWeight.toFixed(1)} → ${pattern.avgEngagement.toFixed(1)} (underperformed, ${ratio.toFixed(1)}x avg)`);
    }
    // Between 0.5-1.3x = average, no change

    if (pattern.avgEngagement !== oldWeight) updated++;
  }

  if (updated > 0) savePlaybook(playbook);
  return { updated, changes };
}

// ── Parse tweet ID from bird CLI output ──
// bird tweet output looks like: "url: https://x.com/user/status/123456789"
export function parseTweetId(birdOutput: string): string | null {
  const match = birdOutput.match(/status\/(\d+)/);
  return match?.[1] || null;
}

// ── Parse engagement from bird read output ──
// bird read output includes lines like: "likes: 42  retweets: 5  replies: 3"
export function parseEngagement(birdOutput: string): { likes: number; retweets: number; replies: number } {
  const likes = parseInt(birdOutput.match(/(\d+)\s*(?:likes?|♡)/i)?.[1] || "0");
  const retweets = parseInt(birdOutput.match(/(\d+)\s*(?:retweets?|🔁|RT)/i)?.[1] || "0");
  const replies = parseInt(birdOutput.match(/(\d+)\s*(?:replies?|💬)/i)?.[1] || "0");
  return { likes, retweets, replies };
}
