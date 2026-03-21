// Social screen — autonomous Moltbook agent dashboard
// Agent posts, comments, upvotes on its own. User monitors and corrects.

import { app, type Screen } from "../tui/app.ts";
import { cursor, fg, bg, style, write, getTermSize } from "../tui/ansi.ts";
import { drawHR, getSpinnerFrame } from "../tui/components.ts";
import { listAgents, type AgentPersonality } from "../agents/personality.ts";
import { loadConfig } from "../utils/config.ts";
import { MoltbookClient } from "../clients/moltbook.ts";
import { ZaiClient, type PersonalityPrompt } from "../clients/zai.ts";
import { buildLearningPrompt, addLearning } from "../agents/learnings.ts";
import type { KeyEvent } from "../tui/input.ts";

type View = "status" | "activity" | "compose" | "review";

let view: View = "status";
let agents: AgentPersonality[] = [];
let activeAgent: AgentPersonality | null = null;
let agentSelectIdx = 0;

// Activity log
interface ActivityEntry {
  time: string;
  action: string;
  detail: string;
  status: "ok" | "fail" | "pending";
}
let activityLog: ActivityEntry[] = [];
let activityScroll = 0;

// Agent state
let isRunning = false;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let lastCheck = "";
let homeData: any = null;

// Compose/review
let draftPost = "";
let draftTitle = "";
let reviewAction: "approve" | "edit" | "reject" | null = null;

// Dedup: track comment IDs we've already replied to
const repliedCommentIds = new Set<string>();

function log(action: string, detail: string, status: ActivityEntry["status"] = "ok") {
  activityLog.unshift({
    time: new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" }),
    action,
    detail: detail.replace(/[\n\r]/g, " ").slice(0, 60),
    status,
  });
  if (activityLog.length > 50) activityLog.length = 50;
  app.requestRender();
}

function getClient(): MoltbookClient | null {
  const config = loadConfig();
  if (!config.moltbookApiKey) return null;
  return new MoltbookClient(config.moltbookApiKey);
}

function getZai(): ZaiClient | null {
  const config = loadConfig();
  if (!config.zaiApiKey) return null;
  return new ZaiClient(config.zaiApiKey, config.zaiModel);
}

function getPersonality(): PersonalityPrompt | null {
  if (!activeAgent) return null;
  const learnings = buildLearningPrompt(activeAgent.id);
  return {
    name: activeAgent.name,
    tone: activeAgent.tone,
    topics: activeAgent.topics,
    style: activeAgent.style,
    bio: activeAgent.bio,
    constraints: activeAgent.constraints,
    learnings,
  };
}

// ── Autonomous agent actions ──

async function checkHome() {
  const client = getClient();
  if (!client) { log("home", "no API key", "fail"); return; }
  try {
    homeData = await client.getHome();
    lastCheck = new Date().toLocaleTimeString("en-US", { hour12: false });
    const notifs = homeData?.your_account?.unread_notification_count || 0;
    log("home", `checked — ${notifs} notifications`);

    // Auto-engage: reply to comments on our posts
    if (homeData?.activity_on_your_posts?.length > 0) {
      for (const activity of homeData.activity_on_your_posts.slice(0, 2)) {
        await autoReply(activity);
      }
    }
  } catch (err: any) {
    log("home", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function autoReply(activity: any) {
  const zai = getZai();
  const client = getClient();
  const persona = getPersonality();
  if (!zai || !client || !persona) return;

  try {
    const comments = await client.getComments(activity.post_id, "new");
    const recentComments = comments?.comments?.slice(0, 2) || [];

    for (const comment of recentComments) {
      if (comment.author_name === activeAgent?.name) continue;
      if (repliedCommentIds.has(comment.id)) continue; // dedup: already replied
      repliedCommentIds.add(comment.id);
      const reply = await zai.chatCompletion([
        { role: "system", content: `You are ${persona.name}. ${persona.tone}. Reply to a comment on your Moltbook post. Be brief (1-2 sentences), authentic, and in character. Just the reply text, nothing else.${persona.learnings || ""}` },
        { role: "user", content: `Post: "${activity.post_title}"\nComment by ${comment.author_name}: "${comment.content}"\n\nReply:` },
      ], { maxTokens: 150 });
      await client.addComment(activity.post_id, reply, comment.id);
      log("reply", `→ ${comment.author_name}: ${reply.slice(0, 40)}`);
    }
  } catch (err: any) {
    log("reply", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function autoPost() {
  const zai = getZai();
  const client = getClient();
  const persona = getPersonality();
  if (!zai || !client || !persona) { log("post", "missing config", "fail"); return; }

  try {
    log("post", "generating...", "pending");
    draftPost = await zai.generatePost(persona);
    draftTitle = await zai.generatePostTitle(draftPost);
    log("post", `draft: "${draftTitle.slice(0, 40)}"`, "pending");

    // Auto-post to general
    const result = await client.createPost({
      submolt_name: activeAgent?.submolts[0] || "general",
      title: draftTitle,
      content: draftPost,
    });

    // Handle verification if needed
    if (result?.verification_required && result?.post?.verification) {
      await handleVerification(client, result.post.verification);
    }

    log("post", `published: "${draftTitle.slice(0, 40)}"`);
  } catch (err: any) {
    log("post", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function handleVerification(client: MoltbookClient, verification: any) {
  const zai = getZai();
  if (!zai) return;

  try {
    const challenge = verification.challenge_text;
    const answer = await zai.chatCompletion([
      { role: "system", content: "You solve obfuscated math word problems. Read through scattered symbols, alternating caps, and broken words to find the math problem. Respond with ONLY the numeric answer with 2 decimal places (e.g., '15.00'). Nothing else." },
      { role: "user", content: challenge },
    ], { maxTokens: 20 });

    await client.verify(verification.verification_code, answer.trim());
    log("verify", `solved challenge: ${answer.trim()}`);
  } catch (err: any) {
    log("verify", err.message?.slice(0, 50) || "failed", "fail");
  }
}

async function autoEngage() {
  const client = getClient();
  const zai = getZai();
  const persona = getPersonality();
  if (!client || !zai || !persona) return;

  try {
    const feed = await client.getFeed("hot", 10);
    const posts = feed?.posts || feed?.data || [];
    if (posts.length === 0) return;

    // Pick a post to engage with
    const post = posts[Math.floor(Math.random() * Math.min(5, posts.length))];
    if (!post) return;

    // Upvote
    try {
      await client.upvote(post.id);
      log("upvote", `↑ "${(post.title || "").slice(0, 40)}"`);
    } catch {}

    // Maybe comment (30% chance)
    if (Math.random() < 0.3) {
      const comment = await zai.chatCompletion([
        { role: "system", content: `You are ${persona.name}. ${persona.tone}. Comment on a Moltbook post. Be brief (1-2 sentences), genuine, add value. Just the comment text.${persona.learnings || ""}` },
        { role: "user", content: `Post by ${post.author_name}: "${post.title}"\n${(post.content || "").slice(0, 300)}\n\nYour comment:` },
      ], { maxTokens: 150 });
      await client.addComment(post.id, comment);
      log("comment", `on "${(post.title || "").slice(0, 30)}": ${comment.slice(0, 30)}`);
    }
  } catch (err: any) {
    log("engage", err.message?.slice(0, 50) || "failed", "fail");
  }
}

function startAgent() {
  if (isRunning || !activeAgent) return;
  isRunning = true;
  log("agent", `started: ${activeAgent.name}`);

  // Initial check
  checkHome();

  // Heartbeat: check home every 5 minutes, post every 30 min, engage every 10 min
  let tickCount = 0;
  heartbeatTimer = setInterval(() => {
    tickCount++;
    checkHome(); // every 5 min
    if (tickCount % 2 === 0) autoEngage(); // every 10 min
    if (tickCount % 6 === 0) autoPost(); // every 30 min
  }, 5 * 60 * 1000);

  app.requestRender();
}

function stopAgent() {
  if (!isRunning) return;
  isRunning = false;
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
  log("agent", "stopped");
  app.requestRender();
}

// ── Rendering ──

function renderStatus() {
  const { rows, cols } = getTermSize();
  const w = Math.min(70, cols - 6);

  cursor.to(3, 3);
  write(`${fg.brightCyan}${style.bold}Social${style.reset}`);

  // Agent selector
  cursor.to(3, 12);
  if (activeAgent) {
    write(`${fg.brightWhite}${style.bold}${activeAgent.name}${style.reset} ${isRunning ? `${fg.brightGreen}● running${style.reset}` : `${fg.gray}○ stopped${style.reset}`}\x1b[K`);
  } else {
    write(`${fg.gray}no agent selected\x1b[K${style.reset}`);
  }

  drawHR(4, 3, w);

  // Quick stats
  if (homeData?.your_account) {
    const acc = homeData.your_account;
    cursor.to(5, 3);
    write(`${fg.gray}Karma: ${fg.brightWhite}${acc.karma || 0}${fg.gray}  Notifications: ${fg.brightYellow}${acc.unread_notification_count || 0}${fg.gray}  Last check: ${fg.white}${lastCheck || "never"}${style.reset}\x1b[K`);
  } else {
    cursor.to(5, 3);
    write(`${fg.gray}No data yet — start the agent to begin${style.reset}\x1b[K`);
  }

  // Controls
  cursor.to(7, 3);
  const controls = [
    isRunning ? `${bg.rgb(40, 30, 30)}${fg.brightRed}${style.bold} S ${style.reset} stop` : `${bg.rgb(30, 40, 30)}${fg.brightGreen}${style.bold} S ${style.reset} start`,
    `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} P ${style.reset} post now`,
    `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} E ${style.reset} engage`,
    `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} H ${style.reset} check home`,
    `${bg.rgb(40, 40, 70)}${fg.brightCyan}${style.bold} Tab ${style.reset} switch agent`,
  ];
  write(controls.join("  ") + "\x1b[K");

  drawHR(9, 3, w);

  // Activity log
  cursor.to(10, 3);
  write(`${fg.gray}${style.bold}Activity${style.reset}\x1b[K`);

  const maxLines = rows - 13;
  for (let i = 0; i < maxLines; i++) {
    const idx = activityScroll + i;
    cursor.to(11 + i, 3);
    if (idx >= activityLog.length) {
      write(`\x1b[K`);
      continue;
    }
    const entry = activityLog[idx]!;
    const statusIcon = entry.status === "ok" ? `${fg.brightGreen}✓` : entry.status === "fail" ? `${fg.brightRed}✗` : `${fg.brightYellow}◑`;
    const actionColor = entry.action === "post" ? fg.brightMagenta : entry.action === "reply" ? fg.brightCyan : fg.gray;
    write(`${fg.gray}${entry.time} ${statusIcon} ${actionColor}${entry.action.padEnd(8)}${fg.white}${entry.detail}${style.reset}\x1b[K`);
  }
}

// ── Key handling ──

export const socialScreen: Screen = {
  name: "social",
  statusHint: "S start/stop • P post • E engage • H home • Tab agent • esc back • q quit",

  onEnter() {
    agents = listAgents();
    if (agents.length > 0 && !activeAgent) {
      activeAgent = agents[0]!;
    }
  },

  onLeave() {
    // Don't stop the agent when leaving — it runs in background
  },

  render() {
    renderStatus();
  },

  onKey(key: KeyEvent) {
    if (key.name === "escape") {
      app.back();
    } else if (key.name === "s" || key.name === "S") {
      if (isRunning) stopAgent();
      else startAgent();
    } else if (key.name === "p" || key.name === "P") {
      if (activeAgent) {
        log("post", "manual trigger...", "pending");
        autoPost();
      }
    } else if (key.name === "e" || key.name === "E") {
      if (activeAgent) {
        log("engage", "manual trigger...", "pending");
        autoEngage();
      }
    } else if (key.name === "h" || key.name === "H") {
      if (activeAgent) checkHome();
    } else if (key.name === "tab") {
      // Cycle through agents
      if (agents.length > 0) {
        agentSelectIdx = (agentSelectIdx + 1) % agents.length;
        const wasRunning = isRunning;
        if (wasRunning) stopAgent();
        activeAgent = agents[agentSelectIdx]!;
        log("agent", `switched to ${activeAgent.name}`);
        if (wasRunning) startAgent();
      }
    } else if (key.name === "up" || key.name === "k") {
      activityScroll = Math.max(0, activityScroll - 1);
      app.requestRender();
    } else if (key.name === "down" || key.name === "j") {
      activityScroll = Math.min(Math.max(0, activityLog.length - 5), activityScroll + 1);
      app.requestRender();
    }
  },
};
